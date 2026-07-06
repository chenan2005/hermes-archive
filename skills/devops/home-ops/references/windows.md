## 目录

- [# windows-proxy-client](##-windows-proxy-client)
- [# windows-local-llm](##-windows-local-llm)
- [# winrm-ssh-recovery](##-winrm-ssh-recovery)

---



# windows-proxy-client

# Windows Proxy Client Deployment

## 适用场景
- 想用纯 CLI 代理客户端以便远程管理（SSH 改配置、查日志、重启）
- 替换 Clash 系 GUI（Clash Verge / Clash Meta）为 sing-box
- Windows 机器通过手机热点（WLAN）翻墙，日常上网走有线

---

## 1. 下载 sing-box

从 GitHub Releases 下载最新版 Windows amd64：

```powershell
$url = "https://github.com/SagerNet/sing-box/releases/download/v1.13.14/sing-box-1.13.14-windows-amd64.zip"
$dir = "C:\ProgramData\sing-box"
New-Item -ItemType Directory -Path $dir -Force | Out-Null
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
Invoke-WebRequest -Uri $url -OutFile "$dir\sing-box.zip" -UseBasicParsing
Expand-Archive -Path "$dir\sing-box.zip" -DestinationPath "$dir\tmp" -Force
Move-Item "$dir\tmp\sing-box-*-windows-amd64\sing-box.exe" "$dir\sing-box.exe" -Force
Remove-Item "$dir\tmp" -Recurse -Force
Remove-Item "$dir\sing-box.zip" -Force
```

也可通过 SSH 远程执行。将上述命令写入 .bat 后用 `ssh minipc 'C:\path\to\deploy.bat'` 执行。

---

## 2. 配置转译（Clash YAML → sing-box JSON）

### 节点映射

| Clash 字段 | sing-box 字段 | 说明 |
|---|---|---|
| `type: vless` | `"type": "vless"` | 直接映射 |
| `type: vmess` | `"type": "vmess"` | 直接映射 |
| `server: xxx` | `"server": "xxx"` | 同 |
| `port: xxx` | `"server_port": xxx` | 不同命名 |
| `uuid: xxx` | `"uuid": "xxx"` | 同 |
| `tls: true` | `"tls": {"enabled": true}` | 嵌套结构 |
| `servername: x` | `"tls": {"server_name": "x"}` | 嵌套在 tls 内 |
| `reality-opts` | `"tls": {"reality": {}}}` | 嵌套在 tls.reality 内 |
| `ws-opts.path` | `"transport": {"type": "ws", "path": "..."}` | 不同结构 |
| `client-fingerprint: chrome` | `"tls": {"utls": {"enabled": true, "fingerprint": "chrome"}}` | 需要 utls 包裹 |
| `interface-name: WLAN` | ❌ **不存在** — sing-box 不支持 `bind_interface` | 详见章节 6a（静态路由方案） |

### VLESS + Reality 示例

```json
{
  "type": "vless",
  "tag": "node-name",
  "server": "43.108.41.245",
  "server_port": 40002,
  "uuid": "...",
  "flow": "",
  "tls": {
    "enabled": true,
    "server_name": "www.bing.com",
    "utls": {
      "enabled": true,
      "fingerprint": "chrome"
    },
    "reality": {
      "enabled": true,
      "public_key": "...",
      "short_id": "a1b2c3d4"
    }
  }
}
```

### VMess + WebSocket 示例

```json
{
  "type": "vmess",
  "tag": "VMISS-HK",
  "server": "vmiss.example.com",
  "server_port": 443,
  "uuid": "...",
  "security": "auto",
  "tls": {
    "enabled": true,
    "server_name": "vmiss.example.com",
    "utls": {
      "enabled": true,
      "fingerprint": "chrome"
    }
  },
  "transport": {
    "type": "ws",
    "path": "/ws-path",
    "headers": {
      "Host": "vmiss.example.com"
    }
  }
}
```

---

## 3. ⚠️ sing-box 版本兼容性（v1.13.x）

| 问题 | 症状 | 修复 |
|---|---|---|
| `sniff` 被移除 | `inbounds[0]: legacy inbound fields...` | 从 inbound 删除 `"sniff": true`，改用 route rules 或直接去掉 |
| `dns` outbound 被移除 | `outbounds[N]: dns outbound is deprecated...` | 删除 `{"type": "dns", "tag": "dns-out"}` 及相关 route rule |
| `cache_file` 迁移 | `cache_file and related fields in Clash API is deprecated...` | 从 `clash_api` 移除 `cache_file`，改为 `experimental.cache_file.enabled: true`。`store_selected` 可保留在 `clash_api` 中 |
| `store_selected` 不在 `cache_file` 中 | `json: unknown field "store_selected"` | `store_selected` 只在 `clash_api` 下有效，不在 `experimental.cache_file` 中 |
| **DNS 旧格式** (1.14 移除) | `legacy DNS servers is deprecated... will be removed in 1.14.0` | 见下方「DNS 格式迁移」|

### DNS 格式迁移（1.12+）

**旧格式（依赖 `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true`）：**

```json
{
  "tag": "dns",
  "address": "223.5.5.5",
  "detour": "direct",
  "strategy": "prefer_ipv4"
}
```

**新格式（1.12+，推荐）：**

```json
{
  "tag": "dns",
  "type": "udp",
  "server": "223.5.5.5"
}
```

变更要点：
- `address` → `type` + `server`（UDP 需显式声明 `"type": "udp"`）
- `detour` 已移除 — DNS 查询走系统网络栈，不再需要指定出站
- `independent_cache` 已移除（1.14 会删掉此字段）
- 去掉 `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS` 环境变量
- `strategy` 从服务器级移到 DNS 顶级或 rule 级

验证：`sing-box check -c config.json` 返回空输出 + 零退出码即无 deprecation 警告。

---

## 4. 完整配置骨架

```json
{
  "log": { "level": "info", "output": "sing-box.log", "timestamp": true },
  "inbounds": [
    { "type": "mixed", "tag": "mixed-in", "listen": "0.0.0.0", "listen_port": 7890 },
    { "type": "socks", "tag": "socks-in", "listen": "0.0.0.0", "listen_port": 7897 }
  ],
  "outbounds": [
    { "type": "selector", "tag": "select", "outbounds": ["node1", "node2"], "default": "node1" },
    // ... proxy nodes (no bind_interface — use Windows static routes instead, see §6a)
    { "type": "direct", "tag": "direct" },
    { "type": "block", "tag": "block" }
  ],
  "route": {
    "rules": [],
    "final": "select"
  }
}
```

---

## 4.5. 复制 Linux 配置到 Windows（路径转译）

从本机（Linux）复制 sing-box 配置到 Windows 机器时，需要修复绝对路径：

```bash
# Linux 上的路径：
#   /home/chenan/.config/sing-box/ruleset/geoip-cn.srs
#   /home/chenan/.local/share/sing-box/cache.db
#
# 需要转为 Windows 路径：
#   C:/Users/chen_/sing-box/ruleset/geoip-cn.srs
#   C:/Users/chen_/AppData/Local/sing-box/cache.db

# 用 sed 批量替换
sed 's|/home/chenan/|C:/Users/chen_/|g;
     s|\.config/sing-box/|sing-box/|g;
     s|\.local/share/sing-box/|AppData/Local/sing-box/|g' \
  linux-config.json > windows-config.json

# 验证
sing-box check -c windows-config.json
# 路径不存在时 sing-box 会报错：open C:\...\file.srs: The system cannot find the path specified
# 确认路径后创建目录，SCP 对应文件到正确位置
```

**验证配置包含本地 rule_set 文件**：检查 `route.rule_set[].path` 指向的文件存在。Windows 版 sing-box 不自动下载 rule_set，必须连同 `.srs` 文件一起复制过去。

---

## 5. 启动/停止

### 本地交互（bat 脚本）

#### start-singbox.bat
```batch
@echo off
cd /d "C:\ProgramData\sing-box"
taskkill /F /IM sing-box.exe 2>nul
timeout /t 1 >nul
start /B /MIN "" "C:\ProgramData\sing-box\sing-box.exe" run -c config.json
timeout /t 3 >nul
curl -s --connect-timeout 5 -x socks5://127.0.0.1:7897 -o nul -w "%%{http_code}\n" https://www.google.com
pause
```

#### stop-singbox.bat
```batch
@echo off
taskkill /F /IM sing-box.exe 2>nul
echo sing-box stopped
pause
```

### ⚠️ 远程启动（通过 SSH） — `start /B` 不可用

`start /B` 在 SSH 会话中不工作（需要 console/session）。**必须用 PowerShell `Start-Process -WindowStyle Hidden`**：

```powershell
Start-Process -FilePath "C:\ProgramData\sing-box\sing-box.exe" -ArgumentList "run","-c","C:\ProgramData\sing-box\config.json" -WindowStyle Hidden
```

#### 完整工作流（从 Linux 本机 SSH）：

```bash
# 1. 传输二进制 + 配置
scp sing-box.exe 9950x3d:'C:/Users/chen_/sing-box/'
scp config.json  9950x3d:'C:/Users/chen_/sing-box/'

# 2. 启动（通过 PowerShell）
ssh 9950x3d powershell -Command 'Start-Process -FilePath "C:\Users\chen_\sing-box\sing-box.exe" -ArgumentList "run","-c","C:\Users\chen_\sing-box\config.json" -WindowStyle Hidden'

# 3. 等待几秒，验证
sleep 3
ssh 9950x3d powershell -Command 'Get-Process sing-box -ErrorAction SilentlyContinue | Format-Table Id,ProcessName,StartTime -AutoSize'
ssh 9950x3d curl -s --max-time 15 -x socks5://127.0.0.1:10880 -o nul -w '"%{http_code}\n"' https://www.google.com

# 4. 停止
ssh 9950x3d taskkill /F /IM sing-box.exe
```

### PowerShell 脚本通过 SSH 执行（解决嵌套引号问题）

直接传 PowerShell 代码时会遇到 bash → cmd → powershell 三层嵌套引号爆炸。可靠方式：

**方式 A：SSH 中执行 ps1 脚本文件**
```bash
# SCP 脚本过去，用 -File 执行（注意引号包裹路径）
ssh 9950x3d powershell -ExecutionPolicy Bypass -File '"C:\Users\chen_\sing-box\test.ps1"'
# 外层单引号防 bash 展开，内层双引号保护反斜杠不丢失
```

**方式 B：用 `-Command` 传简单命令（无 $ 符号变量）**
```bash
ssh 9950x3d powershell -Command "Get-Process sing-box"
```

**方式 C：传含 $ 变量的命令 — 用单引号 + $ 转义**
```bash
ssh 9950x3d powershell -Command "Get-Process sing-box -ErrorAction SilentlyContinue | Format-Table Id,ProcessName"
```

---

## 6. 测试

```bash
# 本地测试
curl -x socks5://127.0.0.1:7897 https://www.google.com

# 远程测试（通过 SSH 端口转发或 LAN IP）
curl -x socks5://192.168.71.21:7897 https://www.google.com
```

成功返回 `HTTP 200` 即部署完成。

---

## 6.5. Architecture: Wired-for-traffic, WiFi-only-for-proxy-relay

This setup uses **two separate network paths** on the same Windows machine:

- **Wired Ethernet**: Default for all non-proxy traffic (gateway 71.9 → OpenClash)
- **WiFi (5G hotspot)**: Only used by sing-box as the outbound interface for SOCKS5 relay. sing-box does NOT support `bind_interface` — instead, a **Windows static route** directs the proxy server's IP through the WiFi gateway (see §7b).

Reference: `references/minipc-relay-architecture.md` — full architecture diagram, config files, routing tables, and failure scenarios.

## 6a. Using a specific network interface for sing-box outbound traffic

### The problem: sing-box does NOT support `bind_interface`

sing-box (v1.13.x+) **does not have a `bind_interface` option**. Unlike Clash Verge (`interface-name: WLAN`), sing-box cannot bind outbound sockets to a specific network interface at the config level. Using `"bind_interface": "WLAN"` anywhere in sing-box's config results in:

```
FATAL decode config: json: unknown field "bind_interface"
```

### The solution: Windows static routing

The correct approach is to add a **Windows static route** that forces traffic to specific proxy server IPs through the WiFi gateway:

```cmd
route add <proxy-server-IP> mask 255.255.255.255 <wifi-gateway> IF <wifi-interface-index> metric 50
```

Example for Alibaba-Seoul node (43.108.41.245) through CMCC-C46N-5G WiFi (gateway 192.168.1.1):

```cmd
route add 43.108.41.245 mask 255.255.255.255 192.168.1.1 IF 11 metric 50
```

**Find the WiFi interface index:**
```cmd
route print -4
# Look for the WLAN interface in the Interface List (index is the number before the MAC)
```

**Verify traffic actually goes through WiFi:**
```powershell
$before = Get-NetAdapterStatistics -Name "WLAN","vEthernet (wan)"
# ... run proxy test ...
$after = Get-NetAdapterStatistics -Name "WLAN","vEthernet (wan)"
$diff = ($after[0].ReceivedBytes - $before[0].ReceivedBytes)
# High recv on WLAN = traffic going through WiFi
```

**To make the route persistent (survives reboot):**
```cmd
route -p add 43.108.41.245 mask 255.255.255.255 192.168.1.1 metric 50
```

### Architecture: how the dual-path design works without `bind_interface`

1. **sing-box runs without any `bind_interface`** — its sockets use the default routing table
2. **Default route (metric 74)** → wired Ethernet (192.168.71.9) — for minipc's normal traffic
3. **Specific route (metric 5050)** → WiFi for proxy server IP (e.g. 43.108.41.245) — when sing-box connects to Alibaba-Seoul, Windows routing sends it through WiFi

```text
minipc 浏览器 → 有线默认路由 → 71.9 OpenClash → 上网
minipc sing-box → 连 43.108.41.245 → 静态路由 → 192.168.1.1(WiFi网关) → 5G/CMCC家宽
```

## 7. Networking Pitfalls on Windows

### 7a. ❌ `bind_interface` is NOT a valid sing-box field — do not use

**Symptom:** `sing-box check -c config.json` returns:
```
FATAL decode config at config.json: bind_interface: json: unknown field "bind_interface"
```

**Fix:** Remove `"bind_interface"` from the config entirely. Use Windows static routing instead (see §6a).

### 7b. ❌ config.json corrupted by PowerShell BOM — use ASCII-only encoding

**Symptom:** `sing-box check -c config.json` returns:
```
FATAL decode config at config.json: invalid character 'ï' looking for beginning of value: row 1, column 1
```

**Root cause:** PowerShell's `Set-Content -Path config.json -Value $json -Encoding UTF8` writes a **UTF-8 BOM** (byte sequence `EF BB BF`) at the start of the file. sing-box's JSON parser (Go standard library) chokes on this BOM.

**Diagnosis:**
```cmd
rem Check first 3 bytes of the file
powershell -Command "Get-Content 'C:\ProgramData\sing-box\config.json' -TotalCount 1 | Format-Hex"
rem First 3 bytes should be 7B (JSON opening brace), not EF BB BF
```

**Fix — use one of these methods to write config.json without BOM:**

Method 1: Use `scp` from Linux (no BOM, ASCII-safe)
```bash
# Write JSON locally with Python's json.dump(ensure_ascii=True, encoding='ascii')
python3 -c "import json; json.dump(config, open('/tmp/config.json','w'), indent=2)"
scp /tmp/config.json minipc:C:/ProgramData/sing-box/config.json
```

Method 2: On Windows, use `[System.IO.File]::WriteAllText()` instead of `Set-Content`
```powershell
[System.IO.File]::WriteAllText("C:\ProgramData\sing-box\config.json", $json)
```

---

## 跨平台 Python 管理脚本

本技能提供两个 Python 脚本，实现跨平台（Linux / Windows）的 sing-box 统一管理：

### `scripts/sing-box-ctrl.py` — 统一管理脚本

| 子命令 | Linux | Windows |
|--------|-------|---------|
| `switch [节点]` | 热重载 (SIGHUP) | stop + start |
| `start` | `systemctl --user start` | `subprocess.Popen` (CREATE_BREAKAWAY_FROM_JOB) |
| `stop` | `systemctl --user stop` | `taskkill /F` |
| `restart` | stop + start | stop + start |
| `status` | `systemctl --user is-active` | `tasklist /FO CSV` |
| `test` | 临时 sing-box (10882) | 临时 sing-box (10882) |
| `help` | 显示帮助 | 显示帮助 |

自动检测 `sys.platform`，两种平台共用一份脚本。Linux 端放 `~/.local/bin/`, Windows 端放 `sing-box.exe` 同级目录。

**Windows PATH 设置：**
```powershell
[Environment]::SetEnvironmentVariable(
    "Path",
    [Environment]::GetEnvironmentVariable("Path", "User") + ";C:\Users\chen_\sing-box",
    "User"
)
```
设置后 `sing-box-ctrl status` 从任何路径都能直接调用。

### `scripts/sing-box-ctrl.cmd` — Windows 命令包装器

放在 sing-box.exe 同级目录，注册到 PATH 后可直接 `sing-box-ctrl <子命令>`：
```cmd
sing-box-ctrl status
sing-box-ctrl test --all
```

**添加到 Windows 用户 PATH：**
```powershell
[Environment]::SetEnvironmentVariable(
    "Path",
    [Environment]::GetEnvironmentVariable("Path", "User") + ";C:\Users\chen_\sing-box",
    "User"
)
```
设置后从任何 cmd/PowerShell 窗口均可调用 `sing-box-ctrl`。

### `scripts/sb-test.py` — 代理带宽测速脚本

跨平台代理延迟+带宽测试。与 `sing-box-ctrl.py test` 功能相同但更轻量：
- `python sb-test.py [节点名]` — 测指定节点
- `python sb-test.py --all` — 全测
- `python sb-test.py --direct` — 直连

### 关键发现

#### sing-box 是被动代理，不接管系统流量

与 Clash TUN 模式不同，默认配置（SOCKS + mixed inbound，无 TUN、无 `set_system_proxy`）下，sing-box 只开放代理端口，不修改系统代理设置，不创建虚拟网卡。应用必须显式指定 `-x socks5://127.0.0.1:10880` 才会走代理，不指定则全部直连。

#### Windows 子进程生命周期 (CREATE_BREAKAWAY_FROM_JOB)

#### Windows 子进程生命周期 (CREATE_BREAKAWAY_FROM_JOB)

**症状：** Python 脚本用 `subprocess.Popen` 启动 sing-box 后，脚本退出时 sing-box 也被杀死。SSH `tasklist` 查不到进程。

**根因：** Windows 的 `subprocess.Popen` 默认在 Job Object (作业对象) 中创建子进程。当父进程 (Python) 退出时，Windows 终止作业对象内的所有进程。Linux 无此行为 (孤儿进程被 init 收养)。

**修复：** 加 `CREATE_BREAKAWAY_FROM_JOB` 标志：
```python
flags = subprocess.CREATE_NO_WINDOW
if hasattr(subprocess, "CREATE_BREAKAWAY_FROM_JOB"):
    flags |= subprocess.CREATE_BREAKAWAY_FROM_JOB  # 0x01000000
proc = subprocess.Popen([...], creationflags=flags)
```

#### GBK 编码崩溃

**症状：** 打印 `✓` `→` `⚠` 等 Unicode 符号时报 `UnicodeEncodeError: 'gbk' codec can't encode character`。

**根因：** Windows 中文系统控制台默认编码 GBK，不支持大部分 Unicode 装饰符号。

**统一规则：** 跨平台脚本全部使用纯 ASCII 符号 (`->` 代替 `→`, `[OK]` 代替 `✓`, `[FAIL]` 代替 `✗`)。

#### sing-box version 不是 flag 而是 subcommand

**错误用法：** `sing-box --version`
**正确用法：** `sing-box version`
**根因：** sing-box v1.13+ 将 `version` 从 flag 改为子命令。用 `--version` 返回 `Error: unknown flag: --version`。

## 支持文件

### 参考
- `references/proxy-bandwidth-testing.md` — Windows Proxy 带宽测试方法论，核心陷阱：speedtest.exe 不支持 SOCKS5。正确使用 `curl -x socks5://127.0.0.1:10880` 或 `scripts/sb-test.py`。

### 脚本
- `scripts/sb-test.py` — 跨平台代理带宽测速工具（移植自 Linux `sing-box-ctrl test`）。需 python3 + sing-box.exe。用法：`python sb-test.py [--all | <节点名>]`
- `scripts/sing-box-ctrl.py` — 跨平台 sing-box 统一管理脚本。自动检测 Windows/Linux。
```

Method 3: PowerShell 7+ `Set-Content -NoBOM`:
```powershell
Set-Content -Path "C:\ProgramData\sing-box\config.json" -Value $json -NoBOM
```

**Verify:**
```cmd
cd /d C:\ProgramData\sing-box
sing-box.exe check -c config.json
rem → empty output (exit 0) = clean
```

**Pitfall — Clash Verge's `interface-name: WLAN` does not translate to sing-box:**
- Clash: `interface-name: WLAN` → bind SOCKS5/TPROXY listener AND all outbound connections to WLAN
- sing-box: No equivalent. All outbound connections use the Windows routing table

### 7g. geoip/geosite rule_set 分流陷阱

#### geosite-cn 必须用 `domain_suffix` 而非 `domain`

sing-box 的 `rule_set` 支持两种域名匹配方式：

| 字段 | 行为 | 示例 |
|------|------|------|
| `domain` | **精确匹配** — 仅匹配该域名自身 | `baidu.com` 不匹配 `www.baidu.com` |
| `domain_suffix` | **后缀匹配** — 匹配所有子域 | `.baidu.com` 匹配 `www.baidu.com` |

**常见错误**：从 v2fly domain-list-community (cn.txt) 提取的域名直接放进 `domain` 数组，导致 `www.baidu.com` 等子域不被匹配，geosite-cn 分流失效。

**正确做法** — 编译 rule_set 时同时加入 `domain` 和 `domain_suffix`：

```python
domains = [...]  # 从 cn.txt 提取
suffixes = ['.' + d for d in domains]  # .baidu.com 匹配所有子域
rule_set = {
    'version': 1,
    'rules': [
        {'domain': domains},
        {'domain_suffix': suffixes}
    ]
}
```

本地编译命令：
```bash
sing-box rule-set compile geosite-cn.json
```

#### rule_set source 生成（CN IP + CN 域名）

当 sing-box 的 remote rule_set 因网络不可用无法下载时，可从公开源本地生成：

```bash
# 1. 下载中国 IP 列表
curl -s -o china_ip_list.txt https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt

# 2. 下载中国域名列表
curl -s -o cn_domains.txt https://raw.githubusercontent.com/v2fly/domain-list-community/release/cn.txt

# 3. 生成 geoip-cn rule_set 源文件
python3 -c "
import json
with open('china_ip_list.txt') as f:
    ips = [l.strip() for l in f if l.strip()]
with open('geoip-cn.json', 'w') as f:
    json.dump({'version': 1, 'rules': [{'ip_cidr': ips}]}, f, separators=(',', ':'))
"

# 4. 生成 geosite-cn rule_set 源文件（含 domain + domain_suffix）
python3 -c "
import json
with open('cn_domains.txt') as f:
    domains = [l.strip().replace('domain:', '') for l in f if l.strip() and not l.startswith('#')]
suffixes = ['.' + d for d in domains]
with open('geosite-cn.json', 'w') as f:
    json.dump({'version': 1, 'rules': [{'domain': domains}, {'domain_suffix': suffixes}]}, f, separators=(',', ':'))
"

# 5. 编译为二进制 srs 文件
sing-box rule-set compile geoip-cn.json
sing-box rule-set compile geosite-cn.json

# 结果: geoip-cn.srs (~25K) geosite-cn.srs (~65K)
```

然后在 config.json 中用 `"type": "local"` 引用：
```json
{
  "tag": "geoip-cn",
  "type": "local",
  "path": "/etc/sing-box/ruleset/geoip-cn.srs"
}
```

### 7c. Windows default route selection with multiple interfaces

**Symptom:** minipc connected to both home Ethernet (192.168.71.x) and phone 5G hotspot WiFi (10.192.244.x). Proxy traffic goes through Ethernet instead of WiFi.

**Root cause:** Windows chooses the default route with the **lowest metric**. The WLAN interface (phone hotspot) typically gets metric 5000, while Ethernet gets metric 74. Without a specific static route for the proxy server IP, all outbound connections use the Ethernet default route.

**Diagnosis:**
```cmd
route print -4 0.0.0.0
```

Look for two `0.0.0.0` entries — one per interface. The one with lower `Metric` is the active default.

**Workaround — static route for proxy server through WLAN:**

When you need sing-box's outbound (to proxy server) to go through 5G but all other traffic stays on Ethernet, add a host route for the proxy server IP through the WLAN gateway:

```cmd
# Replace 43.108.41.245 with your proxy server IP and 10.192.244.122 with WLAN gateway
route add 43.108.41.245 mask 255.255.255.255 10.192.244.122 metric 50
```

Verify with:
```cmd
route print 43.108.*
tracert -d -h 3 43.108.41.245
# First hop should be the WLAN gateway (e.g., 10.192.244.x), confirming 5G path
```

**Caveat:** This route is **not persistent** — it disappears on reboot. Make it persistent with `route -p` or add it to the start-singbox.bat script.

### Pitfall — WLAN disconnects and persistent routes
- When the phone hotspot is turned off, the static route's gateway becomes unreachable. Sing-box reports `connectex: A socket operation was attempted to an unreachable host`. 
- Remove the route with `route delete 43.108.41.245` to restore traffic through the default Ethernet gateway.
- The `-p` flag creates a **persistent** route that survives reboot, but if the WiFi interface itself disappears (radio off, no networks available), the route entry may still exist and cause DNS/reachability delays. On Windows, `route print` will show the route with a different interface index or as "stale" — the easiest recovery is `route delete` for the proxy IP.

### Pitfall — `route add -p` creates duplicate entries when route already exists

When adding a persistent route for an IP that already has a fallback route (e.g., from the default gateway's subnet), `route add -p` creates a **duplicate** rather than replacing the existing one. The lower-metric entry takes effect, but duplicates are untidy. Best practice: delete first, then add:

```cmd
route delete 43.108.41.245
route -p add 43.108.41.245 mask 255.255.255.255 10.192.244.122 metric 50
```

Verify only one entry exists:
```cmd
route print 43.*
```

### 7d. Windows Schannel CRL revocation blocks HTTPS through proxy

**Symptom:** `curl -x socks5://127.0.0.1:8897 https://...` returns HTTP 000, exit code 35. Verbose output shows:

```
schannel: next InitializeSecurityContext failed: CRYPT_E_REVOCATION_OFFLINE (0x80092013)
```

Google and other sites may work, but Cloudflare/DigitalOcean/etc. fail because their certificate chains trigger revocation checks.

**Root cause:** Windows Schannel SSL/TLS implementation checks certificate revocation (CRL/OCSP) for every connection. Through a proxy (SOCKS5/HTTP), the revocation check's outbound connection may not go through the proxy — it connects directly to the CRL/OCSP server. If the direct connection fails (blocked by GFW or routing), Schannel rejects the HTTPS connection.

**Fix for curl:**
```cmd
curl --ssl-no-revoke -x socks5://127.0.0.1:8897 https://target.url
```

**System-wide fix (advanced):** Disable CRL checking via registry:
```
HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings
Value: CertificateRevocation = 0 (DWORD)
```
⚠️ Security trade-off: disabled CRL checking means revoked certificates won't be detected.

**Pitfall — `%%{http_code}%%` format on Windows CMD:** Windows CMD's `%` variable expansion conflicts with curl's `-w %{...}` format specifiers. Use `%%{http_code}%%` in CMD, or switch to PowerShell:
```powershell
(Invoke-WebRequest -Uri "https://target.url" -Proxy "socks5://127.0.0.1:8897").StatusCode
```

### 7e. PowerShell quoting through SSH — the 4-layer model

Every SSH command to Windows passes through four parsers, each interpreting special characters:

```
第1层: Linux bash    →  解释 $var, |, >, 引号
第2层: SSH 传输      →  将参数字符串传给远程 sshd
第3层: Windows cmd   →  sshd 默认启动 cmd.exe，再次解释 &, >, %, ^
第4层: PowerShell    →  -Command 参数再次解析 $, @, {}, 引号
```

If the goal is to create a file with special characters, there's a **fifth layer** — the file content itself.

**Quick failure reference** (creating .bat files on Windows over SSH):

| Approach | Why it failed |
|----------|--------------|
| PowerShell `@\"...\"@` via SSH | `@` misinterpreted by outer shell → `ParserError` |
| cmd `(...)` block + `>` redirect | Block doesn't accumulate multi-line echo output |
| base64 + `[Convert]::FromBase64String` | `$env:USERPROFILE` expanded by bash in double-quotes |
| SCP direct transfer | First failed attempt creates a 0-byte file that Windows locks |

**Strategies that work:**

1. **PowerShell `-EncodedCommand` (base64)** — single token, zero escaping. See `references/ps-enc-bash-functions.md` for bash-side helper functions (`ps_enc`, `ps_run`).

2. **Upload .ps1 via SCP, then `-File` execute** — eliminates all quoting problems. Best for complex scripts.

3. **Python generator pattern** — write a Python script locally, `cat >` transfer to remote Temp, execute. Python's `open().write()` bypasses all shell parsers. See `references/windows-file-creation-via-ssh.md`.

4. **Simple commands with `& { }` wrapper** — works for single pipelines:
   ```bash
   ssh target 'powershell -NoProfile -Command "& { Get-Process | Sort CPU -Descending | Select -First 5 }"'
   ```
   Does NOT work for loops, variables, multi-statement logic.

### 7f. 多个 WLAN 接口（Wi-Fi 7 HBS）

Qualcomm FastConnect 7800 等 Wi-Fi 7 芯片会暴露多个 WLAN 虚拟适配器（HBS = High Band Simultaneous）：

```
WLAN      → 主适配器（连 Wi-Fi 用这个）
WLAN 2-4  → Wi-Fi Direct / 虚拟WiFi / MLO备用
WLAN 5    → 其他功能，通常 Not Present
```

所有适配器共用一个物理芯片，**只用 `WLAN`（不带数字的）**。Windows 系统 WiFi 列表默认走的是这个适配器，不需手动选。

WiFi 连接后，可通过路由表确认哪个接口是默认出口：
```cmd
route print -4 0.0.0.0
```
Metric 最低的接口是实际出口。连手机热点时一般为 35-40，有线以太网通常为 40-5000。如果默认不走 WiFi，需要调整跃点数或用静态路由（见 §7c）。

### 7h. WiFi 连接通过 SSH（`netsh wlan connect` 需从 PowerShell 执行）

**症状：** `ssh minipc netsh wlan connect name='SSID-NAME'` 返回「系统上没有此类无线接口」。

**根因：** SSH Session 0 中 cmd 无 WiFi 管理权限，`netsh wlan` 命令找不到接口。

**修复：通过 PowerShell 执行：**
```powershell
ssh minipc powershell -Command "netsh wlan connect name='SSID-NAME'"
# → 已成功完成连接请求。

# 验证状态
ssh minipc powershell -Command "netsh wlan show interfaces | Select-String 'SSID|State'"
```

### 7i. FreeRDP Headless — WiFi Radio Control from Session 1

Unlike SSH (Session 0), **RDP connects to Session 1**, where the WinRT Radio API can toggle WiFi radio. FreeRDP with Xvfb enables headless radio control from a Linux jumpbox.

> **When to use:** SSH is down (kex reset) but RDP port 3389 is open. Or WiFi radio is soft-off and Session 0 cannot toggle it.

#### Setup

```bash
sudo apt-get install -y freerdp2-x11 xvfb
```

#### Toggle WiFi Radio ON

```bash
# 1. Deploy the script (SCP or RDP app-cmd)
scp toggle-wifi-radio.ps1 target:'C:\Users\chen_\toggle-wifi-radio.ps1'

# 2. Headless RDP execute
Xvfb :99 -screen 0 1024x768x16 &
export DISPLAY=:99
xfreerdp /v:<host>:<port> /u:<user> /p:"$(cat /tmp/tmp-passwd)" \
  /cert-ignore /sec:nla /network:auto /bpp:16 \
  /app:"powershell.exe" /app-icon \
  /app-cmd:"-NoProfile -ExecutionPolicy Bypass -File C:\Users\chen_\toggle-wifi-radio.ps1"
```

#### Preferred: Upload + Execute (avoids quoting hell)

```bash
# Upload once → execute via RDP with -File flag
xfreerdp ... /app:"powershell.exe" /app-cmd:"-NoProfile -File C:\Users\<user>\Desktop\toggle-wifi.ps1"
```

#### Simpler: netsh wlan connect (radio already on)

```bash
xfreerdp /v:<target>:<port> /u:<user> /p:"$(cat /tmp/tmp-passwd)" \
  /cert-ignore /sec:nla /network:auto /bpp:16 \
  /app:"cmd.exe" /app-icon \
  /app-cmd:"/c netsh wlan connect name=MyWiFiSSID"
```

#### Port check — confirm machine alive before RDP

```bash
for port in 22 3389 5985 445 135; do
  nc -zv -w 3 <target> $port 2>&1
done
# 22 open but kex reset → sshd hung, RDP available
# 3389 open → RDP available for recovery
```

See `references/toggle-wifi-radio-ps1.md` for the WinRT Radio API script.
See `scripts/toggle-wifi-radio.ps1` for the deployable script.

> **⚠️ Danger: Do NOT use `schtasks /it` (interactive mode) from SSH.** Windows Defender ASR detects this as lateral movement (Session 0 → Session 1 injection) and quarantines `sshd-session.exe`, breaking SSH entirely. Recovery requires WinRM. Always use WinRM or RDP for Session 1 operations.

## 8. Xray 部署（替代 v2rayN GUI）

**v2rayN 是 GUI 壳，实际跑的是 Xray 核心。远程部署时跳过 v2rayN，直接装 Xray。**

### v2rayN vs Xray 直装

| | v2rayN | Xray 直装 |
|---|---|---|
| 启动方式 | GUI 应用，SSH Session 0 不可用 | CLI，任何 session 可用 |
| 配置方式 | guiNConfig.json（复杂） | 标准 Xray config.json |
| 持久化 | 需登录桌面 | schtasks SYSTEM 账户 |
| 适用场景 | 本地桌面使用 | 远程部署 / 服务器 |

**结论：SSH 远程部署只用 Xray 核心。v2rayN 可保留安装，供日后本地 GUI 使用。**

### 部署步骤

```bash
# 1. 下载 v2rayN（带 Xray 核心）
#    注意：Self-contained zip 解压到 v2rayN-windows-64 子目录，需上移内容
ssh minipc powershell -Command '
  Invoke-WebRequest -Uri "https://github.com/2dust/v2rayN/releases/download/7.22.7/v2rayN-windows-64.zip" -OutFile "$env:TEMP\\v2rayN.zip"
  Expand-Archive -Path "$env:TEMP\\v2rayN.zip" -DestinationPath "C:\\Users\\chen_\\v2rayN\\" -Force
  # Self-contained zip 内多一层 v2rayN-windows-64/ 目录
  Get-ChildItem "C:\\Users\\chen_\\v2rayN\\v2rayN-windows-64" | Move-Item -Destination "C:\\Users\\chen_\\v2rayN\\" -Force
  Remove-Item "C:\\Users\\chen_\\v2rayN\\v2rayN-windows-64" -Force
'

# Xray 核心位置: C:\\Users\\chen_\\v2rayN\\bin\\xray\\xray.exe (v26.6.1)
# 还包含 mihomo/ 和 sing_box/ 目录，可根据需要选用
```

# 2. 写 Xray 配置（VLESS+Reality 示例）
#    注意：必须用 [System.IO.File]::WriteAllText() 避免 BOM！(见 §7b)
```

### VLESS+Reality Xray 配置模板

```json
{
  "log": { "loglevel": "warning" },
  "inbounds": [{
    "tag": "socks-in",
    "port": 10808,
    "listen": "0.0.0.0",
    "protocol": "socks",
    "settings": { "udp": true },
    "sniffing": { "enabled": true, "destOverride": ["http","tls"] }
  }],
  "outbounds": [
    {
      "tag": "node-name",
      "protocol": "vless",
      "settings": {
        "vnext": [{
          "address": "43.108.41.245",
          "port": 40002,
          "users": [{
            "id": "UUID-HERE",
            "encryption": "none",
            "flow": ""
          }]
        }]
      },
      "streamSettings": {
        "network": "tcp",
        "security": "reality",
        "realitySettings": {
          "serverName": "www.bing.com",
          "fingerprint": "chrome",
          "publicKey": "KEY-HERE",
          "shortId": "SHORTID-HERE",
          "spiderX": ""
        }
      }
    },
    { "tag": "direct", "protocol": "freedom" }
  ]
}
```

⚠️ Xray 节点地址**只用 IP 不用域名**（避免 DNS 绕路），Reality SNI 填域名（仅 TLS 握手用，不触发 DNS）。

### 测试配置

```bash
ssh minipc 'C:\Users\chen_\v2rayN\bin\xray\xray.exe run -c C:\Users\chen_\v2rayN\guiConfigs\5g-seoul.json -test'
# → "Configuration OK." = 配置有效
```

### 持久化运行（schtasks SYSTEM 账户）

**SSH Session 0 中 `Start-Process` 启动的进程会在 SSH 断开后被回收。** 必须用计划任务：

```powershell
$taskName = 'Xray-SOCKS5'
$xrayExe = 'C:\Users\chen_\v2rayN\bin\xray\xray.exe'
$config = 'C:\Users\chen_\v2rayN\guiConfigs\5g-seoul.json'

schtasks /delete /tn $taskName /f 2>$null

$action = New-ScheduledTaskAction -Execute $xrayExe -Argument "run -c `"$config`"" -WorkingDirectory 'C:\Users\chen_\v2rayN'
$trigger = New-ScheduledTaskTrigger -AtStartup
$principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force
Start-ScheduledTask -TaskName $taskName
```

要点：
- `SYSTEM` 账户：不依赖用户登录，开机即运行
- `RestartCount 999` + `RestartInterval 5min`：崩溃自动重试
- 防火墙：`New-NetFirewallRule -DisplayName 'Xray SOCKS5' -Direction Inbound -Protocol TCP -LocalPort 10808 -Action Allow`

### 静态路由（VLESS 节点走 WiFi）

```cmd
route delete 43.108.41.245
route -p add 43.108.41.245 mask 255.255.255.255 192.168.1.1 metric 50
```

## 9. 运维命令

### v2rayN GUI 与 xray 核心脱钩陷阱

**现象**：打开 v2rayN GUI 界面，看不到任何节点配置，但 `netstat -ano | findstr 10808` 显示 xray.exe 在监听。用 SOCKS5 测试也能通。

**根因**：v2rayN 只"看见"它自己启动的 xray 实例。如果 xray 是通过其他方式启动的（schtasks SYSTEM 账户、命令行直接 `xray.exe run -c`、或其他脚本），v2rayN GUI 完全不知道它的存在。

**诊断**：
```powershell
# 1. 查谁在监听代理端口
netstat -ano | findstr LISTENING | findstr 10808
# → 记下 PID

# 2. 查该进程的完整命令行和父进程
Get-CimInstance Win32_Process -Filter "ProcessId=<PID>" | Select-Object ParentProcessId,Name,CommandLine

# 3. 如果父进程是 svchost.exe (Schedule 服务) → 是 schtasks 启动的
#    如果父进程是 v2rayN.exe → GUI 管理的
Get-CimInstance Win32_Process -Filter "ProcessId=<ParentPID>" | Select-Object Name
```

**清理独立 xray 实例**：
```powershell
# 停进程
Stop-Process -Id <PID> -Force
# 删计划任务（如果存在）
schtasks /delete /tn Xray-SOCKS5 /f
```

**教训**：管理 xray/v2rayN 时，**先看进程再看 GUI**。`netstat -ano | findstr <port>` 是唯一可靠的真相来源。

### VLESS 分享链接生成

从 Xray/sing-box JSON 配置生成 vless:// 链接（用于 v2rayN 导入）：

```python
import urllib.parse

uuid = 'a5fa1889-1316-4115-a866-96c8f30523ef'
host = '43.108.41.245'
port = 40002
params = {
    'encryption': 'none',
    'security': 'reality',
    'sni': 'www.bing.com',       # Reality serverName
    'fp': 'chrome',              # fingerprint
    'pbk': '<public-key>',       # Reality publicKey
    'sid': '<short-id>',         # Reality shortId
    'type': 'tcp',
}
name = '节点名称'

qs = '&'.join(f'{k}={v}' for k, v in params.items())
link = f'vless://{uuid}@{host}:{port}?{qs}#{urllib.parse.quote(name)}'
print(link)
```

v2rayN 导入方式：服务器 → 从剪贴板导入 → 粘贴链接。或把链接写入 `.txt` 文件拖进 v2rayN。

## 9. 运维命令

| 操作 | SSH 命令 |
|---|---|
| 启动 (Xray) | `ssh minipc 'schtasks /run /tn Xray-SOCKS5'` |
| 停止 (Xray) | `ssh minipc 'taskkill /F /IM xray.exe'` |
| 查进程 | `ssh minipc powershell -Command 'Get-Process xray -ErrorAction SilentlyContinue'` |
| 查端口 | `ssh minipc netstat -ano | grep 10808` |
| 校验 Xray 配置 | `ssh minipc 'C:\Users\chen_\v2rayN\bin\xray\xray.exe run -c C:\Users\chen_\v2rayN\guiConfigs\5g-seoul.json -test'` |
| 更新配置 | scp 新 config.json → `Start-ScheduledTask` 或 `taskkill + schtasks /run` |

**sing-box 运维（旧方案，见上方章节）：**

| 操作 | SSH 命令（通过 PowerShell 后台启动） |
|---|---|
| 启动 | `ssh minipc powershell -Command 'Start-Process -FilePath "C:\ProgramData\sing-box\sing-box.exe" -ArgumentList "run","-c","C:\ProgramData\sing-box\config.json" -WindowStyle Hidden'` |
| 停止 | `ssh minipc 'taskkill /F /IM sing-box.exe'` |
| 查进程 | `ssh minipc 'tasklist \| findstr /I sing-box'` |
| 查日志 | `ssh minipc 'powershell -Command "Get-Content \"C:\ProgramData\sing-box\sing-box.log\" -Tail 20"'` |
| 校验配置 | `ssh minipc '\"C:\ProgramData\sing-box\sing-box.exe\" check -c \"C:\ProgramData\sing-box\config.json\"'` |
| 更新配置 | scp 新 config.json + .srs 文件到目标目录，然后 kill+restart |

# windows-local-llm

# Windows Local LLM (llama.cpp) Management

## Quick reference: start/stop script pattern

Two batch scripts on Desktop for manual control:

**qwen-start.bat** — starts llama-server, shows live output:
```batch
@echo off
set MODEL=C:\llama\models\Qwen3.6-27B-Q4_K_M.gguf
set SLOTS=C:\llama\slots

if not exist "%MODEL%" (
    echo [ERROR] Model not found: %MODEL%
    pause
    exit /b 1
)

if not exist "%SLOTS%" mkdir "%SLOTS%"

echo [%date% %time%] Starting llama-server...
echo.
title Qwen3.6-27B Server

C:\llama\llama-server.exe ^
    -m "%MODEL%" ^
    -c 262144 ^
    -ctk q8_0 -ctv q8_0 ^
    -ngl 99 ^
    --host 0.0.0.0 --port 8080 ^
    -t 16 ^
    -b 512 ^
    --n-predict 32768 ^
    --slot-save-path "%SLOTS%"

echo.
echo [%date% %time%] Server exited with code %ERRORLEVEL%
pause
```

Key parameters (2026-07-05):
- `--n-predict 32768` — output cap (was `-1` unlimited)
- `--slot-save-path C:\llama\slots` — slot save/restore API
- No `> server.log 2>&1` — output visible in console
- `kv_unified = true` (auto) — 4 slots share one KV cache

**qwen-stop.bat** — kills the server:
```batch
@echo off
echo Stopping llama-server...
taskkill /F /IM llama-server.exe >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo llama-server stopped successfully.
) else (
    echo llama-server was not running.
)
pause
```

## Pitfall: unsupported KV cache types

`-ctk` / `-ctv` only accept these values:

```
f32, f16, bf16, q8_0, q4_0, q4_1, iq4_nl, q5_0, q5_1
```

**`q6_k` is NOT supported** (unlike model quantization levels). Using it causes:

```
error while handling argument "-ctk": Unsupported cache type: q6_k
```

The server exits immediately with code 1. Fix: use `q8_0` instead (good quality for Q4_K_M models on RTX 5090 32GB, ~27.8GB VRAM used).

## Checking for auto-start scheduled tasks

User does NOT want local models auto-launching — manual control only. Check with:

```cmd
schtasks /query /fo LIST /v | findstr /i "llama qwen server model"
```

On Chinese Windows, pipe through `chcp 65001` first to avoid GBK garbling:

```cmd
chcp 65001 >nul & schtasks /query /tn "\LlamaServer" /fo LIST /v
```

Key fields to inspect:
- `Scheduled Task State: Enabled` → disable or delete if auto-start unwanted
- `Task To Run` → what executable it launches
- `Schedule Type` / `Start Time` / `Start Date` → when it triggers

To disable: `schtasks /change /tn "\LlamaServer" /disable`
To delete: `schtasks /delete /tn "\LlamaServer" /f`

## Remote batch script editing via SSH

When editing `.bat` files on Windows through SSH, Python one-liners may fail silently (encoding mismatch between SSH transport and NTFS). Use PowerShell's native cmdlet instead:

```bash
# Works reliably — PowerShell handles the file encoding correctly
ssh 9950x3d powershell -Command "(Get-Content 'C:\Users\chen_\Desktop\qwen-start.bat') -replace 'OLD','NEW' | Set-Content 'C:\Users\chen_\Desktop\qwen-start.bat'"

# Verify with type
ssh 9950x3d "type C:\Users\chen_\Desktop\qwen-start.bat"
```

## Reading logs remotely

```bash
ssh 9950x3d "type C:\llama\server.log"
```

The log captures both stdout and stderr (`> server.log 2>&1`). On startup failure, the error message is the last few lines of this file.

# winrm-ssh-recovery

# WinRM SSH Recovery for Windows

Use when SSH to a Windows machine is down but WinRM (port 5985) is still accessible.

## Prerequisites

- Python 3 with `pywinrm` (`python3-winrm` package on Debian/Ubuntu: `sudo apt install python3-winrm`)
- A Windows account password (stored in `/tmp/tmp-passwd`, cleaned after use)
- Network access to the target on port 5985
## Python 3.12+ MD4 Workaround

Python 3.12 removed MD4 from hashlib. pywinrm needs MD4 for NTLM auth.

Save the following pure-Python MD4 as `/tmp/winrm_cmd2.py` (also available in this skill as `scripts/md4-patch.py`):

```python
# /tmp/winrm_cmd2.py — Pure-Python MD4 monkey-patch for Python 3.12+
import hashlib, struct

class _MD4:
    def __init__(self, data=b''):
        self._buf = bytearray(data)
    def update(self, data): self._buf.extend(data)
    def digest(self):
        buf = bytearray(self._buf) + b'\x80'
        while len(buf) % 64 != 56: buf.append(0)
        buf += struct.pack('<Q', len(self._buf) * 8)
        A, B, C, D = 0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476
        def F(x,y,z): return (x&y)|(~x&z)
        def G(x,y,z): return (x&y)|(x&z)|(y&z)
        def H(x,y,z): return x^y^z
        def lrot(x,n): return ((x<<n)|(x>>(32-n)))&0xFFFFFFFF
        for blk in range(0, len(buf), 64):
            X = list(struct.unpack('<16I', buf[blk:blk+64]))
            AA, BB, CC, DD = A, B, C, D
            for i, s in [(0,3),(1,7),(2,11),(3,19),(4,3),(5,7),(6,11),(7,19),
                         (8,3),(9,7),(10,11),(11,19),(12,3),(13,7),(14,11),(15,19)]:
                if i%4==0: A=lrot((A+F(B,C,D)+X[i])&0xFFFFFFFF,s)
                elif i%4==1: D=lrot((D+F(A,B,C)+X[i])&0xFFFFFFFF,s)
                elif i%4==2: C=lrot((C+F(D,A,B)+X[i])&0xFFFFFFFF,s)
                else: B=lrot((B+F(C,D,A)+X[i])&0xFFFFFFFF,s)
            for n in range(16):
                i, s = [0,4,8,12,1,5,9,13,2,6,10,14,3,7,11,15][n], [3,5,9,13][n%4]
                if n%4==0: A=lrot((A+G(B,C,D)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                elif n%4==1: D=lrot((D+G(A,B,C)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                elif n%4==2: C=lrot((C+G(D,A,B)+X[i]+0x5A827999)&0xFFFFFFFF,s)
                else: B=lrot((B+G(C,D,A)+X[i]+0x5A827999)&0xFFFFFFFF,s)
            for n in range(16):
                i, s = [0,8,4,12,2,10,6,14,1,9,5,13,3,11,7,15][n], [3,9,11,15][n%4]
                if n%4==0: A=lrot((A+H(B,C,D)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                elif n%4==1: D=lrot((D+H(A,B,C)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                elif n%4==2: C=lrot((C+H(D,A,B)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
                else: B=lrot((B+H(C,D,A)+X[i]+0x6ED9EBA1)&0xFFFFFFFF,s)
            A = (AA+A)&0xFFFFFFFF; B = (BB+B)&0xFFFFFFFF
            C = (CC+C)&0xFFFFFFFF; D = (DD+D)&0xFFFFFFFF
        return struct.pack('<4I',A,B,C,D)
    def copy(self): return _MD4(bytes(self._buf))

# Monkey-patch: preserve original, replace md4
_orig_new = hashlib.new
def _patched_new(name, data=b''):
    if name == 'md4':
        h = _MD4()
        if data: h.update(data)
        return h
    return _orig_new(name, data)
hashlib.new = _patched_new
```

### Usage: connect and run a command via SSH

Store the patch in `/tmp/winrm_cmd2.py`, then when connecting:

```python
exec(open('/tmp/winrm_cmd2.py').read())
import winrm
pwd = open('/tmp/tmp-passwd').read().strip()
s = winrm.Session('192.168.71.21', auth=('chen_', pwd), transport='ntlm')
r = s.run_ps('Write-Host WINRM_OK')
print(r.std_out.decode('utf-8', errors='replace'))
```

## Common Recovery Tasks

### Restart sshd service

```
Restart-Service sshd -Force
Start-Sleep 3
Get-Service sshd | Format-Table Status,Name,StartType
```

### Reinstall OpenSSH when files are missing

If `sshd-session.exe` (required by SSH 10.x) or other binaries are deleted:

```powershell
$url = "https://github.com/PowerShell/Win32-OpenSSH/releases/download/10.0.0.0p2-Preview/OpenSSH-Win64-v10.0.0.0.msi"
$msi = "C:\Users\chen_\OpenSSH-Win64.msi"
Invoke-WebRequest -Uri $url -OutFile $msi -UseBasicParsing
Start-Process msiexec -ArgumentList "/i `"$msi`" /quiet /norestart" -Wait -NoNewWindow
Remove-Item $msi -Force
Restart-Service sshd -Force
```

### Toggle WiFi radio (WinRT API)

```powershell
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { 
    $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and 
    $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
Function Await($WinRtTask, $ResultType) {
    $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
    $netTask = $asTask.Invoke($null, @($WinRtTask))
    $netTask.Wait(-1) | Out-Null
    $netTask.Result
}
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$wifi = $radios | ? { $_.Kind -eq 'WiFi' }
$result = Await ($wifi.SetStateAsync([Windows.Devices.Radios.RadioState]::On)) ([Windows.Devices.Radios.RadioAccessStatus])
Write-Output "Result: $result"
```

## Pitfalls

- **Python 3.12 has no MD4** — must monkey-patch. OpenSSL 3.0+ also disabled MD4.
- **SSH Session 0 vs WinRM Session 1** — WinRM runs in Session 1 (interactive), Radio API only works there.
- **Clean up passwords** — `rm /tmp/tmp-passwd` immediately after use.
- **sshd-session.exe** — OpenSSH 10.x+ uses a split architecture. If this file is deleted, sshd crashes immediately with ExitCode 1067.
- **Do NOT use `Register-ScheduledTask -LogonType Interactive` from SSH** — Windows Defender ASR detects this as lateral movement (Session 0 → Session 1 injection) and quarantines `sshd-session.exe`. This is what causes the crash. Always use WinRM for operations needing Session 1 access.