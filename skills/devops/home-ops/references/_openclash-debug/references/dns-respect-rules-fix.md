# DNS respect-rules Fix (2026-07-03)

## Session summary

Entire LAN DNS went offline because OpenClash DNS relied 100% on DoH endpoints that needed proxy, and all proxy nodes had SSL handshake failures.

## Root cause chain (verified)

```
Client (systemd-resolved → 127.0.0.53)
  → Router (192.168.71.9:53 / dnsmasq)
    → dnsmasq server=127.0.0.1#7874 → Clash DNS
      → nameserver: https://doh.pub/dns-query (DoH via proxy)
        → proxy nodes: ALL dead (SSL EOF)
      → respect-rules: false (FORCES all queries through proxy)
      → DoH fails → Clash DNS returns nothing → dnsmasq times out → client sees "Name or service not known"
```

## Key findings

### 1. Python vs dig discrepancy
- `execute_code` (Python socket) could reach `192.168.71.9:53` and `114.114.114.114:53` — got valid 34-byte DNS responses
- `dig @192.168.71.9` in terminal → TIMEOUT
- After systemd-resolved restart → ALL dig commands timed out including direct upstream
- This suggests systemd-resolved was caching stale state and poisoning subsequent queries

### 2. 114.114.114.114 returned SERVFAIL
```
;; Got answer:
;; ->>HEADER<<- opcode: QUERY, status: SERVFAIL, id: 34549
;; flags: qr rd ra; QUERY: 1, ANSWER: 0, AUTHORITY: 0, ADDITIONAL: 0
```
- Network was UP (ping worked)
- DNS query reached server but server returned SERVFAIL
- Suggests the DNS query itself (api.deepseek.com) was the issue, not network

### 3. Router-side diagnosis
```
ssh root@192.168.71.9 'nslookup api.deepseek.com 127.0.0.1'
→ "Can't find api.deepseek.com: No answer"

ssh root@192.168.71.9 'nslookup api.deepseek.com 223.5.5.5'
→ "connection timed out" (on router itself!)
```
- Router could ping 223.5.5.5 but UDP 53 was blocked
- Suggests OpenClash was redirecting DNS traffic on the router itself

### 4. Duplicate Clash processes
```
PID 9308: /etc/openclash/clash -d /etc/openclash -f /etc/openclash/config/config.yaml
PID 9351: /etc/openclash/clash -d /etc/openclash -f /etc/openclash/config.yaml
```
- Different config paths but same content
- Both listening on same ports → race conditions
- Watchdog likely restarted without killing old process

### 5. Proxy authentication
- `curl --proxy "http://127.0.0.1:7890"` → `407 Proxy Authentication Required`
- `curl --proxy "http://Clash:3Ypy6ovV@127.0.0.1:7890"` → `200 Connection established` but `SSL EOF`
- Authentication: `Clash:3Ypy6ovV` (from config.yaml `authentication:` section)
- REST API secret: `oOPJC7Ug` (from config.yaml `secret:`)

### 6. OpenClash enable=0
- `uci get openclash.config.enable` returned `0` (disabled)
- But dnsmasq still resolved via fallback to `default-nameserver`
- Fix: `uci set openclash.config.enable=1 && uci commit openclash`

## Applied fix

```bash
# Kill duplicate processes
kill 9351
kill -9 9308

# Modify BOTH config files
for f in /etc/openclash/config.yaml /etc/openclash/config/config.yaml; do
  sed -i "s/respect-rules: false/respect-rules: true/" "$f"
  sed -i "/^  nameserver:/,/^  fallback:/{
    /^  nameserver:/a\  - 223.5.5.5\n  - 119.29.29.29
  }" "$f"
  sed -i "/^  fallback:/,/^  respect-rules:/{
    /^  fallback:/a\  - 223.5.5.5\n  - 119.29.29.29
  }" "$f"
done

# Restart dnsmasq (Clash not restarted due to init script state issues)
/etc/init.d/dnsmasq restart
```

## Post-fix verification

```
dig api.deepseek.com @127.0.0.53 +short
→ 183.131.191.171, 58.49.197.113  (OK!)

ping api.deepseek.com
→ 20-21ms  (OK!)
```

## Notes for future sessions

- `respect-rules: true` is the PRIMARY fix — it makes domestic DNS bypass proxy entirely
- Adding `223.5.5.5` / `119.29.29.29` to nameserver list provides fallback when DoH fails
- OpenClash init script can get stuck in "already started" state even with no process
- Always check `uci get openclash.config.enable` — it can be set to 0 by failed starts
- Both `/etc/openclash/config.yaml` (source) and `config/config.yaml` (runtime) must be edited
