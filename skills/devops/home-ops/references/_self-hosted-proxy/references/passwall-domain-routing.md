# PassWall Domain-Based SNI Routing (Dual Outbound)

## Problem

You have two proxy nodes (e.g., KVM for general traffic, Seoul for Google auth) and need to route specific domains through a specific node. PassWall's built-in shunt only supports `_direct`, `_default`, `_blackhole` actions — it cannot route to a second proxy node.

The ipset+iptables approach (dnsmasq ipset → iptables REDIRECT → separate xray) seems attractive but has fatal flaws:
- **IP collision**: Google services share IPs across auth/non-auth (e.g., accounts.google.com and YouTube both resolve to 142.251.x.x)
- **Collateral routing**: Non-Google services get caught (Facebook/Twitter IPs entered ipset via shared CDN for gstatic.com/reCAPTCHA)
- Result: YouTube video traffic gets routed through the auth-only proxy

## Solution: V2Ray SNI routing with multiple outbounds

### Approach A: Cloudflare Tunnel (Recommended, ~15-28 Mbps)

The secondary proxy (Seoul) is accessed via Cloudflare Tunnel instead of direct Reality. The V2Ray outbound connects to the tunnel URL as VMess+WS+TLS, eliminating the need for a separate Xray process on the client side.

See `openwrt-proxy-acceleration` skill's `references/passwall-sni-routing.md` for the full unified config with Cloudflare Tunnel outbound.

### Approach B: Local Xray Upstream (DEPRECATED, ~0.75 Mbps)

The original approach using a separate Xray instance on OpenWrt as SOCKS upstream to Seoul Reality. This is limited by the direct China→Korea bandwidth bottleneck.

### Architecture

```
Client → iptables → V2Ray(1041) → [{SNI sniff}] → routing
  ├── accounts.google.com → seoul_socks → 127.0.0.1:1071 → Xray → VLESS+Reality → Seoul
  └── everything else     → izRNaKFP → VMess+WS+TLS → KVM
```

### Step 1: Run Seoul Xray (SOCKS-only upstream)

```bash
cat > /etc/xray-seoul.json << 'EOF'
{
  "log": {"loglevel": "warning"},
  "inbounds": [{
    "port": 1071,
    "protocol": "socks",
    "listen": "127.0.0.1",
    "sniffing": {"enabled": true, "destOverride": ["http", "tls"]},
    "settings": {"udp": true, "auth": "noauth"}
  }],
  "outbounds": [{
    "protocol": "vless",
    "tag": "seoul",
    "settings": {
      "vnext": [{
        "address": "43.108.41.245",
        "port": 40001,
        "users": [{
          "id": "<UUID>",
          "encryption": "none",
          "level": 0
        }]
      }]
    },
    "streamSettings": {
      "network": "tcp",
      "security": "reality",
      "realitySettings": {
        "publicKey": "<PUBKEY>",
        "serverName": "www.microsoft.com",
        "shortId": "<SHORTID>",
        "fingerprint": "chrome",
        "spiderX": "/"
      }
    }
  }]
}
EOF
/usr/bin/xray run -c /etc/xray-seoul.json > /tmp/xray-seoul.log 2>&1 &
```

### Step 2: Modify PassWall V2Ray config

Add a `socks` outbound pointing to 127.0.0.1:1071, plus domain routing rules:

```json
{
  "outbounds": [
    { "... izRNaKFP (KVM) ..." },
    {
      "protocol": "socks",
      "tag": "seoul_socks",
      "settings": {
        "servers": [{"address": "127.0.0.1", "port": 1071}]
      }
    },
    { "... direct ..." },
    { "... blackhole ..." }
  ],
  "routing": {
    "domainStrategy": "AsIs",
    "domainMatcher": "hybrid",
    "rules": [{
      "type": "field",
      "outboundTag": "seoul_socks",
      "domain": [
        "domain:accounts.google.com",
        "domain:accounts.google.co.kr",
        "domain:accounts.google.com.hk",
        "domain:accounts.google.com.sg",
        "domain:accounts.youtube.com",
        "domain:oauth2.googleapis.com",
        "domain:www.googleapis.com",
        "domain:openidconnect.googleapis.com",
        "domain:securetoken.googleapis.com",
        "domain:identitytoolkit.googleapis.com",
        "domain:android.googleapis.com",
        "domain:clientauth.googleapis.com",
        "domain:people.googleapis.com",
        "domain:content-googleapis.com",
        "domain:ssl.gstatic.com",
        "domain:www.gstatic.com",
        "domain:apis.google.com",
        "domain:play.google.com",
        "domain:myaccount.google.com"
      ]
    }]
  }
}
```

### Step 3: Ensure Google auth domain IPs enter PassWall's blacklist

PassWall's gfwlist may NOT include accounts.google.com. Traffic to Google auth IPs would route directly (fail due to GFW), never reaching V2Ray's SNI routing.

**Fix**: Add Google auth domains to `proxy_host` UCI list (forces DNS through overseas → IPs enter `passwall_blacklist` → iptables redirects to V2Ray).

```bash
for domain in accounts.google.com accounts.youtube.com oauth2.googleapis.com \
  www.googleapis.com openidconnect.googleapis.com securetoken.googleapis.com \
  identitytoolkit.googleapis.com android.googleapis.com clientauth.googleapis.com \
  people.googleapis.com content-googleapis.com ssl.gstatic.com www.gstatic.com \
  apis.google.com play.google.com myaccount.google.com \
  accounts.google.co.kr accounts.google.com.hk accounts.google.com.sg; do
  uci add_list passwall.@global_rules[0].proxy_host="${domain}"
done
uci commit passwall
```

**Alternative**: Directly add Google AS15169 IP ranges to `passwall_blacklist` ipset:

```bash
for cidr in 173.194.0.0/16 142.250.0.0/15 142.251.0.0/16 \
  216.58.192.0/19 216.239.32.0/19 64.233.160.0/19 \
  74.125.0.0/16 172.217.0.0/16; do
  ipset add passwall_blacklist $cidr 2>/dev/null
done
```

### Step 4: Persistence

**Critical**: PassWall regenerates `/tmp/etc/passwall/TCP_SOCKS.json` on every restart, overwriting custom modifications.

**Solution**: Store the unified config template at `/etc/v2ray-unified.json` and use an init script (START=99, after PassWall) to copy it in:

```bash
cat > /etc/init.d/v2ray-seoul-inject << 'EOF'
#!/bin/sh /etc/rc.common
START=99
start() {
    sleep 15
    # Add Google IPs to blacklist
    for cidr in 173.194.0.0/16 142.250.0.0/15 142.251.0.0/16; do
        ipset add passwall_blacklist $cidr 2>/dev/null
    done
    # Inject unified config
    if ! grep -q "seoul_socks" /tmp/etc/passwall/TCP_SOCKS.json; then
        cp /etc/v2ray-unified.json /tmp/etc/passwall/TCP_SOCKS.json
        PID=$(ps | grep "TCP_SOCKS.json" | grep -v grep | awk '{print $1}')
        [ -n "$PID" ] && kill $PID
        sleep 1
        /tmp/etc/passwall/bin/v2ray run -c /tmp/etc/passwall/TCP_SOCKS.json \
          > /tmp/passwall-tcp.log 2>&1 &
    fi
}
EOF
chmod +x /etc/init.d/v2ray-seoul-inject
/etc/init.d/v2ray-seoul-inject enable
```

## Why ipset+iptables approach fails

Don't use dnsmasq ipset + iptables REDIRECT for domain-based proxy splitting:

1. **IP-level routing is too coarse**: When `accounts.google.com` resolves to 142.251.40.99 (shared with YouTube services), ALL traffic to that IP gets redirected, including video streaming
2. **Collateral damage**: Google's CDN domains (gstatic.com) resolve to shared IPs, pulling non-Google services (Facebook, Twitter) into the redirect
3. **SNI-based routing in V2Ray** solves this: routes by TLS SNI domain, not destination IP

## Full Google auth domain list

Used in the routing rules above. These 19 domains cover Google's complete OAuth/SSO/auth flow including regional variants and reCAPTCHA static resources.
