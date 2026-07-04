---
name: openwrt-proxy-acceleration
description: Diagnose and accelerate China cross-border proxy bandwidth on OpenWrt PassWall. Covers bottleneck identification, Cloudflare Tunnel/CDN acceleration, SNI-based split routing.
category: devops
triggers:
  - proxy slow
  - bandwidth bottleneck
  - cloudflare accelerate
  - passwall split routing
  - china international link
  - cross border speed
---

# OpenWrt Proxy Bandwidth Diagnosis & Acceleration

## Bottleneck Diagnosis Flow

Test server-side bandwidth first, then compare through proxy to isolate the bottleneck:

```
Seoul服务器本机 → 东京CDN: 600Mbps+  → 服务器没问题
OpenWrt裸连Seoul:   ~0.75Mbps       → 跨境链路瓶颈
OpenWrt→CF→Seoul:   25-40Mbps      → CF有效
```

### Step 1: Server bare bandwidth
```bash
ssh <server>
curl -s --max-time 15 -o /dev/null -w "DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin"
```

### Step 2: OpenWrt raw HTTP test (no proxy)
On Seoul ECS, start a simple HTTP server and test from OpenWrt:
```bash
# Seoul side
cd /tmp
dd if=/dev/zero bs=1M count=100 of=100mb.bin
python3 -m http.server 9999 &

# OpenWrt side
curl -s --max-time 30 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "http://<seoul-ip>:9999/100mb.bin"
```

### Step 3: Through-proxy speed test
```bash
# Via PassWall SOCKS
curl -s --max-time 20 --socks5-hostname 127.0.0.1:1070 -o /dev/null \
  -w "DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin"
```

## Cloudflare Tunnel Acceleration Test

Use `cloudflared` to create a quick tunnel and test if Cloudflare's backbone helps.
**Use v2024.12.2** — newer versions have a UUID parsing bug with quick tunnels.

```bash
# Install
curl -sL https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/cloudflared-linux-amd64 -o /tmp/cf-old
chmod +x /tmp/cf-old

# Start HTTP server + tunnel
/tmp/cf-old tunnel --url http://127.0.0.1:9999 > /tmp/cf-out.log 2>&1 &
sleep 10
CF_URL=$(grep -o "https://[a-z0-9.-]*\.trycloudflare\.com" /tmp/cf-out.log | head -1)

# Test from OpenWrt
curl -s --max-time 30 -o /dev/null -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" "$CF_URL/100mb.bin"
```

## Cloudflare CDN Production Setup (VMess+WS)

The production setup uses Cloudflare's DNS proxy (orange cloud) instead of cloudflared.
Same pattern as running KVM behind Cloudflare at 40Mbps.

### Architecture

```
OpenWrt → seoul.domain.com:80 (VMess+WS, HTTP)
       → Cloudflare edge (proxied, TLS terminated at edge)
       → Seoul:80 (VMess+WS, no TLS)
```

### Steps

1. **Add domain to Cloudflare** (free plan), enable orange cloud proxy for the subdomain.

2. **Set Cloudflare SSL/TLS to "Flexible"** (not Full). Flexible sends HTTP to origin port 80. Full sends HTTPS — won't work with VMess unless origin presents a valid cert.

3. **Origin (Seoul): VMess+WS on port 80, no TLS**:
```json
{
  "listen": "0.0.0.0", "port": 80, "protocol": "vmess",
  "settings": {"clients": [{"id": "<uuid>", "email": "openwrt-cf"}]},
  "streamSettings": {
    "network": "ws", "security": "none",
    "wsSettings": {"path": "/ws-seoul"}
  }
}
```

4. **OpenWrt PassWall node**: address=the domain, port=80, tls=0, transport=ws, path=/ws-seoul.

5. DNS resolves to Cloudflare IPs (104.x, 172.x). Cloudflare proxies to origin.

### x-ui Config Pitfall

3X-UI **regenerates config.json from its SQLite database** on every panel operation or x-ui restart.
Manual edits to `/usr/local/x-ui/bin/config.json` get overwritten on `x-ui restart`. This means:

- Editing config via SQLite (sudo sqlite3 /etc/x-ui/x-ui.db) works but gets overwritten on x-ui restart
- Editing `/usr/local/x-ui/bin/config.json` directly works but gets overwritten on x-ui restart
- Editing the DB + restarting x-ui: changes persist but ONLY if DB fields are correctly formatted

To bypass this for a config with non-standard inbounds:

```bash
# 1. Stop x-ui
sudo systemctl stop x-ui

# 2. Write clean config with ALL required inbounds (Reality, VMess+WS, etc.)
#    Include outbounds and remove metrics/api to avoid port conflicts
sudo tee /usr/local/x-ui/bin/config.json << 'CONFIG'
{
  "log": {"loglevel": "warning"},
  "inbounds": [
    { "port": 40001, "protocol": "vless", ... },   # Reality
    { "port": 80, "protocol": "vmess", ... },      # WS (no TLS, for Cloudflare)
    { "port": 443, "protocol": "vmess", ... }       # WS+TLS (self-signed, for direct)
  ],
  "outbounds": [
    {"protocol": "freedom", "tag": "direct"},
    {"protocol": "blackhole", "tag": "blocked"}
  ]
}
CONFIG

# 3. Run xray directly (NOT through x-ui)
sudo /usr/local/x-ui/bin/xray-linux-amd64 -c /usr/local/x-ui/bin/config.json &

# 4. Never restart x-ui afterward (or the config is lost)
# To auto-start on boot, create a systemd service for xray directly
```

### Cloudflare SSL Mode Decision Tree

| Origin setup | Required CF SSL mode | Why |
|-------------|---------------------|-----|
| VMess+WS on port **80** (no TLS) | **Flexible** | CF sends HTTP to origin:80. Full sends HTTPS → WS handshake fails on TLS port |
| VMess+WS+TLS on port **443** (self-signed cert) | **Full** (not strict) | CF sends HTTPS, accepts any origin cert |
| VMess+WS+TLS on port **443** (Let's Encrypt/CA cert) | **Full (strict)** | CF validates origin cert per CA chain |

**Default for new Cloudflare zones is `Full`** — which works for self-signed port 443 but BREAKS for port-80-only setups. Change to `Flexible` if your origin runs VMess+WS on 80.

> **Why `Full` breaks port-80 WS:** `Full` sends HTTPS to the origin. If origin is listening on port 80 with WS (no TLS), it expects HTTP. The TLS handshake from Cloudflare arrives, the origin's WS server sees garbage (TLS bytes, not HTTP), and the connection fails silently — no error message, just timeout on the client side.

| Test | Direct CN→KR | Via Cloudflare |
|------|:-----------:|:------------:|
| Server→Tokyo | 620 Mbps | same |
| OpenWrt→Seoul raw | ~0.75 Mbps | ~25-40 Mbps |
| YouTube experience | 240p only | 1080p+ |

Cloudflare improves China→Korea routes **33-50x** by routing through their backbone (likely Hong Kong/Japan).

## PassWall Node Verification & Testing

PassWall may have proxy nodes registered in the UCI database that aren't set as the active TCP/UDP node. Verify ALL nodes are alive:

```bash
# List all nodes with their IDs
for id in $(uci show passwall | grep "=nodes" | cut -d= -f1 | cut -d. -f2); do
  echo "$id: $(uci get passwall.$id.remarks 2>/dev/null) - $(uci get passwall.$id.address 2>/dev/null):$(uci get passwall.$id.port 2>/dev/null)"
done
```

### Test a specific node via temporary switch

```bash
old=$(uci get passwall.@global[0].tcp_node)
uci set passwall.@global[0].tcp_node=<NODE_ID>
uci commit passwall
/etc/init.d/passwall restart
sleep 8
curl -sx "socks5://127.0.0.1:1070" --max-time 10 https://cp.cloudflare.com/generate_204 \
  -o /dev/null -w "%{http_code} %{time_total}s"
# Restore original node
uci set passwall.@global[0].tcp_node=$old
uci commit passwall
/etc/init.d/passwall restart
```

Set `NODE_ID` from the output above (e.g., `cfg131c7e` for Seoul-CF, `cfg141c7e` for VMISS-HK).

## SNI-based Split Routing in PassWall V2Ray

Route specific domains through a different proxy node at the SNI level (bypasses IP collision issues from ipset-based routing).

### Architecture
```
V2Ray inbound -> SNI domain matching -> Seoul outbound or KVM outbound
```

### Implementation

1. Inject Seoul xray as SOCKS upstream:
```bash
/usr/bin/xray run -c /etc/xray-seoul.json > /tmp/xray-seoul.log 2>&1 &
```

2. Patch PassWall's generated V2Ray config (keep template at `/etc/v2ray-unified.json`):
   - Add SOCKS outbound pointing to `127.0.0.1:1071`
   - Add routing rules with SNI domain list
   - Copy config over PassWall's TCP_SOCKS.json after each PassWall restart

3. See `references/passwall-sni-routing.md` for the full unified config JSON structure.
4. See `references/seoul-xray-config.md` for the Seoul server multi-inbound xray config.

### DNS + iptables support

Add Google auth domains to PassWall's proxy_host list and Google IP ranges to blacklist:
```bash
# UCI
for domain in accounts.google.com oauth2.googleapis.com ...; do
  uci add_list passwall.@global_rules[0].proxy_host="${domain}"
done

# Blacklist (ensure Google IPs get caught by redirect)
for cidr in 173.194.0.0/16 142.250.0.0/15 142.251.0.0/16 216.58.192.0/19 216.239.32.0/19 64.233.160.0/19 74.125.0.0/16 172.217.0.0/16; do
  ipset add passwall_blacklist $cidr 2>/dev/null
done
```

## Cloudflare Tunnel Production Setup (systemd)

A persistent alternative to CDN proxy. Does NOT require Cloudflare DNS — works with any DNS provider.

### Architecture

```
OpenWrt → trycloudflare-random.trycloudflare.com:443 (VMess+WS+TLS)
       → Cloudflare edge → tunnel → cloudflared (Seoul) → localhost:80 → xray
```

Warning: The quick tunnel URL changes on cloudflared restart. For a stable URL, use a named tunnel with `cloudflared tunnel create`.

### Systemd Service

```bash
# Install (use v2024.12.2 - newer versions have UUID parsing bug)
sudo cp /tmp/cf-old /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# Create service
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:80
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now cloudflared
```

### Retrieve tunnel URL

```bash
sudo journalctl -u cloudflared --no-pager -n 30 | grep -oP 'https://[a-z0-9.-]+\.trycloudflare\.com' | tail -1
```

### DNS resolution caveat

Chinese DNS resolvers (including OpenWrt dnsmasq + chinadns-ng) may return `SERVFAIL` for `*.trycloudflare.com`. Add tunnel hostname to /etc/hosts on OpenWrt:

```bash
echo "<cloudflare-ip> <tunnel-hostname>.trycloudflare.com" >> /etc/hosts
```

Resolve IP from Google DNS (8.8.8.8) or Cloudflare DNS (1.1.1.1) since they resolve correctly.

### OpenWrt PassWall node for tunnel

Configure a PassWall node with the tunnel hostname as address:

```
address=<tunnel-hostname>.trycloudflare.com
port=443
tls=1
tls_serverName=<tunnel-hostname>.trycloudflare.com
transport=ws
ws_path=/ws-seoul
ws_host=<tunnel-hostname>.trycloudflare.com
```

### Speed comparison

| Method | Speed | Requires Cloudflare DNS? |
|--------|:----:|:------------------------:|
| Direct CN→KR | ~0.75 Mbps | No |
| Cloudflare CDN (orange cloud) | ~25-40 Mbps | Yes |
| Cloudflare Tunnel (quick tunnel) | ~15-28 Mbps | No |
| KVM (US + Cloudflare) | ~40 Mbps | Yes (optional) |

### Stop x-ui from overwriting manual config

3X-UI regenerates config.json from its SQLite database on restart. For persistent manual configs:

```bash
sudo systemctl stop x-ui
# Write your custom config
sudo tee /usr/local/x-ui/bin/config.json << 'CONFIG'
{ ... inbounds, outbounds ... }
CONFIG
# Run xray directly
sudo /usr/local/x-ui/bin/xray-linux-amd64 -c /usr/local/x-ui/bin/config.json &
# Do NOT restart x-ui afterward
```

## Pitfalls

- **ipset IP routing causes IP collision**: Google shares IPs across services. ipset-based routing will route YouTube traffic through the auth proxy if they hit the same IP. Always prefer SNI/domain-based routing.
- **V2Ray DNS loop**: V2Ray's internal DNS can create circular dependencies. Use `dns.servers: ["localhost"]` or use IP addresses directly.
- **PassWall overwrites config**: Every restart regenerates TCP_SOCKS.json. Use a post-generation hook (init script START=99 after PassWall) to re-inject the unified config.
- **Port QoS**: Different proxy ports may get different QoS treatment. Port 443 (HTTPS) sometimes gets better bandwidth than high ports. On Alibaba Cloud Seoul, port QoS is negligible vs the physical link limit.
- **China cross-border BW**: China->Japan/Korea often <1Mbps. China->US via Cloudflare can be 40Mbps+. The bottleneck is the physical international link, not the proxy protocol.
- **Cloudflare + VMess SSL mode**: Must use "Flexible" (not Full) when origin has no TLS. Full mode sends HTTPS to origin:80 which breaks VMess.
- **Self-signed certs with Cloudflare proxy**: Cloudflare Full (strict) requires a valid CA-signed cert. Self-signed certs only work with Full (non-strict) mode. For VMess+WS without TLS, use Flexible mode instead.
