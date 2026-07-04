# Bandwidth Test Results — 2026-06-27 12:19 UTC+8

## Test Configuration

- **Tool:** OpenClash on ImmortalWrt (192.168.71.9)
- **Timing:** `curl -w "%{http_code} %{time_total} %{size_download}"`
- **Test file:** `https://mirror.nforce.com/pub/speedtests/25mb.bin` (26,214,400 bytes)
- **Per-node timeout:** 60s per download
- **Timing method:** curl's `%{time_total}` (includes DNS + connect + transfer)

## Results Table

| Node | Time | Bandwidth | Size Downloaded | Status |
|------|------|-----------|----------------|--------|
| VMISS-HK | 7.013s | 3.6 MB/s (28.5 Mbps) | 25MB (full) | ✅ |
| Alibaba-Seoul-VLESS-Reality | 60.001s (timeout) | ~0.09 MB/s (~0.7 Mbps)* | 5.58 MB | ⚠️ partial |
| 233boy-KVM | 60.000s (timeout) | ~0.20 MB/s (~1.6 Mbps)* | 12.10 MB | ⚠️ partial |
| Seoul-Cloudflare | 10.415s | 2.4 MB/s (19.2 Mbps) | 25MB (full) | ✅ |

*Bandwidth estimated from partial download ÷ 60s.

## Analysis

### VMISS-HK (28.5 Mbps) — Best performer
- Completed 25MB in 7 seconds — fastest node by far
- Good for streaming, downloads, general browsing

### Seoul-Cloudflare (19.2 Mbps) — Second
- Completed 25MB in 10.4 seconds
- Adequate for most uses

### 233boy-KVM (1.6 Mbps) — Degraded
- Previously the user's preferred primary bandwidth node (735ms delay from prior testing)
- Only managed 12MB in 60s in this test — severe peak-hour degradation
- Possible causes: routing congestion, server-side bandwidth throttling, or the 233boy server being overloaded in evening hours
- Recommend re-testing at different times of day

### Alibaba-Seoul-VLESS-Reality (0.7 Mbps) — Known slow
- Consistent with prior observations: "very small return bandwidth (~0.4 Mbps proxy)"
- Only suitable for: Google auth, light browsing, low-bandwidth tasks
- Not suitable for: speed tests, large downloads, streaming

## Post-Test Group Selection

AUTO group was restored after testing completed.

## Script Used

The test script was written locally via `write_file`, transferred via `scp -O` (forced legacy protocol — OpenWrt busybox lacks sftp-server), and executed remotely on the OpenWrt test router at 192.168.71.9.
