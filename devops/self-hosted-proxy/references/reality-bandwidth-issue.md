# Reality Protocol Bandwidth Throttling

## Finding (2026-06-19)

VLESS+Reality on Alibaba Cloud Seoul (shared 200Mbps) was severely throttled to ~0.5-0.8 Mbps when accessed from China (OpenWrt behind China Telecom), despite the server itself having 620Mbps bandwidth to Tokyo.

## Test results

| Path | Speed |
|------|-------|
| Seoul ECS → Tokyo Linode (direct) | **620 Mbps** (100MB in 1.3s) |
| OpenWrt → Seoul Reality → Tokyo Linode | **0.6 Mbps** (1.6MB in 20s) |
| OpenWrt → KVM VMess+WS+TLS → Tokyo Linode | **40 Mbps** (100MB in 20s) |

Both KVM and Seoul tested from the same OpenWrt, through the same GFW, at the same time. Two different xray binaries (Xray 26.5.3 and V2Ray 5.22) gave identical results on both paths — ruling out a client-side binary issue.

## Server config verified clean

3X-UI config.json inspected:
- No bandwidth limits in `policy.levels`
- No per-user rate limiting
- `statsUserDownlink: true` but no `bufferSize` or bandwidth caps

## Root cause (likely)

The GFW appears to throttle Reality protocol traffic on certain paths/ports more aggressively than VMess+WS+TLS. Possible mechanisms:

1. **Protocol fingerprinting**: Reality's TLS fingerprint (chrome, www.microsoft.com SNI) on port 40001 may trigger different QoS rules than VMess+WS+TLS on 30717
2. **Non-443 port penalization**: Reality on port 40001 (non-standard) may be throttled harder; Xray itself warns "Listening on non-443 ports may get your IP blocked"
3. **Cloud provider throttling**: Alibaba Cloud's "shared 200Mbps" may have aggressive China→Korea international bandwidth caps
4. **TCP-over-TCP meltdown**: Reality uses TCP transport; nested TCP congestion control can amplify loss

## Mitigation: Cloudflare Tunnel (verified, 33-53x improvement)

When the cross-border link itself is the bottleneck (Layer 2 = slow), Cloudflare's free tunnel can dramatically improve throughput. Found: China→Korea link went from 0.75 Mbps direct to 24-40 Mbps through Cloudflare — matching KVM's performance.

### How it works

```
Client → Cloudflare edge (HK/JP PoP) → Cloudflare backbone → cloudflared tunnel → Seoul
```

Cloudflare backbone bypasses congested China→Korea bilateral peering. Edge PoP selection is automatic via Anycast.

### Test results

| Path | Speed | vs Direct |
|------|-------|-----------|
| Direct China→Seoul (raw HTTP) | 0.75 Mbps | 1x |
| China→Cloudflare→Seoul tunnel | **24-40 Mbps** | **33-53x** |
| Comparison: KVM (US, VMess) | 40 Mbps | ~same |

### Quick bandwidth test (cloudflared tunnel)

```bash
# On VPS:
curl -sL https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/cloudflared-linux-amd64 -o /tmp/cf
chmod +x /tmp/cf
cd /tmp && dd if=/dev/zero bs=1M count=100 of=100mb.bin
python3 -m http.server 9999 &
/tmp/cf tunnel --url http://127.0.0.1:9999
# Prints: https://xxxx.trycloudflare.com

# On client:
curl -s --max-time 30 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "https://xxxx.trycloudflare.com/100mb.bin"

# Compare with direct:
curl -s --max-time 20 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s\n" \
  "http://<VPS_IP>:9999/100mb.bin"
```

### Version note

- **cloudflared 2024.12.2**: quick tunnel works reliably
- **cloudflared 2026.6.1**: quick tunnel fails with `"invalid UUID length: 0"` — use older version

### Limitations

- `trycloudflare.com` tunnels have **no uptime guarantee** (~24h expiration)
- For production: set up a **named tunnel** with registered domain (free tier, requires Cloudflare account)
- Free plan has no China-optimized edge (Enterprise only), but non-China edges still outperform direct links

### When Cloudflare tunnel may NOT help

- **VPS bandwidth cap** (Layer 1 slow) → tunnel adds overhead
- **Protocol overhead** (Layer 3 << Layer 2) → tunnel adds another layer
- **Both sides outside China** → direct path is probably fine

## Cloudflare CDN proxy (Option B, no cloudflared required)

Alternative to cloudflared tunnel: use Cloudflare's DNS proxy (orange cloud) with VMess+WS+TLS on the origin. The client connects to `seoul.bernarty.xyz` (resolves to Cloudflare IPs), Cloudflare terminates TLS and proxies WebSocket traffic to the origin's VMess port.

### Architecture

```
Client V2Ray → seoul.bernarty.xyz:443 (Cloudflare IP) → Cloudflare CDN → origin:443 (VMess+WS+TLS)
```

### Setup steps

1. **Move DNS to Cloudflare** (or add zone if using subdomain delegation)
   - Cloudflare nameservers: `adele.ns.cloudflare.com`, `weston.ns.cloudflare.com`
   - Change at domain registrar (Tencent Cloud → 域名管理 → 修改 DNS 服务器)

2. **Add DNS records**
   - The zone is in `pending` status until registrar NS change propagates
   - After migration, test with `dig +short seoul.bernarty.xyz` (should return Cloudflare IPs like `104.21.x.x`)

3. **Configure VMess+WS+TLS inbound on the origin server**
   - Generate a self-signed cert matching the domain: `openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 3650 -nodes -subj "/CN=seoul.bernarty.xyz"`
   - Add inbound via 3X-UI database (port 443, protocol=vmess, network=ws, security=tls)
   - wsSettings: `{"path": "/ws-seoul"}`
   - tlsSettings: `{"serverName": "seoul.bernarty.xyz", "certificates": [{"certificateFile": "...", "keyFile": "..."}]}`

4. **Client (PassWall) node config**
   ```
   type=V2ray, protocol=vmess
   address=seoul.bernarty.xyz, port=443
   uuid=<same as server>
   transport=ws, ws_path=/ws-seoul, ws_host=seoul.bernarty.xyz
   tls=1, tls_serverName=seoul.bernarty.xyz
   ```

### Pitfalls

- **SSL mode must be "Full"** (not "Flexible"). Default for new Cloudflare zones is "Flexible", which sends HTTP to origin (not HTTPS). "Full" sends HTTPS and accepts self-signed origin certs. Set at: Dashboard → SSL/TLS → Overview → Full.
- **Cloudflare API token must have SSL/TLS permissions** to read/change `zones/settings/ssl`. A DNS-only token (from "Edit zone DNS" template) returns 403 on `/settings/ssl`.
- **Self-signed origin cert and Cloudflare Full** mode works — no need for Cloudflare Origin CA.
- **WebSocket is enabled by default** on all Cloudflare plans. No special config needed.
- **cloudflared quick tunnel (Option A) vs CDN proxy (Option B)**: Option A is easier to test (no DNS changes needed), but the `trycloudflare.com` URL expires ~24h. Option B is more stable (permanent subdomain) but requires DNS migration and SSL mode verification.

## Security groups matter

Alibaba Cloud ECS security group only allows specific inbound ports by default. When testing raw bandwidth:

| Port | Allowed by default | Use case |
|------|-------------------|----------|
| 22 | ✅ Yes | SSH |
| 80 | ❌ No | HTTP test server |
| 443 | ❌ No | HTTPS/VMess |
| 8080 | ❌ No | Alternative HTTP |
| 40001 | ✅ Yes (was xray port) | xray Reality |
| 12345 | ❌ No | nc test |

**For bandwidth tests**, use an already-allowed port (22 for SSH throughput, or the xray port that's already open). Opening new ports requires security group console or CLI.

## Other mitigation options

1. **Use VMess+WS+TLS** on Seoul (same protocol as KVM which achieves 40Mbps)
2. **Add Hysteria2 as acceleration bypass** (QUIC-based, handles poor links better)
3. **Cloudflare Tunnel** (33-53x verified improvement — see section above)
4. **Try different dest domain** for Reality (www.microsoft.com may be flagged)
5. **Test with different Chinese ISP** (throttling may be China Telecom-specific)

## Diagnostic workflow

**Three-layer isolation** — test each layer independently to pinpoint the bottleneck:

```bash
# Layer 1: Server-side self-test (measures raw VPS bandwidth)
ssh seoul-vps
curl -s --max-time 15 -o /dev/null -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s\n" \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin"
# Example: 100MB in 1.3s = 620 Mbps → server bandwidth is fine

# Layer 2: Client→Server RAW test (measures bare cross-border link, NO proxy)
# Start HTTP server on VPS: cd /tmp && dd if=/dev/zero bs=1M count=100 of=100mb.bin && sudo python3 -m http.server 80
# Then from client:
curl -s --max-time 30 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "http://<SERVER_IP>/100mb.bin"
# Example: 2.87MB in 30s = 0.75 Mbps → cross-border link IS the bottleneck!

# Layer 3: Client-side proxy test (measures Reality tunnel throughput)
curl -s --max-time 20 --socks5-hostname 127.0.0.1:1070 -o /dev/null \
  -w "DL:%{size_download}B t:%{time_total}s\n" \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin"
# Example: 0.6 Mbps → proxy overhead is negligible (~0.15 Mbps)
```

**Interpretation matrix:**

| Layer 1 (server) | Layer 2 (raw link) | Layer 3 (proxy) | Bottleneck |
|------------------|-------------------|-----------------|------------|
| Fast | Fast | Slow | Proxy protocol/config |
| Fast | Slow | ~same as Layer 2 | Cross-border link (not fixable) |
| Slow | Slow | Slow | Server/VPS bandwidth |

**Critical**: If server-side speed is high AND raw link speed is high but proxy is slow, the bottleneck is in the tunnel (protocol or path). If raw link speed matches proxy speed, the protocol is irrelevant — the cross-border link itself is the limit.
