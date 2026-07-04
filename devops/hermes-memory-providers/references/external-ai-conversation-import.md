# Importing External AI Assistant Conversations into Hindsight

How to extract conversations from third-party AI apps (DeepSeek, Doubao, ChatGPT, etc.)
and import them into Hindsight memory. Distinct from importing Hermes sessions from
`state.db` (see `scripts/import_sessions_to_hindsight.py`).

## When to Consider Re-Extraction (vs Let Old Data Be)

Before re-importing or re-extracting, evaluate which config changes actually benefit:

| Config Change | Needs Re-Extraction? | Why |
|---------------|:---:|------|
| `recall_max_tokens` | No | Recall-phase parameter, doesn't affect stored facts |
| `recall_types` | No | Retrieval filter, doesn't affect stored facts |
| `retain_extraction_mode` change (concise→verbose) | Marginal | More detail per fact, but recall ranking (semantic+BM25+graph+temporal) is dominated by embedding model, not fact verbosity |
| `retain_mission` | Marginal | Steers extraction focus, but incremental benefit on old data is low |
| Switching extraction LLM | High risk | Untested models may not follow Hindsight's structured output format; dry-run first |

**Bottom line:** Let old data be. New sessions with improved config gradually accumulate
richer memories. Old + new facts coexist in recall (ranked by relevance, not detail level).

## Source: DeepSeek (chat.deepseek.com)

DeepSeek has internal APIs accessible after extracting the auth token from localStorage. Use CDP browser automation to get the token, then call APIs directly.

### Proven Approach: CDP + Direct API Calls

1. Start Edge with debug port (on Windows, use `CREATE_BREAKAWAY_FROM_JOB` so it survives SSH disconnect):
   ```
   --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run
   ```
   See `windows-remote-control/references/cdp-browser-data-extraction.md` for the full CDP client pattern.

2. Extract token from localStorage via CDP eval:
   ```javascript
   JSON.parse(localStorage.getItem('userToken')).value
   ```

3. Call DeepSeek internal APIs with `Authorization: Bearer {token}`:

   ```
   GET /api/v0/chat_session/fetch_page?before_seq_id={seq_id}  # paginated session list
   GET /api/v0/chat/history_messages?chat_session_id={id}        # messages per session
   ```

   Required headers:
   ```
   Authorization: Bearer {token}
   x-client-platform: web
   x-client-version: 1.2.0-sse-hint
   x-app-version: 20241129.1
   referer: https://chat.deepseek.com/
   ```

4. No Playwright or Selenium needed — just `websocket-client` + stdlib `urllib`.

A working export script is available at `templates/export_deepseek.py` (copy to Windows, `python export_deepseek.py`, output: `~/deepseek_export.json`).

### Key Pitfalls

- Edge needs `--remote-allow-origins=*` or WebSocket connections get 403.
- `/json/new` uses PUT, not GET.
- The URL param on `/json/new` doesn't work; use `Page.navigate` via WebSocket after tab creation.
- Use `CREATE_BREAKAWAY_FROM_JOB` (0x01000000) when starting Edge from Python to prevent it from dying with the SSH session.
- `taskkill /f /im msedge.exe` via `subprocess.run()` can block — avoid it; let Edge start fresh each run.
- Full CDP client pattern and troubleshooting: `windows-remote-control/references/cdp-browser-data-extraction.md`

## Source: Doubao (豆包, www.doubao.com)

### Current Status (July 2026)

- Web version at `doubao.com/chat` works and shows sidebar conversations
- **Settings page at `/settings` (plural) — NOT `/setting`**
- No built-in export feature found (only privacy settings)
- **API endpoints confirmed returning 401:** `/api/v1/conversations`, `/api/v1/conversation/list`, `/api/conversations` — cookie-based auth is used but the extraction pattern is not yet cracked
- Conversation data is NOT stored in IndexedDB (`samantha-web` database has only app state, not messages)
- Most conversations reside only on the mobile app — web version sync may be incomplete
- No `localStorage` token — auth is purely cookie-based

### Working Approaches

**App built-in export (reliable but manual):**
The Doubao mobile app supports per-conversation export to Word/PDF/TXT
(对话 → 分享按钮 → 导出文件). Most reliable option currently.

**DOM extraction via CDP (partial):**
If conversations are visible on the web version, DOM scraping works:
1. Scroll sidebar to collect conversation IDs from `a[href*="/chat/"]`
2. Navigate to `doubao.com/chat/{id}` for each
3. Extract `document.body.innerText` — conversations render in plain text

Limitation: role detection (user vs assistant) is unreliable from DOM classes alone.

### Settings Page URLs

| URL | Result |
|-----|--------|
| `/setting` | 404 — page not found |
| `/settings` | ✅ Settings page (account, privacy, model preferences) |
| `/settings/privacy` | Privacy settings (no export option) |

## Importing Extracted Conversations into Hindsight

After extracting conversations to JSON, format as plain text and use the retain API:

```python
from hindsight_client import Hindsight

client = Hindsight(base_url="http://localhost:8888")

for conv in extracted_data:
    # Format as readable conversation transcript
    text = f"Conversation: {conv['title']}\n\n"
    for msg in conv["messages"]:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        text += f"### {role}\n{content}\n\n"

    # Retain with a unique document_id for provenance
    doc_id = f"import-deepseek-{conv['id']}"
    client.retain(
        bank_id="main",
        content=text,
        document_id=doc_id,
        context="imported DeepSeek conversation",
        tags=["imported", "deepseek", "historical"],
        retain_async=True,
    )
```

**Re-retaining with the same `document_id` replaces old facts** — useful for
re-extraction experiments on a subset of documents.

## Pitfalls

- **CDP port must be accessible.** If the controlling machine is remote, use SSH tunneling.
- **Login sessions expire.** Cookie-based API calls may need re-authentication.
- **Rate limiting.** Add `time.sleep()` between API calls. Doubao may throttle.
- **The content itself is never stored verbatim** in Hindsight — only structured facts.
  Keep the raw JSON export as your source of truth.
- **Extraction is async.** Facts won't be immediately searchable after retain.
