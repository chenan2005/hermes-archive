---
name: cloudflare-proxy-acceleration
title: Cloudflare Proxy Acceleration for OpenWrt/PassWall
description: Use Cloudflare CDN or Cloudflare Tunnel to accelerate slow overseas proxy connections to OpenWrt PassWall. Covers domain migration, tunnel setup, SNI routing injection, and multi-protocol coexistence.
trigger: User has an overseas VPS (e.g., Seoul) with slow direct connection to China and wants to accelerate via Cloudflare.
domain: ["openwrt", "passwall", "cloudflare", "xray", "v2ray", "vps"]
---

# Cloudflare Proxy Acceleration

## When to use

When a VPS's **direct China→overseas bandwidth is poor** (< 2 Mbps) but the server itself has good bandwidth in its local region. Cloudflare's backbone (edge → tunnel/CDN) bypasses the congested direct China international link.

## Architecture options

### Option A: Cloudflare CDN (orange cloud proxy)
```
Client(V2Ray) → Cloudflare CDN(HTTPS) → VPS:443(VMess+WS+TLS)
```
- Requires DNS on Cloudflare (nameserver migration)
- SSL mode: **Full** (for 443 with self-signed cert) or **Flexible** (for 80 without TLS)
- Speed: typically 25-40 Mbps improvement over direct

### Option B: Cloudflare Tunnel (cloudflared)
```
Client(V2Ray) → Cloudflare edge(HTTPS) → tunnel(QUIC) → cloudflared → localhost:80(VMess+WS)
```
- Independent of DNS provider
- Quick tunnels (`*.trycloudflare.com`) are free but URL changes on restart
- Speed: typically 15-25 Mbps

## Setup Steps

### 1. Server-side: xray backend

Stop x-ui (it overwrites manual config changes):

```bash
sudo systemctl stop x-ui
sudo killall -9 xray xray-linux-amd64
```

Write a clean config with all protocols. Recommended ports:

| Port | Protocol | Purpose |
|------|----------|---------|
| 80 | VMess+WS (no TLS) | Cloudflare Tunnel backend |
| 443 | VMess+WS+TLS (self-signed cert) | Cloudflare CDN backend |
| 40001 | VLESS+Reality | Direct connection (optional) |

Write config as JSON at `/usr/local/x-ui/bin/config.json` and start xray manually:

```bash
sudo /usr/local/x-ui/bin/xray-linux-amd64 -c /usr/local/x-ui/bin/config.json &
```

### 2. Cloudflare DNS setup (Option A only)

1. Add domain to Cloudflare dashboard
2. Change nameservers at registrar to Cloudflare's
3. Add A record with orange cloud (proxied) enabled
4. Set SSL/TLS encryption mode to **Full** or **Flexible**

### 3. Cloudflare Tunnel setup (Option B only)

```bash
# Install
curl -sL https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Systemd service
cat > /etc/systemd/system/cloudflared.service << 'SERVICEEOF'
[Unit]
Description=Cloudflare Tunnel
After=network.target
[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:80
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl enable --now cloudflared
```

Get tunnel URL:
```bash
journalctl -u cloudflared --no-pager -n 20 | grep -o 'https://[a-z0-9.-]*\.trycloudflare\.com' | head -1
```

### 4. OpenWrt PassWall: add node

Add a VMess node for the tunnel:

```bash
uci add passwall nodes
uci set passwall.${NODE}.remarks="Seoul-via-Cloudflare"
uci set passwall.${NODE}.type="V2ray"
uci set passwall.${NODE}.protocol="vmess"
uci set passwall.${NODE}.address="<tunnel-hostname>.trycloudflare.com"
uci set passwall.${NODE}.port="443"
uci set passwall.${NODE}.uuid="<uuid>"
uci set passwall.${NODE}.security="auto"
uci set passwall.${NODE}.transport="ws"
uci set passwall.${NODE}.ws_path="/ws-seoul"
uci set passwall.${NODE}.ws_host="<tunnel-hostname>.trycloudflare.com"
uci set passwall.${NODE}.tls="1"
uci set passwall.${NODE}.tls_serverName="<tunnel-hostname>.trycloudflare.com"
uci set passwall.${NODE}.add_mode="1"
uci commit passwall
```

**Critical:** Add tunnel hostname to `/etc/hosts` on OpenWrt:

```bash
echo "104.16.230.132 <tunnel-hostname>.trycloudflare.com" >> /etc/hosts
```

Without this, dnsmasq + chinadns-ng returns SERVFAIL for `*.trycloudflare.com`.

### 5. SNI Routing Injection (KVM-main + Seoul-auth split)

When KVM is the default and Seoul only serves Google auth domains:

1. Let PassWall generate config with KVM as `tcp_node`
2. Inject a unified config at `/tmp/etc/passwall/TCP_SOCKS.json` with:
   - KVM outbound as default
   - Seoul tunnel outbound (VMess+WS+TLS)
   - SNI routing rules (19 Google auth domains → Seoul)
3. Add Google IP CIDRs to `passwall_blacklist` for iptables redirection
4. Restart V2Ray TCP process

Google auth domains for SNI routing:

```
accounts.google.com, accounts.youtube.com, oauth2.googleapis.com,
www.googleapis.com, openidconnect.googleapis.com, securetoken.googleapis.com,
identitytoolkit.googleapis.com, android.googleapis.com, clientauth.googleapis.com,
people.googleapis.com, content-googleapis.com, ssl.gstatic.com, www.gstatic.com,
apis.google.com, play.google.com, myaccount.google.com
```

Also add these to PassWall's `proxy_host` list for dnsmasq-based redirection:

```bash
uci add_list passwall.@global_rules[0].proxy_host="accounts.google.com"
uci commit passwall
```

### 6. Persistence (survive reboots)

Save the unified config template:

```bash
# Generate /tmp/v2ray-tunnel.json on the controller machine
# then scp to OpenWrt:
cat /tmp/v2ray-tunnel.json | ssh root@openwrt.lan.11 'cat > /etc/v2ray-unified.json'
```

Create `/etc/init.d/v2ray-seoul-inject` (START=99) to run after PassWall:

```bash
# Wait 15s for PassWall to fully start
# Copy /etc/v2ray-unified.json over PassWall's TCP_SOCKS.json
# Add Google CIDRs to ipset
# Add tunnel hostname to /etc/hosts
# Restart V2Ray TCP process
```

## Pitfalls

- **x-ui overwrites config:** Stop x-ui (`systemctl stop x-ui`) and run xray manually for custom configs
- **trycloudflare.com DNS:** OpenWrt dnsmasq returns SERVFAIL → add to `/etc/hosts`
- **Tunnel URL changes on restart:** Quick tunnels get random URLs. Check `journalctl -u cloudflared` after restart
- **PassWall restart kills injected config:** Injection must run AFTER PassWall in START order
- **SSL mode mismatch:** Cloudflare Full + self-signed cert works; Flexible expects plain HTTP on origin
- **Google IP ranges change:** CIDRs in blacklist may stale. Supplement with `proxy_host` list

## Verification

```bash
# Connection test
curl -s -o /dev/null -w "YouTube:%{http_code}\n" https://www.youtube.com
curl -s -o /dev/null -w "GoogleAuth:%{http_code}\n" https://accounts.google.com

# Server check
ssh <vps> 'ss -tlnp | grep -E ":(80|443) "'
ssh <vps> 'sudo systemctl is-active cloudflared'

# Routing check
tail -10 /tmp/etc/passwall/TCP.log | grep -E "seoul|izRNaKFP"
```
