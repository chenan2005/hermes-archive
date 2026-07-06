# IPv6 配置与排坑

> 最后更新: 2026-07-06
> 覆盖: OpenWrt 24.10 IPv6 完整配置 / fw4 防火墙 IPv6 修复 / 全设备 IPv6 验证 / 光猫管理页面访问 / 电信 IPv6 行为

## IPv6 拓扑

```
电信 OLT (71.1, fe80::105:7cc9:26ef:316)
    │  RA/DHCPv6: 240e:389:a3a5:3f00::/64
    │
    ├── minipc (71.21) → SLAAC + DHCPv6 ✅
    ├── 9950x3d (71.41) → SLAAC + DHCPv6 ✅
    ├── 本机 (71.24) → DHCPv6 ✅ (需 accept_ra=2)
    │
    └── ImmortalWrt (71.9)
        ├── eth1 (WAN) → SLAAC + DHCPv6 ✅
        └── br-lan (37.1) → 240e:389:a3a5:3f00::1/64 静态，LAN 设备通过 odhcpd 拿地址

**电信行为**:
- 只给单个 /64 前缀，不支持 DHCPv6-PD（无法切更小子网）
- 国际 IPv6 TCP 被封锁（ping 通但 TCP 超时），国内 IPv6 正常
- IPv6 通过 SLAAC (Router Advertisement) 下发，同时有 DHCPv6 地址可用

**当前状态 (2026-07-06)**: ImmortalWrt IPv6 已调通，所有设备正常。

## 71 网段 vs 37 网段：IPv6 DNS 行为完全不同

这是理解家庭网络 IPv6 DNS 的核心架构差异：

```
71 网段（OLT 直连）:             37 网段（ImmortalWrt 后）:
  OLT RA RDNSS ↓                    ImmortalWrt dnsmasq ↓
  电信 IPv6 DNS (240e:58:...)        路由器 IPv6 DNS (240e:389:...)
  → 污染 ❌                          → dnsmasq → OpenClash DNS → 干净 ✅
  → 需 DisabledComponents=0x20       → 无需任何修改
```

| | 71 网段 (9950x3d, minipc, 本机) | 37 网段 (9900K, realme, etc.) |
|---|---|---|
| IPv6 DNS 来源 | OLT RA RDNSS (电信 DNS) | ImmortalWrt dnsmasq |
| IPv6 DNS 地址 | `240e:58:c000:...` | `240e:389:a3a5:3f00::1` |
| DNS 是否被污染 | ❌ 是（电信注入） | ✅ 否（走 OpenClash） |
| 需 DisabledComponents? | ✅ 需要 | ❌ 不需要 |
| IPv4 DNS 途径 | `192.168.71.9`（需 dnsmasq listen_address） | `192.168.37.1`（dnsmasq 默认监听） |

**关键结论**：只有直连 OLT 的 Windows 设备才需要 `DisabledComponents=0x20`。
37 网段设备（9900K、realme 等）的 IPv6 DNS 走路由器 dnsmasq → OpenClash，天然干净。

### Windows DNS 诊断工具差异

`nslookup` 和 `Resolve-DnsName` 行为不同，排查时注意：

| 工具 | 行为 | 超时 |
|------|------|------|
| `nslookup` | 直接查询 DNS 服务器，**绕过 Windows DNS Client** | 2s（硬编码） |
| `Resolve-DnsName` | 走系统 DNS 解析栈（含缓存、重试） | 系统默认 |
| 浏览器/应用 | 走系统 DNS 解析栈 | 系统默认 |

`nslookup` 的 2 秒超时不能反映实际浏览体验。只要 `Resolve-DnsName` 和浏览器正常，`nslookup timeout` 可以忽略。

## 已知问题：LAN 设备 IPv6 WAN 转发

ImmortalWrt 当前 IPv6 默认路由使用 source-specific routing（`from 240e:389:a3a5:3f00::/64`），路由器自身可以出 IPv6，但 LAN 设备（37.x）的 IPv6 包转发到 WAN 时失败（`Network unreachable`）。表现为：

- 路由器 `ping6 -I 240e:389:a3a5:3f00::1 2400:3200::1` → ✅
- LAN 设备（9900K）`ping -6 2400:3200::1` → ❌
- LAN IPv6 通信正常（9900K ↔ 路由器）
- 不影响翻墙（OpenClash TPROXY 走 IPv4）

**待解决**：需要排查 source-specific 路由的行为，或改用 NDP proxy 模式。

## OpenWrt 24.10 ImmortalWrt IPv6 完整配置

### 1. /etc/config/network

```
# wan — 保持静态 IPv4，加 ip6assign
config interface 'wan'
    option device 'eth1'
    option proto 'static'
    option ipaddr '192.168.71.9'
    option netmask '255.255.255.0'
    option gateway '192.168.71.1'
    option ip6assign '64'

# wan6 — DHCPv6 客户端
config interface 'wan6'
    option device '@wan'
    option proto 'dhcpv6'
    option reqaddress 'try'
    option reqprefix 'no'

# lan — 静态 IPv6 给 br-lan
config interface 'lan'
    option device 'br-lan'
    option proto 'static'
    option ipaddr '192.168.37.1'
    option netmask '255.255.255.0'
    option gateway '192.168.37.1'
    option ip6assign '64'
    option ip6ifaceid '::1'
```

### 2. /etc/config/firewall — fw4 IPv6 放行规则

```bash
# DHCPv6 客户端响应
uci add firewall rule
uci set firewall.@rule[-1].name="Allow-DHCPv6"
uci set firewall.@rule[-1].src="wan"
uci set firewall.@rule[-1].proto="udp"
uci set firewall.@rule[-1].src_port="547"
uci set firewall.@rule[-1].dest_port="546"
uci set firewall.@rule[-1].family="ipv6"
uci set firewall.@rule[-1].target="ACCEPT"

# ICMPv6 NDP + essential
uci add firewall rule
uci set firewall.@rule[-1].name="Allow-ICMPv6-Input"
uci set firewall.@rule[-1].src="wan"
uci set firewall.@rule[-1].proto="icmp"
uci set firewall.@rule[-1].family="ipv6"
for t in router-solicitation router-advertisement neighbour-solicitation \
  neighbour-advertisement echo-request echo-reply destination-unreachable \
  packet-too-big time-exceeded bad-header unknown-header-type; do
  uci add_list firewall.@rule[-1].icmp_type="$t"
done
uci set firewall.@rule[-1].target="ACCEPT"
uci commit firewall && fw4 reload
```

### 3. /etc/config/dhcp — odhcpd server 模式

```bash
uci set dhcp.lan.ra='server'
uci set dhcp.lan.dhcpv6='server'
uci set dhcp.lan.ra_slaac='1'
uci set dhcp.wan.ignore='1'
uci commit dhcp
/etc/init.d/odhcpd restart
```

### 4. sysctl — accept_ra

```bash
echo "net.ipv6.conf.eth1.accept_ra=2" >> /etc/sysctl.conf
sysctl -w net.ipv6.conf.eth1.accept_ra=2
```

### 5. 持久化 — hotplug 脚本

```bash
mkdir -p /etc/hotplug.d/dhcpv6

# 97-br-lan-route: 确保 br-lan 路由优先级高于 eth1（关键！）
cat > /etc/hotplug.d/dhcpv6/97-br-lan-route << 'EOF'
#!/bin/sh
[ "$INTERFACE" = "wan6" ] || exit 0
[ "$ACTION" = "ifup" ] || exit 0
sleep 2
# br-lan metric 128 < eth1 metric 256 → 回包优先走 br-lan
ip -6 route replace 240e:389:a3a5:3f00::/64 dev br-lan metric 128 2>/dev/null
EOF
chmod +x /etc/hotplug.d/dhcpv6/97-br-lan-route

# 98-br-lan-ipv6: 添加 br-lan 静态 IPv6 + 开启转发
cat > /etc/hotplug.d/dhcpv6/98-br-lan-ipv6 << 'EOF'
#!/bin/sh
[ "$INTERFACE" = "wan6" ] || exit 0
[ "$ACTION" = "ifup" ] || exit 0
sleep 2
ip -6 addr replace 240e:389:a3a5:3f00::1/64 dev br-lan 2>/dev/null
sysctl -w net.ipv6.conf.all.forwarding=1
EOF
chmod +x /etc/hotplug.d/dhcpv6/98-br-lan-ipv6

# 99-default-route: 添加无源约束的默认路由
cat > /etc/hotplug.d/dhcpv6/99-default-route << 'EOF'
#!/bin/sh
[ "$INTERFACE" = "wan6" ] || exit 0
[ "$ACTION" = "ifup" ] || exit 0
sleep 2
ip -6 route replace default via fe80::105:7cc9:26ef:316 dev eth1 metric 512 2>/dev/null
EOF
chmod +x /etc/hotplug.d/dhcpv6/99-default-route
```

## ⚠️ OpenWrt 24.10 fw4 防火墙：IPv6 被阻断的根因

## ⚠️ LAN 设备 IPv6 外网不通：路由表冲突

**症状**: 路由器自身能 ping6 外网，LAN 设备能 ping6 路由器，但 LAN 设备无法 ping6 外网。

**根因**: 当 WAN (eth1) 和 LAN (br-lan) **共享同一 /64 前缀**（ND Proxy 模式），内核路由表中两条路由：
```
240e:389:a3a5:3f00::/64 dev eth1  metric 256
240e:389:a3a5:3f00::/64 dev br-lan metric 256
```
metric 相同，tiebreak 后 eth1 优先。回包到达路由器时，dst=LAN 设备地址的内核路由到 eth1——但 LAN 设备在 br-lan，导致丢包。

**诊断**:
```bash
# 本应走 br-lan 却走 eth1 → 确认冲突
ip -6 route get 240e:389:a3a5:3f00::200
# 输出: dev eth1 src ...  ← 应该是 dev br-lan！
```

**修复**:
```bash
# 降低 br-lan 的 metric 使其优先
ip -6 route replace 240e:389:a3a5:3f00::/64 dev br-lan metric 128
```

**持久化**: hotplug 脚本 `97-br-lan-route`（在 wan6 ifup 时执行）。

**教训**: NDP proxy 不是根因。不需要 NAT66。跟防火墙无关。纯粹的路由表优先级问题。

**这是 ImmortalWrt IPv6 不通的真正原因，非 Hyper-V 问题。**

### 诊断流程

```bash
# 1. 先排除 Hyper-V：启动同交换机的旧 OpenWrt 22.03 VM
#    如果旧 VM 能拿 IPv6 → 不是 Hyper-V 问题，是防火墙
# 2. 确认 fw4 未生成 IPv6 规则
nft list chain inet fw4 input_wan | grep -E "ipv6|icmpv6|udp.*54[67]"
#    空输出 → IPv6 全被 drop
```

### 为什么 fw4 没有 IPv6 规则

OpenWrt 22.03→24.10 防火墙从 fw3 (iptables) 切换到 fw4 (nftables)。fw4 的 `input_wan` 链规则全部加了 `meta nfproto ipv4` 限制，IPv6 流量无任何放行规则，全部落到 `reject_from_wan`。

具体被阻断：DHCPv6 服务器响应 (UDP 547→546)、ICMPv6 NDP (types 133-136)、所有 IPv6 入站。

### 触发条件

任何 ImmortalWrt 24.10 新部署（或 OpenWrt 22.03→24.10 升级），只要 WAN 侧需要 IPv6，都需要手动添加这两条防火墙规则。

## 光猫管理页面访问

光猫 (HN8145X6N) 管理页面在 `192.168.1.1`，桥接模式下与 71.x PON 网段隔离，本机无法直接访问。

### SSH 隧道方法

ImmortalWrt (71.9) 的 WAN 口直连光猫 LAN 口，可以访问 192.168.1.1：

```bash
# 在本机上建立隧道
ssh -f -N -L 18080:192.168.1.1:80 root@192.168.71.9

# 浏览器打开 http://localhost:18080
```

### 登录凭据

| 用户 | 密码 | 来源 |
|------|------|------|
| useradmin | 7nia7 | 资产清单 |
| telecomadmin | nE7jA%5m | 推测（超级管理员） |

## 调试技巧

### 检查 RA 是否到达

```bash
# 邻居表中带 "router" 标记 = 收到过 RA
ip -6 neigh show dev eth1 | grep router
```

### 触发 Router Solicitation

```bash
# accept_ra 从 0→2 过渡会触发内核发送 RS
sysctl -w net.ipv6.conf.eth1.accept_ra=0
sleep 1
sysctl -w net.ipv6.conf.eth1.accept_ra=2
```

### 检查 IPv6 组播是否通

```bash
ping6 -c 2 ff02::1%eth1    # WAN 侧
ping6 -c 2 ff02::1%br-lan  # LAN 侧
```

### 验证 Hyper-V 是否为根因

```bash
# 如果 LAN 侧组播通但 WAN 侧不通 → Hyper-V 交换机问题
# 如果两侧都不通 → VM 内核/IPv6 栈问题
```

## Windows 客户端 IPv6 DNS 污染问题与修复

### 问题

71 网段 Windows 客户端（9950x3d、minipc）直接从 OLT 获取 IPv6 地址，OLT 通过 RA RDNSS (RFC 6106) 和 DHCPv6 OtherStateful 下发电信 IPv6 DNS 服务器 (`240e:58:c000:...`)。这导致：

- DNS 查询走电信 IPv6 → 被污染（国外域名返回假地址）
- 即使 IPv4 DNS (192.168.71.9) 经 OpenClash 正确，Windows 仍可能优先用 IPv6 DNS

### Windows 移除 IPv6 DNS 的尝试（全部失败或半失败）

| 方法 | 命令 | 结果 |
|------|------|------|
| netsh delete static DNS | `netsh interface ipv6 delete dnsservers "以太网" all` | 只删静态，DHCP/RDNSS 快速恢复 |
| 注册表清 DhcpNameServer | `Set-ItemProperty -Path HKLM:...Interfaces\{GUID} -Name DhcpNameServer -Value ''` | DHCP 续期后恢复 |
| PowerShell 禁用 DHCPv6 | `Set-NetIPInterface -Dhcp Disabled` | 权限问题，`ManagedAddressConfiguration` 仍然 Enable |
| netsh 禁用 managedaddress | `netsh int ipv6 set int 4 managedaddress=disabled` | "参数错误" |
| 禁用 RA-based DNS | `netsh int ipv6 set int 4 rabaseddnsconfig=disable` | 重启网卡后恢复 |
| 路由器设 IPv6 DNS 接管 | 让 dnsmasq 监听 IPv6:53，Windows 设静态 DNS 到路由器 | WAN 侧客户端无法通过路由器 IPv6 DNS 解析（dnsmasq bind 在 br-lan，WAN→LAN 路径不工作） |

OLT RA 的 M/O/RDNSS 标志在网卡重启后总是重新应用，Windows 优先遵从此类下发的 DNS。

### 唯一可靠方案：DisabledComponents=0x20

通过注册表强制 Windows 在 DNS 解析时**优先 IPv4 而非 IPv6**：

```powershell
# 设置 DisabledComponents = 0x20 (prefer IPv4 over IPv6 for DNS)
Set-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Services\Tcpip6\Parameters' `
    -Name 'DisabledComponents' -Value 0x20 -Type DWORD -Force
```

> **Linux 对比**：Linux (systemd-resolved / NetworkManager) **不会**自动接收 RA RDNSS 下发的 IPv6 DNS 服务器。`resolvectl dns` 只显示管理员手动配置或 DHCPv4 下发的 DNS 地址，且全部为 IPv4。因此本机 Linux 无需任何额外配置即可避免 IPv6 DNS 污染——它根本没有 IPv6 DNS 服务器。这是 Windows 独有的问题。

**原理**：不删除...

**效果**：
- DNS → IPv4 → 71.9 → OpenClash → 干净域名解析 ✅
- IPv6 地址（SLAAC）正常获取，国内 v6 直连正常 ✅
- 重启不丢失（注册表持久） ✅
- 网卡重启/RA 续期不破坏 ✅

**bit 值说明**：
| bit | 值 | 效果 |
|-----|----|------|
| 0x10 | 16 | 禁用所有隧道接口 IPv6 |
| 0x20 | 32 | **Prefer IPv4 over IPv6**（DNS 优先 v4） |
| 0x40 | 64 | 禁用所有非隧道接口 IPv6（除 loopback） |
| 0xff | 255 | 完全禁用 IPv6 |

`0x20` 是最小改动：IPv6 功能完整保留，仅 DNS 优先级调整。

### 一键脚本

脚本 `scripts/fix-ipv6-dns.ps1` 自动完成上述修复：

```powershell
# 预览（不修改）
powershell -ExecutionPolicy Bypass -File fix-ipv6-dns.ps1

# 执行
powershell -ExecutionPolicy Bypass -File fix-ipv6-dns.ps1 -Apply
```

脚本会：
1. 检测活跃网卡 → 设 `DisabledComponents=0x20`
2. 确保 IPv4 DNS = `192.168.71.9`
3. 重启 DNS Client 服务
4. 显示修复前后对比

适用于 9950x3d、minipc 等所有 71 网段 Windows 设备。

### 为什么不在路由器侧劫持 DNS

路由器 `dnsmasq` 绑定在 `br-lan` (37.x)，71 网段客户端请求 `240e:389:a3a5:3f00::1:53` 走 WAN 入站路径。响应包的回程路径（br-lan→eth1）在 IPv6 转发中遇到问题导致超时。客户端侧 DNS 优先 IPv4 更简单可靠——DisableComponents=0x20 后，DNS 自动走 `192.168.71.9:53`。

**注意**：如果客户端手动设了 IPv4 DNS = `192.168.71.9`，必须确保 dnsmasq 在该 IP 上监听，否则所有 DNS 超时：

```bash
uci add_list dhcp.@dnsmasq[0].listen_address="192.168.71.9"
uci commit dhcp
/etc/init.d/dnsmasq restart
```

详见 `home-ops/proxy-openclash.md` Pitfall 10k。
