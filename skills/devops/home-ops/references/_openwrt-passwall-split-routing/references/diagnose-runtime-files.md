# Diagnosing Missing PassWall Runtime Files

When `proxy_host` domains are correctly configured in uci but traffic still goes direct (times out on blocked domains), the runtime files may not have been generated.

## Symptom

- `accounts.google.com` is in `proxy_host` uci list
- curl direct from LAN times out (TCP handshake never completes)
- SOCKS5 proxy works (via PassWall's tcp_node_socks_port, e.g. :1070)
- iptables PSW chain shows REDIRECT rules for `passwall_shuntlist` / `passwall_gfwlist` but they're never matched

## Diagnostic Chain

### 1. Check uci configuration

```bash
ssh root@192.168.37.1
uci show passwall.@global_rules[0].proxy_host | grep "accounts.google"
```

Expected: domain is listed. If not, add it:

```bash
uci add_list passwall.@global_rules[0].proxy_host="accounts.google.com"
uci commit passwall
```

### 2. Check runtime files exist

```bash
# Should be non-empty and contain the domains you configured
ls -la /tmp/etc/passwall/proxy_host
cat /tmp/etc/passwall/proxy_host | head -20

# dnsmasd.d should have a passwall config
ls /tmp/etc/dnsmasq.d/ | grep passwall
cat /tmp/etc/dnsmasq.d/passwall.conf 2>/dev/null | head -20
```

**If files are missing or empty** → PassWall didn't generate runtime configs. Restart:

```bash
/etc/init.d/passwall restart
```

### 3. Verify ipsets populated correctly

```bash
# Shuntlist should contain many entries (not just hand-configured IPs)
ipset list passwall_shuntlist | wc -l

# Check if the target domain's IP is in the shuntlist
IP=$(nslookup accounts.google.com 127.0.0.1 | grep Address | tail -1 | awk '{print $2}')
ipset test passwall_shuntlist $IP 2>/dev/null && echo "IN shuntlist" || echo "NOT in shuntlist"
ipset test passwall_gfwlist $IP 2>/dev/null && echo "IN gfwlist" || echo "NOT in gfwlist"
```

**Before restart** — shuntlist has only ~18 entries (hand-configured IPs only), gfwlist has ~1800 but missing the target domain.

**After restart** — shuntlist should grow to thousands (geosite:geolocation-!cn resolved), or gfwlist should include the target IP.

### 4. Trace the iptables chain

```bash
iptables -t nat -S PSW 2>/dev/null
```

Key rules in order:
```
-A PSW -m set --match-set passwall_lanlist dst -j RETURN
-A PSW -m set --match-set passwall_vpslist dst -j RETURN
-A PSW -m set --match-set passwall_whitelist dst -j RETURN
-A PSW -d 192.168.37.1/32 -j RETURN                    # WAN_IP_RETURN
-A PSW -m multiport --dports 22,25,53,143,465,587,853,993,995,80,443 \
       -m set --match-set passwall_shuntlist dst -j REDIRECT --to-ports 1041
-A PSW -m multiport --dports ... -m set --match-set passwall_blacklist dst -j REDIRECT --to-ports 1041
-A PSW -m multiport --dports ... -m set --match-set passwall_gfwlist dst -j REDIRECT --to-ports 1041
-A PSW -j RETURN                                         # fallthrough → direct
```

If the IP isn't in any of the three proxy ipsets, it falls through to `RETURN` and goes **direct**.

### 5. Verify DNS goes through OpenWrt

```bash
# From the LAN client
resolvectl status | grep "DNS Server"
# Should show 192.168.37.1 (or your OpenWrt LAN IP)
```

If client uses DoH/DoT (e.g., Chrome's built-in secure DNS), dnsmasq never intercepts the query, ipset never populates. Fix: disable secure DNS in the browser, or configure OpenWrt to intercept DoH.

### 6. SOCKS5 test (bypasses transparent proxy)

If this works but the transparent proxy doesn't, the issue is in the iptables/ipset layer:

```bash
curl -sI --socks5 192.168.37.1:1070 https://accounts.google.com/
```

## Root causes

- **PassWall restart required** — most common fix. After uci changes, PassWall may not regenerate runtime files until restarted.
- **geosite dat file missing or outdated** — the `geosite:geolocation-!cn` rule in shunt rules needs `/usr/share/v2ray/geosite.dat`. If absent, shuntlist never populates.
- **chinadns-ng not running** — DNS-based ipset population relies on chinadns-ng.
- **iptables modules not loaded** — check `lsmod | grep xt_set` on older OpenWrt kernels (uncommon on 5.x).

## Shuntlist size as a diagnostic indicator

The `passwall_shuntlist` ipset has TWO sources of entries:

1. **Static IP entries** — directly from shunt rule `ip_list` fields (DNS servers, CDN ranges). These are always present.
2. **Dynamic domain entries** — populated by dnsmasq + chinadns-ng when a domain matches a shunt rule (e.g. `geosite:geolocation-!cn`). These appear ONLY when DNS queries for non-Chinese domains return IPs that get added to the set.

**Diagnostic rule of thumb:**

| shuntlist entry count | Meaning |
|---|---|
| ~10-20 | Only static IPs loaded. Domain-based (geosite) rules NOT populating. |
| Hundreds+ | Domain matching working. |

A shuntlist stuck at ~18 entries (only IPs from shunt rule `ip_list` fields like `8.8.8.8`, `1.1.1.1`, `223.5.5.5` etc.) means domain-based geosite rules are not populating — even if chinadns-ng is running, the ipset isn't being fed.

## Fake DNS mechanism (198.18.0.0/16 redirect)

PassWall uses **fake DNS** as an alternative to ipset-based routing. When chinadns-ng determines a non-Chinese domain, dnsmasq may return a **fake IP** in the `198.18.0.0/16` range instead of the real IP. The iptables PSW chain has a dedicated rule for this:

```
-A PSW -d 198.18.0.0/16 -p tcp -j REDIRECT --to-ports 1041
```

This rule **precedes** the ipset-based shuntlist/gfwlist rules, so it takes priority. Fake DNS is often the mechanism that actually makes domains route through the proxy — the ipset approach is supplementary.

**Diagnostic:** If the shuntlist has few entries but `accounts.google.com` still routes correctly through the proxy (returns HTTP 302), fake DNS is likely the working mechanism. The real IP is never matched in the ipset — instead, the client's DNS query returns a 198.18.x.x address, and the iptables redirect catches it there.

**When fake DNS breaks:**
- If the client bypasses OpenWrt's DNS (DoH/DoT in browser, hardcoded 8.8.8.8), the DNS query never hits dnsmasq → no fake IP → traffic goes to the real Google IP → not matched by the 198.18/16 rule → falls through to shuntlist/gfwlist checks → likely not in either → RETURN → direct → timeout.
