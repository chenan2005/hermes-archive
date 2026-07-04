# ARP 主动探测 — 判断 LAN 设备在线/离线的通用方法

## 问题

Windows 默认防火墙禁 ICMP（ping 不通但机器亮着家常便饭）。
SSH 可以判断但需要 sshd 运行且端口可达。
最底层的判断是**二层链路层**：只要网卡连着交换机，就一定能从路由器查到 ARP。

## 原理

ARP（Address Resolution Protocol）是 IP → MAC 的映射协议。
当路由器想跟一个 IP 通信时，会发 ARP 请求该 IP 对应的 MAC。
- 机器在线 → 回复 ARP → 条目标记 COMPLETE（`0x2`）
- 机器离线 → 无回复 → 条目标记 INCOMPLETE（`0x1`）或消失

## 通用命令

```bash
# 推荐：用路由器上的 isonline 脚本（已处理 ip neigh del 的坑）
ssh openwrt 'isonline <目标IP>'

# 手动检测（跳过 ip neigh del，它会在 ImmortalWrt 上挂死）
ssh openwrt '
  ping -c 1 -W 2 <目标IP> >/dev/null 2>&1
  grep <目标IP> /proc/net/arp
'
```

> ⚠️ **ImmortalWrt 上不要用 `ip neigh del`** —— 该命令会永久挂起，卡死整个 shell。只靠 ping 触发 ARP 刷新即可，`isonline` 脚本已避开此坑。

参数：
- `<路由器IP>` — 目标设备所在网段的网关
- `<接口名>` — `ip link show` 查看，常见 `eth0`/`br-lan`/`wan`
- `<目标IP>` — 要检测的设备 IP

## 输出解读

| 输出特征 | 含义 |
|---------|------|
| `0x2` + 真实 MAC（如 `34:5a:60:b5:8d:13`） | **在线 ✅** |
| `0x1` + MAC=`00:00:00:00:00:00` | **离线 ❌** |
| 无输出 | **离线 ❌**（条目已过期） |

## 为什么先 `ip neigh del`

ARP 有缓存。如果机器之前在线后关机，缓存条目还标记为 `0x2`，被动查 `/proc/net/arp` 会误判为在线。
主动删除 → 强制发新 ARP 请求 → 即时反映真实状态。

**但在 ImmortalWrt 上不能用 `ip neigh del`** —— 实测该命令会永久挂起，卡死整个 SSH 会话。`isonline` 脚本通过混合顺序探测（跳过删除，直接 ping 触发 ARP 刷新）避免了这个问题。

## 注意事项

- 指定的接口名称必须正确，否则 `ip neigh del` 静默失败
- ping 在这里的作用不是测连通性，而是**触发内核发 ARP 请求**
- 适用于 OpenWrt/Linux 路由器；商用路由器（小米/华为等）不一定有 SSH 可用的 `/proc/net/arp`
