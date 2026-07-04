# Proxy Software for OpenWrt 24.10 (x86_64)

## Availability in Official OpenWrt Feeds

None of the major proxy LuCI apps (PassWall, OpenClash, HomeProxy, SSR-Plus, etc.) are available in the official OpenWrt 24.10 package feeds. They must be installed from:
- **ImmortalWrt package feeds** (`downloads.immortalwrt.org` — PassWall, HomeProxy available for 24.10.6)
- **Community GitHub releases** (OpenClash from vernesong/OpenClash)
- **Custom feeds** (kenzo, supes — often outdated or broken)

## Comparison

| Software | Source for 24.10 | Backend | DNS Protection | Config UI | Weight |
|----------|-----------------|---------|---------------|-----------|--------|
| **PassWall** | ImmortalWrt feed | Xray/V2Ray + sing-box + shadowsocks-rust + hysteria | chinadns-ng + dns2socks | Mature LuCI | Heavy (~20MB deps) |
| **HomeProxy** | ImmortalWrt feed | sing-box only | Built-in (sing-box) | Clean LuCI | Light |
| **OpenClash** | GitHub releases | Mihomo (Clash Meta) | **Fake-IP (best)** | Polished LuCI | Heaviest (Go + many deps) |
| **SSR-Plus** | Community | ShadowsocksR | Basic | Basic LuCI | Light |

## OpenClash Installation Dependency Chain

1. `kmod-tun` + `kmod-nf-conntrack-netlink` — kernel modules (from kmods feed, version-pinned to kernel)
2. `dnsmasq` → replace with `dnsmasq-full` (conflicts, needs forced removal)
3. `luci-compat` — required for Lua Luci apps on OpenWrt 24.10's JS based Luci
4. `luci-app-openclash` — the main IPK
5. Mihomo core binary — download separately (GitHub releases)

## Tsinghua Mirror Limitations

- `mirrors.tuna.tsinghua.edu.cn/openwrt/` — has OpenWrt 24.10 official packages ✅
- `mirrors.tuna.tsinghua.edu.cn/openwrt/` kmods — has kernel modules ✅
- `mirrors.tuna.tsinghua.edu.cn/immortalwrt/releases/<ver>/targets/x86/64/` — has ImmortalWrt firmware images ✅
- `mirrors.tuna.tsinghua.edu.cn/immortalwrt/releases/<ver>/packages/` — does NOT exist (404) ❌
- `downloads.immortalwrt.org` — has packages but slow from China
- `downloads.openwrt.org` — has packages but slow from China
