# Deployment Session: OpenWrt 22.03.5 → 24.10.0 on Hyper-V

## Context

- **Old VM**: `open-22.03.5` — OpenWrt 22.03.5 (kernel 5.10), PassWall 4.67, SmartDNS
- **New VM**: `openwrt-24.10-test` — OpenWrt 24.10.0 (kernel 6.6.73), OpenClash v0.47.096 + Mihomo v1.19.3
- **Hyper-V host**: minipc — Windows 11 Pro, Ryzen 9 7940HS, 64GB RAM
- **Network**: Two virtual switches (`lan` + `wan`), old VM at LAN 192.168.37.1 / WAN 192.168.71.11

## Key Decisions

### Generation 1 vs 2
Gen1 was chosen for simplicity. Gen2 needed `kmod-hv-net` on older kernels but kernel 6.6 includes `hv_netvsc` as a module — Gen2 with `-EnableSecureBoot Off` would work, but Gen1 is zero-config.

### Proxy Software: PassWall → OpenClash
PassWall's GitHub repo (xiaorouji) was deleted (404). Community builds exist but finding a working 24.10 feed was difficult. OpenClash from vernesong/OpenWrt was easier: direct IPK download from GitHub releases.

### OpenClash Core
OpenClash IPK doesn't include the clash binary. Mihomo v1.19.3 was downloaded separately and placed at `/etc/openclash/core/clash_meta`.

### Gateway Routing for Testing
New VM's WAN gateway was set to old VM's WAN IP (192.168.71.11) instead of upstream (192.168.71.1), so the new VM routes through the old VM's PassWall during testing.

## Problems Encountered

1. **downloads.immortalwrt.org slow** — Timed out repeatedly. Switched to Tsinghua mirrors for firmware images.
2. **Tsinghua missing ImmortalWrt package feeds** — Only has firmware images, not packages/ subdirectory.
3. **scp fails on OpenWrt** — Dropbear lacks sftp-server. Used `cat file | ssh host "cat > dst"` pattern.
4. **OpenClash 404 in Luci** — Needed `opkg install luci-compat` for Lua controller registration on JS-based Luci.
5. **dnsmasq-full conflict** — OpenClash depends on dnsmasq-full which conflicts with dnsmasq. Required `--force-removal-of-dependent-packages`.
6. **Luci cache** — Had to `rm -rf /tmp/luci-* /tmp/luci-modulecache/*` before OpenClash menu appeared.
7. **PowerShell && syntax** — Older Windows PowerShell doesn't support `&&`. Use `;` instead.

## Network Config (New VM)

```
LAN:  br-lan (eth0) @ 192.168.37.2/24, gateway 192.168.37.1
WAN:  eth1 @ 192.168.71.9/24, gateway 192.168.71.11
DNS:  192.168.37.1
```

## Firewall Config (Added)

UCI entries created by default OpenWrt image:
- `forwarding[0]`: src=lan, dest=wan (originally created on first boot)
- `forwarding[1]`: src=wan, dest=lan (manually added for inter-subnet access)

## Clash Nodes Migrated from PassWall

| Node | Protocol | Server | Port | WS Path |
|------|----------|--------|------|---------|
| 233boy-KVM | VMess+WS+TLS | kvm.bernarty.xyz | 30717 | /f2586607-5bbd-4947-a1cb-db23f48aaf0c |
| Seoul-Cloudflare | VMess+WS+TLS | stays-island-captured-introduce.trycloudflare.com | 443 | /ws-seoul |
| VMISS-HK | VMess+WS+TLS | vmiss.bernarty.xyz | 443 | /ws-vmiss |
