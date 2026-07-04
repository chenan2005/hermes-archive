## 目录

- [# openwrt-hyperv-deployment](##-openwrt-hyperv-deployment)
- [# openwrt-passwall-split-routing](##-openwrt-passwall-split-routing)
- [# openwrt-proxy-acceleration](##-openwrt-proxy-acceleration)

---



# openwrt-hyperv-deployment

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

# openwrt-passwall-split-routing

# OpenWrt PassWall Split-Routing

Route specific domains through different proxy nodes when PassWall's built-in shunt feature is insufficient (it only supports `_direct`, `_default`, `_blackhole` targets, not multiple proxy outbounds).

## Method comparison

| Method | Granularity | IP collisions | V2Ray-incompatible protocols |
|--------|------------|---------------|------------------------------|
| **SNI routing (recommended)** | Domain (SNI) | None | Needs SOCKS chain |
| ipset+iptables (fallback) | IP | Yes — shared IPs cause collateral routing | Direct (separate xray) |

**Always prefer SNI routing.** Use ipset+iptables only when SNI routing is impractical (e.g., you can't modify PassWall's V2Ray config).

## Primary method: V2Ray SNI routing + Xray chain

### Architecture

```
All traffic → iptables → PassWall V2Ray (dokodemo-door :1041)
  ├── SNI match: target domains → SOCKS outbound → 127.0.0.1:1071 → Xray → Reality/VLESS
  └── Default route → main proxy node (VMess/other)
```

PassWall's bundled `v2ray` binary is V2Ray, not Xray. For protocols V2Ray doesn't support (Reality, Hysteria2), chain through a SOCKS outbound to a separate Xray instance.

### Steps

#### 1. Extract node credentials

```bash
ssh root@openwrt.lan.11
uci show passwall.<node_name>  # UUID, address, port, streamSettings, etc.
```

#### 2. Create secondary Xray config

`/etc/xray-seoul.json` — SOCKS inbound only (V2Ray connects to it):

```json
{
  "log": {"loglevel": "warning"},
  "inbounds": [{
    "port": 1071,
    "protocol": "socks",
    "listen": "127.0.0.1",
    "sniffing": {"enabled": true, "destOverride": ["http", "tls"]},
    "settings": {"udp": true, "auth": "noauth"}
  }],
  "outbounds": [{
    "protocol": "vless",
    "tag": "secondary",
    "settings": { "vnext": [{"address": "...", "port": ..., "users": [...]}] },
    "streamSettings": { ... }
  }]
}
```

#### 3. Patch PassWall's V2Ray config

Add two things to `/tmp/etc/passwall/TCP_SOCKS.json`:

a) **SOCKS outbound** (insert after main proxy outbound, before `direct`):
```json
{
  "protocol": "socks",
  "tag": "secondary_socks",
  "settings": {"servers": [{"address": "127.0.0.1", "port": 1071}]}
}
```

b) **Routing rules** (replace empty `"rules": []`):
```json
{
  "type": "field",
  "outboundTag": "secondary_socks",
  "domain": [
    "domain:accounts.google.com",
    "domain:oauth2.googleapis.com",
    ...
  ]
}
```

Critical: keep ALL other fields identical to PassWall's generated config — especially `mark: 255` on outbounds (this is how V2Ray bypasses PassWall's own iptables REIRECT via the `mark match 0xff` RETURN rule in nat OUTPUT).

Then restart V2Ray TCP:
```bash
PID=$(ps | grep "TCP_SOCKS.json" | grep -v grep | awk '{print $1}')
kill $PID; sleep 1
/tmp/etc/passwall/bin/v2ray run -c /tmp/etc/passwall/TCP_SOCKS.json > /tmp/passwall-tcp.log 2>&1 &
```

#### 4. Ensure target domains reach V2Ray

PassWall's GFWList may not cover all target domains. If traffic goes direct (bypassing the proxy entirely), SNI routing never triggers. Check:

```bash
IP=$(nslookup accounts.google.com 127.0.0.1 | grep Address | tail -1 | awk '{print $2}')
ipset test passwall_gfwlist $IP  # if "NOT in set" → traffic goes direct → fix needed
```

Fix options:
- **A (quick)**: Add Google IP ranges to `passwall_blacklist`
- **B (persistent)**: Add domains to `proxy_host` via UCI:
  ```bash
  uci add_list passwall.@global_rules[0].proxy_host="accounts.google.com"
  uci commit passwall && /etc/init.d/passwall restart
  ```
  This adds dnsmasq rules that route domain DNS through overseas servers and tag IPs for proxy redirect. Then re-inject the V2Ray config (step 3).

#### 5. Persist across reboots

PassWall regenerates its config on every restart. Create two init scripts:

**`/etc/init.d/xray-seoul`** (START=98): Starts the secondary Xray.
**`/etc/init.d/v2ray-seoul-inject`** (START=99, after PassWall):

```sh
#!/bin/sh /etc/rc.common
START=99
start() {
    sleep 15  # wait for PassWall to fully start
    # Add Google IPs to blacklist
    for cidr in 173.194.0.0/16 142.250.0.0/15 ...; do
        ipset add passwall_blacklist $cidr 2>/dev/null
    done
    # Inject unified V2Ray config if not already injected
    if ! grep -q "secondary_socks" /tmp/etc/passwall/TCP_SOCKS.json; then
        cp /etc/v2ray-unified.json /tmp/etc/passwall/TCP_SOCKS.json
        PID=$(ps | grep "TCP_SOCKS.json" | grep -v grep | awk '{print $1}')
        [ -n "$PID" ] && kill $PID; sleep 1
        /tmp/etc/passwall/bin/v2ray run -c /tmp/etc/passwall/TCP_SOCKS.json > /tmp/passwall-tcp.log 2>&1 &
    fi
}
```

Store the unified config as `/etc/v2ray-unified.json`.

### Verification

```bash
# SOCKS test (domain routing always works here)
curl -s --socks5-hostname 127.0.0.1:1070 -o /dev/null -w "HTTP:%{http_code}\n" https://accounts.google.com

# Transparent proxy test from LAN device
curl -s -o /dev/null -w "HTTP:%{http_code}\n" https://accounts.google.com

# Check V2Ray routing
grep "secondary_socks" /tmp/passwall-tcp.log

# Check Xray log (should show target domains)
tail /tmp/xray-seoul.log

# Verify YouTube is NOT on secondary
grep "googlevideo\|youtube" /tmp/xray-seoul.log  # should be EMPTY
```

## Fallback method: ipset + iptables (use only when SNI routing is impractical)

This method works at IP level — dnsmasq tags resolved IPs, iptables redirects them to a separate xray instance.

**Major pitfall: IP collisions.** Google services share IPs. If `accounts.google.com` resolves to the same IP as `googlevideo.com`, YouTube video traffic gets routed through the secondary proxy. Worse, unrelated services (Facebook, Twitter) can get pulled in if any Google auth domain uses shared CDN IPs. Only use this method if you can't modify PassWall's V2Ray config.

See `references/ipset-iptables-fallback.md` for the full setup if needed.

## References

- `references/reality-node-uci-config.md` — PassWall Reality 节点 UCI 配置要点（`reality='1'`、`tls='1'`、IP vs 域名）

## Pitfalls

1. **PassWall shunt can't reference nodes**: `_direct`, `_default`, `_blackhole` only. Custom node names are silently ignored.
2. **V2Ray ≠ Xray**: PassWall's bundled binary is V2Ray, not Xray. No Reality/Hysteria2 support. Chain through SOCKS to a separate Xray.
3. **GFWList gaps**: `accounts.google.com` may not be in GFWList → traffic goes direct → never reaches V2Ray for SNI routing. Fix with proxy_host or blacklist.
4. **Config overwrite**: PassWall regenerates config on restart. Use init script injection (step 5).
5. **Mark 255/0xFF is required**: This is how V2Ray outbound traffic bypasses PassWall's iptables REIRECT in the nat OUTPUT chain. Don't remove or change it.
6. **Runtime files not generated**: Even with `proxy_host` correctly configured in uci, PassWall may fail to write runtime files (`/tmp/etc/passwall/proxy_host`, `/tmp/etc/dnsmasq.d/passwall.conf`). DNS queries for those domains never populate the ipsets, so traffic goes direct silently. See `references/diagnose-runtime-files.md` for the complete diagnostic workflow. Fix: `/etc/init.d/passwall restart`.
7. **ipset IP collisions** (fallback method only): Google shares IPs across services. SNI routing avoids this entirely.
8. **DNS must go through dnsmasq** (fallback method only): If client uses DoH/DoT, ipset won't populate.
9. **Cross-border bandwidth is the proxy's ceiling**: A VPS may have 200Mbps+ advertised bandwidth, but the China→X link often delivers <1Mbps. Test raw (no proxy) first. If raw is slow, no protocol or port change will help.
10. **Proxy protocol overhead is usually negligible**: Compare raw vs proxied speed for the same file. If the difference is <0.2Mbps, don't blame the protocol — it's the network.

## Testing proxy bandwidth

```bash
# CacheFly 100MB — good global benchmark, no geo-restrictions
curl -s --max-time 20 --socks5-hostname 127.0.0.1:1070 -o /dev/null \
  -w "DL:%{size_download}B t:%{time_total}s sp:%{speed_download}B/s\n" \
  "http://cachefly.cachefly.net/100mb.test"
```

### Diagnosing bandwidth bottlenecks (three-layer method)

When a proxy node feels slow, isolate the bottleneck by testing three layers:

**Layer 1 — Server self-test:** SSH into the VPS and test raw bandwidth to speedtest servers:
```bash
ssh user@vps
# Tokyo Linode — great for Asian VPS
curl -s --max-time 15 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s sp:%{speed_download}B/s\n" \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin"
```

**Layer 2 — Raw TCP (no proxy):** From OpenWrt, download the same file directly from the VPS:
```bash
# Start temporary HTTP server on the VPS
ssh user@vps 'cd /tmp && python3 -m http.server 8888'

# From OpenWrt, download directly (no proxy)
ssh root@openwrt 'curl -s --max-time 20 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s sp:%{speed_download}B/s\n" \
  "http://VPS_IP:8888/100mb.bin"'
```

**Layer 3 — Through proxy:** Same file through the proxy SOCKS port:
```bash
curl -s --max-time 20 --socks5-hostname 127.0.0.1:1070 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s sp:%{speed_download}B/s\n" \
  "http://VPS_IP:8888/100mb.bin"
```

If L1 is fast (>50 MB/s) but L2 and L3 are similarly slow, the bottleneck is the cross-border link (e.g., China→Korea), not the proxy protocol. Changing ports, protocols, or encryption won't help.

If L2 is fast but L3 is slow, the proxy protocol or client-side config is the bottleneck.

## Cloudflare CDN acceleration

When direct cross-border bandwidth is poor (<1Mbps) but the VPS itself has good speed, Cloudflare CDN can drastically improve throughput (30-50x in our tests). Traffic flows:

```
Client(China) → Cloudflare edge(HK/JP) → CF backbone → VPS origin
```

### Method A: Cloudflare DNS proxy (recommended, permanent)

Requires the domain to be on Cloudflare DNS (full NS delegation).

**1. Migrate DNS to Cloudflare**
- Add domain at dash.cloudflare.com
- Import existing A/CNAME records (set non-proxy services to DNS-only, ⚪)
- Add proxy-enabled A record: `seoul.yourdomain.com → YOUR_VPS_IP` (🟠)
- Change NS at registrar from current (DNSPod, etc.) to Cloudflare's NS
- Wait for propagation (minutes to hours)

**2. Configure origin server**
- Add a VMess+WS+TLS inbound on port 443 (or 80 + Cloudflare handles TLS)
- Use a self-signed cert (Cloudflare "Full" SSL mode accepts it)
- Cloudflare's default SSL mode is "Full" — no further config needed

**3. Client connects to Cloudflare-proxied domain**
- PassWall node: address = `seoul.yourdomain.com`, port = 443
- Cloudflare terminates TLS at edge, proxies WS to origin via HTTPS
- Same speed as the Cloudflare tunnel test — typically 25-40Mbps

### Method B: Cloudflare Tunnel (for quick testing or as permanent systemd service)

Use `cloudflared` to create a `*.trycloudflare.com` tunnel — no DNS changes needed:

```bash
# On the VPS
curl -sL https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/cloudflared-linux-amd64 -o /tmp/cloudflared
chmod +x /tmp/cloudflared
cd /tmp && python3 -m http.server 9999 &
/tmp/cloudflared tunnel --url http://127.0.0.1:9999
# Output: https://random-words.trycloudflare.com

# From OpenWrt
curl -s --max-time 30 "https://random-words.trycloudflare.com/100mb.bin"
```

**For permanent deployment** (systemd service, auto-reconnect on crash/reboot):

```bash
sudo cp /path/to/cloudflared /usr/local/bin/cloudflared
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:80
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now cloudflared
```

After starting, retrieve the tunnel URL from journalctl:
```bash
sudo journalctl -u cloudflared --no-pager -n 20 | grep -o 'https://[a-z0-9.-]*\.trycloudflare\.com'
```

**Pitfall: trycloudflare.com DNS SERVFAIL on OpenWrt.** OpenWrt's dnsmasq + chinadns-ng returns SERVFAIL for `*.trycloudflare.com`. Fix by adding the Cloudflare IP to `/etc/hosts`:

```bash
# Get CF IPs from public DNS
IP=$(dig @1.1.1.1 +short tries-words.trycloudflare.com | head -1)
echo "$IP tries-words.trycloudflare.com" >> /etc/hosts
```

**Version note**: cloudflared 2026.6.1 quick tunnel fails with `"invalid UUID length: 0"`. Use **2024.12.2** or earlier for reliable quick tunnel creation.

### Interpreting results

Compare three measurements:
| Test | Expected |
|------|----------|
| VPS self-test to CDN | 500+ Mbps |
| OpenWrt → VPS (raw) | 0.5-5 Mbps (China cross-border) |
| OpenWrt → VPS via Cloudflare | 20-40 Mbps (30-50x improvement) |

If Cloudflare helps, the cross-border link is the bottleneck. If throughput is similar, the VPS's total bandwidth or peering is the limit.


## References

- `references/google-auth-domains.md` — Complete list of Google authentication domains
- `references/iptables-redirect-listen.md` — Why 0.0.0.0 vs 127.0.0.1 matters for REDIRECT
- `references/sni-routing-v2ray-config.md` — Detailed V2Ray config injection walkthrough
- `references/ipset-iptables-fallback.md` — Full ipset+iptables setup (for when SNI routing is impractical)
- `references/cloudflare-dns-migration.md` — Moving DNS from DNSPod to Cloudflare for CDN acceleration
- `references/diagnose-runtime-files.md` — Step-by-step diagnostic when proxy_host domains are configured but traffic still goes direct (runtime files not generated)

## Templates

- `templates/xray-secondary.json` — Skeleton Xray config for secondary proxy (SOCKS inbound)
- `templates/v2ray-unified-config.json` — Annotated V2Ray unified config with SOCKS outbound + SNI routing rules

# openwrt-proxy-acceleration

# OpenWrt Proxy Bandwidth Diagnosis & Acceleration

## Bottleneck Diagnosis Flow

Test server-side bandwidth first, then compare through proxy to isolate the bottleneck:

```
Seoul服务器本机 → 东京CDN: 600Mbps+  → 服务器没问题
OpenWrt裸连Seoul:   ~0.75Mbps       → 跨境链路瓶颈
OpenWrt→CF→Seoul:   25-40Mbps      → CF有效
```

### Step 1: Server bare bandwidth
```bash
ssh <server>
curl -s --max-time 15 -o /dev/null -w "DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin"
```

### Step 2: OpenWrt raw HTTP test (no proxy)
On Seoul ECS, start a simple HTTP server and test from OpenWrt:
```bash
# Seoul side
cd /tmp
dd if=/dev/zero bs=1M count=100 of=100mb.bin
python3 -m http.server 9999 &

# OpenWrt side
curl -s --max-time 30 -o /dev/null \
  -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "http://<seoul-ip>:9999/100mb.bin"
```

### Step 3: Through-proxy speed test
```bash
# Via PassWall SOCKS
curl -s --max-time 20 --socks5-hostname 127.0.0.1:1070 -o /dev/null \
  -w "DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" \
  "http://speedtest.tokyo2.linode.com/100MB-tokyo2.bin"
```

## Cloudflare Tunnel Acceleration Test

Use `cloudflared` to create a quick tunnel and test if Cloudflare's backbone helps.
**Use v2024.12.2** — newer versions have a UUID parsing bug with quick tunnels.

```bash
# Install
curl -sL https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/cloudflared-linux-amd64 -o /tmp/cf-old
chmod +x /tmp/cf-old

# Start HTTP server + tunnel
/tmp/cf-old tunnel --url http://127.0.0.1:9999 > /tmp/cf-out.log 2>&1 &
sleep 10
CF_URL=$(grep -o "https://[a-z0-9.-]*\.trycloudflare\.com" /tmp/cf-out.log | head -1)

# Test from OpenWrt
curl -s --max-time 30 -o /dev/null -w "HTTP:%{http_code} DL:%{size_download}B t:%{time_total}s V:%{speed_download}B/s\n" "$CF_URL/100mb.bin"
```

## Cloudflare CDN Production Setup (VMess+WS)

The production setup uses Cloudflare's DNS proxy (orange cloud) instead of cloudflared.
Same pattern as running KVM behind Cloudflare at 40Mbps.

### Architecture

```
OpenWrt → seoul.domain.com:80 (VMess+WS, HTTP)
       → Cloudflare edge (proxied, TLS terminated at edge)
       → Seoul:80 (VMess+WS, no TLS)
```

### Steps

1. **Add domain to Cloudflare** (free plan), enable orange cloud proxy for the subdomain.

2. **Set Cloudflare SSL/TLS to "Flexible"** (not Full). Flexible sends HTTP to origin port 80. Full sends HTTPS — won't work with VMess unless origin presents a valid cert.

3. **Origin (Seoul): VMess+WS on port 80, no TLS**:
```json
{
  "listen": "0.0.0.0", "port": 80, "protocol": "vmess",
  "settings": {"clients": [{"id": "<uuid>", "email": "openwrt-cf"}]},
  "streamSettings": {
    "network": "ws", "security": "none",
    "wsSettings": {"path": "/ws-seoul"}
  }
}
```

4. **OpenWrt PassWall node**: address=the domain, port=80, tls=0, transport=ws, path=/ws-seoul.

5. DNS resolves to Cloudflare IPs (104.x, 172.x). Cloudflare proxies to origin.

### x-ui Config Pitfall

3X-UI **regenerates config.json from its SQLite database** on every panel operation or x-ui restart.
Manual edits to `/usr/local/x-ui/bin/config.json` get overwritten on `x-ui restart`. This means:

- Editing config via SQLite (sudo sqlite3 /etc/x-ui/x-ui.db) works but gets overwritten on x-ui restart
- Editing `/usr/local/x-ui/bin/config.json` directly works but gets overwritten on x-ui restart
- Editing the DB + restarting x-ui: changes persist but ONLY if DB fields are correctly formatted

To bypass this for a config with non-standard inbounds:

```bash
# 1. Stop x-ui
sudo systemctl stop x-ui

# 2. Write clean config with ALL required inbounds (Reality, VMess+WS, etc.)
#    Include outbounds and remove metrics/api to avoid port conflicts
sudo tee /usr/local/x-ui/bin/config.json << 'CONFIG'
{
  "log": {"loglevel": "warning"},
  "inbounds": [
    { "port": 40001, "protocol": "vless", ... },   # Reality
    { "port": 80, "protocol": "vmess", ... },      # WS (no TLS, for Cloudflare)
    { "port": 443, "protocol": "vmess", ... }       # WS+TLS (self-signed, for direct)
  ],
  "outbounds": [
    {"protocol": "freedom", "tag": "direct"},
    {"protocol": "blackhole", "tag": "blocked"}
  ]
}
CONFIG

# 3. Run xray directly (NOT through x-ui)
sudo /usr/local/x-ui/bin/xray-linux-amd64 -c /usr/local/x-ui/bin/config.json &

# 4. Never restart x-ui afterward (or the config is lost)
# To auto-start on boot, create a systemd service for xray directly
```

### Cloudflare SSL Mode Decision Tree

| Origin setup | Required CF SSL mode | Why |
|-------------|---------------------|-----|
| VMess+WS on port **80** (no TLS) | **Flexible** | CF sends HTTP to origin:80. Full sends HTTPS → WS handshake fails on TLS port |
| VMess+WS+TLS on port **443** (self-signed cert) | **Full** (not strict) | CF sends HTTPS, accepts any origin cert |
| VMess+WS+TLS on port **443** (Let's Encrypt/CA cert) | **Full (strict)** | CF validates origin cert per CA chain |

**Default for new Cloudflare zones is `Full`** — which works for self-signed port 443 but BREAKS for port-80-only setups. Change to `Flexible` if your origin runs VMess+WS on 80.

> **Why `Full` breaks port-80 WS:** `Full` sends HTTPS to the origin. If origin is listening on port 80 with WS (no TLS), it expects HTTP. The TLS handshake from Cloudflare arrives, the origin's WS server sees garbage (TLS bytes, not HTTP), and the connection fails silently — no error message, just timeout on the client side.

| Test | Direct CN→KR | Via Cloudflare |
|------|:-----------:|:------------:|
| Server→Tokyo | 620 Mbps | same |
| OpenWrt→Seoul raw | ~0.75 Mbps | ~25-40 Mbps |
| YouTube experience | 240p only | 1080p+ |

Cloudflare improves China→Korea routes **33-50x** by routing through their backbone (likely Hong Kong/Japan).

## PassWall Node Verification & Testing

PassWall may have proxy nodes registered in the UCI database that aren't set as the active TCP/UDP node. Verify ALL nodes are alive:

```bash
# List all nodes with their IDs
for id in $(uci show passwall | grep "=nodes" | cut -d= -f1 | cut -d. -f2); do
  echo "$id: $(uci get passwall.$id.remarks 2>/dev/null) - $(uci get passwall.$id.address 2>/dev/null):$(uci get passwall.$id.port 2>/dev/null)"
done
```

### Test a specific node via temporary switch

```bash
old=$(uci get passwall.@global[0].tcp_node)
uci set passwall.@global[0].tcp_node=<NODE_ID>
uci commit passwall
/etc/init.d/passwall restart
sleep 8
curl -sx "socks5://127.0.0.1:1070" --max-time 10 https://cp.cloudflare.com/generate_204 \
  -o /dev/null -w "%{http_code} %{time_total}s"
# Restore original node
uci set passwall.@global[0].tcp_node=$old
uci commit passwall
/etc/init.d/passwall restart
```

Set `NODE_ID` from the output above (e.g., `cfg131c7e` for Seoul-CF, `cfg141c7e` for VMISS-HK).

## SNI-based Split Routing in PassWall V2Ray

Route specific domains through a different proxy node at the SNI level (bypasses IP collision issues from ipset-based routing).

### Architecture
```
V2Ray inbound -> SNI domain matching -> Seoul outbound or KVM outbound
```

### Implementation

1. Inject Seoul xray as SOCKS upstream:
```bash
/usr/bin/xray run -c /etc/xray-seoul.json > /tmp/xray-seoul.log 2>&1 &
```

2. Patch PassWall's generated V2Ray config (keep template at `/etc/v2ray-unified.json`):
   - Add SOCKS outbound pointing to `127.0.0.1:1071`
   - Add routing rules with SNI domain list
   - Copy config over PassWall's TCP_SOCKS.json after each PassWall restart

3. See `references/passwall-sni-routing.md` for the full unified config JSON structure.
4. See `references/seoul-xray-config.md` for the Seoul server multi-inbound xray config.

### DNS + iptables support

Add Google auth domains to PassWall's proxy_host list and Google IP ranges to blacklist:
```bash
# UCI
for domain in accounts.google.com oauth2.googleapis.com ...; do
  uci add_list passwall.@global_rules[0].proxy_host="${domain}"
done

# Blacklist (ensure Google IPs get caught by redirect)
for cidr in 173.194.0.0/16 142.250.0.0/15 142.251.0.0/16 216.58.192.0/19 216.239.32.0/19 64.233.160.0/19 74.125.0.0/16 172.217.0.0/16; do
  ipset add passwall_blacklist $cidr 2>/dev/null
done
```

## Cloudflare Tunnel Production Setup (systemd)

A persistent alternative to CDN proxy. Does NOT require Cloudflare DNS — works with any DNS provider.

### Architecture

```
OpenWrt → trycloudflare-random.trycloudflare.com:443 (VMess+WS+TLS)
       → Cloudflare edge → tunnel → cloudflared (Seoul) → localhost:80 → xray
```

Warning: The quick tunnel URL changes on cloudflared restart. For a stable URL, use a named tunnel with `cloudflared tunnel create`.

### Systemd Service

```bash
# Install (use v2024.12.2 - newer versions have UUID parsing bug)
sudo cp /tmp/cf-old /usr/local/bin/cloudflared
sudo chmod +x /usr/local/bin/cloudflared

# Create service
sudo tee /etc/systemd/system/cloudflared.service > /dev/null << 'EOF'
[Unit]
Description=Cloudflare Tunnel
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:80
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable --now cloudflared
```

### Retrieve tunnel URL

```bash
sudo journalctl -u cloudflared --no-pager -n 30 | grep -oP 'https://[a-z0-9.-]+\.trycloudflare\.com' | tail -1
```

### DNS resolution caveat

Chinese DNS resolvers (including OpenWrt dnsmasq + chinadns-ng) may return `SERVFAIL` for `*.trycloudflare.com`. Add tunnel hostname to /etc/hosts on OpenWrt:

```bash
echo "<cloudflare-ip> <tunnel-hostname>.trycloudflare.com" >> /etc/hosts
```

Resolve IP from Google DNS (8.8.8.8) or Cloudflare DNS (1.1.1.1) since they resolve correctly.

### OpenWrt PassWall node for tunnel

Configure a PassWall node with the tunnel hostname as address:

```
address=<tunnel-hostname>.trycloudflare.com
port=443
tls=1
tls_serverName=<tunnel-hostname>.trycloudflare.com
transport=ws
ws_path=/ws-seoul
ws_host=<tunnel-hostname>.trycloudflare.com
```

### Speed comparison

| Method | Speed | Requires Cloudflare DNS? |
|--------|:----:|:------------------------:|
| Direct CN→KR | ~0.75 Mbps | No |
| Cloudflare CDN (orange cloud) | ~25-40 Mbps | Yes |
| Cloudflare Tunnel (quick tunnel) | ~15-28 Mbps | No |
| KVM (US + Cloudflare) | ~40 Mbps | Yes (optional) |

### Stop x-ui from overwriting manual config

3X-UI regenerates config.json from its SQLite database on restart. For persistent manual configs:

```bash
sudo systemctl stop x-ui
# Write your custom config
sudo tee /usr/local/x-ui/bin/config.json << 'CONFIG'
{ ... inbounds, outbounds ... }
CONFIG
# Run xray directly
sudo /usr/local/x-ui/bin/xray-linux-amd64 -c /usr/local/x-ui/bin/config.json &
# Do NOT restart x-ui afterward
```

## Pitfalls

- **ipset IP routing causes IP collision**: Google shares IPs across services. ipset-based routing will route YouTube traffic through the auth proxy if they hit the same IP. Always prefer SNI/domain-based routing.
- **V2Ray DNS loop**: V2Ray's internal DNS can create circular dependencies. Use `dns.servers: ["localhost"]` or use IP addresses directly.
- **PassWall overwrites config**: Every restart regenerates TCP_SOCKS.json. Use a post-generation hook (init script START=99 after PassWall) to re-inject the unified config.
- **Port QoS**: Different proxy ports may get different QoS treatment. Port 443 (HTTPS) sometimes gets better bandwidth than high ports. On Alibaba Cloud Seoul, port QoS is negligible vs the physical link limit.
- **China cross-border BW**: China->Japan/Korea often <1Mbps. China->US via Cloudflare can be 40Mbps+. The bottleneck is the physical international link, not the proxy protocol.
- **Cloudflare + VMess SSL mode**: Must use "Flexible" (not Full) when origin has no TLS. Full mode sends HTTPS to origin:80 which breaks VMess.
- **Self-signed certs with Cloudflare proxy**: Cloudflare Full (strict) requires a valid CA-signed cert. Self-signed certs only work with Full (non-strict) mode. For VMess+WS without TLS, use Flexible mode instead.