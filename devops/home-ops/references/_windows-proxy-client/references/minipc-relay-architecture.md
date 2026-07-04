# minipc 代理中继架构（双通道设计）

## 架构总览

```text
                    minipc (192.168.71.21)
┌──────────────────────────────────────────────────────┐
│                                                      │
│  ┌─────────────────┐    ┌─────────────────────────┐  │
│  │ 浏览器/应用       │    │ sing-box (SOCKS5:8897)    │  │
│  │ (直连上网)       │    │ bind_interface: "WLAN"   │  │
│  │ 网关:71.9(OpenCl)│    │ default: Alibaba-Seoul  │  │
│  └────────┬────────┘    └───────────┬─────────────┘  │
│           │                         │                │
│           │ 有线 (metric 74)        │ WiFi (metric 5000)
│           ▼                         ▼                │
│     Realtek 2.5GbE ←→ 71.9     Killer AX1675         │
│     (只走OpenClash)            (只走5G热点)            │
└────────────────┬──────────────────────┬──────────────┘
                 │                      │
                 ▼                      ▼
           OpenClash TPROXY        手机5G热点网关
           (ImmortalWrt 71.9)      (10.192.244.122)
                 │                      │
           ┌─────┴─────┐               │
           │ 国内 → DIRECT│              │
           │ 国外 → PROXY│              │
           │  (走VMISS-  │              │
           │   HK等节点) │              │
           └───────────┘               │
                                       ▼
                               Alibaba-Seoul (43.108.41.245)
                               通过 sing-box → WiFi → 5G → 互联网
```

## 核心约束

| 规则 | 说明 |
|------|------|
| **有线是默认** | minipc 所有非代理流量走有线（Realtek 2.5GbE, 网关71.9） |
| **WiFi 只做代理中继** | 5G 热点仅用于 sing-box 的 SOCKS5 出站，不走任何浏览器/应用流量 |
| **WiFi 跃点数 5000** | 确保 Windows 默认路由不选 WiFi，WiFi 断连不影响有线直连 |
| **sing-box 绑定 WLAN** | `bind_interface: "WLAN"` 保证代理流量走 5G 热点网关 |
| **热点不可用=代理不可用** | WLAN 断连后 sing-box 无法启动，minipc-5g 节点失效，有线直连不受影响 |

## OpenClash 节点切换逻辑

- **minipc-5g 节点**（SOCKS5 → minipc:8897）→ 走 sing-box → WiFi → 5G → Alibaba-Seoul → 快但依赖热点
- **其他节点**（VMISS-HK, KVM, Cloudflare 等）→ 走家里宽带直连 → 热点不开时用
- PROXY 组默认不要选 minipc-5g（否则热点断连时翻墙全挂，但国内DIRECT不受影响）

## 关键配置

### 路由表（WiFi 连上时）

```cmd
route print -4 0.0.0.0
# 0.0.0.0 0.0.0.0 192.168.71.9  ... metric 74     ← 有线，默认上网
# 0.0.0.0 0.0.0.0 10.192.244.122 ... metric 5000   ← WiFi，不抢默认

# 静态路由（让 sing-box 的代理出站走 WiFi）：
route add 43.108.41.245 mask 255.255.255.255 10.192.244.122 metric 50
```

### sing-box config.json

```json
{
  "log": { ... },
  "bind_interface": "WLAN",
  "inbounds": [
    { "type": "socks", "tag": "socks-in", "listen": "0.0.0.0", "listen_port": 8897 }
  ],
  "outbounds": [
    {
      "type": "selector",
      "tag": "select",
      "outbounds": ["Alibaba-Seoul-VLESS-Reality", "VMISS-HK", ...],
      "default": "Alibaba-Seoul-VLESS-Reality"
    },
    ...
  ],
  "route": {
    "rules": [],
    "final": "select"
  }
}
```

> ⚠️ 不要加 `auto_detect_interface: true`——它会覆盖 `bind_interface`，导致 sing-box 直接走有线。

### OpenClash custom_rules.list（防 double-proxy 循环）

```yaml
- IP-CIDR,43.108.41.245/32,DIRECT     # Alibaba-Seoul 走直连，不被TPROXY二次代理
- IP-CIDR,38.47.108.89/32,DIRECT
- DOMAIN,vmiss.bernarty.xyz,DIRECT
- DOMAIN,kvm.bernarty.xyz,DIRECT
- DOMAIN,dressed-circles-smithsonian-jewellery.trycloudflare.com,DIRECT
```

## 故障场景

| 场景 | 表现 | 处理 |
|------|------|------|
| 5G 热点断了 | minipc-5g 节点超时，有线直连正常 | 切 PROXY 组到 VMISS-HK 等直连节点 |
| sing-box 崩了 | minipc-5g 节点即时失败 | 同上 |
| WLAN 重连 | sing-box 重新 bind 到 WLAN | 重启 sing-box，切回 minipc-5g |
| OpenClash mihomo 挂了 | 所有非国内网站超时 | 重启 OpenClash，TPROXY 规则重新加载 |

## 设计原则

WiFi 接口跃点数（5000）是适配器级别（per-adapter）的，不是 per-SSID 的。连任何 WiFi 热点都用这个值，不跟热点名称绑定。详情见 `network-pitfalls` skill 的 Windows 接口跃点数章节。
