# FRP Connection Disconnection Troubleshooting

## Overview

FRP tunnels that disconnect periodically are usually caused by one of three problems:

1. **TCP control connection silently breaks** — a NAT/middlebox (CGNAT or local 光猫) drops the connection tracking state, leaving a half-dead TCP connection. The client's outgoing packets still work but server responses are silently dropped.
2. **DNS resolution fails during reconnect** — frpc uses Go's DNS resolver which has a 10s timeout; if upstream DNS is slow/unreliable, each retry takes 10-16s instead of 1-2s.
3. **Local NAT conntrack table LRU eviction (光猫 WiFi scenario)** — the ISP 光猫's connection tracking table is small and fills up, evicting the FRP control connection entry via LRU. Distinguishable by irregular drop intervals (3-15 min) and no ping loss.

## Diagnostic Flow

### Step 1: Check if frpc process is stable

```bash
systemctl status frpc --no-pager -l
```

Look for: same PID running for days (stable) vs. frequent restarts (crashing). A stable PID means the disconnections are control connection drops, not process crashes.

### Step 2: Collect frpc logs for reconnect pattern

```bash
journalctl -u frpc -n 200 --no-pager
```

Key patterns in frpc logs:

| Log Entry | Meaning |
|-----------|---------|
| `try to connect to server...` | Control connection was lost or dropped |
| `login to server success` → `start proxy success` | Reconnected successfully |
| `connect to server error: lookup X: i/o timeout` | DNS resolution timed out (10s) |
| `connect to server error: dial tcp: i/o timeout` | TCP connection timed out (server unreachable) |

If you see multiple `try to connect` lines within a short span (every 3-20 minutes), the control connection is dropping frequently.

### Step 3: Check frps server logs for the server's perspective

Find the frps process and log file:

```bash
# Find frps
ps aux | grep frp[s]
# Check its working directory
ls -la /proc/$(pgrep frps)/cwd
# Read startup command
cat /proc/$(pgrep frps)/cmdline
# Find log — either redirected in command, journald, or file
# Common: tail -100 /tmp/frps.log
```

Key patterns in frps logs:

| Log Entry | What It Means |
|-----------|---------------|
| `listener is closed: accept tcp [::]:30234: use of closed network connection` | The proxy listener was closed because the control connection dropped. frpc will reconnect and re-register. |
| `failed to send message to work connection from pool: connection write timeout` | **Smoking gun.** The server tried to send data to the frpc client on the control connection, but the TCP write timed out. The TCP connection is in a half-dead state — still open on the client side but not actually routable. |
| `no work connections available, control is closed` | After the write timeout, the server closes the control connection. All proxy listeners for this client are shut down. |
| `tcp proxy listen port [30234]` | frpc reconnected and the proxy is back up. |

### Step 4: Examine the timing pattern

Log the exact timestamps of `try to connect to server` events:

```bash
journalctl -u frpc --since "2 hours ago" 2>&1 | grep "try to connect" | awk '{
  split($3,t,":"); cur=t[1]*60+t[2];
  if (prev) print cur-prev"秒"; prev=cur
}'
```

- **Fixed interval** (every 300s exactly) → likely NAT connection tracking timeout (standard).
- **Variable interval** (3-15 min, irregular) → likely **LRU conntrack eviction**: the local 光猫's NAT table is small and fills up from other devices, kicking out the FRP connection. The key distinction is irregularity — it depends on when OTHER devices create new connections, not on a timer.

### Step 5: tcpdump to confirm unidirectional black hole (smoking gun)

Run ping + tcpdump simultaneously, then wait for the next disconnect:

```bash
# Start monitoring
ping <frps-ip> > /tmp/ping.log &
sudo tcpdump -i wlp1s0 -s 0 -w /tmp/frp-capture.pcap "host <frps-ip>"

# After the next disconnect, check:
tcpdump -r /tmp/frp-capture.pcap -n 2>/dev/null | grep "Flags \[FP\.\]" | tail -10
```

Look for this pattern — **FIN retransmissions** confirm a unidirectional black hole:

```
20:38:42.394  client → server  FIN+PUSH      ← frpc closes the connection
20:38:42.677  client → server  SYN            ← new connection starts immediately
20:38:46.206  client → server  FIN 重传       ← server's FIN-ACK never arrives!
20:39:00.030  client → server  FIN 重传       ← still retransmitting 45 seconds later
```

Interpretation:
- FIN sent successfully = outgoing path works
- **FIN retransmitted** = server's ACK of FIN is being dropped by a NAT device (return path broken)
- New connection SYN-ACK works = fresh conntrack entry is fine
- Ping shows no loss = ICMP takes a different path or is not affected by NAT table exhaustion

This pattern definitively indicates **local 光猫 NAT conntrack table LRU eviction**, not CGNAT timeout.

## Root Cause: CGNAT / Middlebox Half-Dead TCP

### Common scenario: CGNAT drop

The typical client→server path behind CGNAT:

```
frpc → WiFi → 光猫 → OLT → 电信CGNAT → Internet → frps (Tencent Cloud)
```

CGNAT (Carrier-Grade NAT) maintains connection tracking entries for TCP connections. Under certain conditions — port reuse, table congestion, asymmetric routing, or ISP maintenance — the CGNAT silently drops the tracking entry for a connection that appears healthy to both endpoints.

**On the client side:** The TCP socket is still open. Go's net.Conn doesn't immediately detect the failure because no data is being actively sent. The heartbeat (default 30s in frp) might still "succeed" if the OS TCP stack hasn't noticed the breakage yet.

**On the server side:** When the server tries to send data down this broken path, TCP retransmits fail, eventually producing a write timeout. The server correctly concludes the connection is dead and tears down the control connection.

### How to confirm

Check frps logs for this exact sequence:

```
19:54:29  failed to send message to work connection from pool: connection write timeout
19:54:34  listener is closed: accept tcp [::]:30234: use of closed network connection
19:54:34  no work connections available, control is closed
19:54:44  connect to server error: lookup X: i/o timeout   (clientside DNS failure)
19:54:46  tcp proxy listen port [30234]                    (reconnect success)
```

The `connection write timeout` from the server side is the definitive indicator of CGNAT half-dead TCP.

### Local scenario: 光猫 NAT conntrack LRU eviction

When the client machine connects through the ISP 光猫's WiFi (71.x subnet, not OpenWrt PPPoE), the 光猫 itself does NAT for that subnet. The 光猫 has a small connection tracking table. When other devices generate many connections (phones, IoT), the oldest idle entry is **LRU-evicted** — the FRP control connection gets silently dropped.

**Key differences from CGNAT:**

| Feature | CGNAT timeout | 光猫 LRU eviction |
|---------|:-------------:|:-----------------:|
| Drop interval | Fixed (e.g. exactly 300s) | Irregular (3-15 min) |
| Trigger | Timer expiration | Other device creating new connections |
| Ping during drop | May also fail | **Stable (0% loss)** |
| Server-side log | `connection write timeout` | May not log anything (connection never fails on server side) |

**Definitive evidence** comes from running tcpdump on the client (see Step 5 above): FIN retransmissions from the client with no response from the server confirm a unidirectional black hole.

**Fix: bypass the 光猫 NAT** by routing FRP traffic through OpenWrt's PPPoE connection (wired LAN to OpenWrt, or connect to OpenWrt's AP). This eliminates the 光猫 as a NAT layer and uses OpenWrt's larger/more stable conntrack table.

## DNS Resolution Failure

### Why it happens

When frpc reconnects, it resolves `serverAddr` (domain → IP). If the config uses a domain name, the Go DNS resolver queries the system DNS. When the upstream DNS (e.g., 光猫 → ISP DNS) is slow or drops queries, the Go resolver waits ~10s before returning `i/o timeout`.

### Verify DNS health

```bash
# Check configured DNS servers
resolvectl status wlp1s0

# Test direct query
dig +short <frps-domain> @<dns-server>

# Often the issue is: only one upstream DNS server, no fallback
```

### Fix: Eliminate DNS dependency

**Option A (recommended): Use IP address in frpc config**

```toml
serverAddr = "122.51.232.209"    # instead of "www.bernarty.xyz"
serverPort = 10086
```

This is the simplest fix for servers with static public IPs. No DNS, no timeout, reconnect in ~1s.

**Option B: Add /etc/hosts fallback**

```bash
echo "122.51.232.209 www.bernarty.xyz" | sudo tee -a /etc/hosts
```

**Option C: Add backup DNS**

```bash
# Add AliDNS as fallback to systemd-resolved
sudo resolvectl dns wlp1s0 192.168.71.1 223.5.5.5
```

## Fixes

### Immediate: Eliminate DNS (if using domain)

1. Edit `/etc/frp/frpc.toml`, change `serverAddr` from domain to IP
2. Restart frpc: `sudo systemctl restart frpc`

Note: restarting frpc drops all active FRP tunnels. If you're connected via the tunnel you're about to restart, warn the user first.

### Medium-term: Add backup DNS to system DNS resolver

```bash
# Add AliDNS as secondary
nmcli con mod <connection-name> +ipv4.dns 223.5.5.5
```

### Heartbeat/keepalive: fight NAT timeout (caution: not always the right fix)

If connections drop every 3-15 min even after switching to IP direct (no DNS), **do NOT jump to heartbeat config without evidence.** Run tcpdump first (Step 5) to determine the actual failure mode:

- **FIN retransmissions** → local 光猫 LRU eviction → heartbeat helps but doesn't fix root cause; bypass 光猫 NAT is the real solution
- **No FIN retransmissions, ping also drops** → CGNAT timeout → heartbeat is the right fix
- **Server-side `connection write timeout`** → CGNAT half-dead → heartbeat may help

To add aggressive heartbeat config to `/etc/frp/frpc.toml`:

```toml
serverAddr = "1.2.3.4"
serverPort = 10086
auth.token = "your-token"

[transport]
heartbeatInterval = 10
heartbeatTimeout = 30
tcpMuxKeepaliveInterval = 10

[[proxies]]
name = "ssh"
...
```

| Setting | Default | Recommended | Why |
|---------|---------|-------------|-----|
| `heartbeatInterval` | 30s | **10s** | Every 10s refreshes NAT conntrack; default 30s may be longer than CGNAT idle timeout |
| `heartbeatTimeout` | 90s | **30s** | After 3 missed heartbeats, trigger reconnect — faster recovery |
| `tcpMuxKeepaliveInterval` | none (Go default) | **10s** | Keepalive on the multiplexed TCP tunnel, prevents half-dead connection |

After adding: `sudo systemctl restart frpc`

> **Position trap**: `[transport]` must be at the **top level** of the TOML, not inside `[[proxies]]` or any nested block. It configures the control connection, not individual proxy tunnels.

If your frps version also supports it (≥ 0.61), these heartbeat settings cooperate: faster interval means shorter NAT tracking window is survivable. If CGNAT timeout is < 10s even this won't help — consider a tunnel-watchdog cron or SSH -o ServerAliveInterval=15 inside the FRP tunnel.

### Long-term: Monitor connection stability

To confirm or rule out CGNAT as the cause, run a continuous TCP keepalive test:

```bash
# On the frpc machine, check TCP keepalive on the control connection
ss -tnop | grep <frps-ip>:10086
# Check system TCP keepalive settings
sysctl net.ipv4.tcp_keepalive_time net.ipv4.tcp_keepalive_intvl net.ipv4.tcp_keepalive_probes
```

Even with heartbeat config, if CGNAT timeout is very short (< 10s), heartbeats alone won't suffice. In that case, consider:
- A tunnel-watchdog cron that proactively re-registers every few minutes
- SSH -o ServerAliveInterval=15 inside the FRP tunnel for interactive sessions
- Switching from domain to IP and accepting brief reconnections (but reducing DNS failures makes reconnects much faster)

## Pitfalls

- **SSH_CLIENT is misleading through FRP**: When you SSH into a machine through an FRP tunnel, `$SSH_CLIENT` shows `127.0.0.1` (the frpc client connecting to local sshd). But if the machine ALSO has LAN-accessible SSH, `SSH_CLIENT` shows the LAN IP instead. **Do not rely on SSH_CLIENT to determine if a session goes through FRP.** Ask the user directly.

- **frps log flooded by failed auth attempts**: An Android device with wrong token can generate 1-2 log lines per second, making the frps log file huge and grep operations slow. Filter with `grep -v android\|token in login` when searching for specific proxy events.

- **Restarting frpc drops your own SSH if you're inside the tunnel**: When planning a restart, first check if the user's session depends on the tunnel. If yes, either coordinate timing or send the restart command and let the user reconnect.
