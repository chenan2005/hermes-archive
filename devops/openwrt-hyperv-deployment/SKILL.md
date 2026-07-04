---
name: openwrt-hyperv-deployment
description: Deploy OpenWrt on Hyper-V as a soft router VM — disk prep, VM creation, network topology, parallel testing, and cutover. Covers Gen1/Gen2 decisions, pre-configuring network/DHCP on disk images, and coexisting alongside an existing router VM.
---

# OpenWrt Hyper-V Deployment

Deploy a new OpenWrt (or ImmortalWrt) VM on Hyper-V alongside an existing production router VM, with no downtime during setup.

## When to Use

- User has a soft router on Hyper-V (Windows mini PC) and wants to upgrade/replace it
- User wants to test a new OpenWrt version without disrupting the current network
- Deploying a new OpenWrt VM from scratch on Windows Hyper-V

## Prerequisites

- SSH access to the Hyper-V host (Windows with PowerShell)
- SSH access to the current OpenWrt VM (for config backup)
- `qemu-utils` on your local Linux machine (for VHDX conversion)
- Internet access for downloading OpenWrt images (use Chinese mirrors like mirrors.tuna.tsinghua.edu.cn for speed)

## Step-by-Step

### 1. Map the Current Network

On the Hyper-V host, discover the virtual switches:

```powershell
Get-VM | Format-Table Name, State, CPUUsage, MemoryAssigned
Get-VMSwitch | Format-Table Name, SwitchType, NetAdapterName
Get-VMNetworkAdapter -VMName <current-vm> | Format-Table Name, SwitchName, MacAddress
```

On the OpenWrt VM, discover the IP topology:

```bash
ip addr show
ip route show default
uci show network.lan.ipaddr
uci show network.wan
```

Typical topology (two NICs):
- **WAN** interface → Internet-facing virtual switch → gets IP from upstream
- **LAN** interface → LAN virtual switch → bridges to br-lan at the gateway IP

### 2. Download and Prepare the Image

Download from a fast mirror (Tsinghua):

```bash
curl -sL "https://mirrors.tuna.tsinghua.edu.cn/openwrt/releases/<version>/targets/x86/64/openwrt-<version>-x86-64-generic-ext4-combined-efi.img.gz" -o openwrt.img.gz
```

Convert raw image to VHDX for Hyper-V:

```bash
sudo apt install -y qemu-utils
gunzip openwrt.img.gz
qemu-img convert -f raw -O vhdx openwrt.img openwrt-<version>.vhdx
```

> **Note:** ImmortalWrt provides pre-built VHDX files directly on their download server; OpenWrt official does not — conversion is needed.

### 3. Pre-Configure the Disk (Recommended)

Pre-write network config before first boot so the VM is immediately reachable.

Mount the raw image (before VHDX conversion):

```bash
sudo modprobe nbd max_part=8
sudo qemu-nbd -c /dev/nbd0 -f raw openwrt.img
sudo mkdir -p /mnt/openwrt
sudo mount /dev/nbd0p2 /mnt/openwrt
```

Write `/etc/config/network` — set a static IP on the same subnet as existing:

```bash
sudo bash -c 'cat > /mnt/openwrt/etc/config/network << EOF
config interface '\''loopback'\''
        option device '\''lo'\''
        option proto '\''static'\''
        option ipaddr '\''127.0.0.1'\''
        option netmask '\''255.0.0.0'\''

config globals '\''globals'\''
        option ula_prefix '\''fd00:abba:1234::/48'\''

config device
        option name '\''br-lan'\''
        option type '\''bridge'\''
        list ports '\''eth0'\''

config interface '\''lan'\''
        option device '\''br-lan'\''
        option proto '\''static'\''
        option ipaddr '\''<new-ip>'\''
        option netmask '\''255.255.255.0'\''
        option gateway '\''<existing-gateway>'\''
        list dns '\''<existing-gateway>'\''
EOF'
```

Disable the LAN DHCP server to avoid conflicts:

```bash
sudo sed -i '/^config dhcp '\''lan'\''/,/^config/{/^option leasetime/a \\toption ignore '\''1'\''' /mnt/openwrt/etc/config/dhcp
```

Clean up:

```bash
sudo umount /mnt/openwrt
sudo qemu-nbd -d /dev/nbd0
```

Then convert the modified raw image to VHDX with `qemu-img convert`.

### 4. Create the Hyper-V VM

Copy the VHDX to the Hyper-V host:

```bash
scp openwrt-<version>.vhdx user@hyperv-host:C:/hyper-v-vm/
```

On the Hyper-V host, create a Gen1 VM:

```powershell
New-VM -Name "<vm-name>" `
  -MemoryStartupBytes 1GB `
  -BootDevice VHD `
  -VHDPath "C:\hyper-v-vm\openwrt-<version>.vhdx" `
  -Path "C:\hyper-v-vm" `
  -Generation 1 `
  -SwitchName "<lan-switch>"

Set-VM -Name <vm-name> -ProcessorCount 2 -AutomaticStartAction Nothing
```

> **Gen1 vs Gen2 trade-off:**
> - **Gen1** (recommended for simplicity): Works out of the box. NIC emulates Intel PRO/1000 (e1000 driver built into kernel 6.6). No extra packages needed. Disadvantage: no hot-add NICs (must stop VM to add a second NIC).
> - **Gen2**: Better performance, hot-add NICs supported. With OpenWrt 24.10 (kernel 6.6), the `hv_netvsc` Hyper-V synthetic NIC driver is built as a kernel module — boot with `Set-VMFirmware -EnableSecureBoot Off` and it works. No extra opkg needed for kernel 6.6+. Start with Gen1 unless you specifically need hot-add NICs or Gen2-only features.

Start the VM:

```powershell
Start-VM -Name <vm-name>
```

Wait ~20s for boot, then ping and access Luci at `http://<new-ip>/`.

### 5. Post-Boot Setup

SSH into the new VM:

```bash
ssh root@<new-ip>
```

Set root password:

```bash
passwd   # temporary password like openwrt123
```

### 5e. Firewall Forwarding for Inter-Subnet Access

By default, OpenWrt allows LAN→WAN forwarding but not WAN→LAN. If the user wants devices on the WAN subnet (e.g., 192.168.71.x) to reach devices on the LAN subnet (192.168.37.x), add a second forwarding rule:

```bash
uci add firewall forwarding
uci set firewall.@forwarding[-1].src='wan'
uci set firewall.@forwarding[-1].dest='lan'
uci commit firewall
/etc/init.d/firewall reload
```

This creates bidirectional forwarding between the two interfaces. The WAN zone's masquerade (NAT) is typically already enabled (`masq='1'`), which handles address translation for traffic leaving the WAN interface.

Verify connectivity:
```bash
# From the new VM's WAN IP, ping a LAN device
ping -c 2 -I 192.168.71.9 192.168.37.234
```

### 5f. Configure Passwordless SSH Access

After setting the root password via the initial SSH session, set up key-based auth so the agent (and you) can `ssh` without a password prompt:

```bash
# On your Hermes machine:
ssh-copy-id -i ~/.ssh/id_ed25519.pub root@<new-ip>
ssh-keygen -f ~/.ssh/known_hosts -R "<new-ip>"
ssh -o StrictHostKeyChecking=accept-new root@<new-ip> "hostname"   # verify
```

Add an SSH config alias for convenience:

```bash
tee -a ~/.ssh/config << 'EOF'

Host <alias>          # e.g. openwrt-t
    HostName <new-ip>
    User root
    StrictHostKeyChecking accept-new
    ConnectTimeout 5
EOF
```

> **Note:** OpenWrt uses dropbear, not OpenSSH. `ssh-copy-id` works but the authorized_keys file is at `~/.ssh/authorized_keys`. If key auth fails, restart dropbear: `/etc/init.d/dropbear restart`.

### 5a. File Transfer Without sftp-server

OpenWrt's dropbear does **not** include sftp-server, so `scp` fails with `sftp-server: not found`. Use a pipe through SSH instead:

```bash
# Transfer a file
cat /path/to/local/file | ssh root@<new-ip> "cat > /path/to/remote/file"

# Transfer a directory as tarball
tar czf - /local/dir | ssh root@<new-ip> "tar xzf - -C /"
```

### 5b. Add WAN NIC and Configure

Stop the VM, add a second NIC on the `wan` virtual switch, then restart:

```powershell
# On Hyper-V host
Stop-VM -Name <vm-name> -TurnOff
Add-VMNetworkAdapter -VMName <vm-name> -SwitchName "wan"
Start-VM -Name <vm-name>
```

After reboot, SSH back in and configure the WAN interface:

```bash
uci set network.wan=interface
uci set network.wan.device='eth1'
uci set network.wan.proto='static'
uci set network.wan.ipaddr='<wan-ip>'   # e.g. 192.168.71.9/24
uci set network.wan.netmask='255.255.255.0'
uci commit network
/etc/init.d/network reload
```

> **Gateway routing trick:** If the old router has a proxy (PassWall/Clash), set the new VM's WAN gateway to the **old router's WAN IP** instead of the upstream gateway. This lets the new VM route through the old router's proxy before it has its own proxy installed. Example: new VM WAN gateway = `192.168.71.11` (old router's WAN), not `192.168.71.1`.

Verify connectivity:
```bash
ping -c 2 8.8.8.8
```

### 5c. Install Proxy Software

PassWall is **NOT** in the official OpenWrt feed. Available options:

| Software | Source | DNS anti-pollution | Weight |
|----------|--------|-------------------|--------|
| **PassWall** | ImmortalWrt package feed (`downloads.immortalwrt.org`) | chinadns-ng + dns2socks | Heavy (many deps: xray-core, sing-box, shadowsocks-rust, etc.) |
| **HomeProxy** | ImmortalWrt package feed | sing-box built-in | Light |
| **OpenClash** | Community IPK builds | Fake-IP mode (best) | Heaviest (Go runtime) |
| **SSR-Plus** | Community IPK builds | Basic | Light |

**Install PassWall from ImmortalWrt feed:**

```bash
# Add ImmortalWrt 24.10 feeds
echo 'src/gz imm_luci https://downloads.immortalwrt.org/releases/24.10.6/packages/x86_64/luci' >> /etc/opkg/customfeeds.conf
echo 'src/gz imm_base https://downloads.immortalwrt.org/releases/24.10.6/packages/x86_64/base' >> /etc/opkg/customfeeds.conf
echo 'src/gz imm_packages https://downloads.immortalwrt.org/releases/24.10.6/packages/x86_64/packages' >> /etc/opkg/customfeeds.conf

rm -f /var/lock/opkg.lock
opkg update
opkg install luci-app-passwall
```

If the ImmortalWrt download server is slow (common from China), download the IPK files from a fast mirror on your local machine and SCP them over:

```bash
# On your local machine, download passwall IPK (from GitHub releases of community builds)
# Then SCP to the new VM
scp luci-app-passwall*.ipk root@<new-ip>:/tmp/
ssh root@<new-ip> "opkg install /tmp/luci-app-passwall*.ipk"
```

### 5d. Install OpenClash (Alternative to PassWall)

OpenClash is a community-maintained proxy client with **Fake-IP DNS** (best-in-class DNS anti-pollution). It uses Mihomo (formerly Clash Meta) as the core engine.

#### Download and Install

```bash
# 1. Download the OpenClash IPK on a fast machine
curl -sL "https://github.com/vernesong/OpenClash/releases/download/v0.47.096/luci-app-openclash_0.47.096_all.ipk" -o luci-app-openclash.ipk
# (check the releases page for the latest version)

# 2. Transfer to OpenWrt
cat luci-app-openclash.ipk | ssh root@<new-ip> "cat > /tmp/luci-app-openclash.ipk"

# 3. Install dependencies on OpenWrt (kmod packages from the kmods feed)
ssh root@<new-ip> "
opkg update
# Kernel modules — needed by OpenClash
wget -q --timeout=15 -O /tmp/kmod-tun.ipk 'https://mirrors.tuna.tsinghua.edu.cn/openwrt/releases/24.10.0/targets/x86/64/kmods/6.6.73-1-a21259e4f338051d27a6443a3a7f7f1f/kmod-tun_6.6.73-r1_x86_64.ipk'
wget -q --timeout=15 -O /tmp/kmod-nf-conntrack-netlink.ipk 'https://mirrors.tuna.tsinghua.edu.cn/openwrt/releases/24.10.0/targets/x86/64/kmods/6.6.73-1-a21259e4f338051d27a6443a3a7f7f1f/kmod-nf-conntrack-netlink_6.6.73-r1_x86_64.ipk'
opkg install /tmp/kmod-tun.ipk /tmp/kmod-nf-conntrack-netlink.ipk

# Dnsmasq-full replacement (conflicts with dnsmasq)
opkg remove dnsmasq --force-removal-of-dependent-packages
opkg install dnsmasq-full

# Luci compat layer (needed for Lua Luci apps on OpenWrt 24.10's JS Luci)
opkg install luci-compat

# 4. Install OpenClash
opkg install /tmp/luci-app-openclash.ipk
"
```

#### Install the Clash Core (Mihomo)

```bash
# Download Mihomo core
cd /tmp
curl -sL "https://github.com/MetaCubeX/mihomo/releases/download/v1.19.3/mihomo-linux-amd64-v1.19.3.gz" -o mihomo.gz
gunzip mihomo.gz
chmod +x mihomo

# Transfer to OpenWrt and install
cat mihomo | ssh root@<new-ip> "cat > /etc/openclash/core/clash_meta && chmod 755 /etc/openclash/core/clash_meta"
```

#### Post-Install

```bash
# Clear Luci cache so the OpenClash menu appears
ssh root@<new-ip> "rm -rf /tmp/luci-* /tmp/luci-modulecache/*; /etc/init.d/uhttpd restart"

# Enable and start OpenClash
ssh root@<new-ip> "
uci set openclash.config.enable=1
uci commit openclash
/etc/init.d/openclash enable
/etc/init.d/openclash start
"
```

Access the Luci interface at `http://<new-ip>/cgi-bin/luci/admin/services/openclash`.

> **OpenClash config file location:** Add a config file through the Luci interface (click "Add Config File" → upload YAML or paste subscription URL), or place a `config.yaml` file at `/etc/openclash/config/config.yaml` manually. OpenClash looks for configs in `/etc/openclash/config/` — this is the `config` subdirectory, not the parent directory. After adding a config, restart OpenClash: `/etc/init.d/openclash restart`. The dashboard shows port information (e.g., Mix Proxy at `192.168.37.2:7893`, Control Panel at `192.168.37.2:9090`).

For DNS anti-pollution alongside PassWall, install chinadns-ng:

```bash
/etc/init.d/dnsmasq disable
/etc/init.d/dnsmasq stop
```

### 6. Migrate PassWall Proxies to OpenClash

When moving from PassWall to OpenClash, the proxy config is stored in UCI format under `/etc/config/passwall`. Convert each `config nodes` section to Clash YAML.

#### Extract Node Config

```bash
ssh root@<old-openwrt>
uci show passwall | grep -E '^passwall\.(.*\.)?(nodes|type|protocol|address|port|uuid|security|transport|tls|ws_path|ws_host|tls_serverName)' | grep -v 'shunt\|_shunt\|_direct\|_default\|_blackhole'
```

This prints all node fields needed for Clash proxy entries. Key mapping:

| PassWall UCI field | Clash YAML field |
|-------------------|------------------|
| `.address` | `server` |
| `.port` | `port` |
| `.uuid` | `uuid` |
| `.tls='1'` | `tls: true` |
| `.tls_serverName` | `servername` |
| `.transport='ws'` | `network: ws` |
| `.ws_path` | `ws-opts.path` |
| `.ws_host` | `ws-opts.headers.Host` |

#### Generate Clash Config

For each VMess node, create a proxy entry:

```yaml
proxies:
  - name: "Node-Name"
    type: vmess
    server: <address>
    port: <port>
    uuid: <uuid>
    alterId: 0
    cipher: auto
    tls: true
    servername: <tls_serverName>
    network: ws
    ws-opts:
      path: <ws_path>
      headers:
        Host: <ws_host>
```

For xray-core nodes with `protocol='_shunt'` (PassWall shunt nodes), these are routing rules, not proxy nodes. They don't convert to Clash proxies — replicate the rules in OpenClash's `rules:` section instead.

#### Complete Clash Config Template

See `templates/clash-migration-config.yaml` for a full annotated config with:
- 3 proxy entries (typical: KVM main + Cloudflare tunnel + HK backup)
- Proxy groups (auto-select + manual select + bypass + adblock)
- DNS in Fake-IP mode (best DNS anti-pollution)
- Rules matching common PassWall shunt setups (OpenAI, Netflix, Games, Google auth, proxy/geolocation-!cn, cn/direct, ads)

After placing the config at `/etc/openclash/config/config.yaml`, restart:

```bash
/etc/init.d/openclash restart
tail -f /tmp/openclash_start.log  # watch for errors
```

Verify the proxy with a curl test through OpenClash's HTTP proxy port:

```bash
curl -s --connect-timeout 5 -x http://127.0.0.1:7890 https://www.youtube.com -o /dev/null \
  -w 'HTTP %{http_code} %{time_total}s\n'
```

### 7. Migration Path (Cutover)

When the new VM is configured and tested:

1. **Backup old configs** from the old VM:
   ```bash
   ssh root@<old-ip> "tar cf - /etc/config/passwall /etc/config/smartdns /etc/config/dhcp" > backup.tar
   ```

2. **Make the new VM WAN-independent** before shutting down the old VM:
   ```bash
   # Change WAN gateway from old router to upstream gateway
   uci set network.wan.gateway='<upstream-gateway>'
   uci commit network
   /etc/init.d/network reload
   ip route show default  # verify gateway changed
   ```
   Without this, the new VM loses internet access when the old VM goes down.

3. **Enable WAN SSH access** on the new VM (if not already) so it can be managed directly:
   ```bash
   uci add firewall rule
   uci set firewall.@rule[-1].name="Allow-WAN-SSH"
   uci set firewall.@rule[-1].src="wan"
   uci set firewall.@rule[-1].proto="tcp"
   uci set firewall.@rule[-1].dest_port="22"
   uci set firewall.@rule[-1].target="ACCEPT"
   uci set firewall.@rule[-1].family="ipv4"
   # Restrict source to LAN subnet:
   uci set firewall.@rule[-1].src_ip="<wan-subnet>/24"
   uci commit firewall
   /etc/init.d/firewall reload
   ```

4. **Stop the old VM's DHCP** to prevent IP conflicts:
   ```bash
   uci set dhcp.lan.ignore="1"
   uci commit dhcp
   /etc/init.d/dnsmasq restart
   ```

5. **Stop the old VM** or disconnect its WAN NIC

6. **Assign the old LAN IP** to the new VM:
   ```bash
   uci set network.lan.ipaddr='<lan-gateway-ip>'
   uci commit network
   /etc/init.d/network reload
   ```

7. **Verify default route** — after LAN IP change, the default route may shift to the LAN interface:
   ```bash
   ip route show default
   # If wrong (shows br-lan instead of eth1), fix:
   ip route del default
   ip route add default via <upstream-gateway> dev eth1
   uci set network.wan.gateway='<upstream-gateway>'
   uci commit network
   /etc/init.d/network reload
   ```

8. **Reconfigure DNS on WAN-side clients** — clients on the WAN subnet (e.g., 71.x) that used the old router as DNS server will lose resolution. Either set them to use the new VM's WAN IP (if dnsmasq listens on WAN) or configure public DNS (114.114.114.114, 223.5.5.5).

9. **Verify internet connectivity** through the new VM

10. **Shut down the old VM**:
   ```powershell
   # On Hyper-V host
   Stop-VM -Name <old-vm> -TurnOff
   ```

11. **Disable old VM auto-start** (prevents conflicts on Hyper-V host reboot):
   ```powershell
   Set-VM -Name <old-vm> -AutomaticStartAction Nothing
   Get-VM <new-vm> | Select-Object Name, AutomaticStartAction
   # Expected: StartIfRunning
   ```

12. **Fix WAN-side clients' DNS** — Clients on the WAN subnet (e.g., hypervisor at 71.21) that had their DNS set to the old router's IP will lose resolution after shutdown. Fix with:
   ```powershell
   # On each WAN client (Windows):
   netsh interface ipv4 set dns name="<interface-name>" static <dns-ip>

   # Example: point minipc to public DNS
   netsh interface ipv4 set dns name="vEthernet (wan)" static 114.114.114.114

   # Or to the new VM's WAN IP (if dnsmasq allows WAN queries)
   netsh interface ipv4 set dns name="vEthernet (wan)" static 192.168.71.9
   ```

   The `netsh` command is persistent. `PowerShell Set-DnsClientServerAddress` may fail silently — use `netsh` for reliability.

13. **Make WAN-side client's default route persistent** — `route ADD` without `-p` is lost on reboot:
   ```powershell
   # Delete the non-persistent route first
   route DELETE 0.0.0.0 MASK 0.0.0.0 <old-gateway>
   # Add persistent route
   route -p ADD 0.0.0.0 MASK 0.0.0.0 <new-gateway> METRIC <metric> IF <interface-idx>
   ```
   Verify with `route print -4` — the route should appear in both the active and persistent (静态路由) sections.

14. **Add a WAN DNS firewall rule on the new VM** (if WAN clients use its dnsmasq):
   ```bash
   uci add firewall rule
   uci set firewall.@rule[-1].name="Allow-WAN-DNS"
   uci set firewall.@rule[-1].src="wan"
   uci set firewall.@rule[-1].proto="tcp udp"
   uci set firewall.@rule[-1].dest_port="53"
   uci set firewall.@rule[-1].target="ACCEPT"
   uci set firewall.@rule[-1].family="ipv4"
   uci commit firewall
   /etc/init.d/firewall reload
   ```
   (The dnsmasq process itself listens on WAN by default — the missing piece is the firewall input rule.)

#### Migration Pitfalls

- **Default route shifts to LAN after IP change** — When you change the LAN IP and run `network reload`, OpenWrt may move the default route from the WAN interface (eth1) to the LAN bridge (br-lan). Always verify `ip route show default` after the LAN IP change and fix if needed.
- **Old DNS server reference persists on WAN clients** — After shutting down the old VM, any WAN-side client that had its DNS set to the old router's IP will have dead DNS. This breaks resolution silently (SSH over IP works, but `nslookup`, `curl`, `ping` all hang or fail). Fix requires explicit `netsh interface ipv4 set dns` on each client — `Set-DnsClientServerAddress` may fail silently via PowerShell, use `netsh` instead.
- **Non-persistent Windows routes** — `route ADD` (without `-p`) creates routes that vanish on reboot. If you add a default route through the new VM during testing, make it persistent with `route -p ADD` or the client loses connectivity after the next restart.
- **`netsh set dns` warns "DNS 服务器不正确或不存在" even when it works** — This warning appears when the DNS server IP is not immediately reachable at the moment of configuration, but the change is still written and applied. Ignore the warning and verify with `netsh interface ipv4 show dns`.
- **Firewall may show "not running" while rules are active** — fw4 (nftables) on OpenWrt 24.10+ does not reliably report status via `/etc/init.d/firewall running`. Verify with `nft list tables` instead. ImmortalWrt 24.10 uses nftables (fw4) exclusively—`iptables` command is not available, use `nft` instead.
- **WAN SSH rule is temporary until the firewall is reloaded** — Adding the rule via `uci` and running `firewall reload` is sufficient, but subsequent `network reload` operations may reset firewall state. Verify WAN SSH still works after each networking change.
- **OpenClash takes over DNS and firewall** — In Fake-IP mode, OpenClash intercepts all DNS (returns 198.18.0.0/16 addresses) and redirects TCP traffic to its proxy port. This is transparent to clients but means the new VM's dnsmasq is only used for initial DNS queries before OpenClash intercepts them.

## Pitfalls

- **Gen2 VMs with kernel 6.6+ work** — OpenWrt 24.10 (kernel 6.6) includes `hv_netvsc` as a built-in module. Gen2 works with `Set-VMFirmware -EnableSecureBoot Off`. Gen1 is still simpler (no driver config needed) and recommended unless hot-add NICs are required.
- **IP/subnet conflicts** — Pre-configure the new VM with an IP on the same subnet as production. If subnets differ, devices on production can't reach the new VM because the gateway has no route to the other subnet.
- **DHCP conflicts** — Disable DHCP (`option ignore '1'`) on the new VM before first boot to avoid handing out conflicting IPs.
- **Tsinghua mirror doesn't host ImmortalWrt package feeds** — `mirrors.tuna.tsinghua.edu.cn/immortalwrt/releases/` has firmware images but **not** the `packages/` subdirectory. Adding `src/gz imm_luci ...` pointing to Tsinghua's ImmortalWrt packages path will fail silently (404 → opkg skips the feed). Use `downloads.immortalwrt.org` directly for package feeds, or download IPK files from a community GitHub release.
- **Mount order** — Pre-configure the raw `.img` first, **then** convert to VHDX. VHDX images don't mount easily via qemu-nbd on Linux.
- **PowerShell on older Windows** — Use `;` instead of `&&` for chaining commands; older PowerShell versions don't support `&&`.
- **Checkpoints/snapshots** — Hyper-V auto-creates checkpoints on Stop-VM which create differencing AVHDX disks. If you replace the parent VHDX, remove the checkpoint first (`Get-VMSnapshot | Remove-VMSnapshot`).
- **Luci cache after installing apps** — LuCI caches controller registrations. After installing a new Lua-based app (like OpenClash), clear the cache with `rm -rf /tmp/luci-* /tmp/luci-modulecache/*` and restart uhttpd, or the app menu won't appear.
- **Luci-compat required on 24.10** — OpenWrt 24.10 ships JS-based Luci by default. Lua-based apps (most community packages) need `opkg install luci-compat` to register their controllers. Without it, the page gives a 404 even though the controller file exists at `/usr/lib/lua/luci/controller/`.
- **dnsmasq → dnsmasq-full** — OpenClash requires `dnsmasq-full` which conflicts with the default `dnsmasq` package. Remove dnsmasq first, then install dnsmasq-full. The `/etc/config/dhcp` conffile is preserved but a separate `dhcp-opkg` file is created with the new version's defaults.

### 5g. Route a Test Client Through the New VM's WAN Interface

To test the new VM's proxy without modifying LAN-side routing for all devices, route a single client through the new VM's **WAN IP** as its default gateway.

#### How It Works

```
Test client (e.g., 71.21) ── gateway=71.9 ──→ OpenWrt WAN (eth1, 71.9)
  │                                            │
  │  ↓ TCP (intercepted)                       │  OpenClash redirect (tcp:7892)
  │  ↓ ICMP (forwarded directly)               │
  │                                            ↓
  │                              Default route via 71.11 → 光猫 → internet
  └─── ICMP works transparently
  └─── TCP goes through OpenClash → proxy → internet
```

The test client stays on the same subnet (71.x) as both the old and new router WAN ports. Only its default gateway changes.

#### Step 1 — Change Client's Default Gateway

On the test client (e.g., a Windows minipc):

```powershell
# Remove old gateway route
Remove-NetRoute -DestinationPrefix '0.0.0.0/0' -NextHop <old-gateway> -InterfaceIndex <if-index> -Confirm:$false

# Add new route through new VM's WAN IP
New-NetRoute -DestinationPrefix '0.0.0.0/0' -NextHop <new-vm-wan-ip> -InterfaceIndex <if-index> -RouteMetric 0
```

> **Pitfall:** If the client has multiple default routes (e.g., WLAN), check metrics: `Get-NetRoute -DestinationPrefix '0.0.0.0/0'`. The lowest metric wins. Set the new route to metric 0 to make it preferred.

#### Step 2 — Allow WAN-Side Input to OpenClash Redirect Port

When traffic arrives through the WAN interface and gets intercepted by OpenClash's `dstnat` REDIRECT to port 7892, the packet lands in the **INPUT chain** (post-NAT dest is localhost). OpenWrt's default WAN zone input policy REJECTs everything except DHCP and Ping, so the redirected TCP SYN is dropped.

Add a firewall exception:

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

This creates an nftables rule in the `input_wan` chain:
```
tcp dport 7892 counter accept comment "Allow-LAN-WAN-to-OpenClash"
```

#### Step 3 — Verify

```powershell
# ICMP (direct forward) — should work immediately
ping 8.8.8.8

# TCP through OpenClash proxy — needs Step 2's firewall exception
curl -s --connect-timeout 10 -o NUL -w "HTTP_CODE: %{http_code} TIME: %{time_total}s\n" https://www.google.com

# Both proxy and direct routing work
curl -s --connect-timeout 10 -o NUL -w "HTTP_CODE: %{http_code} TIME: %{time_total}s\n" https://www.youtube.com
curl -s --connect-timeout 10 -o NUL -w "HTTP_CODE: %{http_code} TIME: %{time_total}s\n" https://www.baidu.com
```

Expected results:
- Google → `HTTP_CODE: 302` (redirect, expected)
- YouTube → `HTTP_CODE: 200`
- Baidu → `HTTP_CODE: 200` (direct, no proxy)

#### Diagnostic: nftables Packet Flow

If TCP fails but ICMP works, trace the packet path on the new VM:

```bash
# 1. Check input_wan chain — is the OpenClash port open?
nft list chain inet fw4 input_wan

# 2. Check forward_wan chain — is WAN→WAN forwarding allowed?
nft list chain inet fw4 forward_wan

# 3. Check OpenClash redirect rule
nft list chain inet fw4 openclash

# 4. Check FORWARD policy and counters
nft list chain inet fw4 forward

# 5. Check NAT redirect counters
nft list chain inet fw4 dstnat
```

Key insight: OpenClash's `dstnat` intercepts ALL TCP (`ip protocol tcp jump openclash`) and redirects to `:7892`. After REDIRECT, the packet has `dst=127.0.0.1:7892` → enters INPUT chain → needs an ACCEPT rule in `input_wan` or it hits `reject_from_wan`.

#### Reverting

To switch the test client back:

```powershell
Remove-NetRoute -DestinationPrefix '0.0.0.0/0' -NextHop <new-vm-wan-ip> -InterfaceIndex <if-index> -Confirm:$false
New-NetRoute -DestinationPrefix '0.0.0.0/0' -NextHop <old-gateway> -InterfaceIndex <if-index> -RouteMetric 0
```

## Reference Files

- `references/example-deployment-session.md` — Full transcript of a real 22.03.5→24.10.0 migration session on Hyper-V
- `references/testing-via-wan-gateway.md` — Detailed session transcript of routing a WAN-side client through a new OpenWrt VM for proxy testing, including nftables firewall fixes
- `templates/clash-migration-config.yaml` — Full annotated Clash config for proxy migration

## Post-Deployment Maintenance

For disk expansion, boot recovery, and offline filesystem repair on existing VMs, see `references/disk-expansion-boot-recovery.md`.

## Verification

- [ ] New VM responds to ping at configured static IP
- [ ] Luci web interface accessible via browser
- [ ] No DHCP conflicts (check old router's DHCP lease list)
- [ ] New VM can reach internet via old router as its gateway
- [ ] Proxy software installed (PassWall/OpenClash/HomeProxy) and running
- [ ] Proxy test passes: `curl -x http://127.0.0.1:7890 https://www.youtube.com` returns HTTP 200
- [ ] Mihomo/Clash core shows as "MetaRunning" in OpenClash dashboard
- [ ] WAN→LAN forwarding verified: `ping -I <wan-ip> <lan-device-ip>` succeeds
- [ ] WAN gateway set to old router's WAN IP during testing (for proxied connectivity)
- [ ] SSH key-based auth works: `ssh <alias>` without password
