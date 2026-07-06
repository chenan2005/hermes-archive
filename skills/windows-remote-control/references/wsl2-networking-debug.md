# WSL2 Networking: Approaches and Limitations

> **HISTORICAL — WSL2 removed 2026-06-19.** Ubuntu-24.04 was unregistered due to Hyper-V NAT limitations. Future container workloads use Hyper-V VMs with bridged networking. This reference preserved for documentation.

How to make WSL2 services accessible from LAN — and why most approaches fail.

## The Core Problem

WSL2 uses a **NAT'd Hyper-V virtual switch**. The WSL VM gets an IP like `172.21.x.x` on a private network that's only directly reachable from the Windows host (via `localhost` or `127.0.0.1`). From other machines on the LAN, WSL's services are invisible.

## Approaches Tested

### 1. netsh interface portproxy (Default Approach)

```powershell
netsh interface portproxy add v4tov4 listenport=2222 listenaddress=0.0.0.0 connectport=22 connectaddress=<wsl-ip>
netsh advfirewall firewall add rule name="WSL SSH" dir=in action=allow protocol=TCP localport=2222
```

**Result: TCP connects, but SSH protocol gets RST.** `kex_exchange_identification: read: Connection reset by peer` during SSH banner exchange. Raw TCP (nc echo test) works fine — data flows bidirectionally. The RST is SSH-protocol-specific.

**Not caused by:**
- Windows sshd on port 22 (stopping it doesn't help)
- Port number (same behavior on 2222, 22222)
- socat intermediate (same behavior with socat forwarding instead of direct WSL:22)

**Root cause:** Hyper-V firewall's NAT network enforcement. A `New-NetFirewallHyperVRule` for port 2222 shows `EnforcementStatus: NATInboundRuleNotApplicable` — Hyper-V firewall **cannot enforce inbound rules on NAT networks**. External connections forwarded by portproxy arrive at the vSwitch as NAT-inbound, and the vSwitch drops them.

### 2. SSH ProxyCommand (Works Reliably)

```text
Host minipc-wsl
    HostName 127.0.0.1
    User root
    IdentityFile ~/.ssh/id_ed25519
    StrictHostKeyChecking accept-new
    ConnectTimeout 15
    ProxyCommand ssh minipc wsl -d Ubuntu-24.04 -u root -- nc -q 0 localhost 22
```

**Works because:** The connection originates INSIDE WSL (`wsl ... nc localhost 22`). To the vSwitch, this is a local VM-to-VM connection, not external. The SSH pipe flows through the `ssh minipc` session to Windows, then through `wsl` to the `nc` process in WSL.

**Requirements:**
- `netcat-openbsd` (or any `nc`) must be installed in WSL
- `openssh-server` running in WSL
- SSH key in WSL's `/root/.ssh/authorized_keys`
- `minipc` host configured in `~/.ssh/config` to reach Windows sshd

**Note on "tunnel" vs "implementation detail":** From the user's perspective, `ssh minipc-wsl` is a direct connection. The ProxyCommand is an SSH config implementation detail, not an exposed tunnel.

### 3. Route through OpenWrt

```bash
ssh openwrt "ip route add 172.21.224.0/20 via 192.168.71.21"
```

**Result: Connection timed out.** Traffic reaches minipc (confirmed via OpenWrt route table), but Windows doesn't forward to the WSL vSwitch. Even with `Set-NetIPInterface -Forwarding Enabled` and registry `IPEnableRouter=1`, the Hyper-V NAT vSwitch won't accept forwarded external traffic.

### 4. Port Ordering Fix (Avoiding Port 22 Conflict)

Move WSL SSH to port 2222 (was 22), netsh portproxy 2222→WSL:2222.

**Result: Same RST behavior.** Changing the port doesn't bypass the NAT vSwitch limitation. Raw TCP works, SSH protocol fails at the same point.

### 5. Restart Registry Change + Interfaces

`IPEnableRouter=1` + `Set-NetIPInterface -Forwarding Enabled` requires a full system reboot to take effect on some Windows 10 builds. Without reboot, routing changes are not applied.

## Summary

| Approach | SSH | HTTP | Raw TCP | Survives WSL Restart |
|----------|-----|------|---------|---------------------|
| Portproxy | RST during banner | ✅ works | ✅ works | ❌ (IP changes) |
| ProxyCommand | ✅ works | N/A | N/A | ✅ (no port rules) |
| Route via OpenWrt | ❌ timeout | ❌ timeout | ❌ timeout | N/A |
| Direct access from Windows | ✅ (localhost) | ✅ (localhost) | ✅ | N/A |

**Bottom line:** For SSH access to WSL, ProxyCommand is the only reliable approach. For HTTP services, netsh portproxy works because HTTP doesn't trigger the RST issue. For anything SSH-related through portproxy, the RST appears to be a Windows networking limitation at the Hyper-V vSwitch level (`NATInboundRuleNotApplicable`).

## PowerShell Quoting for WSL + SSH

When writing scripts that reference `$_` (PowerShell automatic variable) through a bash SSH command, the `$_` gets interpreted by bash as the last argument of the previous command. Use `.ps1` files (scp + execute) to avoid this.
