# CDN / Destination-Side Reputation Blocking

Some destination websites block connections based on the **source IP range** of the proxy server, independent of the proxy protocol used.

## Case study: pornhub.com blocked on Alibaba Cloud Seoul (2026-06-26)

### Scenario
- Seoul nodes (VLESS direct + VMess via CF Tunnel) both failed to reach pornhub.com
- VMISS-HK and KVM nodes worked fine
- Same protocol (VLESS/VMess), same client config, same GFW — **the only variable was the source IP**

### Test results

| Test | Result |
|------|--------|
| TCP 443 from Seoul | ✅ Open (mtr reaches 66.254.114.41 in 35ms) |
| HTTP 80 from Seoul | ✅ Returns pornhub "Down for Maintenance" page |
| **HTTPS 443 from Seoul** | ❌ TLS ClientHello sent, 0 bytes back — `errno=104` |
| HTTPS from VMISS-HK (38.47.x.x) | ✅ Full TLS handshake, DigiCert chain received |
| DNS resolution | ✅ Consistent across Alibaba DNS, Google DNS, and HK |

### Root cause
pornhub.com uses **Reflected Networks** (AS29789, anycast IP 66.254.114.41) as CDN/edge provider. Their edge node drops TLS connections originating from Alibaba Cloud's IP range (43.108.x.x), while accepting plain HTTP connections from the same range. This is likely a **reputation-based block** — Alibaba Cloud IPs are commonly associated with scrapers, bots, and proxy exits, so the CDN applies stricter TLS-level filtering.

### Diagnostic method
1. Confirm standard TLS fallback works: `curl -vk https://<IP>:<PORT>` → gets dest's TLS cert ✅
2. Then test the actual target site: `openssl s_client -connect <target-ip>:443 -servername <target-host>`
3. Compare from a different VPS (VMISS, KVM) — if the target works from one IP range but not another, it's CDN-side filtering, not a protocol issue
4. Verify it's not DNS: `dig +short <target> @8.8.8.8` vs `@<VPS-internal-DNS>`

### Implications
- **Not a GFW issue**: the block happens at the destination CDN, not on the China-side network
- **Not a protocol issue**: VMess and VLESS fail equally when the source IP is unfavored
- **Can't be fixed from the client side**: changing proxy protocol, port, or destination domain won't help
- **Workarounds**: use a different VPS provider (VMISS HK, KVM US), or route traffic through a second proxy (double-hop) to change the exit IP
