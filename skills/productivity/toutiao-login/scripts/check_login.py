#!/usr/bin/env python3
"""
检查今日头条登录状态

用法: python3 check_login.py <WS_URL>
"""

import websocket, json, sys

def main():
    ws_url = sys.argv[1] if len(sys.argv) > 1 else input('CDP WebSocket URL: ')
    
    ws = websocket.create_connection(ws_url, timeout=10)
    cid = [0]
    
    def call(method, params=None):
        cid[0] += 1
        msg = {'id': cid[0], 'method': method}
        if params:
            msg['params'] = params
        ws.send(json.dumps(msg))
        dl = time.monotonic() + 8
        while time.monotonic() < dl:
            try:
                r = json.loads(ws.recv())
                if 'id' in r and r['id'] == cid[0]:
                    return r
            except:
                pass
        return None
    
    def ev(js):
        r = call('Runtime.evaluate', {
            'expression': f'String({js})',
            'returnByValue': True
        })
        return r.get('result', {}).get('result', {}).get('value', '') if r else ''
    
    call('Page.enable')
    
    # 检查收藏链接
    fav = ev("""(function(){
        var links = document.querySelectorAll('a');
        var result = [];
        for(var a of links){
            var t = a.textContent.trim();
            if(t.includes('收藏') || t.includes('书签')){
                result.push({text: t, href: a.href});
            }
        }
        return JSON.stringify(result);
    })()""")
    
    # 检查用户信息
    user = ev("""(function(){
        var loginBtn = document.querySelector('.login-button');
        return JSON.stringify({
            loginBtnExists: !!loginBtn,
            title: document.title
        });
    })()""")
    
    print(f'页面: {user}')
    print(f'收藏链接: {fav}')
    
    ws.close()

if __name__ == '__main__':
    import time
    main()
