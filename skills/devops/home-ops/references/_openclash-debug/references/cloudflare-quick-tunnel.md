# Seoul-Cloudflare Node: Quick Tunnel (Auto-Heal)

## 当前方案（2026-06-21 更新）

Seoul VPS 到国内直连带宽仅 0.75Mbps，**必须走 Cloudflare 快速隧道加速**。隧道 URL 每次 cloudflared 重启会变，由 OpenWrt 上的自愈脚本自动检测并修复。

### 架构

```
Client → OpenClash → Seoul-Cloudflare 节点 → seoul.bernarty.xyz
                                               ↓
                                        Cloudflare Edge
                                               ↓ (tunnel)
                                        cloudflared (Seoul)
                                               ↓ (localhost:80)
                                        xray VMess+WS (无TLS)
```

### 节点配置
- 服务器: `<动态URL>.trycloudflare.com`
- 端口: 443, 协议: VMess+WS+TLS
- UUID: ac6aa939-156c-452f-a7da-4ddd79b7d5c9
- WS Path: /ws-seoul
- TLS SNI: `<动态URL>.trycloudflare.com`
- 无需 skip-cert-verify（Cloudflare 边缘有合法证书）

### Seoul VPS 配置
- xray 监听 80 端口（VMess+WS，无 TLS）
- cloudflared 隧道：`cloudflared tunnel --url http://127.0.0.1:80`
- 日志输出到 `/var/log/cloudflared.log`

### 自愈脚本
- 路径: `/usr/bin/seoul-tunnel-watch`
- 频率: 每 30 分钟（crontab）
- 动作: 检测不通 → SSH到Seoul取新URL → 更新配置 → 重启核心
- 日志: `/var/log/seoul-tunnel.log`

### 手动查当前隧道 URL
```bash
ssh alibaba "sudo cat /var/log/cloudflared.log | grep trycloudflare | tail -1"
```

### 为什么不用固定 DNS 直连
试过迁移到 `seoul.bernarty.xyz` 直连，但直连带宽仅 0.75Mbps，Cloudflare 隧道能提供 15-25Mbps 的加速效果。DNS 直连方案回退备用。

### 命名隧道（Named Tunnel）不可行的原因
- bernarty.xyz 的 NS 在 DNSPod（腾讯云），迁到 Cloudflare 会影响其他域名管理
- 子域名委派 Cloudflare 免费版不支持只接子域名
- 所以保留快速隧道 + 自动修复
