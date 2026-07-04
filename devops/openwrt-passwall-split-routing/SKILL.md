---
name: openwrt-passwall-split-routing
description: OpenWrt PassWall domain-level split-routing — route specific domains through different proxy nodes using V2Ray SNI routing (primary) or ipset+iptables (fallback). Use when PassWall shunt is insufficient or you hit IP-sharing collisions.
---

# OpenWrt PassWall Split-Routing

Route specific domains through different proxy nodes when PassWall's built-in shunt feature is insufficient (it only supports `_direct`, `_default`, `_blackhole` targets, not multiple proxy outbounds).

## Method comparison

| Method | Granularity | IP collisions | V2Ray-incompatible protocols |
|--------|------------|---------------|------------------------------|
| **SNI routing (recommended)** | Domain (SNI) | None | Needs SOCKS chain |
| ipset+iptables (fallback) | IP | Yes — shared IPs cause collateral routing | Direct (separate xray) |

**Always prefer SNI routing.** Use ipset+iptables only when SNI routing is impractical (e.g., you can't modify PassWall's V2Ray config).

## Primary method: V2Ray SNI routing + Xray chain

### Architecture

```
All traffic → iptables → PassWall V2Ray (dokodemo-door :1041)
  ├── SNI match: target domains → SOCKS outbound → 127.0.0.1:1071 → Xray → Reality/VLESS
  └── Default route → main proxy node (VMess/other)
```

PassWall's bundled `v2ray` binary is V2Ray, not Xray. For protocols V2Ray doesn't support (Reality, Hysteria2), chain through a SOCKS outbound to a separate Xray instance.

### Steps

#### 1. Extract node credentials

```bash
ssh root@openwrt.lan.11
uci show passwall.<node_name>  # UUID, address, port, streamSettings, etc.
```

#### 2. Create secondary Xray config

`/etc/xray-seoul.json` — SOCKS inbound only (V2Ray connects to it):

```json
{
  "log": {"loglevel": "warning"},
  "inbounds": [{
    "port": 1071,
    "protocol": "socks",
    "listen": "127.0.0.1",
    "sniffing": {"enabled": true, "destOverride": ["http", "tls"]},
    "settings": {"udp": true, "auth": "noauth"}
  }],
  "outbounds": [{
    "protocol": "vless",
    "tag": "secondary",
    "settings": { "vnext": [{"address": "...", "port": ..., "users": [...]}] },
    "streamSettings": { ... }
  }]
}
```

#### 3. Patch PassWall's V2Ray config

Add two things to `/tmp/etc/passwall/TCP_SOCKS.json`:

a) **SOCKS outbound** (insert after main proxy outbound, before `direct`):
```json
{
  "protocol": "socks",
  "tag": "secondary_socks",
  "settings": {"servers": [{"address": "127.0.0.1", "port": 1071}]}
}
```

b) **Routing rules** (replace empty `"rules": []`):
```json
{
  "type": "field",
  "outboundTag": "secondary_socks",
  "domain": [
    "domain:accounts.google.com",
    "domain:oauth2.googleapis.com",
    ...
  ]
}
```

Critical: keep ALL other fields identical to PassWall's generated config — especially `mark: 255` on outbounds (this is how V2Ray bypasses PassWall's own iptables REIRECT via the `mark match 0xff` RETURN rule in nat OUTPUT).

Then restart V2Ray TCP:
```bash
PID=$(ps | grep "TCP_SOCKS.json" | grep -v grep | awk '{print $1}')
kill $PID; sleep 1
/tmp/etc/passwall/bin/v2ray run -c /tmp/etc/passwall/TCP_SOCKS.json > /tmp/passwall-tcp.log 2>&1 &
```

#### 4. Ensure target domains reach V2Ray

PassWall's GFWList may not cover all target domains. If traffic goes direct (bypassing the proxy entirely), SNI routing never triggers. Check:

```bash
IP=$(nslookup accounts.google.com 127.0.0.1 | grep Address | tail -1 | awk '{print $2}')
ipset test passwall_gfwlist $IP  # if "NOT in set" → traffic goes direct → fix needed
```

Fix options:
- **A (quick)**: Add Google IP ranges to `passwall_blacklist`
- **B (persistent)**: Add domains to `proxy_host` via UCI:
  ```bash
  uci add_list passwall.@global_rules[0].proxy_host="accounts.google.com"
  uci commit passwall && /etc/init.d/passwall restart
  ```
  This adds dnsmasq rules that route domain DNS through overseas servers and tag IPs for proxy redirect. Then re-inject the V2Ray config (step 3).

#### 5. Persist across reboots

PassWall regenerates its config on every restart. Create two init scripts:

**`/etc/init.d/xray-seoul`** (START=98): Starts the secondary Xray.
**`/etc/init.d/v2ray-seoul-inject`** (START=99, after PassWall):

```sh
#!/bin/sh /etc/rc.common
START=99
start() {
    sleep 15  # wait for PassWall to fully start
    # Add Google IPs to blacklist
    for cidr in 173.194.0.0/16 142.250.0.0/15 ...; do
        ipset add passwall_blacklist $cidr 2>/dev/null
    done
    # Inject unified V2Ray config if not already injected
    if ! grep -q "secondary_socks" /tmp/etc/passwall/TCP_SOCKS.json; then
        cp /etc/v2ray-unified.json /tmp/etc/passwall/TCP_SOCKS.json
        PID=$(ps | grep "TCP_SOCKS.json" | grep -v grep | awk '{print $1}')
        [ -n "$PID" ] && kill $PID; sleep 1
        /tmp/etc/passwall/bin/v2ray run -c /tmp/etc/passwall/TCP_SOCKS.json > /tmp/passwall-tcp.log 2>&1 &
    fi
}
```

Store the unified config as `/etc/v2ray-unified.json`.

### Verification

```bash
# SOCKS test (domain routing always works here)
curl -s --socks5-hostname 127.0.0.1:1070 -o /dev/null -w "HTTP:%{http_code}\n" https://accounts.google.com

# Transparent proxy test from LAN device
curl -s -o /dev/null -w "HTTP:%{http_code}\n" https://accounts.google.com

# Check V2Ray routing
grep "secondary_socks" /tmp/passwall-tcp.log

# Check Xray log (should show target domains)
tail /tmp/xray-seoul.log

# Verify YouTube is NOT on secondary
grep "googlevideo\|youtube" /tmp/xray-seoul.log  # should be EMPTY
```

## Fallback method: ipset + iptables (use only when SNI routing is impractical)

This method works at IP level — dnsmasq tags resolved IPs, iptables redirects them to a separate xray instance.

**Major pitfall: IP collisions.** Google services share IPs. If `accounts.google.com` resolves to the same IP as `googlevideo.com`, YouTube video traffic gets routed through the secondary proxy. Worse, unrelated services (Facebook, Twitter) can get pulled in if any Google auth domain uses shared CDN IPs. Only use this method if you can't modify PassWall's V2Ray config.

See `references/ipset-iptables-fallback.md` for the full setup if needed.

## References

- `references/reality-node-uci-config.md` — PassWall Reality 节点 UCI 配置要点（`reality='1'`、`tls='1'`、IP vs 域名）

## Pitfalls

1. **PassWall shunt can't reference nodes**: `_direct`, `_default`, `_blackhole` only. Custom node names are silently ignored.
2. **V2Ray ≠ Xray**: PassWall's bundled binary is V2Ray, not Xray. No Reality/Hysteria2 support. Chain through SOCKS to a separate Xray.
3. **GFWList gaps**: `accounts.google.com` may not be in GFWList → traffic goes direct → never reaches V2Ray for SNI routing. Fix with proxy_host or blacklist.
4. **Config overwrite**: PassWall regenerates config on restart. Use init script injection (step 5).
5. **Mark 255/0xFF is required**: This is how V2Ray outbound traffic bypasses PassWall's iptables REIRECT in the nat OUTPUT chain. Don't remove or change it.
6. **Runtime files not generated**: Even with `proxy_host` correctly configured in uci, PassWall may fail to write runtime files (`/tmp/etc/passwall/proxy_host`, `/tmp/etc/dnsmasq.d/passwall.conf`). DNS queries for those domains never populate the ipsets, so traffic goes direct silently. See `references/diagnose-runtime-files.md` for the complete diagnostic workflow. Fix: `/etc/init.d/passwall restart`.
7. **ipset IP collisions** (fallback method only): Google shares IPs across services. SNI routing avoids this entirely.
8. **DNS must go through dnsmasq** (fallback method only): If client uses DoH/DoT, ipset won't populate.
9. **Cross-border bandwidth is the proxy's ceiling**: A VPS may have 200Mbps+ advertised bandwidth, but the China→X link often delivers <1Mbps. Test raw (no proxy) first. If raw is slow, no protocol or port change will help.
10. **Proxy protocol overhead is usually negligible**: Compare raw vs proxied speed for the same file. If the difference is <0.2Mbps, don't blame the protocol — it's the network.

## Testing proxy bandwidth

```bash
# CacheFly 100MB — good global benchmark, no geo-restrictions
curl -s --max-time 20 --socks5-hostname 127.0.0.1:1070 -o /dev/null \
  -w "DL:%{size_download}B t:%{time_total}s sp:%{speed_download}B/s\n" \
  "http://cachefly.cachefly.net/100mb.test"
```

### Diagnosing bandwidth bottlenecks (three-layer method)

When a proxy node feels slow, isolate the bottleneck by testing three layers:

**Layer 1 — Server self-test:** SSH into the VPS and test raw bandwidth to speedtest servers:
```bash
ssh user@vps
# Tokyo Linode — great for Asian VPS
curl -s --max-time 15 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s sp:%{speed_download}B/s\n" \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin"
```

**Layer 2 — Raw TCP (no proxy):** From OpenWrt, download the same file directly from the VPS:
```bash
# Start temporary HTTP server on the VPS
ssh user@vps 'cd /tmp && python3 -m http.server 8888'

# From OpenWrt, download directly (no proxy)
ssh root@openwrt 'curl -s --max-time 20 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s sp:%{speed_download}B/s\n" \
  "http://VPS_IP:8888/100mb.bin"'
```

**Layer 3 — Through proxy:** Same file through the proxy SOCKS port:
```bash
curl -s --max-time 20 --socks5-hostname 127.0.0.1:1070 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s sp:%{speed_download}B/s\n" \
  "http://VPS_IP:8888/100mb.bin"
```

If L1 is fast (>50 MB/s) but L2 and L3 are similarly slow, the bottleneck is the cross-border link (e.g., China→Korea), not the proxy protocol. Changing ports, protocols, or encryption won't help.

If L2 is fast but L3 is slow, the proxy protocol or client-side config is the bottleneck.

## Cloudflare CDN acceleration

When direct cross-border bandwidth is poor (<1Mbps) but the VPS itself has good speed, Cloudflare CDN can drastically improve throughput (30-50x in our tests). Traffic flows:

```
Client(China) → Cloudflare edge(HK/JP) → CF backbone → VPS origin
```

### Method A: Cloudflare DNS proxy (recommended, permanent)

Requires the domain to be on Cloudflare DNS (full NS delegation).

**1. Migrate DNS to Cloudflare**
- Add domain at dash.cloudflare.com
- Import existing A/CNAME records (set non-proxy services to DNS-only, ⚪)
- Add proxy-enabled A record: `seoul.yourdomain.com → YOUR_VPS_IP` (🟠)
- Change NS at registrar from current (DNSPod, etc.) to Cloudflare's NS
- Wait for propagation (minutes to hours)

**2. Configure origin server**
- Add a VMess+WS+TLS inbound on port 443 (or 80 + Cloudflare handles TLS)
- Use a self-signed cert (Cloudflare "Full" SSL mode accepts it)
- Cloudflare's default SSL mode is "Full" — no further config needed

**3. Client connects to Cloudflare-proxied domain**
- PassWall node: address = `seoul.yourdomain.com`, port = 443
- Cloudflare terminates TLS at edge, proxies WS to origin via HTTPS
- Same speed as the Cloudflare tunnel test — typically 25-40Mbps

### Method B: Cloudflare Tunnel (for quick testing or as permanent systemd service)

Use `cloudflared` to create a `*.trycloudflare.com` tunnel — no DNS changes needed:

```bash
# On the VPS
curl -sL https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/cloudflared-linux-amd64 -o /tmp/cloudflared
chmod +x /tmp/cloudflared
cd /tmp && python3 -m http.server 9999 &
/tmp/cloudflared tunnel --url http://127.0.0.1:9999
# Output: https://random-words.trycloudflare.com

# From OpenWrt
curl -s --max-time 30 "https://random-words.trycloudflare.com/100mb.bin"
```

**For permanent deployment** (systemd service, auto-reconnect on crash/reboot):

```bash
sudo cp /path/to/cloudflared /usr/local/bin/cloudflared
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

sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared
```

After starting, retrieve the tunnel URL from journalctl:
```bash
sudo journalctl -u cloudflared --no-pager -n 20 | grep -o 'https://[a-z0-9.-]*\.trycloudflare\.com'
```

**Pitfall: trycloudflare.com DNS SERVFAIL on OpenWrt.** OpenWrt's dnsmasq + chinadns-ng returns SERVFAIL for `*.trycloudflare.com`. Fix by adding the Cloudflare IP to `/etc/hosts`:

```bash
# Get CF IPs from public DNS
IP=$(dig @1.1.1.1 +short tries-words.trycloudflare.com | head -1)
echo "$IP tries-words.trycloudflare.com" >> /etc/hosts
```

**Version note**: cloudflared 2026.6.1 quick tunnel fails with `"invalid UUID length: 0"`. Use **2024.12.2** or earlier for reliable quick tunnel creation.

### Interpreting results

Compare three measurements:
| Test | Expected |
|------|----------|
| VPS self-test to CDN | 500+ Mbps |
| OpenWrt → VPS (raw) | 0.5-5 Mbps (China cross-border) |
| OpenWrt → VPS via Cloudflare | 20-40 Mbps (30-50x improvement) |

If Cloudflare helps, the cross-border link is the bottleneck. If throughput is similar, the VPS's total bandwidth or peering is the limit.


## References

- `references/google-auth-domains.md` — Complete list of Google authentication domains
- `references/iptables-redirect-listen.md` — Why 0.0.0.0 vs 127.0.0.1 matters for REDIRECT
- `references/sni-routing-v2ray-config.md` — Detailed V2Ray config injection walkthrough
- `references/ipset-iptables-fallback.md` — Full ipset+iptables setup (for when SNI routing is impractical)
- `references/cloudflare-dns-migration.md` — Moving DNS from DNSPod to Cloudflare for CDN acceleration
- `references/diagnose-runtime-files.md` — Step-by-step diagnostic when proxy_host domains are configured but traffic still goes direct (runtime files not generated)

## Templates

- `templates/xray-secondary.json` — Skeleton Xray config for secondary proxy (SOCKS inbound)
- `templates/v2ray-unified-config.json` — Annotated V2Ray unified config with SOCKS outbound + SNI routing rules
