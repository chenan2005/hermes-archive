# Multi-Inbound Xray Server

Run multiple proxy protocols on the same VPS simultaneously. Verified on Alibaba Cloud Seoul with 3 active inbounds.

## Architecture

```
                    ┌───────────────┐
                    │   Xray        │
                    │   (direct,    │
                    │   no x-ui)    │
                    │               │
Port 80  ──────────┤  VMess+WS     │──→ Freedom outbound
                    │  (no TLS)     │
Port 443 ──────────┤  VMess+WS+TLS │
                    │  (self-signed)│
Port 40001 ────────┤  VLESS+Reality│
                    └───────────────┘
```

## Config file

Deployed at `/usr/local/x-ui/bin/config.json` (runs directly, not via x-ui):

```json
{
  "log": {"loglevel": "warning"},
  "inbounds": [
    {
      "listen": "0.0.0.0",
      "port": 40001,
      "protocol": "vless",
      "settings": {
        "clients": [{"id": "<UUID>", "flow": "xtls-rprx-vision", "email": "openwrt"}],
        "decryption": "none", "fallbacks": []
      },
      "streamSettings": {
        "network": "tcp", "security": "reality",
        "realitySettings": {
          "dest": "www.microsoft.com:443",
          "serverNames": ["www.microsoft.com"],
          "privateKey": "<PRIVATE_KEY>",
          "shortIds": ["a1b2c3d4"],
          "settings": {
            "publicKey": "<PUBLIC_KEY>",
            "fingerprint": "chrome",
            "spiderX": "/"
          }
        }
      },
      "tag": "inbound-40001",
      "sniffing": {"enabled": true, "destOverride": ["http", "tls", "quic"]}
    },
    {
      "listen": "0.0.0.0",
      "port": 443,
      "protocol": "vmess",
      "settings": {
        "clients": [{"id": "<UUID>", "email": "openwrt-cf"}]
      },
      "streamSettings": {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {
          "serverName": "seoul.example.com",
          "certificates": [{
            "certificateFile": "/etc/ssl/seoul/cert.pem",
            "keyFile": "/etc/ssl/seoul/key.pem"
          }]
        },
        "wsSettings": {"path": "/ws-seoul"}
      },
      "tag": "inbound-443",
      "sniffing": {"enabled": true, "destOverride": ["http", "tls"]}
    },
    {
      "listen": "0.0.0.0",
      "port": 80,
      "protocol": "vmess",
      "settings": {
        "clients": [{"id": "<UUID>", "email": "openwrt-cf"}]
      },
      "streamSettings": {
        "network": "ws", "security": "none",
        "wsSettings": {"path": "/ws-seoul"}
      },
      "tag": "inbound-80-ws",
      "sniffing": {"enabled": true, "destOverride": ["http", "tls"]}
    }
  ],
  "outbounds": [
    {"protocol": "freedom", "settings": {}, "tag": "direct"},
    {"protocol": "blackhole", "settings": {}, "tag": "blocked"}
  ]
}
```

## Deploy

```bash
# 1. Stop x-ui (it would overwrite our manual config)
sudo systemctl stop x-ui
sudo killall xray xray-linux-amd64

# 2. Write config
sudo tee /usr/local/x-ui/bin/config.json < /path/to/config.json

# 3. Start xray directly
sudo /usr/local/x-ui/bin/xray-linux-amd64 \
  -c /usr/local/x-ui/bin/config.json > /tmp/xray.log 2>&1 &

# 4. Verify all ports
ss -tlnp | grep -E ":(80|443|40001) "
```

X-UI web panel still works for monitoring — just don't click its "restart xray" button (it'll start a second instance and cause port conflicts).

## Port allocation rationale

| Port | Protocol | Purpose |
|------|----------|---------|
| 80 | VMess+WS (no TLS) | Cloudflare Tunnel upstream. Cloudflare handles TLS, so origin doesn't need it. |
| 443 | VMess+WS+TLS | Cloudflare CDN proxied (orange cloud). Self-signed cert works with "Full" mode. |
| 40001 | VLESS+Reality | Direct connection for clients that prefer native Reality. |
| 22 | SSH | Management (always available). |

## Generating self-signed cert for port 443

```bash
sudo mkdir -p /etc/ssl/seoul
sudo openssl req -x509 -newkey rsa:2048 \
  -keyout /etc/ssl/seoul/key.pem \
  -out /etc/ssl/seoul/cert.pem \
  -days 3650 -nodes \
  -subj "/CN=seoul.example.com"
```

## Cloudflared tunnel integration (systemd)

Point the tunnel at the local xray port 80 (VMess+WS, no TLS — Cloudflare handles TLS on the edge):

```bash
# systemd service
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << 'SERVICE'
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
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared
```

### Fetching the tunnel URL

```bash
sudo journalctl -u cloudflared --no-pager | grep -o "https://[a-z0-9.-]*\.trycloudflare\.com" | tail -1
```

The URL changes on cloudflared restart. The client V2Ray config must be updated with the new URL. On OpenWrt, also update `/etc/hosts` if DNS can't resolve the tunnel domain (some ISPs/dns resolvers block `trycloudflare.com`).

### Pitfall: cloudflared version

Version 2026.6.1 (latest as of June 2026) fails with `"invalid UUID length: 0"` on quick tunnel. Use **2024.12.2**:
```bash
curl -sL https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/cloudflared-linux-amd64 -o /tmp/cf
```

### Integration with multi-inbound xray

The tunnel URL resolves to Cloudflare edge IPs. The client V2Ray connects via VMess+WS+TLS to `*.trycloudflare.com:443`. Cloudflare forwards through the tunnel to Seoul xray port 80 (VMess+WS, no TLS, path `/ws-seoul`).

Flow: `Client V2Ray → TLS → Cloudflare edge → tunnel (QUIC) → cloudflared → localhost:80 → xray (VMess+WS)`

## Client connections

- **Reality (direct)**: `43.108.41.245:40001`, VLESS, TLS, Reality
- **Cloudflare CDN (443)**: `seoul.example.com:443`, VMess, WS+TLS, path `/ws-seoul`
- **Cloudflare Tunnel (80)**: `*.trycloudflare.com:443`, VMess, WS+TLS, path `/ws-seoul`
