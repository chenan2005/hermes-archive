# Xray Config Export for Client Devices

Extract connection parameters from a running xray instance and present them in client-compatible format (v2rayNG, Clash, Sing-box, etc.).

## Finding the active config

xray instances from 3X-UI store config at `/usr/local/x-ui/bin/config.json`. Standalone xray uses whatever was passed with `-c`.

```bash
# Find the config path from the running process
ps aux | grep xray | grep -v grep | grep -oP '\-c \K\S+'
# → /usr/local/x-ui/bin/config.json
```

Then read it:

```bash
cat /usr/local/x-ui/bin/config.json
```

## Extracting client parameters from xray inbounds

Each `inbounds[]` entry defines one server port/protocol. Extract the fields below:

### Common fields (all protocols)

| JSON path | Client field | Example |
|-----------|-------------|---------|
| `inbounds[i].port` | Port | `443` |
| `inbounds[i].protocol` | Protocol | `vmess`, `vless` |
| `inbounds[i].settings.clients[0].id` | UUID / ID | `ac6aa939-...` |
| `inbounds[i].streamSettings.network` | Transport | `ws`, `tcp`, `kcp` |
| `inbounds[i].streamSettings.security` | TLS? | `tls`, `reality`, `none` |

### VMess+WebSocket+TLS

```json
{
  "port": 443,
  "protocol": "vmess",
  "settings": {"clients": [{"id": "ac6aa939-..."}]},
  "streamSettings": {
    "network": "ws",
    "security": "tls",
    "tlsSettings": {"serverName": "vmiss.bernarty.xyz"},
    "wsSettings": {"path": "/ws-vmiss"}
  }
}
```

| Client field | Value |
|-------------|-------|
| Address | Server IP or domain |
| Port | `443` |
| UUID | `ac6aa939-...` |
| Transport | WebSocket |
| Path | `/ws-vmiss` |
| TLS | On, SNI = `vmiss.bernarty.xyz` |

### VMess+WebSocket (no TLS)

Same as above but `security: "none"` — turn TLS OFF in client.

### VLESS+Reality

```json
{
  "port": 40001,
  "protocol": "vless",
  "settings": {
    "clients": [{"id": "a5fa1889-...", "flow": "xtls-rprx-vision"}],
    "decryption": "none"
  },
  "streamSettings": {
    "network": "tcp",
    "security": "reality",
    "realitySettings": {
      "dest": "www.microsoft.com:443",
      "serverNames": ["www.microsoft.com"],
      "privateKey": "4A7jrb8gbfL96N9Zb...",
      "shortIds": ["a1b2c3d4"],
      "settings": {
        "publicKey": "0o3XsyApUXA0_1Ns2GZP...",
        "fingerprint": "chrome",
        "spiderX": "/"
      }
    }
  }
}
```

| Client field | Value |
|-------------|-------|
| Address | Server IP (e.g. `43.108.41.245`) |
| Port | `40001` |
| UUID | `a5fa1889-...` |
| Flow | `xtls-rprx-vision` |
| Transport | TCP |
| TLS | Reality |
| SNI | `www.microsoft.com` |
| PublicKey | `0o3XsyApUXA0_1Ns2GZP...` |
| ShortId | `a1b2c3d4` |
| Fingerprint | `chrome` |

> **Note**: `realitySettings.settings` (publicKey, fingerprint, spiderX) are stored in the config but 3X-UI's UI may not generate them — they're inferred from privateKey + shortId by the client. However, v2rayNG needs the publicKey explicitly.

### VLESS+Reality without publicKey in config

If your config.json has `realitySettings` but **no `settings.publicKey`** (common with minimal 3X-UI DB insertion), retrieve the public key from the private key:

```bash
# On the server (xray binary can derive public from private)
# xray x25519 generates NEW key pairs — can't go backwards
# The publicKey must be saved at creation time

# Workaround: check 3X-UI database
sqlite3 /etc/x-ui/x-ui.db "SELECT stream_settings FROM inbounds WHERE port=40001;" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('realitySettings',{}).get('settings',{}).get('publicKey','NOT FOUND'))"

# Or: re-add the node via 3X-UI panel (saves publicKey in stream_settings)
```

If lost, regenerate keys and update both server and client — you cannot derive publicKey from privateKey.

## Converting to vmess:// link format

v2rayNG supports base64-encoded vmess:// links for easy import.

```python
import base64, json

config = {
    "v": "2",
    "ps": "VMISS-HK",           # display name
    "add": "vmiss.bernarty.xyz", # server address
    "port": "443",               # port (string!)
    "id": "ac6aa939-156c-452f-a7da-4ddd79b7d5c9",  # UUID
    "aid": "0",                  # alterId (should be 0 for modern servers)
    "scy": "auto",               # security — "auto" or "aes-128-gcm" or "chacha20-poly1305"
    "net": "ws",                 # network — "ws", "tcp", "kcp"
    "type": "none",              # header type
    "host": "vmiss.bernarty.xyz", # host (sent as HTTP Host header for WS)
    "path": "/ws-vmiss",         # path
    "tls": "tls"                 # "tls" if TLS enabled, "" if not
}

encoded = base64.b64encode(json.dumps(config).encode()).decode()
print(f"vmess://{encoded}")
```

**Important**: v2rayNG's vmess:// parser is strict. Fields must be strings (even port), `v` must be `"2"`, and extra fields may cause silent failures.

### For VLESS, use vless:// link format

```python
# With flow (recommended for latest v2rayNG)
link = (f"vless://{uuid}@{host}:{port}"
        f"?type=tcp"
        f"&security=reality"
        f"&flow=xtls-rprx-vision"
        f"&sni={sni}"
        f"&pbk={publicKey}"
        f"&sid={shortId}"
        f"&fp=chrome"
        f"&#{name}")

# Without flow (compatibility with older v2rayNG)
link = (f"vless://{uuid}@{host}:{port}"
        f"?type=tcp"
        f"&security=reality"
        f"&sni={sni}"
        f"&pbk={publicKey}"
        f"&sid={shortId}"
        f"&fp=chrome"
        f"&#{name}")
```

When the user's v2rayNG logs `"flow" doesn't support "xtls-rprx-vision"`, generate the no-flow variant.

## Generating QR codes for mobile clients

After generating the share links, create scannable QR codes so the user can add nodes by scanning, avoiding manual entry on mobile.

### QR code as PNG (requires `pip install qrcode[pil]`)

```python
import qrcode

# Generate from vmess:// or vless:// link
link = "vmess://eyJ2Ij..."  # your full share link
img = qrcode.make(link)
img.save("/home/chenan/proxy-node.png")
```

### QR code HTML page (recommended — shows multiple nodes)

Embed QR codes as base64 in a self-contained HTML page for browser display:

```python
import base64, qrcode

nodes = {
    "VMISS 香港 (VMess+WS+TLS)": "vmess://...",
    "Seoul Reality (VLESS+Reality)": "vless://..."
}

html = ['<!DOCTYPE html><html><head><meta charset="utf-8"><title>Proxy QR</title>'
        '<style>body{background:#111;color:#eee;font-family:system-ui;display:flex;'
        'flex-direction:column;align-items:center;padding:40px}'
        '.card{background:#222;border-radius:16px;padding:30px;margin:20px;text-align:center}'
        '.card img{width:320px;height:320px;border-radius:8px;background:#fff;padding:10px}'
        '</style></head><body>']

for name, link in nodes.items():
    img = qrcode.make(link)
    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    html.append(f'<div class="card"><h2>{name}</h2>'
                f'<img src="data:image/png;base64,{b64}"/>'
                f'<p>v2rayNG → + → 扫描二维码</p></div>')

html.append('</body></html>')
with open("/home/chenan/proxy-qr.html", "w") as f:
    f.write("\n".join(html))
```

The user opens the HTML in a browser, then scans the QR codes with v2rayNG's camera scanner.

**Pitfall**: terminal output may truncate long base64 strings (shows `eyJ2Ij...IifQ`). Always write links to a file or pipe directly into code — don't rely on terminal echo for verification.

## Distributing configs to Android devices via FRP tunnels

When the user's Android devices (phone, tablet) run Termux with SSH access behind NAT, copy config files through FRP tunnels:

```bash
# Realme phone (FRP tunnel → port 30205)
scp -P 30205 proxy-links.txt chen_@proxy.example.com:/data/data/com.termux/files/home/

# MagicPad tablet (FRP tunnel → port 30177)
scp -P 30177 proxy-links.txt u0_a250@proxy.example.com:/data/data/com.termux/files/home/
```

Use pipe-through-SSH instead of scp if scp truncates:

```bash
cat proxy-links.txt | ssh -p 30205 chen_@proxy.example.com \
  "cat > /data/data/com.termux/files/home/proxy-links.txt"
```

Verify with `wc -c` — the file should match the original byte count.

## Reality diagnostic with local xray client

When a user reports a Reality node "doesn't connect" on their phone, eliminate server-side issues by testing from a local xray client:

```bash
# 1. Download xray
curl -sL "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip" -o /tmp/xray.zip
unzip -o /tmp/xray.zip xray geosite.dat geoip.dat -d /tmp/ && chmod +x /tmp/xray

# 2. Create client config
cat > /tmp/xray-client.json << 'CONFIG'
{
  "log": {"loglevel": "info"},
  "inbounds": [{
    "listen": "127.0.0.1",
    "port": 10808,
    "protocol": "socks",
    "settings": {"udp": true}
  }],
  "outbounds": [{
    "protocol": "vless",
    "settings": {
      "vnext": [{
        "address": "SERVER_IP",
        "port": PORT,
        "users": [{
          "id": "UUID",
          "flow": "xtls-rprx-vision",
          "encryption": "none"
        }]
      }]
    },
    "streamSettings": {
      "network": "tcp",
      "security": "reality",
      "realitySettings": {
        "serverName": "SNI_DOMAIN",
        "fingerprint": "chrome",
        "publicKey": "PUBLIC_KEY",
        "shortId": "SHORT_ID"
      }
    }
  }]
}
CONFIG

# 3. Run xray client in background
/tmp/xray run -c /tmp/xray-client.json
# (use terminal background=true for Hermes)

# 4. Test through SOCKS proxy
curl -s --connect-timeout 8 --socks5-hostname 127.0.0.1:10808 \
  https://www.google.com -o /dev/null -w "HTTP:%{http_code} TTFB:%{time_starttransfer}s\n"
```

**Interpretation**:
- **HTTP:200** → server is fine, issue is client-specific (v2rayNG version too old, phone network filtering)
- **Connection timeout / TCP refused** → server unreachable (firewall, port blocked, xray not running)
- **TLS handshake succeeds but xray rejects** → key mismatch (publicKey/shortId wrong)

**Pitfall**: Some Android ISPs (China Mobile, China Telecom) throttle direct connections to Korean IPs. If the test from a local VPS works but the phone doesn't, try through Cloudflare Tunnel or switch to a less-throttled route.

### Common v2rayNG Reality issues

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Node shows "Connected" but no traffic | v2rayNG version < 1.8.13 (no Reality support) | Update v2rayNG to latest |
| Log says `infra/conf: VLESS users: "flow" doesn't support "xtls-rprx-vision" in this version` | v2rayNG bundles an older xray-core that lacks flow support | **Option A** (preferred): Update v2rayNG. **Option B** (workaround): Remove `&flow=xtls-rprx-vision` from the vless:// link entirely. Reality works without flow — just loses the Vision multi-plexing optimization (CPU difference negligible on phones). Keep all other params. |
| "Fail to connect" with no details | `publicKey` or `shortId` mismatch | Regenerate link from server config |
| Timeout after TLS handshake | Reality flow mismatch (client has flow but server doesn't) | Ensure server client entry has `"flow": "xtls-rprx-vision"` |

### Distributing APK updates to Android devices via FRP

When the user needs to update v2rayNG (or any APK) and the Play Store isn't available:

```bash
# 1. Download the latest APK (check arch: arm64-v8a for most modern phones)
curl -sL "https://github.com/2dust/v2rayNG/releases/download/2.2.4/v2rayNG_2.2.4_arm64-v8a.apk" -o /tmp/v2rayNG.apk

# 2. Transfer via FRP tunnel (pipe to avoid SCP truncation on large files)
cat /tmp/v2rayNG.apk | ssh -p 30205 -o ConnectTimeout=15 chen_@proxy.example.com \
  "cat > /data/data/com.termux/files/home/v2rayNG_2.2.4.apk"

# 3. Verify size matches
ssh -p 30205 chen_@proxy.example.com "ls -la v2rayNG_2.2.4.apk"

# 4. User installs via Termux on the Android device:
#    termux-open v2rayNG_2.2.4.apk
```

**Note**: 28.5MB transfers through a 15Mbps FRP tunnel take ~15-30 seconds. Set scp/ssh timeouts to 60-120s for APK transfers. Verify the destination file size matches the source before telling the user to install.

**APK signing variant pitfall**: The non-FDroid `.apk` files from 2dust's GitHub releases are signed with 2dust's self-signed certificate. Some Android systems (realme UI 6.0, some Xiaomi/Huawei skins) reject these with "安装包已损坏" (package corrupted) even when the file SHA256 matches GitHub exactly. **Always prefer the FDroid variant** when deploying to Chinese-branded Android phones:

| Variant | Signing | Compatibility | Filename pattern |
|---------|---------|---------------|-----------------|
| **FDroid** | F-Droid official key (well-trusted) | ✅ Works on all devices | `v2rayNG_*-fdroid_arm64-v8a.apk` |
| **Non-FDroid** | 2dust self-signed cert | ⚠️ May fail on Chinese ROMs | `v2rayNG_*_arm64-v8a.apk` |

Download URL pattern for FDroid version:
```bash
curl -sL "https://github.com/2dust/v2rayNG/releases/download/2.2.4/v2rayNG_2.2.4-fdroid_arm64-v8a.apk" -o /tmp/v2rayNG.apk
```

Verify SHA256 against the release page's clipboard-digest button before telling the user to install.

**Install methods on Android**: Two approaches work from Termux:

| Method | Command | Requirement |
|--------|---------|-------------|
| Package installer UI | `termux-open /path/to/app.apk` | User taps "Install" on screen — preferred |
| CLI (silent) | `pm install /data/local/tmp/app.apk` | Requires root (file must be under `/data/local/tmp/`, not Termux home) |

`pm install` reads from `/data/local/tmp/` only — files in `/data/data/com.termux/files/home/` get SELinux-denied with `"Unable to open file: ... Consider using a file under /data/local/tmp/"`. Termux cannot write there without root. Use `termux-open` instead — it invokes the Android package installer via Intent.

## Minimal field checklist for v2rayNG

| Field | Required for VMess+WS | Required for VLESS+Reality |
|-------|----------------------|---------------------------|
| Address | ✅ | ✅ |
| Port | ✅ | ✅ |
| UUID | ✅ | ✅ |
| Transport | ✅ (ws) | ✅ (tcp) |
| Path | ✅ (if WS) | ❌ |
| TLS | ✅ (on/off) | ✅ (Reality) |
| SNI | ✅ (if TLS) | ✅ |
| PublicKey | ❌ | ✅ |
| ShortId | ❌ | ✅ (can be empty but field must exist) |
| Flow | ❌ | ✅ (xtls-rprx-vision) |
| Fingerprint | ❌ | ✅ (chrome) |
