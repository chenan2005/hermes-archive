# Alibaba Cloud ECS site-blocking findings

## Reflected Networks / pornhub.com blocking (2026-06-26)

**Symptom:** From Alibaba Cloud Seoul ECS (43.108.41.245), `https://www.pornhub.com` (66.254.114.41) fails on TLS handshake level (no response to ClientHello), while HTTP port 80 returns the site's maintenance page successfully. Other nodes (KVM US, VMISS Hong Kong) work fine for the same site.

**Root cause:** Not a proxy protocol or GFW issue. The site/path uses **Reflected Networks** (AS29789, anycast) as CDN. Their edge node drops TLS connections (port 443) from Alibaba Cloud IP ranges while allowing HTTP (port 80) — likely an IP reputation / anti-abuse filter, not a routing issue (mtr shows identical path for both ports).

**What it affects:**
- Any proxy protocol (VLESS, VMess, Reality) through a Seoul node → fails for this site
- Even direct curl from the server → fails
- Not specific to any Chinese ISP (same issue on Telecom and Mobile networks via proxy)

**What still works:**
- The same site through KVM (US) or VMISS (Hong Kong) nodes
- Seoul node for general Internet access (confirmed fast on mobile 5G)
- Sites using Cloudflare, Akamai, Fastly, or other CDNs are unaffected

**Mitigation:**
- Route blocked sites through a different exit node (VMISS-HK for adult content)
- Or use Cloudflare Tunnel backend (exit IP becomes Cloudflare's, which has better reputation)
