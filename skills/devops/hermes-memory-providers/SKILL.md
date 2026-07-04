---
name: hermes-memory-providers
description: "Configure and compare Hermes Agent's 8 external memory providers — setup, selection criteria, pricing, hardware requirements."
version: 1.1.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [hermes, memory, providers, hindsight, mem0, holographic, honcho, openviking, retaindb, byterover, supermemory]
    related_skills: [hermes-agent, hermes-custom-providers, hermes-patch-maintenance]
---

# Hermes Memory Providers

Hermes Agent ships with **3 built-in memory layers** plus **8 pluggable external memory providers**. Built-in memory (`MEMORY.md` + `USER.md` + SQLite FTS5 session search) always runs; external providers add structured capture, better retrieval, and cross-session persistence on top.

**Only one external provider can be active at a time.** Switch with `hermes memory setup` or `hermes config set memory.provider <name>`.

## Quick Start

```bash
# Interactive picker — installs deps, prompts for config
hermes memory setup

# Check status
hermes memory status

# Disable external provider (built-in still works)
hermes memory off
```

Or manual config in `~/.hermes/config.yaml`:
```yaml
memory:
  provider: hindsight   # or honcho, mem0, holographic, openviking, retaindb, byterover, supermemory, memori
```

### How It Works

When a provider is active, Hermes automatically:
1. **Injects provider context** into the system prompt **at session start** (`/new` only)
2. **Prefetches relevant memories** before each turn (background, non-blocking)
3. **Syncs conversation turns** after each response
4. **Extracts memories on session end** (provider-dependent)
5. **Mirrors built-in memory writes** to external provider
6. **Adds provider-specific tools** (search, store, manage)

**Critical timing distinction:**
| Mechanism | When it works | Tool |
|-----------|:------------:|------|
| Auto-injected context | **Only on `/new`** | None needed — memories appear in system prompt |
| Manual recall | **Any turn, any session** | `hindsight_recall`, `hindsight_reflect` |
| Manual retain | **Any turn, any session** | `hindsight_retain` |
| Auto-retain (silent) | **Every turn** after initial setup | None needed — writes automatically |

Auto-injected memories = zero-effort but requires a new session.
Recall/reflect tools = immediate but requires an explicit call.
Both work with the same memory bank — the tools are always available.

Built-in memory is additive, not replaced.

## Provider Comparison

| Provider | Storage | Cost (Cloud) | Free Self-Host? | Dependencies | Best For |
|----------|---------|-------------|-----------------|-------------|----------|
| **Holographic** | Local SQLite | Free | ✅ N/A | None (zero deps) | Zero-dependency local memory |
| **Hindsight** | Local/Cloud | Pay-as-you-go (~$10-15/mo typical) | ✅ Docker/pip | PostgreSQL + LLM API key | Highest accuracy + knowledge graph |
| **OpenViking** | Self-hosted | Free | ✅ pip server | OpenViking server + LLM + embedder | Token savings via tiered loading |
| **Mem0** | Cloud | Freemium ($249/mo+) | ✅ Docker | API key | Fastest setup, auto extraction |
| **Supermemory** | Cloud | Paid | ❌ Enterprise only | API key | Multi-container isolation (work/personal) |
| **Honcho** | Cloud/Self-host | Varies | ✅ Docker/K3s | PostgreSQL + pgvector + Redis | Dialectic user modeling |
| **ByteRover** | Local/Cloud | Freemium | ✅ | LLM only (no DB) | Human-readable knowledge tree |
| **RetainDB** | Cloud | $20/mo | ❌ | API key | Delta compression |

## Provider Deep Dives

### Holographic — Zero-Dependency Local Memory
- **Mechanism:** HRR (Holographic Reduced Representations) — complex-valued vectors with algebraic recall
- **Tools:** 2 tools (minimal surface area)
- **Setup:** `hermes memory setup` → select `holographic`. No API key, no server, no installs.
- **Trust scoring:** Memories gain/lose weight across sessions; contradictory entries decay
- **Trade-off:** No LLM-based extraction — stores conversational content, not a knowledge graph
- **Best for:** Air-gapped systems, lowest-friction setup, privacy-first environments

### Hindsight — Knowledge Graph + Reflect Synthesis
- **Mechanism:** Stores structured facts + entities + relationships (knowledge graph). 4-way parallel retrieval (semantic + BM25 + graph + temporal) with cross-encoder reranking. Unique `reflect` for cross-memory synthesis.
- **Benchmark:** 94.6% (473/500) on LongMemEval — top of Agent Memory Benchmark
- **Tools:** `hindsight_retain`, `hindsight_recall`, `hindsight_reflect`
- **Setup:**
  - Cloud: `hermes memory setup` → set `HINDSIGHT_API_KEY` in `.env`
  - Self-hosted: `docker run ... ghcr.io/vectorize-io/hindsight:latest`
    - **Pitfall:** Always use `--env-file` to pass API keys, never `-e`, because Hermes terminal secret redaction replaces the key with `***` before execution.
    - **Pitfall:** Set `HINDSIGHT_API_LLM_PROVIDER=deepseek` (or your provider). Hindsight defaults to `openai` and will 401 otherwise.
    - **Pitfall:** You must use `hermes config set memory.provider hindsight` to enable for the active profile — editing the **active** profile's `config.yaml` directly is blocked by Hermes security guard. For **named** (non-active) profiles, direct `patch` on their `config.yaml` works fine.
    - After Docker runs, create `hindsight/config.json` with `{"mode": "local_external", "api_url": "http://localhost:8888"}`.
    - **Path:** For the **default profile**, place at `~/.hermes/hindsight/config.json`. For a **named profile**, place at `~/.hermes/profiles/<name>/hindsight/config.json`.
    - **Two-step setup for named profiles:** creating `hindsight/config.json` is only half the work — you must also set `memory.provider: hindsight` in that profile's `config.yaml`. Either `hermes profile use <name> && hermes config set memory.provider hindsight`, or directly patch the named profile's `config.yaml` (the security guard only blocks editing the *active* profile).
    - Add a `bank_id` field to isolate memory banks across profiles (e.g. `"bank_id": "main"` for default, `"bank_id": "test-foo"` for experiments). Omit to auto-generate. Multiple profiles can share the same `bank_id` (e.g. `"main"`) to pool memory across machines.`
- **Pricing (Cloud):** Per-million-token: Retain $15, Recall $0.75, Reflect $3, Iris Extract $7.50 — no monthly fee
- **Hardware (self-hosted):** 2 GB RAM min, 2 vCPU, Docker (Full image ~9GB AMD64 / ~3.7GB ARM64)
- **Storage (self-hosted):** ~6.4GB image + ~500MB-2GB data. Default Docker data-root is `/var/lib/docker` on the system partition. If space is tight, migrate to a larger partition — see `references/docker-data-root-migration.md` for a step-by-step procedure.
- **Best for:** Highest retrieval accuracy, entity-aware memory, cross-memory reasoning

### OpenViking (ByteDance) — Tiered Self-Hosted
- **Mechanism:** Filesystem-style hierarchy with tiered loading (L0 ~50t → L1 ~500t → L2 full)
- **Tools:** `viking_search`, `viking_read`, `viking_browse`, `viking_remember`, `viking_add_resource`
- **Setup:** `pip install openviking && openviking-server && hermes memory setup`
- **Key advantage:** 80-90% token cost reduction vs full-context loading
- **Best for:** Cost-conscious deployments, filesystem-transparent inspection

### Mem0 — Server-Side Auto Extraction
- **Mechanism:** LLM extracts facts on server side. Dual scope: session memory (short-term) + user memory (long-term)
- **Tools:** `mem0_profile`, `mem0_search`, `mem0_conclude`
- **Setup:** Fastest — `hermes memory setup` → set `MEM0_API_KEY`, ~30 seconds
- **Benchmark:** 67.6% on LongMemEval-S
- **Circuit breaker:** 5 consecutive failures → 2-min pause, agent keeps working
- **Best for:** Quick start, hands-off

### Supermemory — Scoped Multi-Container Memory
- **Mechanism:** Knowledge graph + container isolation. Default tag `hermes-{profile}`, optional multi-container routing.
- **Tools:** `supermemory_profile`, `supermemory_search`, `supermemory_remember`, `supermemory_forget`
- **Setup:** `pip install supermemory` → `hermes memory setup` → select `supermemory`
- **Key feature:** Context fencing — work vs personal containers don't mix
- **Best for:** Multi-role users needing context isolation

### Honcho — Dialectic User Modeling
- **Mechanism:** Two-layer injection (base + dialectic reasoning). Models *how you think* — reasoning patterns, communication style.
- **Tools (5):** `honcho_profile`, `honcho_search`, `honcho_context`, `honcho_reasoning`, `honcho_conclude`
- **Config knobs:** `contextCadence`, `dialecticCadence`, `dialecticDepth` (1-3)
- **License:** OSS is AGPL v3.0 — use Cloud to avoid
- **Best for:** Long-term personalization, multi-agent systems

### ByteRover — Markdown Knowledge Tree
- **Mechanism:** Hierarchical context tree in human-readable Markdown files. No embedding model or database needed.
- **Setup:** `hermes memory setup` → select `byterover`
- **Best for:** Visual inspection of agent's memory as files

### RetainDB — Hybrid Search Cloud
- **Mechanism:** Vector + BM25 + reranking with delta compression
- **Cost:** $20/mo
- **Setup:** `hermes memory setup` → `RETAINDB_API_KEY` in `.env`
- **Note:** Latency ~940ms p50. Full benchmarks still pending.
- **Best for:** Managed cloud with hybrid search

## Community/Third-Party Projects

### Memory OS (github.com/ClaudioDrews/memory-os)
- 6-layer stack: Workspace + Sessions + Structured Facts + Fabric + Vector DB (Qdrant) + LLM Wiki
- MIT licensed, requires Docker + Qdrant + Redis + ARQ Worker
- Not an official provider — runs as a separate stack layered on Hermes

### Obsidian as Memory Backend
- Reddit approach: let Hermes read/write your Obsidian vault as long-term memory
- Requires custom tool wiring

## Best Practice: Provider Selection

| Your Priority | Pick This |
|--------------|-----------|
| **Zero infrastructure** | Holographic |
| **Best recall accuracy** | Hindsight |
| **Cheapest token usage** | OpenViking |
| **Fastest setup, hands-off** | Mem0 |
| **Work/personal isolation** | Supermemory |
| **User personality modeling** | Honcho |
| **Visual, inspectable memory** | ByteRover |
| **Managed enterprise** | RetainDB |

**User preference (chenan):** "对成本敏感不代表不愿意花钱，只是不想花不必要的钱。对于记忆，我是希望质量越高越好。" When recommending providers, prioritize **recall quality** (Hindsight at 94.6% LongMemEval is the clear leader) and justify any downgrade to cheaper alternatives with specific trade-offs. The token cost difference between providers is negligible (pennies per 100 turns) — the real decision factors are recall accuracy and context window overhead.

**Always test in a new profile first:**
```bash
hermes profile create test-<provider>
hermes profile use test-<provider>
hermes memory setup           # select provider
# ...run a few sessions...
hermes memory status          # verify
```

## Pitfalls

- **Only one external provider at a time.** Built-in is always active alongside.
- **Provider affects every session profile-wide.** Test in a separate profile, not the default.
- **API keys go in `.env`, not `config.yaml`.** Sensitive configs stay out of git.
- **Retain is often async.** Facts stored this turn won't be searchable until next turn (relevant for Hindsight, Mem0).
- **Disable built-in memory tool if provider has its own tools** — otherwise LLM may ignore provider tools: `hermes tools disable memory`
- **Env vars read at startup.** Restart Hermes after changing `.env` or provider config.
- **Some providers require LLM API key even in self-host mode.** The provider itself needs an LLM for extraction.
- **Provider changes only apply to NEW sessions.** The `memory.provider` config is read once at agent startup (`agent_init.py`). If you change the provider mid-conversation, `initialize()` never runs for the new provider — `sync_turn()` iterates an empty `_providers` list and stores nothing. You MUST send `/new` (or restart the Hermes gateway) for the change to take effect. To verify: `hermes memory status` should show the provider as active after the new session begins.

### Hindsight Configuration Tuning

See `references/hindsight-config-tuning.md` for detailed guidance on:
- `bank_retain_mission` — crafting extraction prompts for multi-domain knowledge bases
- `recall_types` — observation-only default vs all three types
- `retain_extraction_mode` — concise vs verbose (bank API only, not config.json)
- `recall_max_tokens` — bank-level API limit vs plugin config
- The retain-vs-recall distinction (independent config on both sides)
- The tool-output capture gap and mitigation strategies
- Deployment discovery when Hindsight is already running

### Hindsight Database Schema

See `references/hindsight-database-schema.md` for the full 20-table PostgreSQL schema
with column definitions, indexes, and probing technique. Covers: memory_units unified
fact table, memory_links 7-type relationship graph, observation consolidation mechanism,
four-strategy retrieval index architecture, and entity co-occurrence statistics.

### Hindsight-Specific Pitfalls

- **Config key naming**: The config.json key is `bank_retain_mission` (not `retain_mission`). Using `retain_mission` in config.json is silently ignored.
- **`bank_retain_mission` is read but NEVER written to the bank by the plugin.** The Hermes Hindsight plugin (`plugins/memory/hindsight/__init__.py`) reads `bank_retain_mission` from config.json at startup (line 1309) but `_build_retain_kwargs()` (line 1572) does NOT include `retain_mission` in the retain API call, and there is no bank-config PATCH on startup. Even with the correct key and a Hermes restart, the Hindsight bank will still show `retain_mission: null`. **The only way to set `retain_mission` is a direct bank API call**: `curl -X PATCH http://localhost:8888/v1/default/banks/main/config -H 'Content-Type: application/json' -d '{"updates":{"retain_mission":"<text>"}}'`. Once set via API, it persists across container restarts.
- **`retain_extraction_mode` is NOT a config.json field.** It must be set via the bank API: `curl -X PATCH ...banks/main/config -d '{"updates":{"retain_extraction_mode":"verbose"}}'`
- **Bank-level `recall_max_tokens` overrides plugin config.** Check both with an empty bank config PATCH to see actual overrides.
- **Self-hosted Hindsight defaults to openai provider.** Always set `HINDSIGHT_API_LLM_PROVIDER=deepseek` (or your real provider) as an env var on the Docker container. Without it, the key is sent to `api.openai.com` and gets a 401.
- **Hermes terminal redaction corrupts Docker `-e` flags.** When you type a `docker run -e HINDSIGHT_API_LLM_API_KEY=<key>` in a Hermes terminal call, the output redactor replaces the key with `***` before execution, so the container gets a literal `***` as the key. **Always use `--env-file` with a temp file written via `execute_code` Python** to bypass this.
- **Self-hosted Hindsight mode.** When running a local Docker instance, set `mode: local_external` in `$HERMES_HOME/hindsight/config.json`. Default `mode: cloud` tries the cloud API endpoint.
- **model.api_key empty-string trap.** If you run `hermes config set model.api_key ''` to clear it, the empty string overrides the env var. Remove the key entirely from config.yaml instead.
- **Hindsight needs its own LLM for fact extraction.** Even though Hermes talks to the Hindsight API, Hindsight internally calls an LLM to extract structured facts. Configure via `HINDSIGHT_API_LLM_PROVIDER` + `HINDSIGHT_API_LLM_API_KEY` + `HINDSIGHT_API_LLM_MODEL` on the Docker container.
- **Container running ≠ provider enabled.** The Docker container may be up for days (`sudo docker ps`), yet `hermes memory status` shows `Provider: (none — built-in only)` if `memory.provider` was never set in `config.yaml`. Always check BOTH the Docker health endpoint and `hermes memory status` to confirm Hindsight is actually wired in.
- **`docker ps` without sudo may show nothing even when Docker is running.** If your user is in the `docker` group, a newgrp/su session is required for permission changes to apply. Use `sudo docker ps` as a reliable fallback check.
- **Bind mount ownership.** If using a host-directory bind mount instead of Docker volumes, the directory must be owned by UID 1000 (the container's rootless user). Docker named volumes auto-handle this. Symptom: container restarts with `"The embedded database directory is not writable by this container (UID 1000)"`. Fix: `sudo chown 1000:1000 <bind-mount-dir>`.

## Historical Import — Bulk-Loading Past Sessions

Hindsight captures conversations from activation onward, but you can also
bulk-import past sessions from Hermes's SQLite session store (`state.db`).

For importing conversations from **external AI apps** (DeepSeek, Doubao, ChatGPT, etc.),
see `references/external-ai-conversation-import.md` — covers CDP browser automation,
API-based extraction, and the re-extraction cost/benefit analysis framework.

### Session Analysis (Count, Token Usage, Themes)

Before importing, inspect what's available:

```bash
# Count sessions and tokens by date
sqlite3 ~/.hermes/state.db "
SELECT substr(id, 1, 8) as date,
       count(*) as sessions,
       sum(message_count) as messages,
       sum(input_tokens + output_tokens) as total_tokens
FROM sessions
WHERE message_count > 0
GROUP BY date
ORDER BY date DESC
"
```

```bash
# List sessions for a specific day with metadata
sqlite3 -header ~/.hermes/state.db "
SELECT id, title, message_count,
       input_tokens, output_tokens,
       (input_tokens + output_tokens) as total_tokens,
       datetime(started_at, 'unixepoch', '+8 hours') as started_cst
FROM sessions
WHERE id LIKE '20260621_%' AND message_count > 0
ORDER BY started_at
"
```

Adjust the date filter (`20260621_%`) and timezone offset (`+8 hours`) as needed.

### Import Script

The skill ships a reusable script at `scripts/import_sessions_to_hindsight.py`.
It reads every non-empty session from `state.db`, reconstructs the conversation
as readable text (user ↔ assistant ↔ tool), and imports each via
`retain_batch()`.

**Usage:**

```bash
python3 ~/.hermes/skills/devops/hermes-memory-providers/scripts/import_sessions_to_hindsight.py
```

**What it does:**
1. Queries `state.db` for sessions matching the configured date window
2. Fetches all messages per session (user/assistant/tool/system, ordered)
3. Formats into a markdown conversation transcript (truncates long tool output to 500 chars)
4. Calls `client.retain_batch(..., retain_async=True)` for each session
5. Tags imports as `historical` + `batch-import` for provenance

**Customize the date range:**
Edit the `fetch_sessions()` SQL WHERE clause in the script — e.g.:
`WHERE (id LIKE '20260620_%' OR id LIKE '20260621_%')` for a wider window.

### Notes on Historical Import

| Concern | Detail |
|---------|--------|
| **Extraction is async** | After importing, Hindsight runs Iris Extract in the background. Facts won't be searchable until it finishes (~minutes for small batches). |
| **Source of truth** | `state.db` is the canonical store — more reliable than `request_dump_*.json` files which may be absent or incomplete. |
| **Deduplication** | Hindsight's observation layer consolidates overlapping facts. Importing similar sessions won't explode the bank. |
| **Self-hosted cost** | Goes through your configured LLM key for Iris Extract processing. |
| **Tag for provenance** | The script adds `tags=["historical", "batch-import"]` to distinguish imported memories from auto-captured ones. |

## Verification: Is Hindsight Actually Working?

After setup, run this full diagnostic to confirm Hindsight is capturing and returning memories:

```bash
# 1. Docker status
sudo docker ps --filter name=hindsight --format "{{.Names}} {{.Status}}"

# 2. API health
curl -s http://localhost:8888/health

# 3. Hermes provider status
hermes memory status
# Must show: Provider: hindsight, Status: available ✓

# 4. Check stored memory count
python3 -c "
from hindsight_client import Hindsight
c = Hindsight(base_url='http://localhost:8888')
r = c.list_memories(bank_id='main')
print(f'Total memory units: {r.total}')
"

# 5. Functional recall test
python3 -c "
from hindsight_client import Hindsight
c = Hindsight(base_url='http://localhost:8888')
r = c.recall(bank_id='main', query='test', budget='low')
print(f'Recall results: {len(r.results) if r.results else 0}')
for i, m in enumerate(r.results[:5]):
    print(f'  [{i}] {m.text[:120]}')
"
```
