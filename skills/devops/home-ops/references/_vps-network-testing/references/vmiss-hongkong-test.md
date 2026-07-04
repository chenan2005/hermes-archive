# VMISS Hong Kong BGP DC1 Test Results

Date: 2026-06-19, ~21:00 CST

## Server specs

- Provider: VMISS (vmiss.com)
- Plan: CN.HK.BGP.Basic (CAD $5/mo)
- Tier: BGP DC1 (Cloudie DC) — China optimized
- IP: 38.47.108.89
- Specs: 1 vCore, 1GB RAM, 10GB SSD, 100Mbps port, 300GB transfer
- OS: Ubuntu (stock image)

## Outbound test (VPS → Internet)

| Target | Result |
|--------|--------|
| YouTube | HTTP 200, TTFB 0.24s |
| Tokyo Linode 100MB | 5.6 MB/s (45 Mbps) |
| Google | HTTP 302, TTFB 0.13s |

## Return test (VPS → China client)

### Client: Lenovo laptop (WiFi, 192.168.37.234)

| Time | Speed |
|------|-------|
| Direct download | 6.5 MB/s (52 Mbps) |
| Via V2Ray SOCKS proxy | 4.6 MB/s (37 Mbps) |

### Client: OpenWrt router (192.168.37.1, wired)

| Time | Speed |
|------|-------|
| Peak hour (~21:20 CST) | 4.5 MB/s (36 Mbps) |
| Sustained 100MB | 100MB / 23.15s |

## Routing

Confirmed China-optimized BGP return. The "BGP (unlabeled)" tier at VMISS provides good return-to-China performance comparable to CN2/CMI routing.

## Comparison

| Metric | Seoul (Alibaba) | VMISS HK |
|--------|----------------|----------|
| Return speed | 0.75 Mbps | 36-52 Mbps |
| Outbound speed | 620 Mbps | 45 Mbps |
| Price | ¥56/mo | ~¥26/mo (CAD $5) |
| Routing | Shared BGP (no CN opt) | China-optimized BGP |

## Conclusion

The VMISS HK BGP Basic plan delivers excellent return-to-China speed (36-52 Mbps) even at peak hours, 50-70x better than the Alibaba Cloud Seoul plan at half the price. Recommended for users who need reliable China-facing proxy bandwidth.
