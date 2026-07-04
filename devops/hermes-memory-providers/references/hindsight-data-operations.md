# Hindsight Data Operations — Verification, Listing, Historical Import

Beyond what the Hermes plugin does automatically, you can interact directly with Hindsight's API to inspect stored data, import historical conversations, or diagnose issues.

## Python Client

Hindsight ships a Python client library `hindsight_client`. Available methods:

| Method | Purpose |
|--------|---------|
| `aretain(bank_id, content, ...)` | Store a single document |
| `aretain_batch(bank_id, items, document_id, ...)` | Store multiple documents in one call |
| `arecall(bank_id, query, ...)` | Search/recall memories |
| `areflect(bank_id, query, ...)` | Cross-memory synthesis |
| `list_memories(bank_id, type, search_query, limit, offset)` | Enumerate stored memories |
| `create_bank(bank_id, ...)` | Create a new memory bank |
| `get_bank_config(bank_id)` | Get bank configuration |
| `delete_bank(bank_id)` | Delete a bank and all its data |
| `retain_files(bank_id, files, context, ...)` | Store file content as memories |

### `aretain_batch()` Signature

```python
async def aretain_batch(
    self,
    bank_id: str,
    items: list[dict],
    document_id: str | None = None,
    document_tags: list[str] | None = None,
    retain_async: bool = False
)
```

Each `item` dict supports:
- `content` (str, required) — the data to store
- `context` (str, optional) — context label for the content
- `metadata` (dict[str,str], optional) — arbitrary key-value metadata
- `tags` (list[str], optional) — tags for filtering
- `update_mode` (str, optional) — `"append"` to add to existing document

### `list_memories()` Signature

```python
def list_memories(
    self,
    bank_id: str,
    type: str | None = None,        # "observation" | "world" | "experience"
    search_query: str | None = None,
    limit: int = 100,
    offset: int = 0
)
```

Returns paginated results — useful for checking "how much has been stored".

## Importing Historical Conversations

Hindsight is NOT limited to recording from activation onward. You can import past conversations via `retain_batch()`.

### What to Import

Hermes stores sessions in two places:

| Source | Description | Recommended? |
|--------|-------------|:----------:|
| **`state.db`** (SQLite) | Canonical session store at `~/.hermes/state.db`. Always present, complete, and queryable. | ✅ **Best** |
| `request_dump_*.json` | Individual request dump files in `~/.hermes/sessions/`. May be absent or incomplete. | ❌ Secondary |

**Prefer `state.db`** — it's the canonical store with session metadata (token counts, timestamps, message count) and all messages ordered and typed.

### Import via state.db (Recommended)

The `hermes-memory-providers` skill ships a ready-to-run script at
`scripts/import_sessions_to_hindsight.py`. Use it directly:

```bash
python3 ~/.hermes/skills/devops/hermes-memory-providers/scripts/import_sessions_to_hindsight.py
```

The script:
1. Queries `state.db` for sessions matching a date window
2. Fetches all messages per session (user/assistant/tool/system)
3. Formats into a markdown conversation transcript
4. Calls `client.retain_batch(..., retain_async=True)` for each session
5. Tags imports as `historical` + `batch-import`

### Import via request_dump JSON (Legacy)

```python
import json, glob
from hindsight_client import Hindsight

client = Hindsight(base_url="http://localhost:8888")

sessions = sorted(glob.glob("/home/chenan/.hermes/sessions/request_dump_*.json"))
for path in sessions:
    with open(path) as f:
        data = json.load(f)
    
    messages = []
    # Structure varies by dump format — adapt extraction logic as needed
    for entry in data if isinstance(data, list) else [data]:
        if isinstance(entry, dict) and "content" in entry:
            messages.append({
                "role": "user" if "user" in str(entry.get("role", "")).lower() else "assistant",
                "content": entry["content"]
            })
    
    if not messages:
        continue
    
    content = json.dumps(messages, ensure_ascii=False)
    client.retain_batch(
        bank_id="main",
        items=[{
            "content": content,
            "context": "historical Hermes conversation",
            "metadata": {"source": "session-dump", "file": path}
        }],
        retain_async=True
    )
```

### Notes on Historical Import

| Concern | Detail |
|---------|--------|
| **Extraction is async** | After importing, Hindsight runs Iris Extract in the background. Facts won't be searchable immediately. |
| **Token cost (cloud)** | Retain: $15/M tokens. ~100-turn session (~15K tokens) ≈ $0.23. |
| **Token cost (self-hosted)** | Goes through your configured LLM key. |
| **Deduplication** | Observations layer consolidates overlapping facts. Importing similar sessions won't explode the bank. |
| **Tag for provenance** | Add `tags=["historical"]` and `metadata={"source": "batch-import"}` to distinguish auto-captured vs imported memories. |

## Verification Diagnostic Sequence

```bash
# 1. Is Docker running?
docker ps --filter name=hindsight --format "{{.Names}} {{.Status}}"

# 2. Is the API healthy?
curl -s http://localhost:8888/health
# Expected: {"status":"healthy","database":"connected"}

# 3. Is the provider configured in Hermes?
hermes memory status
# Should show: Provider: hindsight, Status: available

# 4. Is config.yaml set?
grep -A2 '^memory:' ~/.hermes/config.yaml
# Should contain: provider: hindsight

# 5. Does hindsight config exist?
cat ~/.hermes/hindsight/config.json

# 6. How many memories exist?
python3 -c "
from hindsight_client import Hindsight
c = Hindsight(base_url='http://localhost:8888')
result = c.list_memories(bank_id='main')
print(f'Total memory units: {result.total_count if hasattr(result, \"total_count\") else len(result)}')"
```

### Common Failure Modes

| Symptom | Likely Cause |
|---------|-------------|
| Health OK but `hermes memory status` shows no provider | `memory.provider` not set in `config.yaml` |
| Docker container doesn't exist | Was never created, or was removed |
| Docker exists but stopped | Check `docker logs hindsight` |
| Plugin loads but never stores data | `auto_retain: false` or `retain_every_n_turns` too high |
| "No relevant memories" on recall | Fresh install — no data yet, or `recall_types` narrowed to `observation` only |
