# sing-box Windows Client Deployment

## Use Case

Replace Clash Verge GUI with a pure CLI proxy client (sing-box) on a Windows machine (minipc) that has both Ethernet (LAN) and WiFi (phone hotspot). The proxy's outbound connections must go through WiFi (WLAN) while the SOCKS5/HTTP listeners are available on the LAN for other devices.

## Installation

```powershell
# Find latest Windows amd64 binary
# URL: https://github.com/SagerNet/sing-box/releases/latest

# Download and extract
$dir = "C:\ProgramData\sing-box"
New-Item -ItemType Directory -Path $dir -Force | Out-Null
$url = "https://github.com/SagerNet/sing-box/releases/download/v1.13.14/sing-box-1.13.14-windows-amd64.zip"
$zip = "$dir\sing-box.zip"
Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing
Expand-Archive -Path $zip -DestinationPath "$dir\tmp" -Force
Move-Item "$dir\tmp\sing-box-1.13.14-windows-amd64\sing-box.exe" "$dir\sing-box.exe" -Force
Remove-Item "$dir\tmp" -Recurse -Force
Remove-Item $zip -Force
```

## Configuration

### Avoid Clash Verge Default Ports

Clash Verge uses ports 7890/7897 by default. If you may ever reinstall Clash Verge, choose different ports (e.g. 8890/8897) to avoid conflicts. Update the port numbers in config.json, firewall rules, and startup scripts consistently.

### Config Format Migration (v1.13.x Breaking Changes)

sing-box >= 1.11 removed several legacy fields. v1.13 enforces these removals as FATAL errors:

| Old (pre-1.11) | New (1.13+) | Migration |
|---|---|---|
| `"sniff": true` in inbounds | Remove entirely | Not needed for SOCKS5/HTTP proxy (protocol already carries destination) |
| `"type": "dns"` outbound | Remove entirely | DNS routing now uses rule actions only |
| `"cache_file": "cache.db"` in `experimental.clash_api` | Move to `experimental.cache_file { "enabled": true }` | `store_selected` and `store_fakeip` stay in `clash_api` |
| `"bind_interface"` in outbound | Same field (still valid) | Use for forcing proxy connections through WLAN |

### Minimal Config (4 Nodes + SOCKS5 + HTTP)

```json
{
  "log": {
    "level": "info",
    "output": "sing-box.log",
    "timestamp": true
  },
  "inbounds": [
    {
      "type": "mixed",
      "tag": "mixed-in",
      "listen": "0.0.0.0",
      "listen_port": 8890
    },
    {
      "type": "socks",
      "tag": "socks-in",
      "listen": "0.0.0.0",
      "listen_port": 8897
    }
  ],
  "outbounds": [
    {
      "type": "selector",
      "tag": "select",
      "outbounds": [
        "Alibaba-Seoul-VLESS-Reality",
        "VMISS-HK",
        "233boy-KVM",
        "Seoul-Cloudflare"
      ],
      "default": "Alibaba-Seoul-VLESS-Reality"
    },
    {
      "type": "vless",
      "tag": "Alibaba-Seoul-VLESS-Reality",
      "server": "43.108.41.245",
      "server_port": 40002,
      "uuid": "<uuid>",
      "bind_interface": "WLAN",
      "tls": {
        "enabled": true,
        "server_name": "www.bing.com",
        "utls": { "enabled": true, "fingerprint": "chrome" },
        "reality": {
          "enabled": true,
          "public_key": "<public-key>",
          "short_id": "<short-id>"
        }
      }
    },
    {
      "type": "vmess",
      "tag": "VMISS-HK",
      "server": "vmiss.bernarty.xyz",
      "server_port": 443,
      "uuid": "<uuid>",
      "security": "auto",
      "bind_interface": "WLAN",
      "tls": {
        "enabled": true,
        "server_name": "vmiss.bernarty.xyz",
        "utls": { "enabled": true, "fingerprint": "chrome" }
      },
      "transport": {
        "type": "ws",
        "path": "/ws-vmiss",
        "headers": { "Host": "vmiss.bernarty.xyz" }
      }
    },
    {
      "type": "direct",
      "tag": "direct"
    },
    {
      "type": "block",
      "tag": "block"
    }
  ],
  "route": {
    "rules": [],
    "final": "select"
  }
}
```

**IMPORTANT:** Do NOT set `"auto_detect_interface": true` in the `route` section. On Windows with Hyper-V, this causes sing-box to detect `vEthernet (wan)` (the Hyper-V virtual switch) as the default interface, even though outbounds set `bind_interface: "WLAN"`. The route-level detection overrides per-outbound binding, effectively sending traffic through Ethernet instead of WiFi. Leave `auto_detect_interface` absent (defaults to `false`).

**`bind_interface: "WLAN"`** forces sing-box's outbound sockets to the WiFi interface. Normal apps on the same machine continue using the default route (Ethernet). This replicates Clash Verge's `interface-name: WLAN` behavior.

### Forcing WLAN Routing — Static Route Method

Even with `bind_interface: "WLAN"`, Windows' routing table may still affect connections. When both Ethernet and WiFi are connected, the Ethernet route typically has a lower metric and wins for the system default route:

```
0.0.0.0 0.0.0.0 192.168.71.9   192.168.71.21   74    ← Ethernet (home)
0.0.0.0 0.0.0.0 10.192.244.122 10.192.244.1   5000  ← WLAN (phone hotspot)
```

Add a /32 static route for each proxy server IP through the WLAN gateway to ensure connections go through WiFi:

```cmd
# Check WLAN gateway
ipconfig | findstr "10.192.244"

# Add route for Reality server IP through WLAN
route add 43.108.41.245 mask 255.255.255.255 10.192.244.122 metric 50

# Add routes for other proxy servers as needed
route add <server_ip> mask 255.255.255.255 <hotspot_gateway> metric 50
```

This makes Windows route connections to these specific server IPs through the WLAN interface regardless of the default route metric. Verify with `tracert`:

```
tracert -d -h 3 43.108.41.245
  1     2 ms     1 ms     1 ms  10.192.244.122   ← phone hotspot gateway ✓
```

**Persistence:** These routes are lost on reboot. Add them to a startup script or the schtasks runner:

```cmd
schtasks /Create /SC ONSTART /TN "sing-box-routes" /TR "route add 43.108.41.245 mask 255.255.255.255 10.192.244.122 metric 50" /RU SYSTEM /RL HIGHEST /F
```

## Windows Firewall

Without an inbound rule, Windows Defender firewall blocks LAN-to-sing-box connections by default. Add rules for the proxy ports:

```cmd
netsh advfirewall firewall add rule name="sing-box SOCKS5 (8897)" dir=in protocol=tcp localport=8897 action=allow profile=any
netsh advfirewall firewall add rule name="sing-box HTTP (8890)" dir=in protocol=tcp localport=8890 action=allow profile=any
```

## Persistence (No Window, Auto-Start)

Do NOT use `start /B` via SSH — the process dies when SSH disconnects. Use `schtasks`:

```cmd
:: Create auto-start task (runs at boot, SYSTEM user, no window)
schtasks /Create /SC ONSTART /TN "sing-box-proxy" /TR "C:\ProgramData\sing-box\sing-box.exe run -c C:\ProgramData\sing-box\config.json" /RU SYSTEM /RL HIGHEST /F

:: Start immediately
schtasks /Run /TN "sing-box-proxy"

:: Verify
tasklist | findstr sing-box

:: Stop
taskkill /F /IM sing-box.exe
```

The task runs as SYSTEM with no user login required, no visible terminal window.

## Windows Schannel — CRYPT_E_REVOCATION_OFFLINE (exit 35)

When testing HTTPS through the sing-box proxy from Windows, curl using Schannel (Windows native SSL/TLS) performs certificate revocation checks (OCSP/CRL). Through the proxy, these checks may fail:

```
schannel: next InitializeSecurityContext failed: CRYPT_E_REVOCATION_OFFLINE (0x80092013)
curl: (35) revocation status was not able to be checked
```

**Fix:** Use `--ssl-no-revoke` to skip revocation checking:

```bash
curl -4 --ssl-no-revoke -x socks5://127.0.0.1:8897 -o NUL \
  "https://speed.cloudflare.com/__down?bytes=10485760" \
  -w "http: %{http_code} time: %{time_total}s"
```

**Impact on speed tests:** The Schannel revocation check is why direct Windows curl tests (exit 35) differ from OpenClash bwtest results (which run on OpenWrt using OpenSSL, unaffected). The sing-box proxy itself works fine at ~28 Mbps — it's the Windows SSL layer that blocks the test.

**curl format specifier on Windows CMD:** Windows cmd.exe uses `%` for variable expansion, which conflicts with curl's `-w` format specifier. In SSH commands, ALWAYS use single `%`:

```bash
# CORRECT (Windows curl through SSH):
curl -w "http: %{http_code} time: %{time_total}s"

# WRONG (double %% prevents expansion):
curl -w "http: %%{http_code} time: %%{time_total}s"
# Outputs literal "http: %{http_code} time: %{time_total}s"
```

## Verification

```powershell
# From the same machine
curl -s --connect-timeout 5 -x socks5://127.0.0.1:8897 -o nul -w "HTTP %{http_code} %{time_total}s\n" https://www.google.com
curl -s --connect-timeout 5 -x http://127.0.0.1:8890 -o nul -w "HTTP %{http_code} %{time_total}s\n" https://www.baidu.com

# From another machine on LAN
curl -s --connect-timeout 5 -x socks5://<minipc-lan-ip>:8897 -o /dev/null -w "HTTP %{http_code}\n" https://www.google.com
```

Backup the start-singbox.bat script BEFORE modification:

```batch
copy start-singbox.bat start-singbox.bak
```

**Pitfall — encoding:** PowerShell's `Out-File` and `Set-Content` default to UTF-16 (not UTF-8). Use `[IO.File]::WriteAllText()` or pass `-Encoding UTF8` to ensure UTF-8 output when writing config files through PowerShell.

## Logs

```powershell
type C:\ProgramData\sing-box\sing-box.log
```

## Node Switching

To switch the default node, edit `config.json` → change `"default"` in the selector outbound → kill and restart sing-box. Or connect to the Clash API endpoint if enabled.

**⚠️ v1.13.14 Clash API issue:** The `experimental.clash_api` section with `cache_file` causes a FATA error:
```
create clash-server: cache_file and related fields in Clash API is deprecated
```
Even after moving `cache_file` to `experimental.cache_file`, the check still fails. As a workaround, **omit the entire `experimental` section** — the proxy works fine without the Clash API for node switching. If you need node switching, kill the process, edit the config's `"default"` field, and restart.

Example minimal `experimental` section that also causes issues:
```json
"experimental": {
  "cache_file": { "enabled": true }
}
```

```json
"experimental": {
  "cache_file": { "enabled": true },
  "clash_api": {
    "external_controller": "127.0.0.1:9097",
    "store_selected": true,
    "store_fakeip": false,
    "default_mode": "rule"
  }
}
```

Then switch via API:
```bash
curl -X PUT http://127.0.0.1:9097/proxies/select -d '{"name":"VMISS-HK"}'
```

## Speed Reference

Through OpenClash (testing from the router, bypassing Windows Schannel issues):
| Node | Speed | Notes |
|------|-------|-------|
| minipc-5g (via sing-box → 5G → Reality) | ~28 Mbps (7s, 25MB) | via OpenClash bwtest |
| Direct Windows curl → sing-box SOCKS5 → 5G | ~2-3 Mbps | LOWER due to Schannel not CPU — use --ssl-no-revoke |
