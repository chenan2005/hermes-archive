# mihomo Memory Leak Detection — 10-Minute Monitoring

Run on ImmortalWrt when suspecting OOM or memory growth.

## One-liner (lightweight, 10 samples at 1/min)

```bash
ssh root@192.168.71.9 'PID=$(pgrep -f "clash -d /etc/openclash" | head -1); for i in $(seq 1 10); do VmRSS=$(awk "/^VmRSS:/{print \$2}" /proc/$PID/status 2>/dev/null); VM=$(free -m | awk "NR==2{printf \"%dMB\",\$3}"); echo "$(date +%H:%M)  RSS=${VmRSS:-N/A}kB  used=$VM"; sleep 60; done; echo "=== final ==="; grep -E "^(VmPeak|VmHWM|VmRSS|VmSize)" /proc/$PID/status; free -m'
```

## Interpreting results

| Pattern | Verdict |
|---------|---------|
| RSS flat for last 3+ samples | No leak, GC stable |
| RSS grows <1MB/min then flat | Go runtime warmup, normal |
| RSS grows continuously 2+MB/min without plateau | Memory leak — check version (alpha?) |
| VmHWM >> VmRSS | Startup peak (geosite loading), not a leak |

## Session data (2026-07-04, v1.19.27 after upgrade from alpha)

```
Time     RSS(kB)   Delta    Phase
04:05   101,400     0       Fresh restart
04:09   107,544  +6,144     Go warmup (connection pool, DNS cache)
04:10   107,672    +128     GC active, slowing
04:11   107,800    +128     
04:12   107,800       0     ← Stable (4 consecutive samples flat)
04:14   107,800       0     
```

Conclusion: v1.19.27 stable, no leak. 6MB initial warmup, then completely flat.
Compare alpha-g8f2d84f: grew from 135MB → 194MB before OOM kill.
