#!/usr/bin/env python
"""
Export DeepSeek conversations via CDP on Edge/Chrome.
Extracts userToken from localStorage, then calls DeepSeek internal APIs.

Usage on Windows (9950x3d):
    python export_deepseek.py
    # Output: ~/deepseek_export.json

Dependencies: websocket-client only (pip install websocket-client)
"""
import json, time, urllib.request, sys, os, subprocess

CDP = "http://localhost:9222"
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

def ensure_edge():
    """Start Edge with debug port if not already running."""
    try:
        with urllib.request.urlopen(f"{CDP}/json/version", timeout=3) as r:
            data = json.loads(r.read())
            print(f"Edge CDP OK: {data.get('Browser','?')}")
            return True
    except:
        pass
    
    print("Starting Edge...")
    # Kill any existing Edge
    subprocess.run(["taskkill", "/f", "/im", "msedge.exe"], 
                   capture_output=True, timeout=5)
    time.sleep(2)
    
    # Start detached (survives SSH disconnect)
    flags = 0
    if hasattr(subprocess, 'CREATE_BREAKAWAY_FROM_JOB'):
        flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB
    if hasattr(subprocess, 'DETACHED_PROCESS'):
        flags |= subprocess.DETACHED_PROCESS
    
    subprocess.Popen(
        [EDGE, "--remote-debugging-port=9222", "--remote-allow-origins=*",
         "--no-first-run", "--no-default-browser-check", "about:blank"],
        creationflags=flags, close_fds=True
    )
    
    print("Waiting for CDP...", end="", flush=True)
    for i in range(60):
        time.sleep(1)
        try:
            with urllib.request.urlopen(f"{CDP}/json/version", timeout=2) as r:
                print(f" OK")
                return True
        except:
            print(".", end="", flush=True)
    print(" FAILED")
    return False

def cdp_get(path):
    with urllib.request.urlopen(f"{CDP}{path}", timeout=10) as r:
        return json.loads(r.read())

class CDPClient:
    def __init__(self, ws_url):
        import websocket
        self.ws = websocket.create_connection(ws_url, timeout=60)
        self._mid = 0
    
    def send_and_wait(self, method, params=None, timeout=60):
        self._mid += 1
        mid = self._mid
        msg = {"id": mid, "method": method}
        if params: msg["params"] = params
        self.ws.send(json.dumps(msg))
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
            "expression": expr, "returnByValue": True, "awaitPromise": True
        }, timeout=30)
        ret = r.get("result",{}).get("result",{})
        return ret.get("value")
    
    def close(self):
        self.ws.close()

def open_deepseek_tab():
    """Create tab and navigate to chat.deepseek.com."""
    import websocket
    
    # Create tab (PUT method!)
    req = urllib.request.Request(f"{CDP}/json/new", method='PUT')
    with urllib.request.urlopen(req, timeout=10) as r:
        tab = json.loads(r.read())
    
    # Navigate via WebSocket (URL param on /json/new doesn't work)
    ws = websocket.create_connection(tab['webSocketDebuggerUrl'], timeout=30)
    ws.send(json.dumps({"id":1, "method":"Page.enable"}))
    ws.recv()
    ws.send(json.dumps({"id":2, "method":"Page.navigate", 
                       "params":{"url":"https://chat.deepseek.com"}}))
    dl = time.time() + 30
    while time.time() < dl:
        ws.settimeout(max(1, dl - time.time()))
        try:
            if json.loads(ws.recv()).get("id") == 2:
                break
        except: continue
    ws.close()
    time.sleep(5)
    
    # Find the tab by URL
    tabs = cdp_get("/json/list")
    for t in tabs:
        if 'chat.deepseek.com' in t.get('url', ''):
            return t
    raise Exception("Navigation failed")

def main():
    print("="*50)
    print("DeepSeek Chat Exporter")
    print("="*50)
    
    if not ensure_edge():
        sys.exit(1)
    
    # Check for existing tab or create
    tabs = cdp_get("/json/list")
    tab = None
    for t in tabs:
        if 'chat.deepseek.com' in t.get('url', ''):
            tab = t
            break
    
    if not tab:
        print("Opening chat.deepseek.com...")
        tab = open_deepseek_tab()
    
    print(f"Tab: {tab['title'][:60]}")
    cdp = CDPClient(tab['webSocketDebuggerUrl'])
    cdp.send_and_wait("Runtime.enable")
    
    # Verify page loaded and check login
    page_url = cdp.eval_js("window.location.href")
    print(f"URL: {page_url}")
    
    has_token = cdp.eval_js("""
        (function() {
            try {
                const raw = localStorage.getItem('userToken');
                if (!raw) return 'NO_TOKEN';
                const t = JSON.parse(raw);
                return t && t.value ? 'LOGGED_IN' : 'INVALID';
            } catch(e) { return 'ERROR: ' + String(e); }
        })()
    """)
    print(f"Login: {has_token}")
    
    if has_token != 'LOGGED_IN':
        print("Not logged in! Open the Edge window and log into chat.deepseek.com, then re-run.")
        cdp.close()
        sys.exit(1)
    
    # Extract token
    token_json = cdp.eval_js("localStorage.getItem('userToken')")
    token = json.loads(token_json)['value']
    print(f"Token: {token[:30]}...")
    
    # API headers
    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "*/*",
        "referer": "https://chat.deepseek.com/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "x-client-platform": "web",
        "x-client-version": "1.2.0-sse-hint",
        "x-app-version": "20241129.1",
    }
    
    # Fetch all sessions
    print("\nFetching session list...")
    import urllib.parse as up
    all_sessions = []
    params = {}
    while True:
        url = "https://chat.deepseek.com/api/v0/chat_session/fetch_page"
        if params:
            url += "?" + up.urlencode(params)
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as r:
            data = json.loads(r.read())
        biz = data.get('data',{}).get('biz_data',{})
        sessions = biz.get('chat_sessions',[])
        has_more = biz.get('has_more', False)
        all_sessions.extend(sessions)
        print(f"  +{len(sessions)} (total {len(all_sessions)})")
        if not has_more or not sessions:
            break
        last = sessions[-1].get('seq_id')
        if last:
            params = {'before_seq_id': last}
        else:
            break
    
    print(f"\nTotal: {len(all_sessions)} sessions")
    print("Fetching messages...")
    
    # Fetch messages per session
    output = []
    for i, s in enumerate(all_sessions):
        sid = s.get('id','')
        title = (s.get('title') or 'Untitled')[:60]
        try:
            url = f"https://chat.deepseek.com/api/v0/chat/history_messages?chat_session_id={sid}"
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as r:
                msg_data = json.loads(r.read())
            s['messages_data'] = msg_data
            output.append(s)
            print(f"  [{i+1}/{len(all_sessions)}] {title}")
        except Exception as e:
            print(f"  [{i+1}/{len(all_sessions)}] FAIL: {title} - {e}")
            s['messages_data'] = {'error': str(e)}
            output.append(s)
        time.sleep(0.3)
    
    # Save
    out = os.path.expanduser("~/deepseek_export.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"\nSaved {len(output)} sessions to {out}")
    cdp.close()

if __name__ == "__main__":
    main()
