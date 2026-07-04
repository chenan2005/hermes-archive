# ipset + iptables Fallback (use only when SNI routing is impractical)

> **Prefer SNI routing.** This method has known IP collision problems. Only use when you cannot modify PassWall's V2Ray config.

## Setup

### 1. Create secondary Xray config

`/etc/xray-seoul.json` with TWO inbounds:
- SOCKS (:1071) — for testing
- dokodemo-door (:1072) — for iptables REDIRECT

**CRITICAL**: dokodemo-door must listen on `"0.0.0.0"`, NOT `"127.0.0.1"`. iptables REDIRECT changes the destination IP to the interface address (e.g., 192.168.37.1), so 127.0.0.1 won't receive the traffic.

```json
{
  "inbounds": [
    { "port": 1071, "protocol": "socks", "listen": "0.0.0.0", ... },
    { "port": 1072, "protocol": "dokodemo-door", "listen": "0.0.0.0",
      "settings": {"network": "tcp,udp", "followRedirect": true},
      "streamSettings": {"sockopt": {"tproxy": "redirect"}},
      "tag": "secondary_redir" }
  ],
  "outbounds": [{ ... }]
}
```

### 2. Add dnsmasq ipset rules

```bash
for domain in accounts.google.com oauth2.googleapis.com ...; do
  uci add_list dhcp.@dnsmasq[0].ipset="/${domain}/google_auth"
done
uci commit dhcp
/etc/init.d/dnsmasq restart
```

### 3. Create ipset + iptables rules

```bash
ipset create google_auth hash:ip timeout 3600

# PREROUTING — LAN devices (forwarded traffic)
iptables -t nat -I PREROUTING 1 -m set --match-set google_auth dst -p tcp -j REDIRECT --to-port 1072
iptables -t nat -I PREROUTING 1 -m set --match-set google_auth dst -p udp -j REDIRECT --to-port 1072

# OUTPUT — router's own traffic
iptables -t nat -I OUTPUT 1 -m set --match-set google_auth dst -p tcp -j REDIRECT --to-port 1072
iptables -t nat -I OUTPUT 1 -m set --match-set google_auth dst -p udp -j REDIRECT --to-port 1072
```

**Must be at position 1** — before PassWall's PSW_REDIRECT/PSW_OUTPUT.

### 4. Persist iptables

`/etc/hotplug.d/iface/99-google-auth`:
```sh
#!/bin/sh
[ "$ACTION" = "ifup" ] || exit 0
sleep 10
ipset create google_auth hash:ip timeout 3600 2>/dev/null
# Delete old + insert at top
iptables -t nat -D PREROUTING -m set --match-set google_auth dst -p tcp -j REDIRECT --to-port 1072 2>/dev/null
iptables -t nat -I PREROUTING 1 -m set --match-set google_auth dst -p tcp -j REDIRECT --to-port 1072
# ... (repeat for udp, and for OUTPUT chain)
```

## IP collision problem

This method routes based on IP, not domain. Google uses shared IPs:

```
accounts.google.com → 142.251.40.99
www.googleapis.com   → 142.251.40.99  ← same IP!
googlevideo.com      → 142.251.40.99  ← same IP!
```

Once 142.251.40.99 is in the ipset, ALL traffic to it goes through the secondary proxy — including YouTube video streams.

Worse: if any Google auth domain resolves through a shared CDN to a non-Google IP (Facebook's 157.240.7.20, Twitter's 104.244.42.197), those services get hijacked too.

### Symptoms

```bash
ipset list google_auth
# Facebook IPs (157.240.x.x, 31.13.x.x) in the set → collision
# Twitter IPs (104.244.x.x) → collision
```

### Mitigation (partial)

1. Remove CDN domains from ipset (`ssl.gstatic.com`, `www.gstatic.com` use shared CDNs)
2. Keep ipset timeout short (already 3600s)
3. Regular flush
