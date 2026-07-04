# PassWall V2Ray SNI Split Routing Config (Unified)

This is the dual-outbound V2Ray config template for OpenWrt PassWall.
Kept at `/etc/v2ray-unified.json` and copied over PassWall's generated `TCP_SOCKS.json` after each restart.

## Architecture (Two Approaches)

### Approach A: Cloudflare Tunnel (Recommended, ~15-28 Mbps)

```
V2Ray inbound -> SNI matching -> seoul_tunnel outbound (VMess+WS+TLS)
                                  -> Cloudflare Tunnel URL (trycloudflare.com)
                                  -> cloudflared (Seoul VPS)
                                  -> xray :80 (VMess+WS, no TLS)
```

This is the current approach. No separate xray process on the client side — the secondary outbound connects directly to the Cloudflare tunnel.

### Approach B: Local Xray Upstream (~0.75 Mbps, DEPRECATED)

```
V2Ray inbound -> SNI matching -> seoul_socks outbound (SOCKS)
                                  -> separate xray process on 127.0.0.1:1071
                                  -> Seoul Reality (43.108.41.245:40001, direct)
```

This requires running a separate Xray instance on the OpenWrt router. Only use if Cloudflare Tunnel is unavailable.

## Approach A: Full Config (VMISS default + Cloudflare Tunnel Seoul outbound)

```json
{
  "outbounds": [
    {
      "protocol": "vmess",
      "tag": "vmiss",
      "settings": {
        "vnext": [{
          "address": "vmiss.bernarty.xyz",
          "port": 443,
          "users": [{"id": "<uuid>", "security": "auto"}]
        }]
      },
      "streamSettings": {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {"serverName": "vmiss.bernarty.xyz"},
        "wsSettings": {"path": "/ws-vmiss", "headers": {"Host": "vmiss.bernarty.xyz"}},
        "sockopt": {"mark": 255}
      },
      "mux": {"enabled": false}
    },
    {
      "protocol": "vmess",
      "tag": "seoul_tunnel",
      "settings": {
        "vnext": [{
          "address": "<tunnel-hostname>.trycloudflare.com",
          "port": 443,
          "users": [{"id": "<uuid>", "security": "auto"}]
        }]
      },
      "streamSettings": {
        "network": "ws",
        "security": "tls",
        "tlsSettings": {"serverName": "<tunnel-hostname>.trycloudflare.com"},
        "wsSettings": {"path": "/ws-seoul", "headers": {"Host": "<tunnel-hostname>.trycloudflare.com"}},
        "sockopt": {"mark": 255}
      },
      "mux": {"enabled": false}
    },
    {"protocol": "freedom", "tag": "direct", "streamSettings": {"sockopt": {"mark": 255}}, "settings": {"domainStrategy": "UseIPv4"}},
    {"protocol": "blackhole", "tag": "blackhole"}
  ],
  "routing": {
    "domainStrategy": "AsIs", "domainMatcher": "hybrid",
    "rules": [{
      "type": "field", "outboundTag": "seoul_tunnel",
      "domain": [
        "domain:accounts.google.com", "domain:accounts.google.co.kr",
        "domain:accounts.google.com.hk", "domain:accounts.google.com.sg",
        "domain:accounts.youtube.com", "domain:oauth2.googleapis.com",
        "domain:www.googleapis.com", "domain:openidconnect.googleapis.com",
        "domain:securetoken.googleapis.com", "domain:identitytoolkit.googleapis.com",
        "domain:android.googleapis.com", "domain:clientauth.googleapis.com",
        "domain:people.googleapis.com", "domain:content-googleapis.com",
        "domain:ssl.gstatic.com", "domain:www.gstatic.com",
        "domain:apis.google.com", "domain:play.google.com",
        "domain:myaccount.google.com"
      ]
    }]
  },
  "inbounds": [
    {"port": 1070, "protocol": "socks", "sniffing": {"enabled": true, "destOverride": ["http", "tls"]},
     "settings": {"udp": true, "auth": "noauth"}, "listen": "0.0.0.0"},
    {"sniffing": {"enabled": true, "domainsExcluded": ["courier.push.apple.com","Mijia Cloud"],
     "destOverride": ["http", "tls"], "metadataOnly": false},
     "settings": {"network": "tcp", "followRedirect": true},
     "streamSettings": {"sockopt": {"tproxy": "redirect"}},
     "port": 1041, "protocol": "dokodemo-door", "tag": "tcp_redir"}
  ],
  "log": {"loglevel": "warning"},
  "policy": {"levels": {"0": {"statsUserUplink": false, "statsUserDownlink": false}}}
}
```

## Post-PassWall Injection Script

To survive PassWall restarts, use an init script at `/etc/init.d/v2ray-seoul-inject` (START=99):

```
cp /etc/v2ray-unified.json /tmp/etc/passwall/TCP_SOCKS.json
kill $(ps | grep "TCP_SOCKS.json" | awk '{print $1}')
sleep 1
/tmp/etc/passwall/bin/v2ray run -c /tmp/etc/passwall/TCP_SOCKS.json > /tmp/passwall-tcp.log 2>&1 &
```

## Seoul xray Side Config

Kept at `/etc/xray-seoul.json`, Xray instance listening on port 1071 (SOCKS):

```json
{
  "inbounds": [{
    "port": 1071,
    "protocol": "socks",
    "listen": "127.0.0.1",
    "settings": {"udp": true, "auth": "noauth"}
  }],
  "outbounds": [{
    "protocol": "vless",
    "settings": {
      "vnext": [{
        "address": "43.108.41.245",
        "port": 40001,
        "users": [{"id": "<uuid>", "encryption": "none"}]
      }]
    },
    "streamSettings": {
      "network": "tcp",
      "security": "reality",
      "realitySettings": {
        "publicKey": "<public-key>",
        "serverName": "www.microsoft.com",
        "shortId": "<short-id>",
        "fingerprint": "chrome",
        "spiderX": "/"
      }
    }
  }]
}
```
