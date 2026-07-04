# Proxy 带宽测试方法论（Windows）

## 核心陷阱

**`speedtest.exe` (Ookla CLI) 不支持 SOCKS5 代理。**

即使设置环境变量 `HTTP_PROXY=socks5://127.0.0.1:10880`，speedtest CLI 也不处理这个变量。所有通过 speedtest.exe 跑出来的数据，如果没做专用的代理转发，实际上走的是系统默认路由（直连），**不能反映代理通路带宽**。

## 正确的测试方法

### 方法一：curl -x socks5:// （最简单）

```powershell
# 走代理测国内 CDN 带宽（微信安装包，腾讯 CDN）
curl -s --max-time 60 -x socks5://127.0.0.1:10880 -L -o nul `
  -w "Speed: %{speed_download} B/s (%{size_download} bytes in %{time_total}s)" `
  "https://dldir1.qq.com/weixin/Windows/WeChatSetup.exe"

# 走代理测国际带宽（OVH 欧洲）
curl -s --max-time 30 -x socks5://127.0.0.1:10880 -o nul `
  -w "Speed: %{speed_download} B/s (%{size_download} bytes in %{time_total}s)" `
  "https://proof.ovh.net/files/100Mb.dat"

# 走代理测 Cloudflare 带宽
curl -s --max-time 60 -x socks5://127.0.0.1:10880 -o nul `
  -w "Speed: %{speed_download} B/s (%{size_download} bytes in %{time_total}s)" `
  "https://speed.cloudflare.com/__down?bytes=52428800"
```

### 方法二：Python sb-test.py（推荐，自动化）

脚本位置：`scripts/sb-test.py`（本 skill 目录下）

```powershell
cd <sing-box配置目录>
python sb-test.py              # 测当前节点
python sb-test.py --all        # 测全部节点 + 直连
python sb-test.py <节点名>     # 测指定节点
```

原理：读取 config.json → 提取目标节点 → 生成瞬态最小配置 → 启动临时 sing-box（`auto_detect_interface: true`）→ 10 次 SOCKS5 延迟采样 + 统计去极值均值/抖动 → Cloudflare 50MB 带宽 → 自动清理。

### 方法三：直接通过主 sing-box 测试

如果不切换节点，保持主 sing-box（10880）不变，直接：

```powershell
curl -x socks5://127.0.0.1:10880 ...（同上）
```

## 网络拓扑注意

- 默认路由走有线（WLAN metric 1000 > Ethernet metric 40）
- 服务器连接如 43.108.41.245（VLESS 节点）通过静态路由走 WiFi：
  ```
  route add -p 43.108.41.245 mask 255.255.255.255 <WiFi网关> metric 50
  ```
- 测速时确保这条静态路由存在，否则代理节点连接走有线 → 达不到测试目的

## 常见问题

| 现象 | 原因 | 解决 |
|------|------|------|
| speedtest 显示 900+ Mbps | 实际走有线直连（家宽），非代理 | 用 curl -x socks5:// 重测 |
| ISP 显示 "Alibaba"/"Overland" 不一致 | 不同测试方法走了不同路径 | 确认用 socks5 代理 |
| 代理下载 OVH 很慢（1-5 Mbps） | 代理节点→欧洲带宽有限，正常 | 用国内 CDN 文件测国内带宽 |
| 临时 sing-box 启动失败 | 端口 10882 被占用（TIME_WAIT） | 等几秒重新，或 taskkill /F /IM sing-box.exe |
