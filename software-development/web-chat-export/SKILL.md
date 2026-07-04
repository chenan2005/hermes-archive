---
name: web-chat-export
description: Export AI chat platform conversation history (DeepSeek, Doubao, ChatGPT, etc.) via CDP token/cookie extraction + internal API calls. Covers auth discovery, API reverse-engineering, pagination, and platform quirks.
category: software-development
metadata:
  hermes:
    tags: [cdp, browser-automation, data-export, ai-chat, api-reverse-engineering]
---

# Web Chat Export

Export conversation history from AI chat platforms by extracting authentication via Chrome DevTools Protocol (CDP) and calling internal APIs. Covers both login-token (localStorage) and cookie-based auth platforms.

## Triggers

- "Export my DeepSeek/ChatGPT/Doubao/Claude chat history"
- "Download all my conversations from [platform]"
- "Back up AI chat data for Hindsight import"
- References to `deepseek-chat-exporter` or similar tools

## Workflow

### Phase 1: Auth Discovery

1. **Start browser with CDP** on the target machine
2. **Identify auth mechanism** by inspecting the logged-in page:
   - Check `localStorage` for tokens: `localStorage.getItem('userToken')`, `__session`, etc.
   - Check `document.cookie` + CDP `Network.getCookies` for HttpOnly session cookies
   - Look for Bearer tokens in network requests
3. **Platform-specific auth patterns:**

| Platform | Auth Type | How to Extract |
|---|---|---|
| DeepSeek | localStorage `userToken` | CDP eval `JSON.parse(localStorage.getItem('userToken'))` → Bearer header |
| Doubao | HttpOnly cookies | CDP `Network.getCookies({urls:["https://www.doubao.com"]})` → Cookie header |

### Phase 2: API Discovery

1. **Enable Network monitoring** via CDP: `Network.enable`
2. **Trigger page interactions** to elicit API calls (scroll, click conversations, reload)
3. **Capture and analyze** `Network.requestWillBeSent` events
4. **Test API endpoints** with extracted auth, varying parameters to understand pagination

### Phase 3: Data Extraction

1. **Paginate through all data** using the discovered mechanism
2. **Parse response format** (JSON, protobuf-embedded JSON, streaming)
3. **Handle encoding**: Windows console GBK — use `safe_print()` wrapper with `encode('ascii','replace')` fallback
4. **Save as JSON** with metadata (source, conversation_id, exported_at, messages[])

### Phase 4: Import to Hindsight (optional)

See `references/hindsight_import.md` for full API documentation.

Quick reference:
```python
# POST /v1/default/banks/{bank_id}/memories
item = {
    "content": "Full conversation text with markdown formatting",
    "context": f"{platform}-conv-{conv_id}",
    "tags": ["import", platform, "conversation"],
    "metadata": {"source": platform, "conv_id": str(conv_id), "message_count": str(len(msgs))}
}
payload = {"items": [item], "async": True}
```

Use `async=True` for bulk imports — sync mode may timeout on LLM extraction. Response returns `operation_ids` (may be empty for async; tasks are queued).

Group conversations into manageable chunks:
- DeepSeek: 1 item per session (~15 msgs avg)
- Doubao: 80 messages per chunk (~25KB text each)
- Submit in batches of 20 items with 2s pause between batches

Post-import: check `GET /v1/default/banks/main/operations` for processing status
Check `GET /v1/default/banks/main/documents` for new documents with import tags

## Platform-Specific Details

### DeepSeek (chat.deepseek.com)

- **Auth**: `userToken` in localStorage, passed as `Authorization: Bearer <token>`
- **API**: `/api/v0/chat_session/fetch_page` (session list, paginated), `/api/v0/chat/history_messages?chat_session_id=<id>` (messages)
- **Pagination**: Session list uses `page_token`; messages return all at once
- **Gotcha**: Need to set `Content-Type: application/json` and `User-Agent`
- **Reference script**: `references/deepseek_api.py`

### Doubao (www.doubao.com)

- **Auth**: HttpOnly cookies (sessionid, sid_tt, etc.), must use CDP `Network.getCookies`
- **API**: `POST /im/chain/single?version_code=20800&...` with protobuf-like JSON body
  - `cmd: 3100` = pull message chain
  - `anchor_index` + `direction` for pagination (direction=1 backward, direction=0 forward)
  - Response: `downlink_body.pull_singe_chain_downlink_body.messages[]`
  - Pagination via `next_index` from response → use as `anchor_index` in next request
- **Message format**: `user_type` (1=user, 2=assistant), `tts_content` (clean markdown text), `content` (JSON string with references), `index_in_conv`
- **Limitation**: Web version only syncs ~42 most recent messages; full history on mobile app
- **Anti-replay protection**: Replaying the API call from `eval_js`/`fetch()` (even with exact same URL+body+headers+cookies) returns 0 messages. Only the page's own native fetches (triggered by actual user scroll) work. Likely Service Worker interception or per-request token binding. **Do NOT attempt to paginate via programmatic API calls** — they always return empty.
- **CDP scroll simulation failure**: ALL programmatic scroll methods fail to trigger lazy loading:
  - `scrollBy`, `scrollTo(0)`, `dispatchEvent(scroll)`, `dispatchEvent(wheel)` — no effect
  - CDP `Input.dispatchMouseEvent(mouseWheel)` — no API calls triggered
  - The virtual list (`v_list_scroller-BxcoIX`) uses IntersectionObserver/internal state that filters injected events
- **Best approach**: Semi-automated — user manually scrolls through conversation (to trigger native API calls), CDP captures all `/im/chain/single` responses. User does the scrolling, script does the collecting.
- **Greasy Fork alternative**: [AI对话导出](https://greasyfork.org/en/scripts/542188) userscript installs export buttons; user manually scrolls then clicks export.
- **Reference script**: `references/doubao_api.md`

## Edge CDP on Windows

Edge supports the same CDP as Chrome. Critical flags:
```
--remote-debugging-port=9222
--remote-allow-origins=*       # REQUIRED for WebSocket connections
```

### Starting Edge from SSH Without Locking User Out

**PITFALL**: `subprocess.Popen` from SSH runs Edge in Session 0 (Services), not the interactive desktop session. The user can't see or use the browser.

**SOLUTION**: Use `schtasks` to launch Edge in the interactive session:
```powershell
schtasks /create /tn EdgeDebug /tr '"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --remote-debugging-port=9222 --remote-allow-origins=*' /sc once /st 00:00 /f
schtasks /run /tn EdgeDebug
```

After export, clean up:
```powershell
schtasks /delete /tn EdgeDebug /f
taskkill /f /im msedge.exe  # optional, if user wants normal Edge back
```

Alternative: let the user manually start Edge with the flags (less automation, more reliable).

## CDP Utilities (Python)

```python
import websocket, json, urllib.request

CDP = "http://localhost:9222"

def cdp_get(path):
    with urllib.request.urlopen(f"{CDP}{path}", timeout=10) as r:
        return json.loads(r.read())

# Get all tabs
tabs = cdp_get("/json/list")

# Connect to a tab's WebSocket
ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=60)

def send(method, params=None):
    mid = some_id()
    ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
    # ... read until matching id
```

Key CDP methods used:
- `Runtime.enable` + `Runtime.evaluate` — execute JS in page context
- `Network.enable` + `Network.getCookies` — get all cookies including HttpOnly
- `Page.enable` + `Page.navigate` — navigate to URLs
- `Network.requestWillBeSent` events — intercept API calls

## Pitfalls

### GBK Encoding on Windows
Python `print()` on Windows terminal crashes with `UnicodeEncodeError` for non-GBK chars. Always wrap prints:
```python
def safe_print(s):
    try: print(s)
    except UnicodeEncodeError: print(s.encode('ascii','replace').decode('ascii'))
```

### WebSocket 403 from CDP
If Edge was started WITHOUT `--remote-allow-origins=*`, WebSocket connections to tab URLs fail with 403. Always include this flag.

### Cookie Scope
`document.cookie` only returns non-HttpOnly cookies. Use CDP `Network.getCookies({"urls":["https://domain.com"]})` for complete cookie set.

## Data Verification Checklist

Before declaring export complete:

1. **Check first message makes chronological sense** — if the user remembers starting with "write golang code" but export shows "welcome message", check if idx=1 is an auto-generated system message
2. **Check last message matches recent conversation** — verify the highest-index message is what the user recalls as most recent
3. **Always sort by index when showing first/last**: `sorted(msgs, key=lambda m: int(m['idx']))` — accessing `msgs[-1]` on an unsorted array is unreliable
4. **Spot-check random messages** from the middle of the export to confirm content integrity
5. **Verify index density**: `len(msgs) / (max_idx - min_idx + 1)` — expect ~44% for doubao, higher for platforms without system event gaps
6. **Check role distribution**: user vs assistant counts should be roughly equal (within ±10% for bidirectional conversations)

### Doubao Index vs Count Clarification

Users may see "4301" in API metadata and expect 4301 messages. Explain:
- `index_in_conv` is a server-side event counter, not message count
- System events (tool calls, deleted messages, image generation) occupy index slots
- Observed density: 44% — 1902 user-visible messages out of 4301 index slots
- DO NOT claim 4301 messages were exported if only 1902 were captured ✓
- DO claim "1902 messages across 4301 total events" ✓

### Doubao Anti-Replay Protection

Replaying `/im/chain/single` calls via `Runtime.evaluate` + `fetch()` returns 0 messages even with exact URL + body + cookies. Only the page's own native fetches work (likely Service Worker interception or per-request binding). Do NOT attempt programmatic pagination — stick to intercepting page-initiated requests.

### Edge Process Locking
When Edge runs with `--remote-debugging-port`, it locks the user data directory. Normal Edge launch fails. Kill the debug instance before user resumes normal browsing.

### Silent File Write Failure on Windows

On Windows over SSH, `json.dump()` to an absolute path like `C:/Users/chen_/doubao_export.json` can report success (script prints "Saved 1.1 MB") but the actual file on disk is only 13KB from a previous run. Root cause unclear — may involve filesystem caching or path resolution across SSH sessions. 

**Mitigation**: Save incrementally after every batch of captured responses (not just at the end). The incremental file serves as insurance:
```python
# After each batch of new messages:
with open('doubao_incremental.json', 'w', encoding='utf-8') as f:
    json.dump(current_state, f, ensure_ascii=False)
```

Also save a timestamped final copy on exit as cross-check:
```python
final_path = f'C:/Users/chen_/doubao_{timestamp}.json'
with open(final_path, 'w', encoding='utf-8') as f:
    json.dump(final_state, f, ensure_ascii=False)
```

If the two files differ in size, the timestamped copy is authoritative. This session confirmed the timestamped copy was correct (1.6MB) while the in-place overwrite silently failed.

## Key Takeaway

Always prefer API extraction over DOM scraping for chat platforms. The API is the source of truth; the DOM is a rendering artifact with limited, virtualized content. CDP's role is auth extraction, not data extraction.

## Reference Files

- `references/deepseek_api.md` — Full DeepSeek API schema, pagination, and working script notes
- `references/doubao_api.md` — Doubao IM protocol, message format, CDP scroll-intercept pattern, index density
- `references/hindsight_import.md` — Hindsight REST API bulk import schema, chunking strategy, token cost
