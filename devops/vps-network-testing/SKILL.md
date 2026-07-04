---
name: vps-network-testing
description: Test and evaluate VPS network performance — return speed to China, outbound bandwidth, latency, routing quality, and peak-hour stability.
---

# VPS Network Performance Testing

Test methodology for evaluating a new VPS from a China-based user's perspective.

## When to use

- Evaluating a new VPS purchase (before/after deployment)
- Diagnosing "slow" proxy complaints
- Comparing VPS providers for return-to-China performance
- Buying decisions: which routing tier to choose

## Three-layer diagnostic

Always test all three layers. Missing one leads to wrong conclusions.

```
Layer 1: Server → Internet (outbound)
Layer 2: Server → You (return/回程)  ← MOST IMPORTANT
Layer 3: Through proxy (end-to-end)
```

## Layer 1: Server outbound bandwidth

Test the VPS's ability to reach the open internet. Run these ON the VPS:

```bash
# YouTube reachability (baseline)
curl -s --max-time 10 -o /dev/null \
  -w "HTTP:%{http_code} TTFB:%{time_starttransfer}s\n" \
  "https://www.youtube.com"

# Large file from multiple CDNs
for url in \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin" \
  "http://speedtest.singapore.linode.com/100MB-singapore.bin" \
  "http://speedtest.frankfurt.linode.com/100MB-frankfurt.bin"; do
  echo -n "$(basename $url): "
  curl -s --max-time 20 -o /dev/null \
    -w "DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
    "$url"
done
```

**Interpreting results:**

| Speed | Rating |
|-------|--------|
| >200 Mbps | Excellent |
| 50-200 Mbps | Good |
| 10-50 Mbps | Adequate |
| <10 Mbps | Poor — will bottleneck proxy |

**Pitfall**: CacheFly (cachefly.cachefly.net) often returns 25B on non-US servers (CDN geo-block). Don't use it for Asia VPS tests. Linode speed tests are more reliable.

## Layer 2: Return speed (回程) — the critical metric

This measures server → client bandwidth. Set up a temporary HTTP server on the VPS and download from your machine.

**On VPS:**
```bash
# Create test file
dd if=/dev/zero bs=1M count=100 of=/tmp/test.bin

# Start HTTP server (need python3)
cd /tmp && python3 -m http.server 80

# Or use netcat for a one-shot transfer
cat /tmp/test.bin | nc -l -p 8080
```

**From your machine:**
```bash
curl -s --max-time 30 -o /dev/null \
  -w "DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "http://<VPS_IP>/test.bin"
```

**Test from multiple locations** on your network (router, different WiFi devices) — the results can differ due to local congestion.

**Always test during PEAK HOURS** (19:00-23:00 China time). Daytime speed is meaningless — it's the evening that matters.

**Interpreting results:**

| Return speed | Usability |
|-------------|-----------|
| >50 Mbps | 4K video streaming |
| 20-50 Mbps | 1080p/1440p video |
| 5-20 Mbps | 720p video, browsing |
| 1-5 Mbps | 144p video, browsing OK |
| <1 Mbps | Unusable for video |

## Layer 3: Through-proxy test

Test the actual proxy path (double-check the proxy configuration is correct):

```bash
# On OpenWrt with PassWall
curl -s --socks5-hostname 127.0.0.1:1070 --max-time 30 -o /dev/null \
  -w "HTTP:%{http_code} TTFB:%{time_starttransfer}s V:%{speed_download}B/s\n" \
  "http://<VPS_IP>/test.bin"
```

Compare this with the direct Layer 2 result. If the proxy adds significant overhead (>20%), investigate:
- Protocol choice (Reality has less overhead than VMess+WS+TLS)
- Mux settings
- DNS resolution inside V2Ray

## Routing quality test (traceroute)

**On VPS (must run as root):**
```bash
# Install
apt-get install -y mtr-tiny

# Trace to a known China IP
mtr -r -c 10 -n 223.5.5.5
```

**Key routing markers:**

| Transit IP | Carrier | Quality |
|-----------|---------|---------|
| `59.43.x.x` | CN2 (China Telecom) | ✅ Excellent |
| `202.97.x.x` | CHN169 (China Telecom 163) | ⚠️ Congested |
| `223.120.x.x` | China Mobile CMI | ✅ Good |
| `219.158.x.x` | China Unicom 4837 | ✅ Good |
| `218.105.x.x` | China Unicom 9929 | ✅ Premium |

**BestTrace tool** (better than traceroute for Chinese routing):
```bash
wget -q https://cdn.ipip.net/17mon/besttrace4linux.zip
unzip -o besttrace4linux.zip && chmod +x besttrace4linux
./besttrace -q 1 -g cn 223.5.5.5
```

## VPS purchase evaluation checklist

### BGP / routing tier guide

| Label | Routing | Return to China | Price range |
|-------|---------|----------------|-------------|
| BGP (unlabeled) | China-optimized | ✅ Good through | ¥50-100/mo |
| BGP (非中国优化/INTL) | International only | ❌ Poor | Cheap |
| CN2 GIA | CT premium | ✅ Excellent | $10-30/mo |
| CN2 | CT standard | ✅ Good | $5-15/mo |
| CMI | CM international | ✅ Good | $3-10/mo |
| 9929 | CU premium | ✅ Good | $5-15/mo |
| 163/4837 | Standard CT/CU | ⚠️ Congested peaks | Cheap |

### Key questions before buying

1. **Is it China-optimized?** Look for "BGP", "CN2", "CMI", "9929" labels. Avoid "INTL", "国际线路", "非中国优化".
2. **What's the return path?** Ask for routing test or check reviews. "去程普通回程CN2" is the ideal pattern — cheap outbound, premium return.
3. **Peak hour performance?** Any VPS review that only shows daytime tests is useless.
4. **Refund policy?** Alibaba Cloud HK: 5-day no-questions refund. VMISS: varies. Always check before buying.

### Recommended vendors

| Vendor | Best for | Price range | Notes |
|--------|---------|-------------|-------|
| Alibaba Cloud (HK) | One-click, known brand | ¥56/mo | BGP optimized, 200Mbps peak. **Avoid "非中国优化" version (¥28/mo)**. |
| VMISS (HK) | CN2/CMI routing | CAD $5-10/mo (~¥26-52) | DC1 or DC3 recommended. DC2 has instability. INTL = no China optimization. See `references/vmiss-hk-bgp-variants.md` for full DC comparison. |
| GigsGigsCloud | HK CN2 GIA | ~$8-15/mo | Established, stable |
| DMIT | High-end CN2 GIA | ~$15-30/mo | Premium routing, expensive |
| BandwagonHost (搬瓦工) | US CN2 GIA | ~$50-100/yr | Classic but dated |
| RackNerd | Budget US | ~$2-5/mo | Not for China return |

### Vendor routing truth

Alibaba Cloud HK advertises "200Mbps peak bandwidth" but this is the total port speed — the actual return speed to China depends on whether the plan is **China-optimized BGP** (no label) or **非中国优化 BGP** (labeled). The ¥28/mo plan is explicitly non-China-optimized and will perform similarly to Seoul. Always check the routing label before buying — cheaper plans route through ChinaNet 163 which is congested at peak hours.

## One-liner quick test script

Copy-paste to test any new VPS:

```bash
echo "=== Outbound ===" && \
curl -s --max-time 10 -o /dev/null -w "YouTube: HTTP:%{http_code} TTFB:%{time_starttransfer}s\n" "https://www.youtube.com" && \
curl -s --max-time 20 -o /dev/null -w "Tokyo100M: DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin" && \
echo "" && echo "=== System ===" && \
echo "CPU: $(nproc)核" && free -h | grep Mem && df -h / | tail -1
```

## References

- `references/vmiss-hongkong-test.md` — Full test results from VMISS Hong Kong BGP DC1 (1C/1G/10G SSD, 100Mbps port). Measured: outbound 45Mbps, return 36-52Mbps at peak hours. Used as benchmark for HK BGP tier VPS evaluation.
