---
name: wol-wake
title: WOL 远程唤醒通用工作流
description: 通过 Wake-on-LAN 远程唤醒局域网内任何设备的标准方法。统一经 ImmortalWrt 的 wol/isonline 脚本操作，含排坑记录和设备索引。
---

# WOL 远程唤醒通用工作流

> 最后更新: 2026-06-28

## 核心流程 (4 步)

```
① ARP 探测确认离线 → ② 发 WOL 魔术包 → ③ 等待 30-60s → ④ ARP 探测确认在线
```

判断 Windows 机器开关机**永远不要用 ping**——Windows 默认禁 ICMP。
标准方法是从路由器做 **ARP 主动探测**（二层链路层，不受防火墙影响）。

**最新方案：统一经 ImmortalWrt 的 `wol` 和 `isonline` 脚本操作。**
两个脚本部署在 `/root/.local/bin/`。

⚠️ **PATH 陷阱**：OpenWrt/ImmortalWrt 的 ash 在非交互 SSH 下（`ssh host 'cmd'`）不加载 `/etc/profile`，`/root/.local/bin/` 不在 PATH 中。**必须用完整路径**调用：

```bash
# ✅ 正确：用完整路径
ssh openwrt '/root/.local/bin/wol <MAC>'              # 37.x 设备（默认 br-lan）
ssh openwrt '/root/.local/bin/wol <MAC> eth1'          # 71.x 设备（指定 eth1）
ssh openwrt '/root/.local/bin/isonline <MAC|IP>'       # 判断在线

# ❌ 错误：短命令名可能导致 "ash: wol: not found"
ssh openwrt 'wol <MAC>'                                # 可能失败

# 完整唤醒流程
ssh openwrt '/root/.local/bin/isonline <MAC>'          # ① 确认离线
ssh openwrt '/root/.local/bin/wol <MAC>'               # ② 发魔术包
sleep 45
ssh openwrt '/root/.local/bin/isonline <MAC>'          # ③ 确认上线
```

ImmortalWrt 接口选择：`eth1`=WAN(71.x), `br-lan`=LAN(37.x)。详见 `/root/.local/bin/wol` 脚本。

---

## 前置条件

WOL 要生效，以下三条必须全部满足：

### 1. 主板 BIOS
- **关 ErP Ready**（最大坑，很多主板默认开启）
- **开 PCIe 设备唤醒**（Resume By PCI-E Device / PCIE Devices Power On）

### 2. Windows 网卡驱动

#### GUI 方式
```
设备管理器 → 网络适配器 → 对应网卡 → 属性 → 电源管理
  ☑ 允许此设备唤醒计算机
  ☑ 只允许幻数据包唤醒计算机

高级 → 唤醒魔包 → [开启]
      → 关机唤醒 → [开启]
```

#### 注册表方式（GUI 设了也不生效时用）
```
HKLM\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002bE10318}\
  找到你的网卡子项（逐个看 DriverDesc）
  PnPCapabilities  = 24  (DWORD)  — D3 唤醒，禁止系统断电
  S5WakeOnLan      = 1   (DWORD)
  EnablePME        = 1   (DWORD)
```
修改后重启一次，然后关机。网口灯应该保持亮着，表示 WOL 待命中。

### 3. 快速启动（如有 WOL 不生效时检查）
```
控制面板 → 电源选项 → 选择电源按钮的功能
  ☐ 启用快速启动
```
按住 Shift 点关机 = 完全关机（跳过快速启动），WOL 有效。

---

## ARP 主动探测（判断在线/离线）

### 推荐：用 isonline 脚本（路由器上已部署）

```bash
# 通过 IP 检查
ssh openwrt 'isonline 192.168.71.41'
# → ONLINE  192.168.71.41  34:5a:60:b5:8d:13  (在线)
# → OFFLINE 192.168.71.41 (no response)         (离线)

# 通过 MAC 检查
ssh openwrt 'isonline 34:5a:60:b5:8d:13'
# → ONLINE  192.168.71.41  34:5a:60:b5:8d:13
```

### 手动检测

```bash
ssh openwrt "
  ping -c 1 -W 2 <目标IP> >/dev/null 2>&1
  grep <目标IP> /proc/net/arp
"
```

> ⚠️ **不要在 ImmortalWrt 上用 `ip neigh del`** —— 该命令会永久挂起，卡死整个 shell。跳过它，只靠 ping 触发 ARP 刷新。`isonline` 脚本已避开此坑。

### 输出解读
- `<目标IP>` — 要检测的设备 IP

### 输出解读

| 输出特征 | 含义 |
|---------|------|
| `0x2` + 真实 MAC（如 `34:5a:60:b5:8d:13`） | **在线 ✅** |
| `0x1` + MAC=`00:00:00:00:00:00` | **离线 ❌** |
| 无输出 | **离线 ❌**（条目已过期） |

> 详细原理见 `references/arp-probe.md`

### 一键检查脚本

- `scripts/check.sh <IP>` — 通用检查脚本

---

## 发送 WOL 魔术包

### 统一方案：经 ImmortalWrt 的 `wol` 脚本

路由器上已部署 `wol` 脚本（`/root/.local/bin/wol`，基于 `etherwake`）：

```bash
# 37.x 设备（默认走 br-lan）
ssh openwrt 'wol e0:d5:5e:d3:d7:4e'

# 71.x 设备（指定 eth1）
ssh openwrt 'wol 34:5a:60:b5:8d:13 eth1'
```

ImmortalWrt 网络接口说明：
- `br-lan` → 37.x 内网（DESKTOP-EC5NQUM、手机、平板）
- `eth1` → 71.x WAN 口（9950x3d、minipc、本机）

### 备选：经同网段 Windows 中继（PowerShell）

注意：在 Windows PowerShell 中，**不要用 UdpClient**；UdpClient 的 Connect + Send 不会设置 SO_BROADCAST，广播包会被静默丢弃。必须用原生 Socket：
ssh <用户>@<中继IP> 'powershell -ExecutionPolicy Bypass -Command "
  $mac = [byte[]]@(<MAC字节数组>);
  $packet = [byte[]]@(0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF) + ($mac * 16);
  $sock = New-Object System.Net.Sockets.Socket([Net.Sockets.AddressFamily]::InterNetwork,
    [Net.Sockets.SocketType]::Dgram, [Net.Sockets.ProtocolType]::Udp);
  $sock.EnableBroadcast = $true;
  $sock.Bind((New-Object Net.IPEndPoint([Net.IPAddress]"<中继IP>", 0)));
  $sock.SendTo($packet, (New-Object Net.IPEndPoint([Net.IPAddress]"255.255.255.255", 9)));
  $sock.Close();
"'
```

### MAC → 字节数组换算

```
34:5a:60:b5:8d:13 → 0x34, 0x5A, 0x60, 0xB5, 0x8D, 0x13
e0:d5:5e:d3:d7:4e → 0xE0, 0xD5, 0x5E, 0xD3, 0xD7, 0x4E
```

---

## 完整标准流程（5 步）

```bash
# Step 1: ARP 探测确认离线
ssh root@<路由器IP> "
  ip neigh del <目标IP> dev <接口名> 2>/dev/null
  ping -c 1 -W 2 <目标IP> >/dev/null 2>&1
  cat /proc/net/arp | grep <目标IP>
"
# 看到 0x1 INCOMPLETE → 继续

# Step 2: 发 WOL 包
# 同子网: sudo etherwake -i wlp1s0 <MAC>
# 跨子网: ssh root@<路由器IP> '/tmp/wol <MAC> <广播地址>'

# Step 3: 等待
sleep 60

# Step 4: ARP 探测确认在线
# 同 Step 1，看到 0x2 + MAC → 在线 ✅

# Step 5: (可选) SSH 确认开机时间
ssh <用户>@<目标IP> "powershell -NoProfile -Command \
  \"(Get-CimInstance Win32_OperatingSystem).LastBootUpTime\""
```

---

## 设备索引

### 9950x3d — Ryzen 9950X3D 工作站

| 参数 | 值 |
|------|-----|
| IP | 192.168.71.41 |
| MAC | `34:5a:60:b5:8d:13` |
| 网段 | 71.x（本机 37.x，跨子网） |
| 验证 | ✅ 2026-06-26 |
| 路由器 | ImmortalWrt 192.168.71.9, 接口 `eth1` |
| 用户 | chen_ |
| 本地快捷 | `~/.local/bin/wake-9950x3d` |

**WOL 命令：**\n```bash\n# 推荐: 经 ImmortalWrt eth1 广播（71.x 网段）\nssh openwrt 'wol 34:5a:60:b5:8d:13 eth1'\n\n# 备选: 经 minipc 中继\nssh minipc 'powershell ...'\n```

**检查脚本：** `scripts/check-9950x3d.sh`

### 9900K — DESKTOP-EC5NQUM

| 参数 | 值 |
|------|-----|
| IP | 192.168.37.200 |
| MAC | `e0:d5:5e:d3:d7:4e` |
| 网段 | 37.x（同子网，本机直发） |
| 验证 | ✅ |
| 路由器 | ImmortalWrt 192.168.37.1, 接口 `br-lan` |
| 用户 | chenan |

**WOL 命令：**\n```bash\n# 经 ImmortalWrt br-lan 广播（37.x 网段）\nssh openwrt 'wol e0:d5:5e:d3:d7:4e'\n```

**检查脚本：** `scripts/check-9900k.sh`

---

## 排坑记录

### 常见错误

| 错误 | 后果 | 教训 |
|------|------|------|
| MAC 地址未知就发 WOL | 包无效 | 先捕获 MAC（从路由 DHCP 租约或 ARP 表） |
| 用 ping 判断 Windows 是否开机 | 误判为关机 | 用 ARP 主动探测 |
| 跨子网发 WOL | 广播包不跨路由器 | 从同子网设备中继 |
| BIOS ErP 没关 | WOL 永远不生效 | BIOS 关 ErP，开 PCIe 唤醒 |
| Windows UdpClient 发广播 | 静默丢弃，机器没反应 | 用原生 Socket + EnableBroadcast |

### 注意事项

- **ErP Ready 是最大坑** — 很多主板默认开启，导致 S5 断电，WOL 无效
- **MAC 变了怎么办** — 换网卡/主板/BIOS 重置后 MAC 可能变，WOL 不生效先查 MAC
- **本机 etherwake 只适用同子网** — 跨网段必须中继
- **WOL 只对正常关机/睡眠有效**，对休眠（hibernate）无效
