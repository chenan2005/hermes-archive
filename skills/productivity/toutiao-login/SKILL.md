---
name: toutiao-login
description: 今日头条扫码登录自动化 — 本地 Edge + CDP 提取二维码 → 飞书直发。覆盖登录按钮点击、QR 刷新（关闭弹窗→重新打开）、截图裁剪、飞书推送全流程。触发词：头条登录、头条二维码、扫码登录、toutiao
---

# 今日头条扫码登录

本地 Edge 桌面浏览器 + CDP 自动化提取二维码，秒级直推飞书，用户扫码完成登录。

## 核心约束

- **必须在本地 DISPLAY=:0 GUI 模式运行** — 头条检测 headless/云端浏览器，会返回占位图
- **零 LLM 中转** — QR → 飞书必须全程由脚本完成，不能经过 vision_analyze
- **$HOME 被 profile 重写** — 终端命令中 ~/.hermes/.env 会指向错误路径，必须用绝对路径 `/home/chenan/.hermes/.env`

## 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| Edge 启动 | `--remote-debugging-port=9222 --remote-allow-origins=*` | 必须加 `--remote-allow-origins=*` 否则 CDP 被拒 |
| 登录按钮 | JS `document.querySelector('a.login-button').click()` | CDP dispatchMouseEvent 不触发 React |
| QR 提取 | DOM base64 src，选择器 `.web-login-scan-code__content__qrcode-wrapper__qrcode` | src 是 `data:image/jpeg;base64,...`，直接提取解码 |
| QR 刷新 | 脚本内置：清 cookies → reload → JS click | 浏览器会缓存 QR 数据，必须清缓存才能拿新码 |
| 飞书 App ID | `cli_aa969a7a3f785cce` | |
| 飞书 App Secret | `/home/chenan/.hermes/.env` 中的 `FEISHU_APP_SECRET` | 绝对路径！ |
| 飞书 Chat ID | `oc_f8b7d27c97f45ca5b89fec45760c5728` | 推送目标 |

## 完整流程

### 1. 启动 Edge

```bash
bash scripts/start_edge.sh https://www.toutiao.com/
```

输出 CDP WebSocket URL，格式: `ws://127.0.0.1:9222/devtools/page/<PAGE_ID>`

### 2. 获取二维码并推送飞书

```bash
/tmp/toutiao_venv/bin/python3 scripts/get_qr.py <WS_URL>
```

脚本自动完成（~10 秒）：
1. CDP 连接 → ESC 关闭弹窗
2. **清 cookies + reload** — 必须做，否则浏览器缓存旧 QR
3. JS `.click()` 打开登录弹窗
4. 等待 2 秒让 QR 渲染
5. DOM 直接提取 QR base64（`img.src.split(",")[1]`）→ 解码为 PNG
6. 验证 QR 特征（暗像素 20-60%，尺寸 >= 200x200）
7. 飞书 API 上传图片并发送

### 3. 检查登录状态

```bash
/tmp/toutiao_venv/bin/python3 scripts/check_login.py <WS_URL>
```

检查页面是否已登录（找"退出登录"链接或用户头像）。

## 环境要求

- `DISPLAY=:0`（本地桌面）
- `Pillow` 已安装
- 飞书 API 调用需 `http_proxy=''` + curl `--noproxy *`（防御性措施）
- Python 虚拟环境: `/tmp/toutiao_venv/`（含 `websocket-client`, `Pillow`）

## Pitfalls

### 核心坑（必须遵守）

- **CDP dispatchMouseEvent 无效** — 登录按钮必须用 JS `.click()`，CDP 鼠标事件不触发 React 路由
- **QR 过期（最重要）** — ESC 关弹窗 + JS click 重新打开 → 浏览器缓存 QR 数据，拿到的是旧二维码。必须：`Network.clearBrowserCookies` → `Storage.clearDataForOrigin` → `Page.reload({ignoreCache:true})` → JS click 登录
- **$HOME 被 profile 重写** — `~/.hermes/.env` 会展开到 `~/.hermes/profiles/local-qwen/home/.hermes/.env`（不存在），脚本中必须用 `/home/chenan/.hermes/.env` 绝对路径

### QR 提取相关

- **QR img 选择器** — `.web-login-scan-code__content__qrcode-wrapper__qrcode`，认准 `qrcode-wrapper__qrcode` 这个 class。DOM 里还有 `class="shdf"` 的 img 是刷新图标，不要用错
- **QR 验证** — 解码后检查：暗像素 20-60%，尺寸 >= 200x200，src 以 `data:` 开头
- **截图方案已弃用** — `import -window` + Pillow 裁剪不可靠（DOM 坐标与窗口表面坐标不匹配）；CDP `Page.captureScreenshot` 太慢/超时。唯一可靠方案：DOM `img.src` base64 直接提取
- **CDP 坐标系统** — `getBoundingClientRect()` 返回的是页面视口坐标，与 `import -window` 截取的窗口表面坐标（含 titlebar）不一致，不要混用

### 页面改版应对

- **登录按钮改版** — 如果 `a.login-button` 选择器失效，需重新查找。页面上有两个登录入口：导航栏和右侧面板
- **QR 选择器改版** — 如果 `qrcode-wrapper__qrcode` 选择器失效，通过 DevTools 重新确认。关键特征：img src 是 data URI（base64），解码后是 512x512 的 QR 码
- **登录状态残留** — 如果之前已经登录过，Edge Cookie 保留登录态。测试新流程前需清 cookies 或手动退出

### 其他

- **tmux 无 DISPLAY** — tmux 启动时没有 DISPLAY 环境变量，需 `tmux set-environment -g DISPLAY :0`
- **xhost 权限** — 需要 `xhost +local:` 允许本地程序访问 X11
- **Edge 窗口查找** — `xdotool search --name "今日头条"` 找窗口句柄，窗口名可能因语言/版本变化