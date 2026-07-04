# Testing OpenWrt Proxy Through WAN Gateway

Session transcript: routing a Windows client (minipc, 192.168.71.21) through a new OpenWrt 24.10 test VM (openwrt-t, 192.168.71.9) to verify OpenClash proxy functionality.

## Network Topology

```
光猫 (71.1)
  │
  ├── minipc (71.21)            ← test client
  │     └── vEthernet (wan): gateway changed 71.11→71.9
  │
  ├── OpenWrt 22.03 prod (71.11 WAN → 37.1 LAN)  [old, PassWall]
  │
  └── OpenWrt 24.10 test (71.9 WAN → 37.2 LAN)   [new, OpenClash]
        ├── WAN (eth1): 71.9/24, gateway 71.11
        ├── LAN (br-lan): 37.2/24, gateway 37.1
        └── OpenClash: redirect port 7892, API port 9090
```

## Firewall Diagnosis (nftables)

OpenWrt 24.10 uses **nftables** (fw4), not iptables. Commands that worked on 22.03 (iptables) will show empty output.

### Default Forward Policy

```bash
nft list chain inet fw4 forward
```

Output shows `policy drop` with `ct state { established, related } accept`. NEW traffic from WAN side goes through `forward_wan` → `accept_to_wan` (if WAN→WAN forwarding is enabled).

### Default WAN Input Policy

```bash
nft list chain inet fw4 input_wan
```

Only allows: DHCP, Ping, IGMP, ICMPv6, MLD. Everything else → `reject_from_wan`.

### OpenClash Redirect Mechanism

```bash
nft list chain inet fw4 openclash
```

```
chain openclash {
    ip daddr @localnetwork counter packets return
    ct direction reply counter packets return
    ip protocol tcp ip daddr 198.18.0.0/16 counter redirect to :7892
    ip protocol tcp counter redirect to :7892
}
```

All TCP traffic is REDIRECT-NAT'd to port 7892. After REDIRECT, packet dest becomes `127.0.0.1:7892` → enters INPUT chain (not FORWARD).

### The Bug

TCP traffic from a WAN-side client is:
1. Received on WAN interface (eth1)
2. REDIRECT'd to localhost:7892 by OpenClash dstnat
3. Enters INPUT chain → `input_wan` → `reject_from_wan` (no matching ACCEPT rule)
4. **DROPPED** — connection timeout

ICMP (ping) works because it's NOT redirected by OpenClash, goes through FORWARD → `accept_to_wan`.

### The Fix

Add a firewall rule to ACCEPT TCP/7892 from the WAN zone:

```bash
uci add firewall rule
uci set firewall.@rule[-1].name="Allow-LAN-WAN-to-OpenClash"
uci set firewall.@rule[-1].src="wan"
uci set firewall.@rule[-1].dest_port="7892"
uci set firewall.@rule[-1].proto="tcp"
uci set firewall.@rule[-1].target="ACCEPT"
uci commit firewall
/etc/init.d/firewall restart
```

Result in `input_wan`:
```
tcp dport 7892 counter packets N bytes N accept comment "Allow-LAN-WAN-to-OpenClash"
```

## WAN→WAN Forwarding

WAN→WAN forwarding (traffic from eth1 that exits via eth1) is needed when a WAN-side client routes through the new VM's WAN IP. This is already handled by the forwarding rule added during setup:

```bash
uci add firewall rule
uci set firewall.@rule[-1].src="wan"
uci set firewall.@rule[-1].dest="wan"
uci set firewall.@rule[-1].target="ACCEPT"
uci commit firewall
```

This creates in `forward_wan`:
```
counter packets N bytes N jump accept_to_wan comment "Allow-WAN-to-WAN-forward"
```

And `accept_to_wan` accepts traffic with `oifname "eth1"`:
```
oifname "eth1" counter packets N bytes N accept
```

## Windows Route Management

### Check Current Routes

```powershell
Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Format-Table DestinationPrefix,NextHop,InterfaceAlias,RouteMetric,ifIndex
```

### Change Default Gateway

```powershell
# Remove existing route
Remove-NetRoute -DestinationPrefix '0.0.0.0/0' -NextHop <old-ip> -InterfaceIndex <idx> -Confirm:$false
# Add new route
New-NetRoute -DestinationPrefix '0.0.0.0/0' -NextHop <new-ip> -InterfaceIndex <idx> -RouteMetric 0
```

### Revert

```powershell
Remove-NetRoute -DestinationPrefix '0.0.0.0/0' -NextHop <new-ip> -InterfaceIndex <idx> -Confirm:$false
New-NetRoute -DestinationPrefix '0.0.0.0/0' -NextHop <old-ip> -InterfaceIndex <idx> -RouteMetric 0
```

## Verification

| Test | Expected | Result |
|------|----------|--------|
| `ping 8.8.8.8` | replies | ICMP forwarded directly |
| `curl https://www.google.com` | 302 | OpenClash proxy |
| `curl https://www.youtube.com` | 200 | OpenClash proxy |
| `curl https://www.baidu.com` | 200 | direct (no proxy) |

## Key Findings

- OpenClash REDIRECT handling requires an explicit ACCEPT rule in `input_wan` when traffic arrives from the WAN interface
- OpenWrt 24.10 uses nftables (fw4) — do not attempt `iptables -L` on 24.10; it returns empty or errors
- ICMP traffic is not affected by OpenClash redirect; ICMP working while TCP fails is the diagnostic signal
- Counter values in nftables rules show whether packets are hitting each chain — use `counter packets N bytes N` as real-time debugging
