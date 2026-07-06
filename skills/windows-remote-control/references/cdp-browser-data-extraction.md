# CDP Browser Data Extraction on Windows

Reverse-engineer web app APIs by extracting auth tokens and calling internal endpoints. Uses Chrome DevTools Protocol (CDP) over Edge/Chrome debug port.

## Quick Reference

```bash
# Start Edge with debug port (from SSH, must survive session)
# Use Python subprocess.Popen with CREATE_BREAKAWAY_FROM_JOB
python:
  subprocess.Popen(
      [EDGE, "--remote-debugging-port=9222", "--remote-allow-origins=*",
       "--no-first-run", "--no-default-browser-check", "about:blank"],
      creationflags=subprocess.CREATE_BREAKAWAY_FROM_JOB | subprocess.DETACHED_PROCESS
  )

# Verify CDP is up
curl http://localhost:9222/json/version
```

## Critical Flags

| Flag | Required? | Why |
|------|:--:|------|
| `--remote-debugging-port=9222` | ✅ | Enables CDP |
| `--remote-allow-origins=*` | ✅ | Needed for WebSocket connections to tab devtools URLs. Without it: `WebSocketBadStatusException: Handshake status 403 Forbidden` |
| `--no-first-run` | Recommended | Skip first-run wizard |
| `--no-default-browser-check` | Recommended | Skip default browser prompt |

## Edge Paths (Windows)

```
Edge:  C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
User data: %LOCALAPPDATA%\Microsoft\Edge\User Data
```

## Key CDP Endpoints

| Endpoint | Method | Purpose |
|----------|:--:|------|
| `/json/version` | GET | Verify CDP, get browser version |
| `/json/list` | GET | List all open tabs with WebSocket URLs |
| `/json/new` | **PUT** | Create new tab. Note: PUT, not GET. URL param via query string doesn't work — use `Page.navigate` via WebSocket after creating tab. |

## Python CDP Client (Minimal)

```python
import json, time, urllib.request
import websocket

CDP = "http://localhost:9222"

def cdp_get(path):
    with urllib.request.urlopen(f"{CDP}{path}", timeout=10) as r:
        return json.loads(r.read())

class CDPClient:
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self._mid = 0

    def send_and_wait(self, method, params=None, timeout=60):
        self._mid += 1
        mid = self._mid
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        dl = time.time() + timeout
        while time.time() < dl:
            self.ws.settimeout(max(0.5, dl - time.time()))
            try:
                m = json.loads(self.ws.recv())
                if m.get("id") == mid:
                    return m
            except: continue
        raise TimeoutError(f"No response for {mid}")

    def eval_js(self, expr):
        r = self.send_and_wait("Runtime.evaluate", {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True
        }, timeout=30)
        return r.get("result", {}).get("result", {}).get("value")

    def navigate(self, url):
        self.send_and_wait("Page.navigate", {"url": url})
        time.sleep(3)

    def close(self):
        self.ws.close()
```

## Tab Management

```python
# Open new tab and navigate
req = urllib.request.Request(f"{CDP}/json/new", method='PUT')  # PUT, not GET!
with urllib.request.urlopen(req, timeout=10) as r:
    tab = json.loads(r.read())

# Navigate via WebSocket (the URL param on /json/new doesn't work)
ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=30)
ws.send(json.dumps({"id": 1, "method": "Page.enable"}))
ws.recv()
ws.send(json.dumps({"id": 2, "method": "Page.navigate", "params": {"url": "https://target.com"}}))
# Wait for navigation response
ws.close()
time.sleep(3)

# Find tab by URL
tabs = cdp_get("/json/list")
for t in tabs:
    if 'target.com' in t.get('url', ''):
        print(f"Found: {t['webSocketDebuggerUrl']}")
```

## Pitfalls

### Edge Dies When SSH Session Ends
**Symptom:** Edge starts and CDP works, but on next SSH connection Edge is dead.
**Cause:** `subprocess.Popen` started from SSH will be killed when SSH session exits (even with `start /b` in cmd).
**Fix:** Use `CREATE_BREAKAWAY_FROM_JOB` flag on Windows:

```python
flags = 0
if hasattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB'):
    flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB  # 0x01000000
if hasattr(subprocess, 'DETACHED_PROCESS'):
    flags |= subprocess.DETACHED_PROCESS  # 0x00000008
subprocess.Popen([...], creationflags=flags)
```

Note: `CREATE_NO_WINDOW` (0x08000000) may hide the browser window completely — use only if you don't need the user to see it.

### /json/new Returns 405
**Cause:** The endpoint requires PUT method, not GET.
**Fix:** Use `urllib.request.Request(url, method='PUT')`.

### WebSocket Handshake 403 Forbidden
**Symptom:** `WebSocketBadStatusException: Handshake status 403 Forbidden`
**Message:** "Rejected an incoming WebSocket connection from the http://localhost:9222 origin."
**Fix:** Add `--remote-allow-origins=*` to Edge startup flags.

### localStorage "Access is denied for this document"
**Symptom:** `eval_js("localStorage.getItem('...')")` returns error.
**Cause:** Tab is on `about:blank`, not the target site.
**Fix:** Always `Page.navigate` to the target URL after creating a tab, wait for `readyState === 'complete'`, then verify `window.location.href`.

### Python 3.14 Windows: Missing websocket-client
**Install:** `python -m pip install websocket-client`
No extra deps — only `websocket-client` and stdlib (`json`, `time`, `urllib.request`) needed.

## DeepSeek API (Example Pattern)

Auth token source: `localStorage.getItem('userToken')` → `JSON.parse(raw).value`

Endpoints (all use `Authorization: Bearer {token}` header):
- `GET /api/v0/chat_session/fetch_page?before_seq_id={seq_id}` — paginated session list
- `GET /api/v0/chat/history_messages?chat_session_id={id}` — session messages

Headers required:
```python
headers = {
    "Authorization": f"Bearer {token}",
    "accept": "*/*",
    "referer": "https://chat.deepseek.com/",
    "User-Agent": "Mozilla/5.0 ...",
    "x-client-platform": "web",
    "x-client-version": "1.2.0-sse-hint",
    "x-app-version": "20241129.1",
}
```

## Doubao (豆包) Export — CDP Network Intercept Pattern

### Architecture

Doubao web uses an internal IM protocol over HTTP POST to `/im/chain/single`. Messages are returned as JSON-wrapped protobuf structures. The page uses a **React virtual list** (class: `v_list_scroller-BxcoIX`) with lazy loading on scroll-up.

### Endpoints

| Endpoint | Purpose |
|----------|---------|
| `POST /im/chain/single` | Message list (cmd=3100, paginated via `next_index`) |
| `POST /im/conversation/info` | Conversation metadata (cmd=1110) |
| `POST /im/chain/recent_conv` | Recent conversation list (cmd=3200) |

Request body structure:
```json
{"cmd":3100,"uplink_body":{"pull_singe_chain_uplink_body":{"conversation_id":"4830199810","anchor_index":9007199254740991,"conversation_type":3,"direction":1,"limit":20,"ext":{},"filter":{"index_list":[]},"evaluate_ab_params":"","evaluate_common_params":""}},"sequence_id":"<UUID>","channel":2,"version":"1"}
```

Response: `downlink_body.pull_singe_chain_downlink_body.messages[]` with `has_more` and `next_index` for pagination. Messages have `index_in_conv`, `user_type` (1=user, 2=assistant), `tts_content` (plain text), and `content` (rich JSON).

### The Critical Insight: API Replay Fails

**DO NOT try to replay API calls from outside the page context.** Calling the same endpoint with the same JSON body from Python `urllib` or `eval_js`+`fetch()` returns 0 messages. The page's native fetch requests work; replayed ones don't (likely anti-CSRF or Service Worker routing). 

Only the page's **own** API calls (triggered by scrolling) return data.

### Winning Approach: User Scrolls + CDP Intercepts Responses

```python
# 1. Enable Network monitoring
cdp_send("Network.enable", {"maxTotalBufferSize": 100000000, "maxResourceBufferSize": 50000000})

# 2. Listen for /im/chain/single responses
# Network.responseReceived → collect requestId
# Network.loadingFinished → Network.getResponseBody(requestId) → parse messages

# 3. User manually scrolls the page (JS scrollBy/Input.dispatchMouseEvent does NOT trigger lazy load)
# Each scroll-up triggers a new /im/chain/single call with next_index

# 4. Accumulate unique messages by index_in_conv
# 5. Auto-stop after 20s of no new messages
```

### Why CDP Scroll Simulation Fails

All tested approaches return 0 new API calls:
- `element.scrollBy(0, -height)` — virtual list ignores programmatic scroll
- `element.scrollTo({top: 0})` — no effect on lazy load trigger
- `Input.dispatchMouseEvent({type: "mouseWheel"})` — page filters injected events
- `element.dispatchEvent(new WheelEvent(...))` — same, event is synthetic

The virtual list (`v_list_scroller-BxcoIX`) only responds to native OS-level scroll events. User must scroll manually.

### Incremental Save Is Critical

**Pitfall:** In one session, the listener collected 1203 messages in memory, printed "Saved 1.1MB", but the file on disk was only 14 messages (13KB). The `json.dump()` either silently failed or the file was overwritten. Root cause unclear (Windows file buffering, path resolution, or process timing).

**Fix:** Save incrementally after every batch of new messages:

```python
# After each batch of new messages from Network.getResponseBody:
with open(inc_path, 'w', encoding='utf-8') as f:
    json.dump(export, f, ensure_ascii=False)
```

Use a timestamped filename (`doubao_%Y%m%d_%H%M%S.json`) to avoid overwriting.

### Python Output Buffering on Windows SSH

When running Python scripts on Windows via SSH, stdout is fully buffered (no TTY). Output may appear empty even though the script is running. Fix:

```bash
# Either:
ssh target "set PYTHONUNBUFFERED=1 && python script.py"
# Or in the script:
import sys
sys.stdout.reconfigure(line_buffering=True)  # Python 3.7+
```

### Preloaded State: `_CHAT_APP_.PREFETCHED_DATA`

The page exposes initial server-rendered data at `window._CHAT_APP_.PREFETCHED_DATA`:
- `chat_(id)/page.messageList.message_list` — initial 14 messages
- `chat_layout` — UI config, account info, skill list
- Only covers the first batch; dynamically loaded messages are in React component state (not accessible via CDP without fiber tree traversal)

### Results (2026-07-04)

- Conversation ID: `4830199810`
- Extracted: **1,902 messages** (966 assistant, 936 user)
- Range: index 1 → 4301
- Total: 660 KB of text
- File: 1.5 MB JSON
- Time: ~3 minutes of manual scrolling

### Greasy Fork Alternative

Userscript [#542188](https://greasyfork.org/en/scripts/542188) "AI对话导出word/json/md" supports doubao and other AI platforms. It intercepts network responses in-browser (Tampermonkey). Same limitation: user must manually scroll to trigger API calls before clicking export.

### Other Doubao Notes

- Web version: only ONE conversation visible (the main chat), unlike DeepSeek which lists all
- Settings page: `/settings` (plural), NOT `/setting`
- No built-in export feature
- Auth uses cookies (HttpOnly), not localStorage tokens
- Conversation data NOT in IndexedDB (only UI state in `samantha-web` database)
- PREFETCHED_DATA only covers initial server render — not dynamically loaded messages
