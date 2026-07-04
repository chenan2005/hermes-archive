# 本机 sing-box 配置快照

## 位置
- 配置文件: `~/.config/sing-box/config.json`
- rule_set: `~/.config/sing-box/ruleset/geoip-cn.srs`, `geosite-cn.srs`
- systemd: `~/.config/systemd/user/sing-box.service`
- 切节点工具: `~/.local/bin/sing-box-switch`

## 节点
| 标签 | 协议 | 服务器 | 端口 |
|------|------|--------|:----:|
| VMISS-HK | VMess+WS+TLS | vmiss.bernarty.xyz | 443 |
| 233boy-KVM | VMess+WS+TLS | kvm.bernarty.xyz | 30717 |
| Alibaba-Seoul-VLESS | VLESS+Reality | 43.108.41.245 | 40002 |

## DNS 策略
- 阿里云 223.5.5.5（`detour: "direct"`），无境外 DNS 服务器
- 无 DNS 死锁（AliDNS 从国内网络能正确解析国内外域名）

## 分流
- geoip-cn (7456 CIDR) + geosite-cn (6009 domains) → direct
- 其余 → VMISS-HK（默认）
- rule_set 为本地 `.srs` 文件，零外部依赖

## bandwidth test notes
- 5G 热点 + sing-box → VLESS → Speedtest (Shanghai Unicom): 300 Mbps
- 5G 热点 + sing-box → VLESS → OVH (France 200MB): 42 Mbps
- 家宽直连 → VLESS: 0.43 Mbps（电信国际出口瓶颈，与 sing-box 无关）
- 测速用公共源（OVH, Ookla speedtest），永远不要自建 VPS HTTP server 测速
- fast.com 用不了（JS 渲染，curl 无法执行），替代方案：Ookla speedtest CLI + `ALL_PROXY=socks5://127.0.0.1:10880`
