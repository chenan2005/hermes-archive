# Node Status Query — OpenClash REST API

## One-liner: Query All Node Status

```bash
# For single-use queries (SSH inline):
ssh openwrt-t 'curl -s http://127.0.0.1:9090/proxies -H "Authorization: Bearer $(grep secret /etc/openclash/config.yaml | awk '\''{print $2}'\'')"'

# For scripts (write file first, execute after):
cat > /tmp/query.sh << 'SCRIPT'
#!/bin/sh
S=$(grep secret /etc/openclash/config.yaml | awk '{print $2}')
H="Authorization: Bearer *** -s -H "$H" http://127.0.0.1:9090/proxies 2>/dev/null
SCRIPT
ssh openwrt-t '(cat /tmp/query.sh && sh /tmp/query.sh)'
```

## 4-Node Status (2026-06-23 14:30, After Full Fix)

All 4 nodes alive. OpenClash restarted cleanly (SAFE_PATHS fix, stale process cleanup).

| Node | Type | Status | Delay | Server |
|------|------|--------|-------|--------|
| **233boy-KVM** | VMess+WS+TLS | ✅ | 735ms | kvm.bernarty.xyz:30717 |
| **Seoul-Cloudflare** | VMess+WS (CF Tunnel) | ✅ | 677ms | dressed-circles-...trycloudflare.com:443 |
| **VMISS-HK** | VMess+WS+TLS | ✅ | 1066ms | vmiss.bernarty.xyz:443 |
| **Alibaba-Seoul-VLESS-Reality** | VLESS+Reality | ✅ | **538ms 🏆** | 43.108.41.245:40001 |

## Proxy Group Routing (OpenClash 37.2)

| Group | Type | Current Selection |
|-------|------|-------------------|
| **PROXY** | Selector | **233boy-KVM** (user preference — primary) |
| **AUTO** | URLTest | Alibaba-Seoul-VLESS-Reality (latency-based auto) |
| **Google-Auth** | Selector | **Alibaba-Seoul-VLESS-Reality** (handles Google auth) |
| **Manual-Select** | Selector | PROXY |

**Strategy:**
- Default traffic → PROXY → **233boy-KVM** (preferred for bandwidth)
- Google auth/login → Google-Auth → **Alibaba-Seoul-VLESS-Reality** (low latency, works for auth)
- OpenAI → Manual-Select → PROXY

## Per-Node Detail

### Alibaba-Seoul-VLESS-Reality (43.108.41.245:40001)
- **Lowest ping** (ICMP ~57ms) but **very small return bandwidth** (~0.4 Mbps proxy)
- Good for: Google auth, light browsing, low-bandwidth tasks
- Bad for: speed tests (fast.com), large downloads
- **Server**: xray 26.6.1, x-ui panel, Reality with public-key `0o3XsyApUXA0_1Ns2GZPbzLCbUW8zpAarRxCbb0gr1g`

### VMISS-HK (vmiss.bernarty.xyz:443)
- Higher ping (1066ms) but **better bandwidth** for streaming
- Good for: YouTube, general browsing
- Bad for: fast.com (Netflix CDN route quality issue)

### Seoul-Cloudflare (CF Tunnel via Alibaba)
- CF Tunnel URL: `dressed-circles-smithsonian-jewellery.trycloudflare.com`
- Auto-healing script: `/usr/bin/seoul-tunnel-watch` (cron every 30min)
- **Ubuntu 24.04** server (was 20.04)

### 233boy-KVM (kvm.bernarty.xyz:30717)
- User's preferred primary node for bandwidth reasons
- VMess+WS+TLS, stable

## PassWall (37.1) Node Config

| Node ID | Name | Type | Active |
|---------|------|------|--------|
| cfg151c7e | Alibaba-Seoul-VLESS-Reality | VLESS+Reality | ✅ TCP fallback |
| cfg141c7e | VMISS-HK-VMess-WS-TLS | VMess+WS+TLS | ✅ in db, not active |
| cfg131c7e | Seoul-via-Cloudflare | VMess+WS+TLS | ✅ in db, not active |
| izRNaKFP | 233boy-ws-kvm | VMess+WS+TLS | ✅ Active UDP + TCP |

## Testing Commands

```bash
# Quick test through OpenClash proxy
curl -sx "http://Clash:3Ypy6ovV@127.0.0.1:7890" --max-time 10 https://cp.cloudflare.com/generate_204 -o /dev/null -w "%{http_code} %{time_total}s\n"

# Switch PROXY group (use printf for auth header to avoid quoting issues)
S=$(grep secret /etc/openclash/config.yaml | awk '{print $2}')
H=$(printf 'Authorization: Bearer %s' "$S")
curl -s -X PUT -H "$H" -H "Content-Type: application/json" \
  -d '{"name":"233boy-KVM"}' http://127.0.0.1:9090/proxies/PROXY

# Trigger delay test on specific node
curl -s -H "$H" "http://127.0.0.1:9090/proxies/233boy-KVM/delay?url=https://cp.cloudflare.com/generate_204&timeout=5000"

# Query node group info
for g in PROXY AUTO Google-Auth Manual-Select; do
  curl -s -H "$H" "http://127.0.0.1:9090/proxies/$g" | grep -oE "now[^,}]*"
done
```
