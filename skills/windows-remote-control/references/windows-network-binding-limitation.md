# Windows Network Binding Limitation

## The Problem

Applications on Windows cannot reliably "bind to a specific network interface" (e.g., force a proxy client's outbound connections through WiFi while all other traffic goes through Ethernet).

This is not a bug in any specific proxy client — it is a fundamental limitation of Windows' socket API.

## Socket API Comparison

| System | API | Reliability |
|--------|-----|:-----------:|
| **Linux** | `SO_BINDTODEVICE` — kernel-level, binds entire socket to an interface by name | ✅ Decades-stable |
| **macOS** | `IP_BOUND_IF` / `IP_RECVIF` — binds socket to interface by index | ✅ Reliable |
| **Windows** | `IP_UNICAST_IF` / `IPV6_UNICAST_IF` — sets interface index on socket | ⚠️ Partial |

## Why `IP_UNICAST_IF` Is Unreliable

### 1. First-hop only

`IP_UNICAST_IF` tells the network stack "send the first packet through this interface's index." It does **not** pin the entire socket's route lifetime to that interface. Once the packet leaves the host, Windows is free to route subsequent packets in the same connection through a different interface if conditions change.

Compare with Linux's `SO_BINDTODEVICE`, which forces every packet on that socket through the named device, end to end, regardless of routing table changes.

### 2. Interface state transitions break the binding

`IP_UNICAST_IF` refers to the interface by its Windows **LUID** (Locally Unique Identifier, a runtime index). When:
- The interface disconnects and reconnects (WiFi roam, cable unplug/replug)
- The system resumes from sleep
- A Hyper-V virtual switch is created or destroyed

...the LUID may change, or the binding may not survive across the state transition. The socket silently falls back to the default route.

### 3. Synthetic/virtual network adapters cause interference

Windows' networking stack includes many virtual components that do not exist on Linux:

- **Hyper-V virtual switch** (`vEthernet`) — inserts a virtual adapter that intercepts physical interface traffic
- **WSL2** — adds additional NAT/vSwitch layers
- **Mobile hotspot** — Windows can share a WiFi connection through another virtual adapter
- **VPN adapters** — WireGuard, OpenVPN, SSTP all add their own interfaces

`IP_UNICAST_IF` with a physical adapter name/index may not route correctly when virtual adapters are present in the path between the application and the physical NIC.

### 4. mihomo / Clash Verge `interface-name` uses `IP_UNICAST_IF`

This means Clash Verge's `interface-name: WLAN` setting is fundamentally unreliable on Windows. It may work during testing (one-shot connections) but fail after network events (sleep/wake, interface reset, adapter enable/disable).

## The Only Reliable Workaround: Static Routes

```cmd
# Route traffic for specific IPs through a specific interface
route add <target-ip> mask 255.255.255.255 <gateway-on-that-subnet> metric 50
route add <target-subnet> mask 255.255.255.0 <gateway> metric 50

# Make it persistent:
route add -p <target-ip> mask 255.255.255.255 <gateway> metric 50
```

This works at the IP routing layer — **below** the socket API. Every packet to that destination goes through the specified gateway/interface, regardless of which application sent it or how the socket was created.

### Example: force proxy server traffic through WiFi on minipc

The minipc (71.21) has:
- Ethernet → 192.168.71.9 (OpenClash, default route)
- WiFi → 192.168.1.1 (phone hotspot, proxy node gateway)

```cmd
route add -p 43.108.41.245 mask 255.255.255.255 192.168.1.1 metric 50
route add -p 38.47.108.89 mask 255.255.255.255 192.168.1.1 metric 50
route add -p 154.40.40.38 mask 255.255.255.255  192.168.1.1 metric 50
```

Add `-p` for persistence across reboots.

### Pitfall: route to node IP, not domain name

Proxy server addresses in configs are usually domains (e.g., `vmiss.bernarty.xyz`). You must resolve them first to get the IP, then add a route for that IP. If the IP changes (DNS rotation), you need to update the route.

### Pitfall: can't `-p` across subnets without a gateway

`route add` needs a gateway IP on the same subnet as the target interface. Without it, Windows rejects the route. Verify with `ipconfig` that your WiFi interface has a viable gateway.

## Implications for Proxy Client Choice on Windows

| Client | Interface binding | Reliable way to force interface |
|--------|:----------------:|----------------------------------|
| v2rayN (Xray) | ❌ No support | Static route only |
| Clash Verge (mihomo) | `interface-name` via `IP_UNICAST_IF` | Static route (binding is best-effort) |
| sing-box | `bind_interface` via `SO_BINDTODEVICE` (Windows: graceful fallback, not functional) | Static route only |
| Hiddify Next | sing-box kernel, same limitation | Static route only |

**Static routes work regardless of which client you choose.** When interface binding is needed (dual-homed host, proxy on secondary NIC), evaluate the proxy client by other criteria (UI, protocol support, stability under load) and use static routes for the actual interface pinning.
