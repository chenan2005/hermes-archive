---
name: frp-setup
description: Install and configure FRP client (frpc) for port forwarding / 内网穿透 — download, TOML config, systemd service, and verification.
tags: [frp, reverse-proxy, 内网穿透, port-forwarding, systemd]
---

# FRP Client Setup

Install `frpc`, write TOML config, and run as a persistent systemd service.

## Triggers

- "帮我把端口映射到 frp"
- "frp 内网穿透"
- "设置 frpc"
- Any request to expose a local port through an existing FRP server.
- "frp 断连" / "frp 掉线" / "connection keeps dropping" / "隔一段时间就断"
- Any complaint about FRP tunnel disconnecting periodically through SSH

## Prerequisites — gather from user

Before starting, ask for these if not already known:

1. **Server address** — frps hostname or IP
2. **Server port** — frps bind port (default 7000, but often custom)
3. **Auth token** — if the server requires one (common). Ask; don't assume none.
4. **Remote port** — which port on the server to map to. User may not know the available range — that's set server-side in `frps.toml` (`allowPorts`), not visible from client.
5. **Local port** — what to expose (e.g., 22 for SSH)

## Install frpc

```bash
# Get latest version tag
VER=$(curl -sL https://api.github.com/repos/fatedier/frp/releases/latest | grep -oP '"tag_name":\s*"\K[^"]+')
# Download and extract
curl -sL "https://github.com/fatedier/frp/releases/download/${VER}/frp_${VER#v}_linux_amd64.tar.gz" -o /tmp/frp.tar.gz
tar xzf /tmp/frp.tar.gz -C /tmp
# Install binary
sudo cp /tmp/frp_${VER#v}_linux_amd64/frpc /usr/local/bin/frpc
sudo chmod +x /usr/local/bin/frpc
```

## Configuration (TOML format, frp ≥ v0.61)

Write to `/etc/frp/frpc.toml`:

```toml
serverAddr = "server.example.com"
serverPort = 7000
# auth.token = "your-token-here"   # uncomment if needed

[[proxies]]
name = "ssh"
type = "tcp"
localIP = "127.0.0.1"
localPort = 22
remotePort = 30234
```

Multiple proxies: add more `[[proxies]]` blocks.

## Test connection

Before setting up the service, verify the config works:

```bash
timeout 8 /usr/local/bin/frpc -c /etc/frp/frpc.toml
```

Expected output: `login to server success` → `start proxy success`.

## Systemd service

Create `/etc/systemd/system/frpc.service`:

```ini
[Unit]
Description=FRP Client (frpc)
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/frpc -c /etc/frp/frpc.toml
Restart=always
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable frpc
sudo systemctl start frpc
systemctl status frpc
```

## Troubleshooting Frequent Disconnections

See `references/frp-connection-troubleshooting.md` for the full diagnostic flow. Key points:

- **Check both client and server logs**: frpc logs show DNS timeouts (`lookup X: i/o timeout`) and reconnect attempts. frps logs show the server's perspective — look for `connection write timeout` which is the definitive indicator that the TCP control connection went half-dead through CGNAT/middlebox.
- **DNS dependency**: Using a domain for `serverAddr` introduces DNS as an extra failure point during reconnection. For servers with static public IPs, use the IP directly to eliminate this.
- **Timing pattern analysis**: Fixed-interval drops → NAT timeout. Variable-interval drops → CGNAT housekeeping or network instability.
- **Heartbeat keepalive fix**: If connections drop every 3-15 min even with direct IP (no DNS), add `[transport]` with `heartbeatInterval=10, heartbeatTimeout=30, tcpMuxKeepaliveInterval=10` to frpc.toml. See the "Heartbeat/keepalive: fight NAT timeout" section in the reference doc.

## Pitfalls

- **Server firewall**: The FRP server may have a firewall. The remote port must be within the server's `allowPorts` range AND open in its firewall. If the client shows "start proxy success" but you can't connect externally, check the server firewall first.
- **Auth token**: Most frps deployments require a token. If unsure, try without first — the error message is clear ("authorization failed").
- **Adding token to existing server**: Many frps instances run without a token. To add one, create/update the server config (`frps.ini` or `frps.toml`), add `token = <value>` under `[common]` (INI) or `auth.token = "<value>"` (TOML), then restart frps. Add the SAME token to ALL clients simultaneously, or the old clients will be locked out.
- **Token format mismatch across versions**: Even when frps and frpc are the same version, the token key format MUST match the config file format, NOT the frp version:
  - INI config (`.ini`, `[common]`): `token = my-token`
  - TOML config (`.toml`): `auth.token = "my-token"`
  Using `auth.token` in an INI file silently fails — the key is not recognized and the server treats it as "no token provided", rejecting the client with `token in login doesn't match token from configuration`.
- **Proxy name uniqueness**: Every proxy name across ALL clients connecting to the same frps must be unique. Two clients using `[ssh]` will conflict (`proxy already exists`). Use descriptive names like `[ssh-laptop]`, `[ssh-android]`, `[ssh-tablet]`. When adding a SECOND device to an existing server, always check what proxy names are already taken — inspect the client configs or the frps log (grep for `start proxy success`). A name collision silently blocks the second client's tunnel.
- **TOML vs INI**: frp ≥ v0.61 uses TOML (`auth.token = "..."`). Older versions (0.51.x, still common on servers) use INI format (`token = ...` in `[common]`). Mismatch causes `token in login doesn't match token from configuration`. Check the running frps process: `./frps -c frps.ini` = INI, `./frps -c frps.toml` = TOML.
- **INI config format (old frp)**: Same parameters as TOML but different syntax:
  ```ini
  [common]
  server_addr = 1.2.3.4
  server_port = 10086
  token = my-token
  ```
- **Multiple proxies per config**: Each proxy gets its own `[[proxies]]` block in TOML or `[proxy-name]` section in INI. Don't combine them.
- **Binary location**: Install to `/usr/local/bin/frpc` for consistency with the systemd service file. Don't leave it in `/tmp`.
- **Upgrading frps on remote server**: The server's frps runs from a user directory (often `~/frp/`). SCP the new binary to `/tmp` first, then sudo-mv to the target directory (the user may not have write permission). After replacing the binary, kill the old process and restart with the same config file.
- **SSH_CLIENT is misleading when connected through FRP**: When you SSH into a machine through an FRP tunnel, `$SSH_CLIENT` shows `127.0.0.1` (the frpc client connecting to local sshd). But if the machine ALSO has LAN-accessible SSH, `SSH_CLIENT` shows the LAN IP instead. Do not rely on SSH_CLIENT to determine if a session goes through FRP — ask the user directly.
- **Killing frpc drops the SSH session using the same tunnel**: If you're connected to a device via SSH through its FRP tunnel (e.g. `ssh -p 30177 user@frps.dom`), running `pkill -f "frpc -c"` or `pkill -f proot.*frpc` on the target device will kill the frpc process, which terminates the FRP tunnel and drops your SSH connection immediately (exit code 255). Recovery requires the user to manually restart frpc on the device. To avoid this, either:
  - Send the kill + restart as a single command via SSH and exit immediately (the restart happens before the SSH session drops)
  - Or ask the user to run the restart on their end
  - When using layered auto-start (.bashrc / runit), just tell the user to open Termux — the auto-start hook picks up the restart

## Windows frpc as nssm service

On Windows, frpc is often wrapped by nssm (Non-Sucking Service Manager) as a system service. Find it via:
```bash
ssh windows-host cmd /c "sc query state= all | findstr /i frp"
ssh windows-host 'cmd /c "reg query HKLM\SYSTEM\CurrentControlSet\Services\frpc-service\Parameters"'
```

When upgrading the binary, nssm's registry parameters must be updated:
```bash
# These nssm commands run on the Windows machine itself:
nssm set frpc-service Application C:\Tools\frp_NEW_VERSION\frpc.exe
nssm set frpc-service AppDirectory C:\Tools\frp_NEW_VERSION
```

Restarting a stuck service (STOP_PENDING):
```bash
ssh windows-host 'cmd /c "taskkill /f /im frpc.exe 2>nul & taskkill /f /im nssm.exe 2>nul & timeout /t 3 /nobreak >nul & sc start frpc-service"'
```

## Android / Termux

See `references/android-termux-frp.md` for:
- DNS resolution fix via proot (Go binaries can't read Android's `/etc`)
- runit service setup + .bashrc fallback (two-layer auto-start)
- Stuck reconnection loop diagnosis & fix (after WiFi disconnect/reconnect)
- ARM64 binary download, SSH port, file transfer via FRP tunnel
- Example frpc.ini with matching server config
