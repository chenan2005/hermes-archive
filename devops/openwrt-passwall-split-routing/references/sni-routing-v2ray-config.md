# SNI Routing: V2Ray Config Injection

## Why this works

PassWall's V2Ray handles ALL traffic (both SOCKS on :1070 and transparent proxy on :1041). By injecting a second outbound + SNI-based routing rules, we make V2Ray itself decide which proxy to use — at the domain level, not IP level.

## Key constraint: V2Ray ≠ Xray

PassWall bundles `v2ray` (V2Ray), NOT `xray` (Xray). V2Ray does NOT support:
- VLESS+Reality protocol
- Hysteria2
- Other Xray-only features

To use a Reality node, we chain: `V2Ray outbound → SOCKS → local Xray → Reality`.

## The two config changes

Starting from PassWall's generated `/tmp/etc/passwall/TCP_SOCKS.json`:

### Change 1: Add SOCKS outbound

Insert after the main proxy outbound (tag `izRNaKFP` or similar) and before `direct`:

```json
{
  "protocol": "socks",
  "tag": "seoul_socks",
  "settings": {
    "servers": [{
      "address": "127.0.0.1",
      "port": 1071
    }]
  }
}
```

### Change 2: Replace empty routing rules

Find `"rules": [\n    ]` and replace with:

```json
"rules": [
  {
    "type": "field",
    "outboundTag": "seoul_socks",
    "domain": [
      "domain:accounts.google.com",
      "domain:oauth2.googleapis.com",
      ...
    ]
  }
]
```

### What NOT to change

- `mark: 255` on outbounds — PassWall's nat OUTPUT chain has `mark match 0xff RETURN` which lets V2Ray's own outbound traffic bypass the redirect (prevents loop)
- `_flag_tag`, `_flag_proxy`, `_flag_proxy_tag` — PassWall metadata, not functional but keep for compatibility
- Inbounds, log, policy sections — leave exactly as generated

## How the mark bypass works

PassWall's iptables nat OUTPUT chain:
```
RETURN ... mark match 0xff    ← V2Ray outbound packets (mark=255=0xFF) RETURN here
REDIRECT ... match-set passwall_gfwlist dst redir ports 1041  ← never reached for V2Ray's own traffic
```

Without mark 255, V2Ray's outbound connections would be re-redirected to itself (port 1041) → infinite loop.

## Verification flow

1. Device resolves `accounts.google.com` → gets IP (e.g., 173.194.65.84)
2. IP is in `passwall_blacklist` (or `passwall_gfwlist`) → iptables redirects TCP SYN to :1041
3. V2Ray dokodemo-door receives the raw TCP, TLS ClientHello contains SNI `accounts.google.com`
4. V2Ray routing rule matches `domain:accounts.google.com` → outbound `seoul_socks`
5. V2Ray SOCKS outbound connects to 127.0.0.1:1071 (Xray), relays the TCP stream
6. Xray receives the socks connection, connects to Seoul Reality node, forwards to accounts.google.com
7. Google sees the Seoul IP (not KVM IP) → login allowed ✅

## Debugging SNI routing failures

If transparent proxy test fails but SOCKS test works:

1. Check if domain's IP is in a redirect ipset: `ipset test passwall_gfwlist <IP>`
2. If NOT in any redirect set → traffic goes direct, never reaches V2Ray → add to proxy_host or blacklist
3. Check V2Ray log: `tail /tmp/passwall-tcp.log | grep <domain>`
4. If log shows `accepted tcp:<IP>:443 [main_node]` instead of `[seoul_socks]` → SNI not extracted or routing rule not matching
5. Add `"loglevel": "debug"` to V2Ray config to see SNI extraction details

## Config injection script pattern

```bash
# Store unified config template
cat > /etc/v2ray-unified.json << 'EOF'
{ ... full unified config ... }
EOF

# Inject after PassWall starts
cp /etc/v2ray-unified.json /tmp/etc/passwall/TCP_SOCKS.json
kill $(ps | grep "TCP_SOCKS.json" | grep -v grep | awk '{print $1}')
sleep 1
/tmp/etc/passwall/bin/v2ray run -c /tmp/etc/passwall/TCP_SOCKS.json > /tmp/passwall-tcp.log 2>&1 &
```

**Important**: The unified config template hardcodes the main node's credentials (UUID, address, etc.). If the user changes the main proxy node in PassWall, update the template too.
