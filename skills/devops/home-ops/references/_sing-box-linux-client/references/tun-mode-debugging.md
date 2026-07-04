# TUN Mode Debugging Session Notes (2026-07-01)

## Environment
- **OS**: Linux Mint 22, kernel 6.8.0-124-generic
- **Network**: WiFi wlp1s0, gateway 192.168.71.1 (ISP modem/router)
- **sing-box**: v1.13.14, installed at /usr/local/bin/sing-box
- **Node**: VMISS-HK (vmiss.bernarty.xyz, VLESS+WS+TLS), Alibaba-Seoul-VLESS (43.108.41.245)
- **DNS**: 223.5.5.5 (AliDNS, direct, type: udp)
- **CAP_NET_ADMIN**: Granted via `sudo setcap cap_net_admin+ep /usr/local/bin/sing-box`
- **Management**: Python script ~/.local/bin/sing-box-ctrl.py (platform-aware, platform module)

## Outcome: TUN Mode Abandoned

After 4 attempts, TUN mode (`auto_route` + `strict_route`) caused network outages every time. The root-level issue is a compatibility conflict between sing-box's nftables rules and Linux Mint's NetworkManager-managed networking stack.

**Final decision (2026-07-01):** All TUN code removed from `sing-box-ctrl.py`. Stick with SOCKS5/Mixed port mode. The convenience of automatic traffic capture does not justify the risk of repeated network outages.

## Attempts Summary

### Attempt 1 — Full config (dns_mode + sniff + strict_route)

**Config**: TUN inbound with `strict_route: true`, `dns_mode: "hijack"`, `sniff: true`, plus fakeip DNS server.

**Result**: Fatal errors on both `dns_mode` (1.14+ field) and `sniff` (removed 1.13). Sing-box crashed immediately. nftables rules from `strict_route` remained active → complete network outage. User manually stopped sing-box to recover.

**Root cause**: Version-incompatible fields in a production release. Always validate with `sing-box check -c config.json` before applying. The `dns_mode` field is documented as "since sing-box 1.14.0" on the docs page but we were on 1.13.14.

### Attempt 2 — strict_route: false (no dns_mode, no sniff)

**Config**: TUN inbound with `strict_route: false`, removed `dns_mode` and `sniff`.

**Result**: Baidu (domestic) returned HTTP 200. Google (international) returned HTTP 000 (connection failure). Google via SOCKS5 proxy (port 10880) returned 302 (working). Proxy node connectivity was fine, but TUN-routed international traffic didn't work.

**Diagnosis**: `strict_route: false` does NOT add nftables fwmark bypass rules. Without fwmark bypass, sing-box's own outbound connections to proxy nodes also enter the TUN interface → routing loop: connect to node → go through TUN → sing-box receives → tries to connect to node → goes through TUN again → loop → connection hangs.

**Evidence**:
- `ip rule show` showed no fwmark rules
- `ip route show table 2022` had 14643 routes (all traffic goes through TUN)
- `ip route show` (main table) had only 5 routes (no geoip-cn bypass)
- `sudo nft list ruleset` returned empty — no nftables rules at all
- `ip link show sing-box-tun` showed the interface existed and was UP
- `journalctl` showed no errors (process ran fine)
- Test: `curl -x socks5://127.0.0.1:10880 https://www.google.com` returned 302 (proxy works when bypassing TUN)

### Attempt 3 — strict_route: true + route_exclude_address_set + no fakeip

**Config**: 
```json
{
  "strict_route": true,
  "route_exclude_address_set": ["geoip-cn"],
  "route": { "default_domain_resolver": "dns" }
}
```
No fakeip DNS. No sniff. No dns_mode. DNS unchanged (real AliDNS only).

**Result**: TUN interface created (`sing-box-tun` UP). DNS queries to 223.5.5.5 worked (bypasses TUN via port 53 rule). Baidu returned 200. But sing-box eventually stopped (systemd restart limit), still causing partial network outage.

**Further diagnosis**: `route_exclude_address_set: ["geoip-cn"]` did NOT add iproute2 routes to the main table (still only 5 routes). On Linux with `strict_route: true`, `route_exclude_address_set` uses nftables rules, not iproute2 routing rules. But those nftables rules may conflict with existing system rules (NetworkManager, docker0, etc.).

### Attempt 4 — User's own retry after fixes

The user tried TUN on again after the safety rollback script was updated (ICMP→TCP/HTTP). Still caused a network outage. This confirmed the problem is fundamental: **strict_route's nftables rules conflict with this system's network stack**.

### User feedback

After attempt 4, the user reported: *"又断网了，我停掉了"*. This happened multiple times and the user clearly expressed frustration. The correct response is to stop iterating and accept the system constraint.

**Important lesson**: When a feature causes repeated network outages that disconnect the LLM agent AND require manual intervention to recover, it is not worth continuing to experiment. The user's uptime is more important than any convenience benefit from TUN mode.

## Safety Rollback Implementation

Created `~/.hermes/scripts/sing-box-tun-rollback.sh` as a no-agent cron script.

**V1**: Used ICMP ping. Failed because sing-box routes ICMP through proxy outbound (which doesn't support ICMP) → ping always fails → false positive rollback.

```
WARN inbound/tun[tun-in]: link icmp connection from 198.18.0.1 to 192.168.71.1:
icmp is not supported by default outbound: VMISS-HK
```

**Fix**: Use TCP connect (`/dev/tcp/host/port`) or HTTP curl instead of ICMP ping.

**V2**: Switched to TCP port 80 check on gateway + HTTP curl to baidu.com. Both work through TUN because TCP/HTTP traffic gets properly routed by sing-box.

## DNS Configuration Pitfalls

### Fakeip DNS server (`final` constraint)

```json
{
  "servers": [
    {"tag": "dns", "type": "udp", "server": "223.5.5.5"},
    {"tag": "dns-fakeip", "type": "fakeip", "inet4_range": "198.19.0.0/16"}
  ],
  "final": "dns-fakeip"  // ← FATAL: default server cannot be fakeip
}
```

`final` DNS server must NOT be a fakeip type. The correct approach for TUN with fakeip:
```json
"final": "dns",
"rules": [
  {"rule_set": "geosite-cn", "server": "dns"},
  {"query_type": ["A", "AAAA"], "server": "dns-fakeip"}
]
```

### address vs server format

The documented "new format" for sing-box DNS servers uses `"type": "udp"` + `"server": "223.5.5.5"`, NOT `"address": "223.5.5.5"`. The `"address"` format is actually the **deprecated** format according to the migration guide table (Tab 8 — UDP server). The cleanest format is always `"type" + "server"`.

### Latest DNS format decision

After extensive testing, the safest TUN-mode DNS configuration on Linux Desktop is: **no fakeip, real DNS only**. The DNS server (223.5.5.5) is a Chinese IP, so with `route_exclude_address_set: ["geoip-cn"]` it bypasses TUN entirely.

## TUN Address Field Migration

The TUN inbound address field has been through two migrations:

| Version | Format | Status |
|---------|--------|--------|
| < 1.10 | `"address": "172.19.0.1"` (string, no prefix) | Removed |
| 1.10–1.11 | `"inet4_address": "172.19.0.1/30"` | Deprecated in 1.10, removed in 1.12 |
| 1.12+ | `"address": ["172.19.0.1/30"]` (**array**) | Current |

The error message: `legacy tun address fields are deprecated in sing-box 1.10.0 and removed in sing-box 1.12.0`

## `sniff` inbound field removal

`sniff` at the inbound level was removed in sing-box 1.13.0:
```
legacy inbound fields are deprecated in sing-box 1.11.0 and removed in sing-box 1.13.0
```
In 1.11 it was moved to rule actions. In 1.13 it was entirely removed from inbounds. Simply remove the field entirely.

## `dns_mode` addition

`dns_mode` was added to the TUN inbound in sing-box 1.14.0. Not available in 1.13.x. The docs mention it with "Since sing-box 1.14.0" but this is easy to miss.

## Route default_domain_resolver

sing-box 1.12.0+ requires `route.default_domain_resolver` when TUN mode uses domain-based outbound routing. Without it:
```
missing `route.default_domain_resolver` or `domain_resolver` in dial fields is deprecated
in sing-box 1.12.0 and will be removed in sing-box 1.14.0
```
The env var `ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER=true` can bypass this error but is not recommended.

## Key Lessons

1. **Always validate first**: `sing-box check -c <temp_config>` before applying any config change.
2. **Backup first**: Copy the working config before any TUN toggle.
3. **Safety cron before action**: Schedule the rollback BEFORE running `tun on`, not after.
4. **No ICMP**: TCP/HTTP for connectivity checks, never ping.
5. **No fakeip**: Real DNS only for TUN on Linux Desktop. The complexity is not worth it.
6. **TUN+strict_route+nftables on Linux Mint is fragile**: The interference with NetworkManager and existing nftables rules is a fundamental system-level compatibility issue. If SOCKS5 mode works, stay with it.
7. **Know when to stop**: After 4 failed attempts, TUN mode was permanently abandoned. Not every feature is worth fighting for.
