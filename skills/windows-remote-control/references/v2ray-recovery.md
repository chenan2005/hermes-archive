# V2Ray 233boy Script Recovery

## Service architecture

```
Caddy :30717 (TLS) → reverse_proxy /<uuid-path> → 127.0.0.1:22650 (V2Ray VMess)
```

Config locations:
- Caddy: `/etc/caddy/233boy/kvm.bernarty.xyz.conf`
- V2Ray main: `/etc/v2ray/config.json` (skeleton: routing, api, outbounds)
- V2Ray inbound: `/etc/v2ray/conf/VMess-WS-TLS-<host>.json` (the actual VMess inbound)
- Service: `systemctl status v2ray`, started with `-confdir /etc/v2ray/conf`

## SCP/SFTP subsystem fix

When scp fails with "Connection closed" and sftp also fails, check:
```cmd
type C:\ProgramData\ssh\sshd_config | findstr sftp
```
If it says `Subsystem sftp sftp-server.exe` without full path, fix to:
```
Subsystem	sftp	C:\Program Files\OpenSSH\OpenSSH-Win64\sftp-server.exe
```

## Common failure: port not listening after config change

The service loads configs from `/etc/v2ray/conf/` at startup. If you modify
a conf file, you must restart the service for V2Ray to pick it up:
```bash
systemctl restart v2ray
```
Verify: `ss -tlnp | grep 22650` (replace with actual inbound port)

## Recovery via interactive menu (233boy script)

The v2ray management script is interactive. Navigate it non-interactively with:
```bash
# Restart: 5 (run management) → 3 (restart)
printf "5\n3\n" | v2ray

# Stop + Start: 5 → 2 → 1
printf "5\n2\n1\n" | v2ray
```

## Key auth initially disabled

If `PubkeyAuthentication no` in `/etc/ssh/sshd_config`, fix:
```bash
sed -i 's/^PubkeyAuthentication no/PubkeyAuthentication yes/' /etc/ssh/sshd_config
systemctl restart sshd
```

## DNS mismatch after IP change

If public DNS for `kvm.bernarty.xyz` points to wrong IP (e.g. 154.40.40.204
instead of 154.40.40.38), connect directly via IP and update domain DNS records
at the provider. Meanwhile, add a static entry to OpenWrt for internal resolution.

**DNS caching pitfall**: OpenWrt's dnsmasq may forward queries to a local transparent
proxy DNS (e.g. `127.0.0.1:6353` for PassWall/SSR-Plus) which has its own cache.
After updating upstream DNS, stale records can persist even after `dnsmasq restart`.
Flush with: `resolvectl flush-caches` on the local machine, and restart the proxy
service on OpenWrt (`/etc/init.d/passwall restart` or equivalent). The stale cache
will eventually expire when the upstream DNS TTL elapses.
