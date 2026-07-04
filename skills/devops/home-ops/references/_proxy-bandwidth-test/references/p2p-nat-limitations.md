# P2P NAT Traversal Limitations (Tailscale / ZeroTier)

## Environment

- Home network: China Telecom fixed broadband, behind ImmortalWrt (24.10, OpenClash)
- Mobile network: China Mobile 5G (CGNAT)
- Phone: Realme GT7 (MediaTek Dimensity 9400+)
- Goal: Direct P2P connection between home router and phone for high-speed proxy

## Verdict: P2P Not Achievable

Both Tailscale and ZeroTier were tested. Neither could establish a direct (P2P) connection between the home router (on China Telecom) and the phone (on China Mobile 5G). Both fell back to overseas relay servers (Tokyo DERP / ZeroTier Planet) with poor latency and TLS compatibility issues.

## Why P2P Fails

The combination of **two layers of CGNAT** makes UDP hole-punching nearly impossible:

```
Phone (5G) → China Mobile CGNAT (carrier-grade NAT) → Internet
Home       → China Telecom CGNAT (likely) → ImmortalWrt NAT (masquerade) → LAN
```

Both carriers use CGNAT (no public IPv4). Hole-punching requires at least one side to have a predictable NAT mapping, which CGNAT does not provide.

## Tools Tested

| Tool | P2P Direct? | Fallback | TLS via Fallback |
|------|:-----------:|:---------|:----------------:|
| Tailscale (1.80 → 1.98) | ❌ | DERP Tokyo (relay "tok") | ❌ HTTPS fails via DERP |
| ZeroTier (1.14 → 1.16) | ❌ | RELAY (-1 latency) | ❌ HTTPS fails via relay |

## Why DERP/Relay HTTPS Fails

Overseas relay servers (Tokyo DERP, ZeroTier Planet) have MTU/packet-reordering issues that break TLS handshakes. Domestic HTTP traffic works; international HTTPS fails with `SSL_ERROR_SYSCALL` or connection timeout.

**Workaround attempted:** Lower MTU on tailscale0 interface to 1280 — did NOT fix the issue.

## Firewall Changes That Helped (But Not Enough)

These changes were made on ImmortalWrt to allow Tailscale/ZeroTier traffic through:

1. **Allow UDP 41641 (Tailscale WireGuard) and UDP 9993 (ZeroTier) from WAN**
2. **Skip NAT for Tailscale/ZeroTier virtual IP ranges** (no masquerade)
3. **Add tailscale0/zt interfaces to LAN zone** (no NAT)

These were necessary but insufficient — the mobile-side CGNAT was the blocking factor.

## Moon / Custom Relay

**Existing ZeroTier Moon** on Tencent Cloud (bernarty, 122.51.232.209, ID: db3a8694b4) — already configured and running. But adding it to the phone requires root (Android ZeroTier app removed the Moon UI in newer versions). A Moon file can be placed in the app's data directory with root.

## Alternative Approaches That Work

| Approach | Speed | Complexity |
|----------|-------|:----------:|
| Phone hotspot (5G) → device connects to hotspot | Phone 5G full speed | Low |
| Clash Verge on minipc + WiFi bind + ImmortalWrt SOCKS5 | Depends on 5G + VLESS | Medium |
| WireGuard via Tencent Cloud relay | Dependent on relay bandwidth | High |

## Key Learning

The P2P limitation is not a tool issue (Tailscale vs ZeroTier) — it's a **network architecture constraint**. Both mobile CGNAT and home broadband CGNAT prevent direct UDP hole-punching between them. No amount of configuration on either end can bypass the carrier-level NAT.

**Recommendation:** Don't try more P2P tools. Use relay-based approaches (DERP on domestic server, WireGuard hub) or connection-direction-based approaches (phone initiates connection, home devices connect through it).
