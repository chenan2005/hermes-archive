---
name: minipc-wifi-switch
description: Switch minipc WiFi between SSIDs (CMCC-C46N-5G, realme GT 7 FDC6, ChinaNet-pfwQ-5G) and update static route for VLESS proxy node. Used when minipc WiFi needs to change from one network to another for proxy traffic binding.
---

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
