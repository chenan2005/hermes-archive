# CDN / Origin IP Blocking Debug

When specific sites are inaccessible through a proxy node but work through others, the issue is often the **VPS provider's IP reputation** at the destination CDN — not the proxy protocol.

## Case: pornhub.com via Alibaba Cloud Seoul (2026-06-26)

| Test | Result |
|------|--------|
| Seoul → pornhub (HTTP 80) | "Down for Maintenance 403" page from pornhub's own server ✅ |
| Seoul → pornhub (HTTPS 443) | TLS ClientHello sent, **0 bytes received back** ❌ |
| Seoul → pornhub TCP 443 | Telnet / nc connects ✅ (TCP open) |
| Seoul mtr to pornhub IP | 15 hops, 36ms, NTT → Reflected Networks ✅ |
| VMISS-HK → pornhub (HTTPS) | TLS handshake normal, DigiCert cert chain received ✅ |
| KVM (US) → pornhub (HTTPS) | TLS handshake normal ✅ |
| VMISS-HK → pornhub (HTTP) | Server: `openresty` (pornhub's CDN) |

### Root Cause

pornhub uses **Reflected Networks** (AS29789, anycast IP 66.254.114.41). Their CDN edge nodes have software-level rules that **silently drop TLS handshakes from specific IP ranges** (including Alibaba Cloud) while allowing plain HTTP connections.

The same IP (43.108.41.245) works fine for:
- Non-blocked sites (Google, YouTube, GitHub)
- Standard TLS to non-blocked CDNs

### Diagnosis Steps

1. Separate TCP from TLS: `echo | timeout 5 openssl s_client -connect <IP>:443 -servername <hostname>`
2. Compare HTTP vs HTTPS: `curl -s http://<IP>/` vs `curl -v https://<hostname>/`
3. Route check: `mtr -r -c 5 -n <IP>` (compare 80 vs 443 paths)
4. Cross-reference from another VPS with different IP range
5. Check CDN provider via: `curl -sI https://<site>/ | grep -i server`

### Not a Proxy Protocol Issue

This is **CDN-level filtering** by source IP, not:
- GFW blocking
- Reality vs VMess protocol difference
- Port-specific blocking
- TLS fingerprint detection

All proxy protocols (Reality, VMess+WS, VMess+WS+TLS) fail equally because the CDN blocks the server's source IP before any proxy-layer negotiation happens.

### Workarounds

- Route through a CDN/proxy with different source IP (Cloudflare Tunnel changes source to CF IPs)
- Use a node on a different VPS provider whose IP range isn't blocked
- Contact the destination site (not practical for user-facing work)
