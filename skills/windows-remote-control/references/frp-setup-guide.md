# FRP Setup and Management

FRP (Fast Reverse Proxy) tunnels local services through a public server.

## Architecture

```
外网 → frps (server, public IP) → frpc (client, behind NAT) → local service
```

## Config Formats

FRP uses TWO config formats depending on version:

| Version | Server config | Client config | Token syntax |
|---------|--------------|---------------|-------------|
| ≤ 0.51.x | INI (`frps.ini`, `frpc.ini`) | `[common]` section | `token = xxx` |
| ≥ 0.69.x | TOML (`frps.toml`, `frpc.toml`) | flat key=value | `auth.token = "xxx"` |

**Critical**: mixing formats causes silent auth failures. Match the server's format to the clients'.

### INI format (old)
```ini
[common]
bind_port = 10086
token = mysecrettoken
```

### TOML format (new)
```toml
bindPort = 10086
auth.token = "mysecrettoken"
```

## Token Authentication

Always use tokens. Without auth, anyone who discovers the FRP port can register proxies.

1. Generate: `openssl rand -hex 16`
2. Add to server config
3. Add to ALL client configs using matching format
4. Restart server first, then clients

Verify with: `ssh server 'sudo ss -tlnp | grep frps'`

## Client Management

### Linux (systemd)
```bash
sudo systemctl restart frpc
sudo systemctl status frpc
# Config: /etc/frp/frpc.toml
```

### Windows (nssm service)
FRP is often wrapped by nssm (Non-Sucking Service Manager).

**Find config:**
```cmd
reg query HKLM\SYSTEM\CurrentControlSet\Services\frpc-service\Parameters
```

**Common paths:**
- Binary: `C:\Tools\frp_<version>_windows_amd64\frpc.exe`
- Config: `C:\Tools\frp_<version>_windows_amd64\frpc.ini`
- Log: `C:\Tools\frp_<version>_windows_amd64\frpc.log`

**Update binary path:**
```cmd
nssm set frpc-service Application C:\Tools\frp_0.69.1_windows_amd64\frpc.exe
nssm set frpc-service AppDirectory C:\Tools\frp_0.69.1_windows_amd64
```

**Stuck service (STOP_PENDING):**
```cmd
taskkill /f /im frpc.exe
taskkill /f /im nssm.exe
timeout /t 3 /nobreak >nul
sc start frpc-service
```

### Finding config from process
```cmd
# Method 1: service registry
reg query HKLM\SYSTEM\CurrentControlSet\Services /f frp /k

# Method 2: running process
wmic process where "name='frpc.exe'" get commandline

# Method 3: known paths
dir /b C:\Tools\frp_*\frpc.*
```

## Upgrade Procedure

### Server (Linux)
```bash
# Download latest
curl -sLO https://github.com/fatedier/frp/releases/download/v<VERSION>/frp_<VERSION>_linux_amd64.tar.gz
tar xzf frp_*.tar.gz
# Stop old, copy new binary, restart with existing config
sudo killall frps
sudo cp frp_*/frps /home/lighthouse/frp/frps
cd /home/lighthouse/frp && sudo nohup ./frps -c frps.ini > /tmp/frps.log 2>&1 &
```

### Client (Windows via SSH)
```bash
# Download locally, upload via scp
scp frpc.exe <alias>:C:/Tools/frp_<version>_windows_amd64/frpc.exe
# Copy config from old version
ssh <alias> cmd /c "copy /y C:\Tools\frp_old\frpc.ini C:\Tools\frp_new\frpc.ini"
# Update nssm to point to new binary
ssh <alias> cmd /c "nssm set frpc-service Application C:\Tools\frp_new\frpc.exe"
ssh <alias> cmd /c "nssm set frpc-service AppDirectory C:\Tools\frp_new"
# Kill and restart
ssh <alias> cmd /c "taskkill /f /im frpc.exe & taskkill /f /im nssm.exe & timeout /t 3 & sc start frpc-service"
```

**Pitfall**: nssm.exe path on the remote may differ. On the target machine, find it with `where nssm` or check the service registry.

### Client (Linux)
```bash
wget https://github.com/fatedier/frp/releases/download/v<VERSION>/frp_<VERSION>_linux_amd64.tar.gz
tar xzf frp_*.tar.gz
sudo cp frp_*/frpc /usr/local/bin/
sudo systemctl restart frpc
```

## Verification

Check server-side active ports:
```bash
ssh server 'sudo ss -tlnp | grep frps'
```

Expected output shows bind_port + all active proxies. A missing proxy means the client isn't connected (token mismatch, config error, or service not running).

Check server logs for auth failures:
```bash
ssh server 'grep "token" /tmp/frps.log | tail -10'
```

## Common Issues

| Symptom | Cause | Fix |
|---------|-------|-----|
| `register control error: token doesn't match` | Wrong token or format mismatch | Check `token =` vs `auth.token =` |
| Proxy missing from server | Client not connected | Check service status, token format |
| Service STOP_PENDING on Windows | nssm stuck | `taskkill /f /im frpc.exe` then restart |
| Config file write fails via PowerShell | Quoting/escaping | Use `scp` to upload file |
| Old proxy remains after client disconnect | FRP timeout not yet expired | Wait ~5 min for auto-cleanup |
| `section "common" does not exist` | TOML config fed to old INI-only frps | Use INI format or upgrade binary |
| `proxy [name] already exists` | Two clients using same proxy name | Rename one proxy (e.g. `[ssh]` → `[ssh-tablet]`); proxy names must be unique across ALL clients |
