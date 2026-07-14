---
name: toutiao-login
description: 今日头条扫码登录自动化 — 本地 Edge + CDP 提取二维码 → 飞书直发。覆盖登录按钮点击、QR 刷新（关闭弹窗→重新打开）、截图裁剪、飞书推送全流程。触发词：头条登录、头条二维码、扫码登录、toutiao
---

# 今日头条扫码登录

本地 Edge 桌面浏览器 + CDP 自动化提取二维码，秒级直推飞书，用户扫码完成登录。

## 核心约束

- **必须在本地 DISPLAY=:0 GUI 模式运行** — 头条检测 headless/云端浏览器，会返回占位图
- **QR 刷新必须通过关闭弹窗→重新打开** — 弹窗内刷新按钮 JS click/dispatchEvent 均无效（React 事件不响应）
- **零 LLM 中转** — QR → 飞书必须全程由脚本完成，不能经过 vision_analyze
- **$HOME 被 profile 重写** — 终端命令中 ~/.hermes/.env 会指向错误路径，必须用绝对路径 `/home/chenan/.hermes/.env`

## 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| Edge 启动 | `--remote-debugging-port=9222 --remote-allow-origins=* --window-size=1400,900 --window-position=100,50` | 必须加这些参数 |
| 登录按钮 | JS `document.querySelector('a.login-button').click()` | CDP dispatchMouseEvent 无效 |
| QR 提取 | DOM base64 src，选择器 `.web-login-scan-code__content__qrcode-wrapper__qrcode`，srcLen=`2275`，nw=`512` | 直接提取，绕过截图。src 是 `data:image/jpeg;base64,...` |
| QR 刷新 | `Network.clearBrowserCookies` + `Storage.clearDataForOrigin` + `Page.reload(ignoreCache:true)` | 必须清 cookie，ESC+click 不会刷新 QR（浏览器缓存导致旧码） |
| 飞书 App ID | `cli_aa969a7a3f785cce` | |
| 飞书 App Secret | `/home/chenan/.hermes/.env` 中的 `FEISHU_APP_SECRET` | 绝对路径！ |
| 飞书 Chat ID | `oc_f8b7d27c97f45ca5b89fec45760c5728` | 推送目标 |

## 完整流程

### 1. 启动 Edge

```bash
bash scripts/start_edge.sh https://www.toutiao.com/
```

输出 CDP WebSocket URL，格式: `ws://127.0.0.1:9222/devtools/page/<PAGE_ID>`

### 2. 获取二维码并推送飞书（PRIMARY：DOM 提取）

```bash
/tmp/toutiao_venv/bin/python3 scripts/get_qr.py <WS_URL>
```

脚本自动完成：
1. CDP 连接 → ESC 关闭弹窗 → JS `.click()` 点击 `a.login-button`
2. 等待 3 秒让弹窗渲染
3. **DOM 直接提取 QR base64** — 查找 `.web-login-scan-code__content__qrcode-wrapper__qrcode`，提取 src 中的 base64 数据（srcLen≈2275, nw=512）
4. 解码为图片文件
5. 飞书 API 上传图片并发送

### 3. 刷新二维码（新 QR）

如果 QR 过期，重新运行脚本即可。脚本内部会先关闭弹窗（ESC），再重新点击登录按钮，确保拿到新 QR。

### 4. 检查登录状态

```bash
/tmp/toutiao_venv/bin/python3 scripts/check_login.py <WS_URL>
```

检查页面是否已登录（收藏夹链接是否存在）。

## 环境要求

- `DISPLAY=:0`（本地桌面）
- `xdotool`, `imagemagick`, `Pillow` 已安装
- 飞书 API 调用需 `http_proxy=''` + curl `--noproxy *`（防御性措施，避免 sing-box 异常）
- Python 虚拟环境: `/tmp/toutiao_venv/`（含 `websocket-client`, `Pillow`）

## Pitfalls

- **CDP dispatchMouseEvent 无效** — 登录按钮必须用 JS `.click()`，CDP 鼠标事件不触发 React 路由
- **QR 在 DOM 中有两个 img** — `class` 含 `qrcode-wra` (srcLen≈2275, nw=512) 是**真实登录 QR**，用这个；`class="shdf"` (srcLen=5927, nw=123) 是刷新图标，不要用
- **QR 可能在视口外** — 弹窗是全屏模态框 (1360x771)，QR 元素 y 坐标可能 > 视口高度。DOM 提取不依赖视口位置，不受影响
- **$HOME 被 profile 重写** — `~/.hermes/.env` 会展开到错误路径，脚本中必须用 `/home/chenan/.hermes/.env` 绝对路径
- **登录状态残留** — 如果之前已经登录过，Edge Cookie 保留登录态。测试新流程前需先 JS 点击"退出登录"链接
- **QR 始终 1687 bytes** — 说明浏览器在 headless 模式或云端运行，必须切回 DISPLAY=:0 GUI
- **QR 改版** — 如果 `class="shdf"` 选择器失效，需通过 DevTools 重新确认。特征：srcLen 约 5927，naturalWidth 约 123
- **登录按钮改版** — 如果 `a.login-button` 选择器失效，需重新查找。页面上有两个：导航栏和右侧面板
- **截图方案已弃用** — 之前用 `import -window` + Pillow 裁剪 QR 的方案，因 DOM 坐标与窗口表面坐标不匹配，已改为 DOM base64 直接提取
- **QR 过期问题（关键）** — ESC 关弹窗 + JS click 重新打开登录 → **浏览器缓存 QR 数据，拿到的是旧二维码**。必须执行 `Network.clearBrowserCookies` → `Storage.clearDataForOrigin` → `Page.reload({ignoreCache:true})` → JS click 登录，才能拿到全新的 QR。全流程应在 10 秒内完成
