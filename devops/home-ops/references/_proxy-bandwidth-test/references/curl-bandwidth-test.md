# Curl-Based Bandwidth Test Methodology

From within China, Ookla speedtest servers and international CDNs (Cloudflare, OVH) give misleading results due to server-side throttling and international QoS. The reliable approach is to use domestic CDN downloads for direct tests and Cloudflare 50MB via SOCKS5 for proxy tests.

## Direct (no proxy) test

### Domestic CDN sources

| Source | URL | Size | Typical speed (China Telecom) |
|--------|-----|:----:|:----------------------------:|
| Google Chrome CDN | `https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb` | 133 MB | 180-200 Mbps |
| VS Code (Azure CDN) | `https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64` | 199 MB | 130-170 Mbps |
| Zhejiang Univ (教育网) | `http://speedtest.zju.edu.cn/1000M` | 1000 MB | varies |

### Latency

```bash
curl -s -o /dev/null -w '%{time_total}' --max-time 5 https://www.baidu.com
```

### Bandwidth (via speed_download)

```bash
dl_speed=$(curl -s --max-time 15 -o /dev/null -w '%{speed_download}' \
  "https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb")
mbps=$(echo "scale=1; $dl_speed * 8 / 1000000" | bc)
echo "${mbps} Mbps"
```

## Proxy node test (via SOCKS5)

### Latency

```bash
lat=$(curl -s --socks5 127.0.0.1:10880 -o /dev/null -w '%{time_total}' \
  --max-time 10 "https://www.google.com/generate_204")
lat_ms=$(echo "scale=0; ($lat * 1000) / 1" | bc)
echo "${lat_ms}ms"
```

Fallback if Google is blocked:
```bash
lat=$(curl -s --socks5 127.0.0.1:10880 -o /dev/null -w '%{time_total}' \
  --max-time 10 "http://www.gstatic.com/generate_204")
```

### Bandwidth (Cloudflare 50MB)

```bash
dl_out=$(curl -s --socks5 127.0.0.1:10880 -o /dev/null -w '%{size_download} %{time_total}' \
  --max-time 30 "https://speed.cloudflare.com/__down?bytes=52428800")
dl_bytes=$(echo "$dl_out" | cut -d' ' -f1)
dl_elapsed=$(echo "$dl_out" | cut -d' ' -f2)
mbps=$(echo "scale=1; $dl_bytes * 8 / $dl_elapsed / 1000000" | bc)
echo "${mbps} Mbps"
```

Note: Cloudflare may rate-limit some proxy IPs, returning 0.5-3 Mbps. This is a server-side limit, not the node's real capacity.

### Fallback sources if Cloudflare 403s

- OVH (France): `https://proof.ovh.net/files/100Mb.dat` (supports range requests)
- Tele2 (Netherlands): `http://speedtest.tele2.net/100MB.zip`
- Datapacket: `http://sgp.download.datapacket.com/100mb.bin`

## When to use which

| Scenario | Method | Why |
|----------|--------|-----|
| Direct (no proxy) | domestic CDN curl | Speedtest servers and international CDNs are throttled from China |
| Via any proxy node | Cloudflare 50MB via SOCKS5 | Measures the actual international path throughput |
| Quick connectivity check | `curl --socks5` to gstatic 204 | Fast, no bandwidth cost |

## Known unreliable sources from China

| Source | Misleading result | Actual speed |
|--------|:-----------------:|:------------:|
| speedtest-ookla Shanghai 3633 | 28-34 Mbps | 130-200 Mbps |
| Cloudflare speed test (direct) | 18 Mbps | 130-200 Mbps |
| OVH (direct) | < 1 Mbps | 130-200 Mbps |
