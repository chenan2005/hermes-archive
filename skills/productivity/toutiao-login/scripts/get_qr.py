#!/usr/bin/env python3
"""
今日头条扫码登录 - 获取二维码并推送飞书

用法: python3 get_qr.py <WS_URL>
例:   python3 get_qr.py ws://127.0.0.1:9222/devtools/page/ABC123

全流程无 LLM 中转 (~10s 完成):
  1. CDP 连接 → ESC 关闭弹窗 → JS .click() 打开登录
  2. 等待 QR 渲染 (2s)
  3. 从 DOM img.src 提取 base64 二维码
  4. 飞书 API 上传图片并发送

依赖: websocket-client, Pillow, curl
"""

import websocket, json, time, os, sys, urllib.request, subprocess, base64

# ============ 配置 ============
FEISHU_APP_ID = 'cli_aa969a7a3f785cce'
FEISHU_SECRET_PATH = '/home/chenan/.hermes/.env'
FEISHU_CHAT_ID = 'oc_f8b7d27c97f45ca5b89fec45760c5728'

SS_PATH = '/tmp/toutiao_edge_ss.png'
QR_PATH = '/tmp/toutiao_qr.png'

# ============ 工具函数 ============

def get_feishu_secret():
    with open(FEISHU_SECRET_PATH) as f:
        for line in f:
            if line.startswith('FEISHU_APP_SECRET='):
                return line.strip().split('=', 1)[1].strip().strip("'\"")
    raise RuntimeError(f'FEISHU_APP_SECRET not found in {FEISHU_SECRET_PATH}')

def cdp_session(ws_url):
    """返回 CDP 会话"""
    ws = websocket.create_connection(ws_url, timeout=10)
    cid = [0]
    
    def call(method, params=None):
        cid[0] += 1
        msg = {'id': cid[0], 'method': method}
        if params:
            msg['params'] = params
        ws.send(json.dumps(msg))
        dl = time.monotonic() + 10
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
    
    class Session:
        def __init__(self):
            self.ws = ws
            self.call = call
            self.ev = ev
        def close(self):
            ws.close()
    
    return Session()

def feishu_send_image(img_path):
    """上传图片到飞书并发送"""
    print(f'图片: {os.path.getsize(img_path)} bytes')
    
    secret = get_feishu_secret()
    
    # 获取 token
    token_resp = urllib.request.urlopen(urllib.request.Request(
        'https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal',
        json.dumps({'app_id': FEISHU_APP_ID, 'app_secret': secret}).encode(),
        {'Content-Type': 'application/json'}
    ))
    token = json.loads(token_resp.read())['tenant_access_token']
    
    # 上传图片
    upload = subprocess.run([
        'curl', '-s', '--noproxy', '*',
        'https://open.feishu.cn/open-apis/im/v1/images',
        '-H', f'Authorization: Bearer {token}',
        '-F', 'image_type=message',
        f'-F', f'image=@{img_path}'
    ], capture_output=True, text=True, env={**os.environ, 'http_proxy': '', 'https_proxy': ''})
    data = json.loads(upload.stdout)
    if data.get('code') != 0:
        print(f'Upload fail: {data}')
        return False
    image_key = data['data']['image_key']
    
    # 发送消息
    send_url = f'https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id&receive_id={FEISHU_CHAT_ID}'
    send_resp = urllib.request.urlopen(urllib.request.Request(
        send_url,
        json.dumps({
            'receive_id': FEISHU_CHAT_ID,
            'msg_type': 'image',
            'content': json.dumps({'image_key': image_key})
        }).encode(),
        {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    ))
    result = json.loads(send_resp.read())
    print(f'飞书: {result.get("msg", result)}')
    return True

# ============ 主流程 ============

def main():
    ws_url = sys.argv[1] if len(sys.argv) > 1 else input('CDP WebSocket URL: ')
    
    print('1. 连接 CDP...')
    sess = cdp_session(ws_url)
    sess.call('Page.enable')
    
    # 2. 关闭弹窗 (ESC)
    print('2. 关闭登录弹窗...')
    sess.call('Input.dispatchKeyEvent', {
        'type': 'keyDown', 'text': 'Escape', 'key': 'Escape', 'code': 'Escape',
        'nativeVirtualKeyCode': 27, 'windowsVirtualKeyCode': 27
    })
    time.sleep(0.3)
    
    # 3. 清除 cookies 和缓存（必须！否则浏览器缓存 QR 数据导致过期）
    print('3. 清除 cookies...')
    sess.call('Network.clearBrowserCookies')
    sess.call('Storage.clearDataForOrigin', {
        'origin': 'https://www.toutiao.com',
        'storageTypes': 'cookies,local_storage,shader_cache,indexeddb,web_sql,cache_storage'
    })
    
    # 4. 强制刷新页面
    print('4. 刷新页面...')
    sess.call('Page.reload', {'ignoreCache': True})
    time.sleep(3)
    
    # 5. JS .click() 打开登录
    print('5. 打开登录弹窗...')
    result = sess.ev('(function(){ var btn = document.querySelector("a.login-button"); if(btn){btn.click();return "clicked";} return "no"; })()')
    print(f'   Click result: {result}')
    
    # 6. 等待 QR 渲染
    print('6. 等待 QR 渲染...')
    time.sleep(2)
    
    qr_check = sess.ev('(function(){ var i = document.querySelector(".web-login-scan-code__content__qrcode-wrapper__qrcode"); return i ? JSON.stringify({len:i.src.length,nw:i.naturalWidth}) : "NO"; })()')
    print(f'   QR: {qr_check}')
    
    # 5. 从 DOM img.src 提取 base64
    print('5. 提取 QR base64...')
    b64 = sess.ev('(function(){ var i = document.querySelector(".web-login-scan-code__content__qrcode-wrapper__qrcode"); if(!i) return null; if(!i.src.startsWith("data:")) return null; return i.src.split(",")[1]; })()')
    
    if not b64:
        print('ERROR: QR base64 not found')
        sess.close()
        return
    
    data = base64.b64decode(b64)
    with open(QR_PATH, 'wb') as f:
        f.write(data)
    print(f'   QR saved: {len(data)} bytes')
    
    # 6. 验证
    from PIL import Image
    img = Image.open(QR_PATH)
    gray = img.convert('L')
    dark = sum(1 for x in range(img.width) for y in range(img.height) if gray.getpixel((x,y)) < 128)
    total = img.width * img.height
    dark_pct = dark/total*100
    print(f'   QR: {img.size}, dark={dark_pct:.0f}%')
    
    # QR 应有 20-60% 暗像素，且尺寸合理
    if dark_pct < 20 or dark_pct > 60 or img.width < 200 or img.height < 200:
        print(f'   WARNING: QR may be placeholder (dark={dark_pct:.0f}%, size={img.size})')
        sess.close()
        return
    
    sess.close()
    
    # 7. 发飞书
    print('6. 推送飞书...')
    if feishu_send_image(QR_PATH):
        print('已发送！快扫！')
    else:
        print('发送失败')

if __name__ == '__main__':
    main()
