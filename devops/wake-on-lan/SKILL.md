---
name: wake-on-lan
description: Wake-on-LAN 远程唤醒 Windows 设备 — BIOS 配置、注册表、PowerShell 发魔术包（Win/Linux/OpenWrt）、ARP 探测、跨子网中继和排坑。
category: devops
platforms: [linux, windows]
---

# Wake-on-LAN

Wake a powered-off Windows machine by sending a magic packet to its MAC address.

## Checklist: Enable WoL on Target

1. **BIOS**: ErP Ready → Disabled, Wake Event → BIOS
2. **Windows**: `powercfg /h off` (disable hibernation + Fast Startup)
3. **Registry** (for Realtek/Intel NICs):
   - Find NIC subkey under `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-E325-11CE-BFC1-08002bE10318}\`
   - `PnPCapabilities` = 24 (DWORD) — wake from D3, deny system turn-off
   - `S5WakeOnLan` = 1 (DWORD)
   - `EnablePME` = 1 (DWORD)
4. **Restart Windows**, then shut down. NIC link light must stay ON.

## Finding the MAC Address of an Offline Target

If the target is powered off and you don't know its MAC:

### Check the router's ARP cache
Even after the device goes offline, the router's ARP cache may retain the entry from prior connections.

```bash
# OpenWrt / Linux router
cat /proc/net/arp | grep <target-ip>
# Example output: 192.168.37.200  0x1  0x0  e0:d5:5e:d3:d7:4e  *  br-lan
```

### Check the router's DHCP leases
If the device previously got an IP via DHCP:

```bash
# dnsmasq (OpenWrt / most consumer routers)
cat /tmp/dhcp.leases | grep <target-ip>
```

**TTL hint**: After boot, ping the target. TTL=128 → Windows, TTL=64 → Linux/macOS.

## Sending Magic Packet

### From Windows (same L2 subnet)
```powershell
# MUST use Socket with EnableBroadcast; UdpClient silently drops broadcast
$mac = [byte[]]@(0x34, 0x5A, 0x60, 0xB5, 0x8D, 0x13)
$packet = [byte[]]@(0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF) + ($mac * 16)
$sock = New-Object System.Net.Sockets.Socket(
    [System.Net.Sockets.AddressFamily]::InterNetwork,
    [System.Net.Sockets.SocketType]::Dgram,
    [System.Net.Sockets.ProtocolType]::Udp
)
$sock.EnableBroadcast = $true
$sock.Connect("192.168.71.255", 9)
$sock.Send($packet)
$sock.Close()
```

### From Linux (same subnet)
Install `etherwake` and send the magic packet over the local interface:

```bash
sudo apt install etherwake          # Debian/Ubuntu
sudo etherwake -i <interface> <mac> # e.g. -i wlp1s0 (WiFi) or -i eth0 (wired)
```

Or use `wakeonlan` with the subnet broadcast address:

```bash
sudo apt install wakeonlan
wakeonlan -i <subnet-broadcast> <mac>  # e.g. -i 192.168.37.255
```

### From OpenWrt (or minimal BusyBox systems with no Python/Python/bash)

When the jumpbox is an OpenWrt router or other musl-based system without Python, etherwake, or bash, compile a small static WOL binary on the host (glibc) and SCP it over:

```c
// wol.c — compile with: gcc -static -o wol wol.c; strip wol
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <netinet/in.h>

int main(int argc, char *argv[]) {
    if (argc < 3) return 1;
    unsigned char mac[6], packet[102];
    int port = argc > 3 ? atoi(argv[3]) : 9, i;
    sscanf(argv[1], "%hhx:%hhx:%hhx:%hhx:%hhx:%hhx",
           &mac[0],&mac[1],&mac[2],&mac[3],&mac[4],&mac[5]);
    memset(packet, 0xFF, 6);
    for (i = 0; i < 16; i++) memcpy(packet+6+i*6, mac, 6);
    int sock = socket(AF_INET, SOCK_DGRAM, 0);
    int broadcast = 1;
    setsockopt(sock, SOL_SOCKET, SO_BROADCAST, &broadcast, sizeof(broadcast));
    struct sockaddr_in addr = {.sin_family=AF_INET,.sin_port=htons(port),.sin_addr.s_addr=inet_addr(argv[2])};
    sendto(sock, packet, sizeof(packet), 0, (struct sockaddr*)&addr, sizeof(addr));
    close(sock);
    return 0;
}
```

Transfer and run:
```bash
# Compile on a glibc host (static, works on musl too)
gcc -static -o /tmp/wol /tmp/wol.c && strip /tmp/wol

# Transfer to OpenWrt (use -O for SCP protocol — OpenWrt dropbear lacks sftp-server)
scp -O /tmp/wol root@openwrt:/tmp/

# Send WOL to subnet broadcast (must be sent from the same L2 domain)
ssh root@openwrt '/tmp/wol 34:5a:60:b5:8d:13 192.168.71.255'
```

## Post-WOL Verification

After sending the magic packet, **wait 60+ seconds** for the target to boot — cold boot from WOL takes longer than a warm reboot. Some NICs need two bursts. Be patient: the user explicitly flags impatience (e.g. checking every 2s for 30s) as a mistake. Wait a full 60–90s before concluding the WOL failed.

**⚠️ Windows Firewall blocks ICMP by default.** Ping returning 100% loss does NOT mean the device failed to boot — it may be fully online with SSH available. Always verify via SSH before concluding WOL failed.

Preferred verification order:

1. **SSH port check**: `nc -zv <target-ip> 22` — primary check. If port 22 answers, device is online.
2. **SSH echo**: `ssh -o ConnectTimeout=5 <user>@<target-ip> "hostname"` — confirms SSH service is running and responsive.
3. **Ping** (secondary, Linux-only targets): `ping -c 3 <target-ip>` — reliable only for non-Windows targets.
4. **TTL check from a successful ping** (if ping works): TTL=128 → Windows, TTL=64 → Linux/macOS.

If the target doesn't respond after 90 seconds (no SSH port, no ping), re-send the magic packet.

## Pitfalls

- **UdpClient drops broadcast**: .NET `UdpClient.Connect()` + `Send()` won't set `SO_BROADCAST` on Windows. Always use raw `Socket` with `EnableBroadcast = $true`.
- **Cross-subnet failure**: Magic packet is L2 broadcast — it cannot cross routers. Send from a machine on the same physical subnet.
- **shutdown /s /f may prevent WoL**: Force-close (`/f`) can skip driver S5 sleep transition. Use `shutdown /s /t 5` without `/f` from Windows UI or remote.
- **NIC light off = no WoL**: If the Ethernet port LED is dark when powered off, the NIC has no standby power. Check BIOS and registry.
