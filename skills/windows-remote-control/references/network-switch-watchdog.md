# Network Switch Watchdog Pattern

When switching WiFi (or any network interface) remotely, the SSH connection drops mid-execution — any fallback logic must survive SIGHUP and run in a different process session.

## Architecture

```
┌─────────────────────────────────────────┐
│  main process (SSH)                     │
│  1. Save current connection state       │
│  2. Launch watchdog (nohup + disown)    │
│  3. Switch to target network            │
│  4. Verify connectivity (ping targets)  │
│  5a. OK → touch /tmp/switch-ok          │
│  5b. FAIL → watchdog triggers rollback  │
└─────────────────────────────────────────┘
```

## Key Techniques

### 1. Watchdog Survivor (outlives SSH disconnect)

```bash
nohup bash -c '
    sleep $TIMEOUT
    if [ -f /tmp/switch-ok ]; then exit 0; fi
    nmcli connection up "$CURRENT_CONN" --timeout 30
' > /tmp/watchdog.log 2>&1 &
WATCHDOG_PID=$!
disown "$WATCHDOG_PID"  # critical — prevents SIGHUP from killing it
```

`nohup` detaches from SIGHUP. `disown` removes the job from the shell's job table so the shell doesn't forward SIGHUP on exit.

### 2. State Capture (before switching)

```bash
STATE_FILE="/tmp/network-switch-state"
echo "CURRENT_SSID=$(iwgetid -r)" > "$STATE_FILE"
echo "CURRENT_CONN=$(nmcli -t -f NAME connection show --active | head -1)" >> "$STATE_FILE"
echo "CURRENT_GW=$(ip route | grep ^default | awk '{print $3}')" >> "$STATE_FILE"
```

### 3. Verification Targets

Ping multiple targets to avoid false positives:
- External DNS: `114.114.114.114` (China Telecom), `223.5.5.5` (AliDNS)
- Local gateway: `192.168.1.1` (modem) or `192.168.37.1` (OpenWrt)
- HTTP test: `curl -s --max-time 5 https://cp.cloudflare.com/generate_204`

### 4. Rollback (multiple attempts)

```bash
for i in 1 2 3; do
    nmcli connection up "$CURRENT_CONN" --timeout 30 2>/dev/null && return 0
    sleep 3
done
```

## Subnet Awareness

Before switching, check if the target network is on a different subnet from the current one. If it is:
- DNS names (`lan.11` domains) won't resolve
- LAN services (Hermes, file shares) on the old subnet become unreachable
- The watchdog state file must be written with raw IPs, not hostnames

## Windows WiFi Limitation

This watchdog pattern cannot enable a Windows WiFi radio that is in a `Software Off` state — the radio toggle belongs to the desktop session (Session 1+), and SSH runs in Session 0. See the WiFi Radio section in SKILL.md for workarounds.
