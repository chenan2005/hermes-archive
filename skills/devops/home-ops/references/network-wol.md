## 目录

- [wake-on-lan](#wake-on-lan)
- [wol-wake](#wol-wake)
- [minipc-wifi-switch](#minipc-wifi-switch)

---



# wake-on-lan

# wake-on-lan

# Wake-on-LAN

Wake a powered-off Windows machine by sending a magic packet to its MAC address.

## Checklist: Enable WoL on Target

1. **BIOS**: ErP Ready → Disabled, Wake Event → BIOS
2. **Windows**: `powercfg /h off` (disable hibernation + Fast Startup)
3. **Registry** (for Realtek/Intel NICs):
   - Find NIC subkey under `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002bE10318}\`
   - `PnPCapabilities` = 24 (DWORD) — wake from D3, deny system turn-off
   - `S5WakeOnLan` = 1 (DWORD)
   - `EnablePME` = 1 (DWORD)
4. **Restart Windows**, then shut down. NIC link light must stay ON.

## Finding the MAC Address of an Offline Target

If the target is powered off and you don't know its MAC:

### Check the router's ARP cache
Even after the device goes offline, the router's ARP cache may retain the entry from prior connections.

```bash
# OpenWrt / Linux router
cat /proc/net/arp | grep <target-ip>
# Example output: 192.168.37.200  0x1  0x0  e0:d5:5e:d3:d7:4e  *  br-lan
```

### Check the router's DHCP leases
If the device previously got an IP via DHCP:

```bash
# dnsmasq (OpenWrt / most consumer routers)
cat /tmp/dhcp.leases | grep <target-ip>
```

**TTL hint**: After boot, ping the target. TTL=128 → Windows, TTL=64 → Linux/macOS.

## Sending Magic Packet

### From Windows (same L2 subnet)
```powershell
# MUST use Socket with EnableBroadcast; UdpClient silently drops broadcast
$mac = [byte[]]@(0x34, 0x5A, 0x60, 0xB5, 0x8D, 0x13)
$packet = [byte[]]@(0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF) + ($mac * 16)
$sock = New-Object System.Net.Sockets.Socket(
    [System.Net.Sockets.AddressFamily]::InterNetwork,
    [System.Net.Sockets.SocketType]::Dgram,
    [System.Net.Sockets.ProtocolType]::Udp
)
$sock.EnableBroadcast = $true
$sock.Connect("192.168.71.255", 9)
$sock.Send($packet)
$sock.Close()
```

### From Linux (same subnet)
Install `etherwake` and send the magic packet over the local interface:

```bash
sudo apt install etherwake          # Debian/Ubuntu
sudo etherwake -i <interface> <mac> # e.g. -i wlp1s0 (WiFi) or -i eth0 (wired)
```

Or use `wakeonlan` with the subnet broadcast address:

```bash
sudo apt install wakeonlan
wakeonlan -i <subnet-broadcast> <mac>  # e.g. -i 192.168.37.255
```

### From OpenWrt (or minimal BusyBox systems with no Python/Python/bash)

When the jumpbox is an OpenWrt router or other musl-based system without Python, etherwake, or bash, compile a small static WOL binary on the host (glibc) and SCP it over:

```c
// wol.c — compile with: gcc -static -o wol wol.c; strip wol
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>

int main(int argc, char *argv[]) {
    if (argc < 3) return 1;
    unsigned char mac[6], packet[102];
    int port = argc > 3 ? atoi(argv[3]) : 9, i;
    sscanf(argv[1], "%hhx:%hhx:%hhx:%hhx:%hhx:%hhx",
           &mac[0],&mac[1],&mac[2],&mac[3],&mac[4],&mac[5]);
    memset(packet, 0xFF, 6);
    for (i = 0; i < 16; i++) memcpy(packet+6+i*6, mac, 6);
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    int broadcast = 1;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof(broadcast));
    struct sockaddr_in addr = {.sin_family=AF_INET,.sin_port=htons(port),.sin_addr.s_addr=inet_addr(argv[2])};
    sendto(sock, packet, sizeof(packet), 0, (struct sockaddr*)&addr, sizeof(addr));
    close(sock);
    return 0;
}
```

Transfer and run:
```bash
# Compile on a glibc host (static, works on musl too)
gcc -static -o /tmp/wol /tmp/wol.c && strip /tmp/wol

# Transfer to OpenWrt (use -O for SCP protocol — OpenWrt dropbear lacks sftp-server)
scp -O /tmp/wol root@openwrt:/tmp/

# Send WOL to subnet broadcast (must be sent from the same L2 domain)
ssh root@openwrt '/tmp/wol 34:5a:60:b5:8d:13 192.168.71.255'
```

## Post-WOL Verification

After sending the magic packet, **wait 60+ seconds** for the target to boot — cold boot from WOL takes longer than a warm reboot. Some NICs need two bursts. Be patient: the user explicitly flags impatience (e.g. checking every 2s for 30s) as a mistake. Wait a full 60–90s before concluding the WOL failed.

**⚠️ Windows Firewall blocks ICMP by default.** Ping returning 100% loss does NOT mean the device failed to boot — it may be fully online with SSH available. Always verify via SSH before concluding WOL failed.

Preferred verification order:

1. **SSH port check**: `nc -zv <target-ip> 22` — primary check. If port 22 answers, device is online.
2. **SSH echo**: `ssh -o ConnectTimeout=5 <user>@<target-ip> "hostname"` — confirms SSH service is running and responsive.
3. **Ping** (secondary, Linux-only targets): `ping -c 3 <target-ip>` — reliable only for non-Windows targets.
4. **TTL check from a successful ping** (if ping works): TTL=128 → Windows, TTL=64 → Linux/macOS.

If the target doesn't respond after 90 seconds (no SSH port, no ping), re-send the magic packet.

## Pitfalls

- **UdpClient drops broadcast**: .NET `UdpClient.Connect()` + `Send()` won't set `SO_BROADCAST` on Windows. Always use raw `Socket` with `EnableBroadcast = $true`.
- **Cross-subnet failure**: Magic packet is L2 broadcast — it cannot cross routers. Send from a machine on the same physical subnet.
- **shutdown /s /f may prevent WoL**: Force-close (`/f`) can skip driver S5 sleep transition. Use `shutdown /s /t 5` without `/f` from Windows UI or remote.
- **NIC light off = no WoL**: If the Ethernet port LED is dark when powered off, the NIC has no standby power. Check BIOS and registry.

# wol-wake

# wol-wake

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

# minipc-wifi-switch

# minipc-wifi-switch

# minipc WiFi 切换

> 一键切换 minipc WiFi + OpenClash 代理节点。脚本：`scripts/5g-switch.sh`

## 一键切换（推荐）

```bash
# 切到 realme 5G 热点 + OpenClash minipc-socks
~/.hermes/skills/devops/minipc-wifi-switch/scripts/5g-switch.sh connect

# 断开 WiFi + OpenClash 切回 VMISS-HK
~/.hermes/skills/devops/minipc-wifi-switch/scripts/5g-switch.sh disconnect
```

脚本自动完成：热点检测 → WiFi 切换 → 静态路由更新 → Xray 检查 → OpenClash 节点切换。
热点没开时 connect 会直接报错退出。

---

## 工作原理

minipc 的 WiFi 仅用于代理流量（通过静态路由绑定 VLESS 节点 IP），默认上网走有线 → ImmortalWrt OpenClash。切换 WiFi 时需要同步更新静态路由的下一跳网关。

## 支持的 WiFi

| SSID | 认证 | 密码 | 网关子网 |
|------|------|------|---------|
| `realme GT 7 FDC6` | WPA3 | iehx7624 | 10.192.244.x |
| `CMCC-C46N-5G` | WPA2 | (已保存) | 192.168.1.x |
| `ChinaNet-pfwQ-5G` | WPA2 | (已保存) | 192.168.71.x |

## 切换流程

### 1. 创建配置文件并连接

```powershell
$ssid = 'realme GT 7 FDC6'   # 目标 SSID
$pass = 'iehx7624'            # 密码（仅首次需要，已保存可省略）
$auth = 'WPA3SAE'             # WPA3SAE 或 WPA2PSK

# 删除旧 profile（可选，清理用）
netsh wlan delete profile name="$ssid" 2>$null

# 创建 XML profile
$xml = @"
<?xml version="1.0"?>
<WLANProfile xmlns="http://www.microsoft.com/networking/WLAN/profile/v1">
    <name>$ssid</name>
    <SSIDConfig><SSID><name>$ssid</name></SSID></SSIDConfig>
    <connectionType>ESS</connectionType>
    <connectionMode>auto</connectionMode>
    <MSM>
        <security>
            <authEncryption>
                <authentication>$auth</authentication>
                <encryption>AES</encryption>
                <useOneX>false</useOneX>
            </authEncryption>
            <sharedKey>
                <keyType>passPhrase</keyType>
                <protected>false</protected>
                <keyMaterial>$pass</keyMaterial>
            </sharedKey>
        </security>
    </MSM>
</WLANProfile>
"@

$tmpFile = [System.IO.Path]::GetTempFileName() + '.xml'
[System.IO.File]::WriteAllText($tmpFile, $xml, [System.Text.UTF8Encoding]::new($false))
netsh wlan add profile filename="$tmpFile" interface="WLAN"

# 连接
netsh wlan connect name="$ssid" ssid="$ssid" interface="WLAN"
Start-Sleep -Seconds 8
```

### 2. 更新静态路由

```powershell
$vlessIP = '43.108.41.245'
# 删除旧路由
route delete $vlessIP 2>$null
# 获取新网关
$gw = (Get-NetRoute -InterfaceAlias WLAN -DestinationPrefix '0.0.0.0/0').NextHop
# 添加持久路由（metric 50，低于 WLAN 默认的 5000，高于有线的 ~25）
route -p add $vlessIP mask 255.255.255.255 $gw metric 50
```

### 3. 验证

```powershell
# 检查 WiFi 状态
netsh wlan show interfaces | Select-String 'SSID|State|Radio'

# 检查路由
route print -4 | Select-String '43.108.41'

# 测试 Xray 进程
Get-Process xray -ErrorAction SilentlyContinue | Select Id

# 测试 SOCKS5 端口
Test-NetConnection -ComputerName localhost -Port 10808
```

## 从 Hermes 远程执行

通过 SSH 远程执行 WiFi 切换，使用 PowerShell pipe 方式（避免 SSH 引号问题）：

```bash
# 方法：将 PowerScript 脚本写入临时文件，pipe 到 SSH
cat /path/to/script.ps1 | ssh minipc "powershell -ExecutionPolicy Bypass -Command -"
```

## 网络拓扑

```
minipc:
  有线 (Realtek 2.5GbE, metric ~25)
    → 默认路由 192.168.71.9 (ImmortalWrt) → OpenClash → 日常上网

  WiFi (Killer AX1675x, metric 5000)
    → 仅承载 VLESS 节点流量 (43.108.41.245)
    → 静态路由 metric 50 覆盖 WLAN 默认路由
    → 不会干扰日常上网

  Xray (SYSTEM 计划任务, 开机自启)
    → SOCKS5 0.0.0.0:10808
    → VLESS+Reality → 43.108.41.245:40002
```

## Pitfalls

- **认证类型要匹配**：扫描网络时注意 `身份验证` 字段。realme 热点是 WPA3（`WPA3SAE`），CMCC 是 WPA2（`WPA2PSK`），配错会拒绝连接。
- **SSH 引号问题**：从 Hermes 执行时避免 inline PowerShell，用脚本文件 + pipe 方式。
- **netsh wlan connect 必须指定 interface**：不指定接口可能找不到 profile。
- **静态路由必须用 `-p` 持久化**：否则重启丢失。
- **Xray 运行在 Session 0 (SYSTEM)**：进程存在但无 GUI，属正常行为。
- **WiFi metric 5000 是关键**：确保有线始终是默认路由，WiFi 仅承载代理流量。