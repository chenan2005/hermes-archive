# Seoul Xray Multi-Inbound Config (Reference)

Three inbounds serving different purposes:

| Port | Protocol | Transport | TLS | Use |
|------|----------|-----------|-----|-----|
| 40001 | VLESS | TCP | Reality (www.microsoft.com) | Direct proxy (if CN→KR link allows) |
| 443 | VMess | WS | TLS (self-signed) | Direct proxy or Cloudflare Full SSL |
| 80 | VMess | WS | None | Cloudflare Flexible SSL / Tunnel backend |

## UUIDs

- Reality (40001): `a5fa1889-1316-4115-a866-96c8f30523ef`, flow=xtls-rprx-vision
- VMess (80/443): `ac6aa939-156c-452f-a7da-4ddd79b7d5c9`

## Full Config JSON

```json
{
  "log": {"loglevel": "warning"},
  "inbounds": [
    {
      "listen": "0.0.0.0", "port": 40001, "protocol": "vless",
      "settings": {
        "clients": [{"id": "a5fa1889-1316-4115-a866-96c8f30523ef", "flow": "xtls-rprx-vision", "email": "openwrt"}],
        "decryption": "none", "fallbacks": []
      },
      "streamSettings": {
        "network": "tcp", "security": "reality",
        "realitySettings": {
          "dest": "www.microsoft.com:443",
          "serverNames": ["www.microsoft.com"],
          "privateKey": "4A7jrb8gbfL96N9Zb774hL0rTDM3FmmbwLB3J-cyWlo",
          "shortIds": ["a1b2c3d4"],
          "settings": {"publicKey": "0o3XsyApUXA0_1Ns2GZPbzLCbUW8zpAarRxCbb0gr1g", "fingerprint": "chrome", "spiderX": "/"}
        }
      },
      "tag": "inbound-40001",
      "sniffing": {"enabled": true, "destOverride": ["http", "tls", "quic"]}
    },
    {
      "listen": "0.0.0.0", "port": 443, "protocol": "vmess",
      "settings": {
        "clients": [{"id": "ac6aa939-156c-452f-a7da-4ddd79b7d5c9", "email": "openwrt-cf"}]
      },
      "streamSettings": {
        "network": "ws", "security": "tls",
        "tlsSettings": {
          "serverName": "seoul.bernarty.xyz",
          "certificates": [{"certificateFile": "/etc/ssl/seoul/cert.pem", "keyFile": "/etc/ssl/seoul/key.pem"}]
        },
        "wsSettings": {"path": "/ws-seoul"}
      },
      "tag": "inbound-443",
      "sniffing": {"enabled": true, "destOverride": ["http", "tls"]}
    },
    {
      "listen": "0.0.0.0", "port": 80, "protocol": "vmess",
      "settings": {
        "clients": [{"id": "ac6aa939-156c-452f-a7da-4ddd79b7d5c9", "email": "openwrt-cf"}]
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

## Testing Servers

| Source | URL | Purpose |
|--------|-----|---------|
| Tokyo Linode | http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin | Asia bandwidth |
| Singapore Linode | http://speedtest.singapore.linode.com/100MB-singapore.bin | SEA bandwidth |
| CacheFly | http://cachefly.cachefly.net/100mb.test | US CDN (often geo-blocked from KR/CN) |
