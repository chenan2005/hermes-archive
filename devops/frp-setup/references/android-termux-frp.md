# FRP on Android/Termux

## DNS workaround for Go binaries (proot)

Go programs on Android cannot resolve domain names because `/etc/resolv.conf` is on a read-only filesystem and doesn't exist. Go falls back to `127.0.0.1:53` which has no DNS service.

### Fix: proot fake filesystem (directory-level)

For extensibility, use directory-level binding so future `/etc` additions (hosts, certificates) work too:

```bash
# 1. Create a local /etc substitute
mkdir -p ~/my-etc
echo "nameserver 8.8.8.8" > ~/my-etc/resolv.conf
echo "nameserver 8.8.4.4" >> ~/my-etc/resolv.conf

# 2. Install proot (if not already)
pkg install proot -y

# 3. Run frpc with proot binding the entire /etc
proot -b ~/my-etc:/etc ~/frp/frpc -c ~/frp/frpc.ini
```

`proot -b` user-space binds a file or directory to another path, visible only to the child process. No root needed. Directory-level binding (`~/my-etc:/etc`) is preferred over file-level (`~/resolv.conf:/etc/resolv.conf`) because it allows adding hosts, SSL certs, etc. later without changing the launch command.

### Alternative: use IP directly

If proot is unavailable, use the server IP instead of domain in frpc config:

```ini
server_addr = 122.51.232.209  # instead of www.bernarty.xyz
```

## Auto-start methods (two layers)

### Layer 1: runit service (preferred — survives Termux backgrounding)

Termux uses runit (runsvdir) as its service supervisor. Register frpc as a supervised service:

```bash
# 1. Create the service directory
mkdir -p /data/data/com.termux/files/usr/var/service/frpc/log

# 2. Write the run script
cat > /data/data/com.termux/files/usr/var/service/frpc/run << 'RUNEOF'
#!/data/data/com.termux/files/usr/bin/sh
exec proot -b ~/my-etc:/etc ~/frp/frpc -c ~/frp/frpc.ini
RUNEOF
chmod +x /data/data/com.termux/files/usr/var/service/frpc/run

# 3. Write the log run script
cat > /data/data/com.termux/files/usr/var/service/frpc/log/run << 'LOGEOF'
#!/data/data/com.termux/files/usr/bin/sh
exec svlogd -tt /data/data/com.termux/files/usr/var/log/frpc
LOGEOF
chmod +x /data/data/com.termux/files/usr/var/service/frpc/log/run
mkdir -p /data/data/com.termux/files/usr/var/log/frpc

# 4. runsvdir picks it up automatically
# Check status:
sv status /data/data/com.termux/files/usr/var/service/frpc
# Expected: "run: ... (pid N) Ns"
```

runit auto-starts when Termux launches (runsvdir runs at startup). No additional boot hooks needed.

### Layer 2: .bashrc fallback (opens Termux → starts frpc)

When using **domain names** (needs proot DNS fix):
```bash
cat >> ~/.bashrc << 'EOF'
# frpc auto-start (proot DNS fix)
if ! pgrep -f "proot.*frpc" > /dev/null 2>&1; then
    nohup proot -b ~/my-etc:/etc ~/frp/frpc -c ~/frp/frpc.ini > ~/frp/frpc.log 2>&1 &
fi
EOF
```

When using **server IP directly** (no DNS resolution needed, no proot):
```bash
cat >> ~/.bashrc << 'EOF'
# frpc auto-start (direct IP, no proot needed)
if ! pgrep -f "frpc -c" > /dev/null 2>&1; then
    nohup ~/frp/frpc -c ~/frp/frpc.ini > ~/frp/frpc.log 2>&1 &
fi
EOF
```

The .bashrc check only runs when a Termux shell is opened. If runit is already managing frpc, .bashrc finds the proot process and skips.

### Which one is running? Checking the state

```bash
# ALL frp-related processes
ps aux | grep frp | grep -v grep

# runit service status
sv status /data/data/com.termux/files/usr/var/service/frpc
```

Three possible outcomes:

| `sv status` output | Processes seen | What's happening |
|---------------------|---------------|------------------|
| `run: frpc: (pid 789) 3600s` | Single proot+frpc pair | runit managing it normally |
| `down: frpc: 5s, normally up, want up` | runsv + svlogd + SEPARATE proot+frpc | runit service died but .bashrc's nohup process is still alive |
| `down: frpc: 5s` | ONLY runsv (no proot) | Both runit and .bashrc have nothing — frpc is fully stopped |

## Stuck reconnection loop (common failure)

### Symptom

After a network change (WiFi disconnect/reconnect, VPN toggle, airplane mode), frpc enters a persistent reconnection loop:
```
2026-06-22 23:17:54 [I] try to connect to server...
2026-06-22 23:18:05 [W] connect to server error: i/o deadline reached
2026-06-22 23:18:25 [I] try to connect to server...
```
Each cycle: connect → wait 10s → timeout → retry. The log fills with repeating pairs, no `login success` message. This can continue for hours.

Despite the log showing failures, the TCP port may actually be reachable from the phone (testable via `bash -c 'echo >/dev/tcp/FRP_SERVER_IP/FRP_PORT' 2>&1`). The old frpc process simply never re-established the connection after the network interruption.

### Fix

```bash
# Stop runit service
sv stop /data/data/com.termux/files/usr/var/service/frpc

# Kill ANY stray frpc processes (proot wrappers + actual binaries)
pkill -f "proot.*frpc"
pkill -f "frpc -c"

# Wait a moment
sleep 1

# Restart clean (either way):
# Via runit:
sv start /data/data/com.termux/files/usr/var/service/frpc

# Or via nohup (if runit is not in use):
nohup proot -b ~/my-etc:/etc ~/frp/frpc -c ~/frp/frpc.ini > ~/frp/frpc.log 2>&1 &

# Monitor — should see "login to server success" within 5s
tail -f ~/frp/frpc.log
```

### Prevention

- The runit service has built-in `RestartSec` (2s) via runsv — it will restart the child if it exits. The issue is that the process DOESN'T exit during the reconnection loop; it keeps retrying. The only "fix" is to kill and restart.
- A cron job could periodically check for the stuck state (`grep -q 'i/o deadline reached' ~/frp/frpc.log` for 5+ minutes old)
- Simplest recovery: if you can SSH into the phone, just run the Fix commands above. If you can't, ask the user to open Termux and run them.

## Pitfall: killing frpc while connected via FRP tunnel

If you SSH into the device through its FRP tunnel (e.g. `ssh -p 30177 user@frps.dom`), and then run `pkill -f "frpc -c"` on the same SSH session, the frpc process dies, the tunnel collapses, and your SSH connection drops with exit code 255. The restart command never runs because the shell is already dead.

**Safe approach**: kill AND restart in one pipeline, then exit SSH immediately:
```bash
ssh -p 30177 user@frps.dom "pkill -f 'frpc -c' 2>/dev/null; sleep 1; nohup ~/frp/frpc -c ~/frp/frpc.ini > ~/frp/frpc.log 2>&1 &"
```
Even this can fail if the `sleep 1` is too short or the SSH session drops before the restart. The **safest** approach is to let the user reopen Termux (where .bashrc auto-start handles it) or send the kill+restart as a background command that exits before the tunnel drops.

## Download ARM64 binary for Android

```bash
# Determine latest version
VER=$(curl -sL https://api.github.com/repos/fatedier/frp/releases/latest | grep -oP '"tag_name":\s*"\K[^"]+')

curl -sLO https://github.com/fatedier/frp/releases/download/${VER}/frp_${VER#v}_linux_arm64.tar.gz
tar xzf frp_${VER#v}_linux_arm64.tar.gz
cp frp_${VER#v}_linux_arm64/frpc ~/frp/
```

## SSH port on Android

Android SSH (Termux) typically runs on non-standard ports (e.g., 8022) because port 22 requires root. Adjust `local_port` accordingly in frpc config.

## File transfer to Android via FRP tunnel

When an Android device exposes SSH through an FRP tunnel (e.g., `bernarty:30205 → android:8022`), transfer files with `scp -P`:

```bash
# From any machine that can reach the FRP server
scp -P 30205 -o StrictHostKeyChecking=accept-new /path/to/file user@frp-server.domain:/data/data/com.termux/files/home/
```

Where:
- `-P 30205` — the FRP server's `remotePort` for this tunnel
- `frp-server.domain` — the FRP server's hostname
- Path — Termux's home is `/data/data/com.termux/files/home/` on Android. Use this exact path; `~/` expands to the wrong directory under SSH.

With StrictHostKeyChecking `accept-new`, the first connection stores the Android device's host key (matches the FRP server host, not the Android device — this is fine for FRP forwarding).

### Transfer to Android Download directory

For files the user wants to access from Android apps (not just Termux), transfer to `/storage/emulated/0/Download/`:

```bash
scp -P 30205 -o StrictHostKeyChecking=accept-new local-file \
  user@frp-server.domain:/storage/emulated/0/Download/
```

This path is visible to file managers and apps like V2RayNG's "import from file" feature. Note the file ownership may be `media_rw` for the `media_rw` group — this is normal for files written to shared storage via ADB/SSH.

### Verification

```bash
ssh -p 30205 -o StrictHostKeyChecking=accept-new user@frp-server.domain "ls -la /data/data/com.termux/files/home/"
```

### Piping content (no SCP)

When scp isn't available or you want a one-liner:

```bash
cat local-file | ssh -p 30205 user@frp-server.domain "cat > /data/data/com.termux/files/home/target-file"
```

This works even when the FRP forwarder is different from the actual SSH target — the pipe goes through the FRP tunnel transparently.

## frpc.ini example (for reference)

```ini
[common]
server_addr = www.bernarty.xyz
server_port = 10086
token = YOUR_TOKEN_HERE

[ssh-android]
type = tcp
local_ip = 127.0.0.1
local_port = 8022
remote_port = 30205
```

The server config (`frps.ini`) for this setup:
```ini
[common]
bind_port = 10086
token = YOUR_TOKEN_HERE
# No allow_ports restriction — remote ports are fully available
```

### frp server runs from user home directory

The frps often runs from a non-standard path like `/home/lighthouse/frp/`. Check with:
```bash
ls -la /proc/$(pgrep frps)/cwd
```
The startup command also shows the config path via `cat /proc/$(pgrep frps)/cmdline`.
