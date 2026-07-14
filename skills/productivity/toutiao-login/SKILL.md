---
name: toutiao-login
description: 今日头条扫码登录自动化 — 本地 Edge + CDP 提取二维码 → 飞书直发。覆盖登录按钮点击、QR 刷新（关闭弹窗→重新打开）、截图裁剪、飞书推送全流程。触发词：头条登录、头条二维码、扫码登录、toutiao
---

# 今日头条扫码登录

本地 Edge 桌面浏览器 + CDP 自动化提取二维码，秒级直推飞书，用户扫码完成登录。

## 核心约束

- **必须在本地 DISPLAY=:0 GUI 模式运行** — 头条检测 headless/云端浏览器，会返回占位图
- **QR 刷新必须通过关闭弹窗→重新打开** — JS .click()、dispatchEvent、CDP 鼠标点击均无效（React 事件不响应）
- **零 LLM 中转** — QR 截图 → 飞书必须全程由脚本完成，不能经过 vision_analyze

## 关键参数

| 参数 | 值 | 说明 |
|------|-----|------|
| Edge 启动 | `--remote-debugging-port=9222 --remote-allow-origins=* --window-size=1400,900 --window-position=100,50` | 必须加这些参数 |
| 登录按钮页面坐标 | `(1131, 345)` | CDP dispatchMouseEvent 用页面坐标 |
| 窗口尺寸 | `1400x900` | titlebar ~129px |
| QR 裁剪区域 | `(760, 370, 250x250)` | import 窗口截图后裁剪 |
| 飞书 App ID | `cli_aa969a7a3f785cce` | 从 ~/.hermes/.env 读取 |
| 飞书 App Secret | `~/.hermes/.env` 中的 `FEISHU_APP_SECRET` | 从 env 读取 |
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

脚本自动完成：
1. CDP 连接 → 点登录按钮 `(1131, 345)`
2. 等待 3 秒让弹窗渲染
3. `xdotool` + `import` 截取 Edge 窗口
4. Pillow 裁剪 QR 区域 `(760, 370, 250x250)`
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
- 系统代理 `127.0.0.1:10881` 存在时，飞书 API 调用必须 `http_proxy=''`
- Python 虚拟环境: `/tmp/toutiao_venv/`（含 `websocket-client`, `Pillow`）

## Pitfalls

- **QR 始终 1687 bytes 占位图** — 说明浏览器在 headless 模式或云端运行，必须切回 DISPLAY=:0 GUI
- **刷新按钮点击无效** — React 事件监听不响应 CDP/JS click，必须 ESC 关闭 + 重新打开
- **CDP 截图超时** — `Page.captureScreenshot` 在 1000+px 页面会很慢（8s 超时），用 `import -window` 替代
- **import 坐标偏移** — `import -window` 捕获包含 titlebar 的窗口像素，titlebar 高度约 129px
- **代理问题** — sing-box 有 geosite 自动分流，飞书域名（feishu.cn）和头条域名（toutiao.com）均走直连。Edge 启动不需要 `--proxy-server=`。飞书 API 脚本中仍保留 `http_proxy=''` + curl `--noproxy *` 作为防御性措施，避免 sing-box 异常时的连锁故障。
