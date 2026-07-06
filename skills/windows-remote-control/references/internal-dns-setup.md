# Internal DNS via OpenWrt dnsmasq

The internal network uses `.lan.11` domain suffix, served by the OpenWrt router's dnsmasq.
DHCP static leases bind MAC→IP, and `expandhosts` auto-registers hostnames as DNS.
Cross-subnet devices (e.g. 9950x3d on 192.168.71.x) use static `/etc/hosts` entries.

## DNS Records

```
9950x3d.lan.11  →  192.168.71.41    (static hosts — different subnet, OpenWrt not DHCP server)
minipc.lan.11   →  192.168.37.224   (DHCP auto)
lenovo.lan.11   →  192.168.37.234   (DHCP auto)
realme.lan.11   →  192.168.37.205   (DHCP static lease)
magicpad.lan.11 →  192.168.37.177   (static hosts)
openwrt.lan.11  →  192.168.37.1     (self)
```

## Adding a New Device

```bash
# On OpenWrt (ssh openwrt):
uci add dhcp host
uci set dhcp.@host[-1].name="hostname"
uci set dhcp.@host[-1].mac="AA:BB:CC:DD:EE:FF"
uci set dhcp.@host[-1].ip="192.168.37.X"
uci commit dhcp
/etc/init.d/dnsmasq restart
```

For devices on a different subnet (not managed by OpenWrt DHCP):
```bash
echo "192.168.71.X hostname hostname.lan.11" >> /etc/hosts
/etc/init.d/dnsmasq restart
```

## Android DNS Workaround (Go programs)

Go programs (like frpc) read `/etc/resolv.conf` for DNS, which doesn't exist on Android.
Fix with proot (no root needed):

```bash
mkdir -p ~/my-etc
echo "nameserver 8.8.8.8" > ~/my-etc/resolv.conf
echo "nameserver 8.8.4.4" >> ~/my-etc/resolv.conf
proot -b ~/my-etc:/etc frpc -c ~/frp/frpc.ini
```

For auto-start, add to `~/.bashrc`:
```bash
if ! pgrep -f "proot.*frpc" > /dev/null 2>&1; then
    nohup proot -b ~/my-etc:/etc ~/frp/frpc -c ~/frp/frpc.ini > ~/frp/frpc.log 2>&1 &
fi
```

## DNS Cache Pitfall: smartdns address.conf

OpenWrt's transparent proxy (PassWall) uses smartdns with a persistent
address override at `/etc/smartdns/address.conf`. This file hardcodes
domain→IP mappings that **override ALL upstream DNS**, including the
authoritative DNS server.

```bash
address /kvm.bernarty.xyz/154.40.40.204
```

**Resolution chain** (4 layers, any one can wreck resolution):

```
Public DNS (correct)
  → smartdns (127.0.0.1:6353) → address.conf OVERRIDES
    → dnsmasq (127.0.0.1:53) → caches from smartdns
      → systemd-resolved → caches from dnsmasq
```

**When changing a server's public IP**, update ALL of these:

1. Public DNS provider (Tencent Cloud / DNSPod / etc.)
2. `vi /etc/smartdns/address.conf` → change or remove the address line
3. `rm -f /tmp/smartdns.cache && /etc/init.d/smartdns restart`
4. `/etc/init.d/dnsmasq restart`
5. `resolvectl flush-caches`

**Diagnosing**: `nslookup domain 127.0.0.1:6353` queries smartdns directly.
If smartdns returns the wrong IP despite upstream DNS being correct,
`grep domain /etc/smartdns/address.conf` to check for a hardcode.
