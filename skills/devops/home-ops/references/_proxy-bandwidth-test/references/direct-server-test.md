# Direct-to-Server Bandwidth Test (Bypass OpenClash Proxy)

Use when you need to test bandwidth to a proxy server directly (not through OpenClash routing).

## The Fake-IP Problem

OpenClash returns fake-IPs (198.18.x.x) for all proxied domains, so DNS resolution always returns a local address. Even `dig @8.8.8.8` is intercepted by the router.

## Workflow: DoH + `--resolve`

### 1. Resolve real IP via DNS-over-HTTPS (bypass fake-IP)

```bash
real_ip=$(curl -s --noproxy "*" \
  "https://dns.google/resolve?name=kvm.bernarty.xyz&type=A" \
  | grep -o '"data":"[0-9.]*"' | head -1 | cut -d'"' -f4)
```

DoH queries go directly to Google DNS over HTTPS, bypassing the router's DNS interception.

### 2. Connect directly using real IP

```bash
curl -sv --noproxy "*" --max-time 15 \
  --resolve "kvm.bernarty.xyz:30717:$real_ip" \
  https://kvm.bernarty.xyz:30717/
```

`--resolve` forces curl to connect to the real IP for the given hostname, bypassing the DNS fake-IP.

## Limitations for VMess Servers

Most proxy nodes (VMess, VLESS, Shadowsocks) only accept their protocol on the configured port. For the 233boy-KVM server at 154.40.40.38:30717:

| Test | Result |
|------|--------|
| TCP connect | ~8ms ✅ |
| TLS handshake | ~1s ✅ |
| HTTP GET | 301 redirect ✅ |
| File download via HTTP | ❌ VMess protocol only |
| SSH (port 22) | ❌ Closed |
| HTTPS (port 443) | ❌ Closed |

You cannot directly download files from a VMess server — it only forwards traffic, it doesn't host files.

## Practical Bandwidth Assessment

Since direct file transfer is impossible, assess bandwidth through the node:

### Through OpenClash proxy (but isolate to one node)

1. Switch PROXY group to the target node
2. Download through `127.0.0.1:7890` with proxy auth
3. Compare to direct (no proxy) speed

```bash
# Switch node
curl -s -X PUT http://127.0.0.1:9090/proxies/PROXY \
  -H @/tmp/auth3 \
  -H "Content-Type: application/json" \
  -d '{"name":"233boy-KVM"}'

# Test through node
curl -s --proxy http://127.0.0.1:7890 \
  --proxy-user "Clash:3Ypy6ovV" \
  --max-time 60 -o /dev/null \
  -w "HTTP %{http_code} %{time_total}s %{speed_download}B/s\n" \
  http://speedtest.tele2.net/10MB.zip
```

### Compare with direct (non-proxy) baseline

```bash
# Router's direct internet speed (not through proxy)
curl -s --noproxy "*" --max-time 15 -o /dev/null \
  -w "%{time_total}s %{speed_download}B/s\n" \
  https://mirror.nforce.com/pub/speedtests/25mb.bin
```

The ratio between direct speed and proxy-node speed reveals whether the bottleneck is local internet or the remote server.

## OpenWrt-Specific Workarounds

| Missing tool | Workaround |
|-------------|------------|
| `stat` | Fallback to hardcoded file size `26214400` (25MB) |
| `xxd`, `od`, `hexdump` | Pipe to `hexdump -C` if available, or use `grep` pattern check |
| `base64` | Use `openssl base64 -d` or pipe raw text through `| ssh host 'cat > /tmp/file'` |
| `python3` | Write pure shell scripts (ash-compatible) |
| `timeout` | Use `--max-time` in curl/wget instead |
