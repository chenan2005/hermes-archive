#!/usr/bin/env python3
"""
今日头条扫码登录 - 自动定位二维码并推送飞书

用法: python3 get_qr.py <WS_URL>
例:   python3 get_qr.py ws://127.0.0.1:9222/devtools/page/ABC123

全流程无 LLM 中转:
  1. CDP 连接 → ESC 关闭弹窗 → 点击登录按钮
  2. CDP 获取 QR 元素精确坐标 (getBoundingClientRect)
  3. import 截取 Edge 窗口
  4. 动态计算 titlebar 偏移 → Pillow 裁剪 QR 区域
  5. 飞书 API 上传图片并发送

依赖: websocket-client, Pillow, xdotool, imagemagick, curl
"""

import websocket, json, time, os, sys, urllib.request, subprocess
from PIL import Image

# ============ 配置 ============
FEISHU_APP_ID = 'cli_aa969a7a3f785cce'
FEISHU_SECRET_PATH = os.path.expanduser('~/.hermes/.env')
FEISHU_CHAT_ID = 'oc_f8b7d27c97f45ca5b89fec45760c5728'

LOGIN_BTN_X = 1131
LOGIN_BTN_Y = 345

SS_PATH = '/tmp/toutiao_edge_ss.png'
QR_PATH = '/tmp/toutiao_qr.png'

# QR 裁剪边距 (px) - 包含二维码周围文字区域
CROP_MARGIN = 20

# ============ 工具函数 ============

def get_feishu_secret():
    with open(FEISHU_SECRET_PATH) as f:
        for line in f:
            if line.startswith('FEISHU_APP_SECRET='):
                return line.strip().split('=', 1)[1].strip().strip("'\"")
    raise RuntimeError(f'FEISHU_APP_SECRET not found in {FEISHU_SECRET_PATH}')

def cdp_session(ws_url):
    """返回 CDP 会话上下文管理器"""
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
        'curl', '-s', '-X', 'POST', '--noproxy', '*',
        'https://open.feishu.cn/open-apis/im/v1/images',
        '-H', f'Authorization: Bearer {token}',
        '-F', 'image_type="message"',
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

def get_qr_position(sess):
    """通过 CDP 获取 QR 元素精确位置和窗口信息"""
    info = sess.ev("""(function(){
        var wrapper = document.querySelector('.web-login-scan-code__content__qrcode-wrapper');
        var img = document.querySelector('.web-login-scan-code__content__qrcode-wrapper__qrcode');
        if(!wrapper || !img) return 'NOT_FOUND';
        
        var rWrap = wrapper.getBoundingClientRect();
        var rImg = img.getBoundingClientRect();
        
        return JSON.stringify({
            wrapper: {x: rWrap.x, y: rWrap.y, w: rWrap.width, h: rWrap.height},
            img: {x: rImg.x, y: rImg.y, w: rImg.width, h: rImg.height},
            innerW: window.innerWidth,
            innerH: window.innerHeight,
            outerW: window.outerWidth,
            outerH: window.outerHeight,
            qrLoaded: img.naturalWidth > 0 && img.complete
        });
    })()""")
    
    if info == 'NOT_FOUND':
        return None
    
    return json.loads(info)

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
    time.sleep(0.5)
    sess.call('Input.dispatchKeyEvent', {
        'type': 'keyUp', 'text': 'Escape', 'key': 'Escape', 'code': 'Escape',
        'nativeVirtualKeyCode': 27, 'windowsVirtualKeyCode': 27
    })
    time.sleep(1)
    
    # 3. 点击登录按钮
    print('3. 点击登录按钮...')
    sess.call('Input.dispatchMouseEvent', {
        'type': 'mousePressed', 'x': LOGIN_BTN_X, 'y': LOGIN_BTN_Y,
        'button': 'left', 'clickCount': 1
    })
    time.sleep(0.05)
    sess.call('Input.dispatchMouseEvent', {
        'type': 'mouseReleased', 'x': LOGIN_BTN_X, 'y': LOGIN_BTN_Y,
        'button': 'left', 'clickCount': 1
    })
    
    # 4. 等待 QR 渲染
    print('4. 等待 QR 渲染...')
    time.sleep(3)
    
    qr_info = sess.ev("""(function(){
        var i = document.querySelector('.web-login-scan-code__content__qrcode-wrapper__qrcode');
        if(!i) return 'NO_IMG';
        return JSON.stringify({len: i.src.length, nw: i.naturalWidth, complete: i.complete});
    })()""")
    print(f'   QR: {qr_info}')
    
    # 5. 获取 QR 精确位置
    print('5. 定位 QR...')
    position = get_qr_position(sess)
    if position is None:
        print('ERROR: QR element not found')
        sess.close()
        return
    
    print(f'   wrapper: {position["wrapper"]}')
    print(f'   img: {position["img"]}')
    print(f'   window: {position["innerW"]}x{position["innerH"]} (outer: {position["outerW"]}x{position["outerH"]}')
    
    # 计算 titlebar 高度
    titlebar_h = position['outerH'] - position['innerH']
    print(f'   titlebar height: {titlebar_h}px')
    
    # 6. 截图
    print('6. 截图...')
    sess.close()
    
    edge_win = subprocess.run(
        ['bash', '-c', 'DISPLAY=:0 xdotool search --name "今日头条" | head -1'],
        capture_output=True, text=True
    ).stdout.strip()
    
    if not edge_win:
        print('ERROR: Edge window not found')
        return
    
    os.system(f'DISPLAY=:0 import -window {edge_win} {SS_PATH} 2>/dev/null')
    print(f'   SS: {os.path.getsize(SS_PATH)} bytes')
    
    # 7. 动态裁剪 QR
    print('7. 裁剪 QR...')
    img = Image.open(SS_PATH)
    ss_w, ss_h = img.size
    print(f'   screenshot: {ss_w}x{ss_h}')
    
    # QR wrapper 在窗口截图中的坐标
    # import -window 截的是整个窗口 (含 titlebar)
    # viewport 起始位置: x=0, y=titlebar_h
    w = position['wrapper']
    crop_x = int(w['x'])
    crop_y = int(w['y']) + titlebar_h
    crop_w = int(w['w']) + CROP_MARGIN * 2
    crop_h = int(w['h']) + CROP_MARGIN * 2
    
    # 边界检查
    crop_x = max(0, crop_x - CROP_MARGIN)
    crop_y = max(titlebar_h, crop_y - CROP_MARGIN)
    crop_x2 = min(ss_w, crop_x + crop_w)
    crop_y2 = min(ss_h, crop_y + crop_h)
    
    print(f'   crop: ({crop_x}, {crop_y}, {crop_x2-crop_x}x{crop_y2-crop_y})')
    
    crop = img.crop((crop_x, crop_y, crop_x2, crop_y2))
    crop.save(QR_PATH)
    print(f'   QR: {os.path.getsize(QR_PATH)} bytes, {crop.size}')
    
    # 8. 发飞书
    print('8. 推送飞书...')
    if feishu_send_image(QR_PATH):
        print('已发送！快扫！')
    else:
        print('发送失败')

if __name__ == '__main__':
    main()
