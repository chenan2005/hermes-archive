# Wake-on-LAN — Cross-Subnet & Full Setup

## Key finding

Magic packets MUST originate from the same L2 subnet as the target.
Sending a directed broadcast from a different subnet does NOT reach the
target NIC — routers drop directed broadcasts by default.

## The proven three-element WoL formula

All three are REQUIRED. Missing any one = silent failure.

1. **`SO_BROADCAST`** — `UdpClient` does NOT set this by default on Windows.
   Must use raw `Socket` with `EnableBroadcast = $true`.
2. **`Bind` to a local IP on the target subnet** — ensures the packet leaves
   via the correct interface (not a different NIC or virtual adapter).
3. **`255.255.255.255:9`** — limited broadcast on the local subnet.

## Working implementations

### minipc (PowerShell) — primary, confirmed by Moonlight

`C:\Users\chen_\wol.ps1`:
```powershell
$mac = [byte[]]@(0x34, 0x5A, 0x60, 0xB5, 0x8D, 0x13)
$packet = [byte[]]@(0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF) + ($mac * 16)
$sock = New-Object System.Net.Sockets.Socket(
    [System.Net.Sockets.AddressFamily]::InterNetwork,
    [System.Net.Sockets.SocketType]::Dgram,
    [System.Net.Sockets.ProtocolType]::Udp)
$sock.EnableBroadcast = $true
$sock.Bind((New-Object System.Net.IPEndPoint([System.Net.IPAddress]"192.168.71.21", 0)))
$sock.SendTo($packet, (New-Object System.Net.IPEndPoint([System.Net.IPAddress]"255.255.255.255", 9)))
$sock.Close()
```

### OpenWrt (static C binary) — confirmed

Compiled on the laptop with `gcc -static`, uploaded to OpenWrt as `/tmp/wol`:
```c
int s = socket(AF_INET, SOCK_DGRAM, 0);
int one = 1; setsockopt(s, SOL_SOCKET, SO_BROADCAST, &one, sizeof(one));
struct sockaddr_in local = {AF_INET, 0, {inet_addr("192.168.71.11")}};
bind(s, (struct sockaddr*)&local, sizeof(local));
struct sockaddr_in addr = {AF_INET, htons(9), {inet_addr("255.255.255.255")}};
sendto(s, pkt, 102, 0, (struct sockaddr*)&addr, sizeof(addr));
```

### Local laptop script

`~/.local/bin/wake-9950x3d` — delegates to minipc via SSH:
```bash
#!/bin/bash
ssh minipc 'powershell -ExecutionPolicy Bypass -File C:\Users\chen_\wol.ps1' 2>/dev/null
echo "WoL sent to 34:5a:60:b5:8d:13 via minipc (71 subnet)"
```

**Usage**: `wake-9950x3d` → wait 60-90s → `ssh 9950x3d`

## Failed approaches (do NOT repeat)

| Approach | Why it failed |
|----------|--------------|
| Python from laptop to 192.168.71.255 | Cross-subnet broadcast dropped by router |
| Adding 192.168.71.x to laptop WiFi | Kernel route hijacks 71.x traffic, breaks all connectivity to that subnet |
| `UdpClient.Connect()` + `Send()` | Does NOT set `SO_BROADCAST` on Windows — packet silently dropped |
| `UdpClient` without `Bind` | Picks the wrong network interface |
| OpenWrt shell script via `socat`/`nc` | socat/etherwake/python3/bash not available in OpenWrt 22.03 |
| OpenWrt Python socket | python3 not installable via opkg |

## Windows WoL prerequisites (checklist)

1. **BIOS**: ErP Ready → Disabled, Wake on LAN → BIOS-controlled (not OS)
2. **Windows registry** (requires reboot to apply):
   Find driver key under `HKLM\SYSTEM\CurrentControlSet\Control\Class\{4D36E972-...}\00NN` where DriverDesc matches the NIC:
   - `PnPCapabilities` = 24 (DWORD) — bit4=1 wake from D3, bit3=0 do NOT allow turn off
   - `S5WakeOnLan` = 1 — allow wake from full shutdown S5
   - `EnablePME` = 1
3. **`powercfg /h off`** — disable hibernation (Fast Startup blocks WoL)
4. **Restart Windows** (not shutdown) for registry changes to take effect
5. After restart → shutdown → **NIC link light must stay ON**
6. If light is off, WoL cannot work — recheck registry values and BIOS

## Diagnostic flow

```
Machine off → NIC light ON?
  YES → Send magic packet via minipc (same 71 subnet) → wait 60s → host reachable?
    YES → Done
    NO  → Retry, check MAC, wait 90s
  NO  → BIOS ErP, registry PnPCapabilities/S5WakeOnLan, powercfg /h off
         → Restart Windows → shutdown → check light again
```

## Finding MAC from Router ARP Cache

When the target device has connected to the network at least once, its MAC is cached in the router's ARP table even after it powers off.

### OpenWrt

```bash
ssh root@openwrt 'cat /proc/net/arp' | grep <ip>
```

The `cat /proc/net/arp` output persists MAC entries after the device goes offline (unlike `arp -n` on Linux which shows `(incomplete)`). This works even when DHCP leases have expired or the device uses a static IP.

### Same-subnet WoL (no relay needed)

If your workstation and the target are on the same subnet, WoL directly:

```bash
# 1. Get MAC from OpenWrt ARP cache
ssh openwrt 'cat /proc/net/arp' | grep 192.168.37.200

# 2. Install etherwake (if needed)
sudo apt install etherwake

# 3. Send WOL magic packet via the correct interface
sudo etherwake -i wlp1s0 e0:d5:5e:d3:d7:4e
```

**Pitfall**: Interface matters — use `-i <iface>` to match the NIC on the same broadcast domain as the target. On WiFi (`wlp1s0`), the magic packet reaches the wired subnet via the switch, which bridges the broadcast.

### Whole-subnet WoL from OpenWrt

When `etherwake` isn't available on the source machine, delegate to OpenWrt:

```bash
ssh openwrt 'opkg update && opkg install etherwake && etherwake -i br-lan e0:d5:5e:d3:d7:4e'
```

## Pitfalls

- **Command-line shutdown**: `shutdown /s` may have different behavior than
  manual Start → Shutdown. If WoL doesn't work, try a manual shutdown from
  the Windows UI before debugging further.
- Adding a secondary IP from the target subnet (`ip addr add 192.168.71.x/24`)
  creates a direct kernel route that hijacks traffic away from the gateway,
  breaking ALL connectivity to that subnet. Remove with `ip addr del`.
- `shutdown /s` from Windows may not fully power-off if Fast Startup is on.
  Verify with `powercfg /a`.
- OpenWrt 22.03 minimal has no `socat`, `bash`, `python3`, or `etherwake`
  in its package repos. Use a statically-compiled C binary instead.
- Magic packet port 9 is standard; some NICs also accept 7.
