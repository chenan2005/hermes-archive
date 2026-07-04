# Why dokodemo-door MUST listen on 0.0.0.0 for iptables REDIRECT

## The problem

When iptables uses the REDIRECT target:

```
iptables -t nat -A PREROUTING -p tcp --dport 443 -j REDIRECT --to-port 1072
```

It rewrites the packet's **destination IP** to the primary IP of the interface the packet arrived on. 

If the packet came in on the LAN interface (e.g. `br-lan` with IP `192.168.37.1`):

- Original packet: `src=192.168.37.234 dst=173.194.202.84:443`
- After REDIRECT: `src=192.168.37.234 dst=192.168.37.1:1072`

## The consequence

If xray's dokodemo-door inbound is configured with `"listen": "127.0.0.1"`, it only accepts connections to `127.0.0.1:1072`. The REDIRECT-ed packet has destination `192.168.37.1:1072`, so xray never sees it.

## The fix

Always use `"listen": "0.0.0.0"` for dokodemo-door inbounds that receive iptables REDIRECT traffic:

```json
{
  "port": 1072,
  "protocol": "dokodemo-door",
  "listen": "0.0.0.0",
  "settings": {"network": "tcp,udp", "followRedirect": true},
  "streamSettings": {"sockopt": {"tproxy": "redirect"}}
}
```

## Verification

Check xray logs — a working redirect shows the original destination IP:

```
from 192.168.37.234:56906 accepted tcp:173.194.202.84:443 [seoul_redir >> seoul]
```

The `tcp:173.194.202.84:443` is the ORIGINAL destination — xray's dokodemo-door reads it from the conntrack mark. This confirms REDIRECT → dokodemo-door worked correctly.

## Also: OUTPUT chain

For the router's own locally-generated traffic, REDIRECT rules in the OUTPUT chain behave the same way — destination IP is rewritten to the outgoing interface's IP. Same requirement: `listen: 0.0.0.0`.
