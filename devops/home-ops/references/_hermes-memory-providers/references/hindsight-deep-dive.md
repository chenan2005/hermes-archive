# Hindsight — Detailed Reference

**Source:** vectorize.io/pricing, hindsight.vectorize.io/developer/installation, hermes-agent docs

## Mechanism

Hindsight is the only Hermes memory provider that stores **structured knowledge** (discrete facts + named entities + relationships) in a **knowledge graph** rather than raw text chunks or semantic embeddings.

### Memory Lifecycle (Timing)

Hindsight does NOT extract facts on every turn. The lifecycle has distinct stages:

```
Turn N:  user speaks
   ├─ ① Recall (pre-fetch) — BEFORE agent responds
   │      4-way parallel retrieve → cross-encoder rerank → inject agent context
   │      Non-blocking, ~50-300ms
   │
   ├─ ② Agent responds
   │
   └─ ③ Sync conversation turn to Hindsight server
          Raw text saved in temporary store, NO extraction yet

... several turns later (flush_min_turns, default 6) ...

   └─ ④ Iris Extract (batch)
          LLM analyzes all accumulated turns → structured facts → knowledge graph

... session ends ...

   └─ ⑤ Flush remaining unsynced turns
```

**Key delay:** facts stored in turn N are NOT searchable until the next Iris Extract batch fires (typically turns N+6). This is the "retain is async" rule — never recall in the same turn you stored.

**Five trigger points for Iris Extract:**
| Trigger | When | What happens |
|---------|------|-------------|
| Per-turn sync | After each agent response | Raw text sent to Hindsight, no extraction |
| Flush batch | Every `flush_min_turns` (default 6) | Batch Iris Extract on accumulated turns |
| Explicit `hindsight_retain()` | On demand | Immediate single-fact Iris Extract |
| Nudge | Every `nudge_interval` (default 10) | Agent prompted: "any new facts to retain?" |
| Session end | Cleanup | Remaining unsynced content extracted |

### Iris Extract Pipeline

Iris Extract is how raw conversation text becomes structured knowledge. It calls the configured LLM (`HINDSIGHT_API_LLM_PROVIDER`) with a specialized extraction prompt:

```
Conversation turn(s):
User: "我把主力代理换到VMISS香港BGP了，38.47.108.89，延迟29ms"

                    ▼ Iris Extract (LLM call)

┌──────────────────────────────────────────────────┐
│ Entities extracted:                               │
│   [VMISS_HK] type: vps, ip: 38.47.108.89         │
│   [User]                                          │
│                                                    │
│ Relations extracted:                               │
│   [User] ──uses──▶ [VMISS_HK]                     │
│   [VMISS_HK] ──has_role──▶ [main_proxy]           │
│                                                    │
│ Facts extracted:                                   │
│   VMISS_HK.latency = 29ms                         │
│   User changed primary proxy (configuration_change)│
└──────────────────────────────────────────────────┘
```

The extraction prompt is proprietary but known to:
1. Identify named entities (people, services, concepts, locations)
2. Extract typed relations between entities
3. Capture attribute-value pairs as facts
4. Classify fact types (preference, configuration_change, personal_detail, etc.)

Cost: $7.50/M tokens for cloud Iris. Self-hosted uses your own LLM key.

### Storage Model (Knowledge Graph)

Hindsight stores all memory in a single PostgreSQL database with 20 tables.
The core is a **unified fact table** with a `fact_type` discriminator, plus
dedicated tables for entities, typed relationships, entity co-occurrences,
observation history, and mental models. See `references/hindsight-database-schema.md`
for the full 20-table schema with column definitions and indexes.

**One fact table, three types (NOT three separate tables):**

All facts — world, experience, and observation — live in the single
`memory_units` table, differentiated by a `fact_type` column
(`'world'`, `'experience'`, `'observation'`).

**Graph structure:**

| Table | Stores | Role |
|-------|--------|------|
| **entities** | Named items (people, services, concepts) | Graph nodes |
| **memory_units** | All facts + observations with embeddings | Core fact storage |
| **unit_entities** | M:N bridge linking facts to entities | Entity resolution |
| **memory_links** | 7 typed directed edges between facts | Causal + temporal + semantic graph |
| **entity_cooccurrences** | Entity pair frequency stats | Implicit entity edges |

**memory_links has 7 relationship types:** `temporal`, `semantic`, `entity`, `causes`, `caused_by`, `enables`, `prevents` — each with a 0.0–1.0 confidence weight.

This graph structure enables **graph traversal retrieval** — searching "VPS" finds VMISS_HK entity, walks `unit_entities` to related facts, then `memory_links` to causally connected facts, then to their entities, etc. This is what gives Hindsight its edge over pure vector+BM25 providers.

**Observation consolidation:** World/experience facts are periodically grouped by entity overlap and synthesized by an LLM into observations — deduplicated, evidence-weighted summaries with `source_memory_ids` linking back to source facts. `observation_history` tracks every version.

### Retrieval Pipeline

On `hindsight_recall`, four strategies run in parallel:

1. **Semantic** — vector embedding similarity search (pgvector)
2. **BM25** — keyword/lexical matching (complements semantic)
3. **Graph traversal** — walk relationship edges in the knowledge graph
4. **Temporal** — time-line based retrieval

All four results merged and **cross-encoder reranked** before returning to the agent.

### Context Injection Position

Hindsight does NOT modify the system prompt. It injects retrieved memories as an **independent context message** inserted between the system prompt and conversation history:

```
┌──────────────────────────────────┐
│ System Prompt (fixed)            │
│   - persona, tools, rules        │
├──────────────────────────────────┤
│ ⬆ Hindsight Memory Context      │  ← independent message, refreshed each turn
│   "Relevant memories:            │
│    - User prefers concise...     │
│    - Project uses pytest..."     │
├──────────────────────────────────┤
│ Conversation History             │
├──────────────────────────────────┤
│ Current User Message             │
└──────────────────────────────────┘
```

This matters for **role-aware models** (Claude, etc.) that treat message roles differently — the model sees memories as background context, not part of the current user query.

### Prefix Cache Interaction (DeepSeek / OpenAI)

Hindsight's per-turn memory injection breaks DeepSeek's prefix KV cache because the memory content changes every turn:

```
Turn 1: [SYS] + [Mem_A] + user:Q1
         ✓ cached as this exact prefix

Turn 2: [SYS] + [Mem_B] + user:Q1 + asst:A1 + user:Q2
         ✓ [SYS] matches, but [Mem_B] ≠ [Mem_A]
         ✗ Cache breaks at Mem_B → only SYS hits cache
```

Contrast with no memory: without memory injection, the prefix grows incrementally and most of it hits cache each turn.

Without Hindsight:
```
Turn 2: [SYS] + user:Q1 + asst:A1 + user:Q2
         ✓ [SYS] + user:Q1 hits cache → full price on only asst:A1 + user:Q2
```

**Impact estimate:**
| Scenario | Per-turn full-price tokens | 100-turn cost (DeepSeek V4) |
|----------|---------------------------|---------------------------|
| No hindsight | ~100t (end of history) | ~¥0.003 |
| Hindsight (800t memory) | ~900t | ~¥0.013 |
| Hindsight (2000t memory) | ~2100t | ~¥0.030 |

**Conclusion:** token cost impact is negligible (pennies per 100 turns). The real cost is **context window consumption** — 500-2000 tokens of memory compete with conversation history for space in long sessions.

### Typical Memory Injection Size

| Dimension | Value |
|-----------|-------|
| Retrieved memory count | 5-15 facts |
| Per-fact token size | 50-200t |
| **Typical total injection** | **500-2000 tokens** |
| Sparse-context sessions | 250-500t |
| Dense multi-entity sessions | Up to 3000t |

### Reflect (Unique to Hindsight)

`hindsight_reflect` traverses the knowledge graph and synthesizes across ALL memories — the only provider that can answer open-ended questions like "based on everything you know about me, suggest X" rather than just retrieving facts.

### Design Trade-off: Provider Quality vs Prefix Cache

Hindsight's high recall accuracy (94.6%) and per-turn dynamic retrieval inherently conflict with prefix cache hit rates — accurate memory means fresh content each turn. Providers that preserve prefix cache (Holographic, OpenViking with stable L0) sacrifice retrieval quality. This is a fundamental architectural trade-off, not a configuration issue.

**Incremental injection pattern (discussed but not implemented):** for a future optimization, instead of replacing memory context each turn, keep already-injected memories in the conversation history and only append new/changed facts. This preserves the prefix for cache but requires dedup logic and risks context window bloat.

## Cloud Pricing

No monthly fee, no per-seat pricing. Pure pay-as-you-go per million tokens:

| Operation | $/M tokens | When it fires |
|-----------|-----------|---------------|
| Retain | $15.00 | Every time agent stores a fact |
| Recall | $0.75 | Every pre-fetch before conversation turn |
| Reflect | $3.00 | Cross-memory synthesis queries |
| Iris Extract | $7.50 | Structured extraction from raw text |
| Mental Model Retrieve | $0.25 | Mind model read |
| Mental Model Refresh | $3.00 | Mind model update |

**Typical monthly cost estimate:**
- 100 conversation turns/day, pre-fetch recall each turn, retain every ~3 turns
- Recall: ~200K tok/mo × $0.75/M = ~$1.50
- Retain: ~500K tok/mo × $15/M = ~$7.50
- Other: ~$2
- **Total: ~$10-15/month** for a heavy user (300+ turns/day: ~$30-40)

Free credits on signup for testing.

## Self-Hosted Hardware Requirements

### Docker (Recommended)

| Variant | Size | Min RAM | Recommended RAM | When to Use |
|---------|------|---------|-----------------|-------------|
| **Full** (`latest`) | ~9GB AMD64 / ~3.7GB ARM64 | 1.5 GB | 2 GB | Default, out-of-box, only needs LLM API key |
| **Slim** (`latest-slim`) | ~500 MB | 512 MB | 1 GB | If using external embeddings (OpenAI/Cohere/TEI) |

### Memory Breakdown (Full Image)

| Component | Idle | Loaded |
|-----------|------|--------|
| API service (BGE embedder 130MB + MiniLM cross-encoder 90MB + runtimes) | 0.8-1.0 GB | 1.2-1.5 GB |
| PostgreSQL (embedded pg0) | 0.3-0.5 GB | 0.5-1.0 GB |
| Control Plane UI (Next.js) | 128 MB | 256 MB |
| **Total** | **~1.2-1.5 GB** | **~1.7-2.5 GB** |

### CPU
- 2 vCPUs fine for dev/light use
- Production reranker (cross-encoder) benefits from GPU; alternatively use external reranker (TEI, Cohere)

### One-Line Docker Deploy (OpenAI)

```bash
docker run -it --pull always --name hindsight --restart unless-stopped \
  -p 8888:8888 -p 9999:9999 \
  -e HINDSIGHT_API_LLM_API_KEY=YOUR_OPENAI_KEY \
  -v hindsight-data:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest
```

### Docker Deploy with DeepSeek (Non-OpenAI Providers)

```bash
# WARNING: Do NOT use -e HINDSIGHT_API_LLM_API_KEY= directly in Hermes terminal!
# Hermes secret redaction replaces the actual key with *** before execution.

# Instead, write env vars to a file first (use execute_code or bash -c):
cat > /tmp/hindsight.env << 'EOF'
HINDSIGHT_API_LLM_PROVIDER=deepseek
HINDSIGHT_API_LLM_API_KEY=sk-your-actual-key-here
HINDSIGHT_API_LLM_MODEL=deepseek-v4-flash
EOF

docker run -d --restart unless-stopped --name hindsight \
  -p 8888:8888 -p 9999:9999 \
  --env-file /tmp/hindsight.env \
  -v hindsight-data:/home/hindsight/.pg0 \
  ghcr.io/vectorize-io/hindsight:latest

# Clean up
rm /tmp/hindsight.env
```

**Key env vars for self-hosted Hindsight:**

| Env Var | Purpose | Example |
|---------|---------|---------|
| `HINDSIGHT_API_LLM_PROVIDER` | LLM provider for fact extraction | `deepseek`, `openai`, `anthropic`, `groq`, `ollama` |
| `HINDSIGHT_API_LLM_API_KEY` | API key for the LLM | `sk-...` |
| `HINDSIGHT_API_LLM_MODEL` | Model for fact extraction | `deepseek-v4-flash`, `gpt-4o-mini` |
| `HINDSIGHT_API_LLM_BASE_URL` | Custom endpoint (if not default) | `https://api.deepseek.com/v1` |

**Critical: Hindsight defaults to `openai` as the LLM provider.** If you pass a DeepSeek key without setting `HINDSIGHT_API_LLM_PROVIDER=deepseek`, Hindsight sends the key to `api.openai.com` and gets a 401.

- Port 8888 = memory API
- Port 9999 = control plane UI
- Data persisted in Docker volume `hindsight-data` (or bind mount writable by UID 1000)

## Hermes Configuration (Self-Hosted Mode)

After the Docker container is running:

```bash
# 1. Create a test profile (always test in isolation)
hermes profile create test-hindsight

# 2. Set memory provider
hermes config set memory.provider hindsight -p test-hindsight

# 3. Create Hindsight config file at profile's hindsight/config.json
#    (This tells the plugin it's local_external, not cloud)
mkdir -p ~/.hermes/profiles/test-hindsight/hindsight
cat > ~/.hermes/profiles/test-hindsight/hindsight/config.json << 'CONFIG'
{
  "mode": "local_external",
  "api_url": "http://localhost:8888",
  "bank_id": "test-hindsight"
}
CONFIG

# 4. Verify plugin status
test-hindsight memory status
# Expected: Provider: hindsight, Status: available ✓

# 5. Test
test-hindsight chat -q "Please remember: my email is an@example.com"
# Look for ⚡ hindsight prefix in output
```

### Verification

```bash
curl http://localhost:8888/health
# {"status":"healthy","database":"connected"}
```

## Notes

- **Retain is async** — don't recall in the same turn you stored
- **If using self-hosted, you still need an LLM API key** — Hindsight itself needs an LLM for fact extraction
- **Self-hosted is MIT licensed** (not AGPL like Honcho)
- **Use `hermes tools disable memory`** if LLM ignores hindsight tools in favor of built-in memory tool
- **Profile isolation:** Config lives in `$HERMES_HOME/hindsight/config.json` (profile-specific)
