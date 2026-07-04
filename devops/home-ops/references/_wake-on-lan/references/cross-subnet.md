# Cross-Subnet WoL Strategy

Magic packets are L2 Ethernet broadcasts — they cannot cross IP subnets.
If the sender and target are on different subnets, use a jumpbox.

## Our Setup

```
9950x3d (71.41) ← L2 broadcast ← minipc (71.21, same subnet)
                                  ↑
                                  wake-9950x3d script SSHs here
```

The script `~/.local/bin/wake-9950x3d` SSHs into minipc (on the 71 subnet)
and runs PowerShell with the raw Socket approach.

## Common Failure Modes

1. **`UdpClient` silently drops broadcast** on Windows — must use `Socket` + `EnableBroadcast = $true`
2. **Binding to wrong source IP** — if the jumpbox has multiple NICs, bind explicitly to the subnet's IP
3. **`shutdown /s /f` from command line** can prevent WoL — prefer Windows UI shutdown or `shutdown /s /t 5` without `/f`
4. **Directed broadcast (192.168.71.255) from different subnet** — routers may drop it; use jumpbox
