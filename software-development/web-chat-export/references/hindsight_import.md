# Hindsight Bulk Import via REST API

Import conversation exports into Hindsight memory system for LLM fact extraction.

## API Endpoint

```
POST /v1/default/banks/{bank_id}/memories
```

## MemoryItem Schema

```json
{
  "content": "Full text of the conversation, markdown formatted",
  "timestamp": "2026-01-15T10:30:00Z",
  "context": "platform-conv-identifier",
  "tags": ["import", "platform_name", "conversation"],
  "metadata": {
    "source": "deepseek",
    "conv_id": "abc123",
    "message_count": "38"
  },
  "document_id": null,
  "entities": null
}
```

Only `content` is required. All other fields are optional.

## Bulk Import Pattern

1. Format each conversation/session as a MemoryItem
2. Group into batches of 20 items
3. Submit with `async=true` (sync may timeout on LLM extraction)
4. Wait 2s between batches to avoid rate limiting
5. Response includes `operation_ids` (may be empty for async — tasks are queued)

```python
for batch in batches:
    payload = {"items": batch, "async": True}
    resp = requests.post(f"{HINDSIGHT}/v1/default/banks/{BANK}/memories", json=payload)
    time.sleep(2)
```

## Chunking Strategy

| Platform | Strategy | Reason |
|---|---|---|
| DeepSeek | 1 item per session | Sessions are already bounded (avg 15 msgs) |
| Doubao | 80 msgs per chunk | Single long conversation, 80 msgs ≈ 25KB |

Keep each chunk under ~50KB for efficient LLM extraction. Larger chunks = better context but slower extraction and higher token cost.

## Post-Import Verification

Check operations queue:
```
GET /v1/default/banks/main/operations?limit=5&order=desc
```

Check new documents:
```
GET /v1/default/banks/main/documents?limit=20&offset=0
```
New imports will have `tags: ["import", ...]`.

## Token Cost Estimation

- DeepSeek V4 Flash for extraction (verbose mode)
- ~1KB text ≈ 250 tokens input → ~50-100 facts extracted
- 1MB total text ≈ 250K tokens → ~$0.03 with DeepSeek V4 Flash pricing
- Processing time: ~30-60s per memory item (async, parallelizable within bank limits)

## Pitfalls

### GET bank returns 405

`GET /v1/default/banks/{bank_id}` returns `405 Method Not Allowed`. Use `GET /v1/default/banks` (list all banks) and filter by `bank_id` instead:

```python
banks = requests.get(f"{HINDSIGHT}/v1/default/banks").json()
bank = next(b for b in banks["banks"] if b["bank_id"] == "main")
fact_count = bank["fact_count"]
```

### Async response has empty operation_ids

When `async: true`, the response may contain `operation_ids: []` even though tasks were queued successfully. This is normal — operations are created and processed asynchronously. Check via `GET /v1/default/banks/main/operations` to confirm.

### Progress monitoring

For long-running imports (100+ items), set up a `no_agent` cron job that polls Hindsight and delivers progress to Feishu/other channels:

```python
# ~/.hermes/scripts/hindsight_progress.py
# Polls fact_count, pending operations, and completed/failed counts
# Format: concise status message, markdown
```

Cron config:
```
schedule: every 5m
no_agent: true
script: hindsight_progress.py
deliver: all    # or feishu:<home_channel>
```

Stop the cron after import completes (when `import_ops_pending == 0` and fact_count > baseline).
