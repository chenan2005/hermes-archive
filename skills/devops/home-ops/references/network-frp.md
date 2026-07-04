## 目录

- [frp-setup](#frp-setup)
- [cloudflare-proxy-acceleration](#cloudflare-proxy-acceleration)
- [cloudflare-quick-tunnel](#cloudflare-quick-tunnel)

---



# frp-setup

# frp-setup

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

# cloudflare-proxy-acceleration

# cloudflare-proxy-acceleration

# Cloudflare Proxy Acceleration

## When to use

When a VPS's **direct China→overseas bandwidth is poor** (< 2 Mbps) but the server itself has good bandwidth in its local region. Cloudflare's backbone (edge → tunnel/CDN) bypasses the congested direct China international link.

## Architecture options

### Option A: Cloudflare CDN (orange cloud proxy)
```
Client(V2Ray) → Cloudflare CDN(HTTPS) → VPS:443(VMess+WS+TLS)
```
- Requires DNS on Cloudflare (nameserver migration)
- SSL mode: **Full** (for 443 with self-signed cert) or **Flexible** (for 80 without TLS)
- Speed: typically 25-40 Mbps improvement over direct

### Option B: Cloudflare Tunnel (cloudflared)
```
Client(V2Ray) → Cloudflare edge(HTTPS) → tunnel(QUIC) → cloudflared → localhost:80(VMess+WS)
```
- Independent of DNS provider
- Quick tunnels (`*.trycloudflare.com`) are free but URL changes on restart
- Speed: typically 15-25 Mbps

## Setup Steps

### 1. Server-side: xray backend

Stop x-ui (it overwrites manual config changes):

```bash
sudo systemctl stop x-ui
sudo killall -9 xray xray-linux-amd64
```

Write a clean config with all protocols. Recommended ports:

| Port | Protocol | Purpose |
|------|----------|---------|
| 80 | VMess+WS (no TLS) | Cloudflare Tunnel backend |
| 443 | VMess+WS+TLS (self-signed cert) | Cloudflare CDN backend |
| 40001 | VLESS+Reality | Direct connection (optional) |

Write config as JSON at `/usr/local/x-ui/bin/config.json` and start xray manually:

```bash
sudo /usr/local/x-ui/bin/xray-linux-amd64 -c /usr/local/x-ui/bin/config.json &
```

### 2. Cloudflare DNS setup (Option A only)

1. Add domain to Cloudflare dashboard
2. Change nameservers at registrar to Cloudflare's
3. Add A record with orange cloud (proxied) enabled
4. Set SSL/TLS encryption mode to **Full** or **Flexible**

### 3. Cloudflare Tunnel setup (Option B only)

```bash
# Install
curl -sL https://github.com/cloudflare/cloudflared/releases/download/2024.12.2/cloudflared-linux-amd64 \
  -o /usr/local/bin/cloudflared
chmod +x /usr/local/bin/cloudflared

# Systemd service
cat > /etc/systemd/system/cloudflared.service << 'SERVICEEOF'
[Unit]
Description=Cloudflare Tunnel
After=network.target
[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:80
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
SERVICEEOF

systemctl enable --now cloudflared
```

Get tunnel URL:
```bash
journalctl -u cloudflared --no-pager -n 20 | grep -o 'https://[a-z0-9.-]*\.trycloudflare\.com' | head -1
```

### 4. OpenWrt PassWall: add node

Add a VMess node for the tunnel:

```bash
uci add passwall nodes
uci set passwall.${NODE}.remarks="Seoul-via-Cloudflare"
uci set passwall.${NODE}.type="V2ray"
uci set passwall.${NODE}.protocol="vmess"
uci set passwall.${NODE}.address="<tunnel-hostname>.trycloudflare.com"
uci set passwall.${NODE}.port="443"
uci set passwall.${NODE}.uuid="<uuid>"
uci set passwall.${NODE}.security="auto"
uci set passwall.${NODE}.transport="ws"
uci set passwall.${NODE}.ws_path="/ws-seoul"
uci set passwall.${NODE}.ws_host="<tunnel-hostname>.trycloudflare.com"
uci set passwall.${NODE}.tls="1"
uci set passwall.${NODE}.tls_serverName="<tunnel-hostname>.trycloudflare.com"
uci set passwall.${NODE}.add_mode="1"
uci commit passwall
```

**Critical:** Add tunnel hostname to `/etc/hosts` on OpenWrt:

```bash
echo "104.16.230.132 <tunnel-hostname>.trycloudflare.com" >> /etc/hosts
```

Without this, dnsmasq + chinadns-ng returns SERVFAIL for `*.trycloudflare.com`.

### 5. SNI Routing Injection (KVM-main + Seoul-auth split)

When KVM is the default and Seoul only serves Google auth domains:

1. Let PassWall generate config with KVM as `tcp_node`
2. Inject a unified config at `/tmp/etc/passwall/TCP_SOCKS.json` with:
   - KVM outbound as default
   - Seoul tunnel outbound (VMess+WS+TLS)
   - SNI routing rules (19 Google auth domains → Seoul)
3. Add Google IP CIDRs to `passwall_blacklist` for iptables redirection
4. Restart V2Ray TCP process

Google auth domains for SNI routing:

```
accounts.google.com, accounts.youtube.com, oauth2.googleapis.com,
www.googleapis.com, openidconnect.googleapis.com, securetoken.googleapis.com,
identitytoolkit.googleapis.com, android.googleapis.com, clientauth.googleapis.com,
people.googleapis.com, content-googleapis.com, ssl.gstatic.com, www.gstatic.com,
apis.google.com, play.google.com, myaccount.google.com
```

Also add these to PassWall's `proxy_host` list for dnsmasq-based redirection:

```bash
uci add_list passwall.@global_rules[0].proxy_host="accounts.google.com"
uci commit passwall
```

### 6. Persistence (survive reboots)

Save the unified config template:

```bash
# Generate /tmp/v2ray-tunnel.json on the controller machine
# then scp to OpenWrt:
cat /tmp/v2ray-tunnel.json | ssh root@openwrt.lan.11 'cat > /etc/v2ray-unified.json'
```

Create `/etc/init.d/v2ray-seoul-inject` (START=99) to run after PassWall:

```bash
# Wait 15s for PassWall to fully start
# Copy /etc/v2ray-unified.json over PassWall's TCP_SOCKS.json
# Add Google CIDRs to ipset
# Add tunnel hostname to /etc/hosts
# Restart V2Ray TCP process
```

## Pitfalls

- **x-ui overwrites config:** Stop x-ui (`systemctl stop x-ui`) and run xray manually for custom configs
- **trycloudflare.com DNS:** OpenWrt dnsmasq returns SERVFAIL → add to `/etc/hosts`
- **Tunnel URL changes on restart:** Quick tunnels get random URLs. Check `journalctl -u cloudflared` after restart
- **PassWall restart kills injected config:** Injection must run AFTER PassWall in START order
- **SSL mode mismatch:** Cloudflare Full + self-signed cert works; Flexible expects plain HTTP on origin
- **Google IP ranges change:** CIDRs in blacklist may stale. Supplement with `proxy_host` list

## Verification

```bash
# Connection test
curl -s -o /dev/null -w "YouTube:%{http_code}\n" https://www.youtube.com
curl -s -o /dev/null -w "GoogleAuth:%{http_code}\n" https://accounts.google.com

# Server check
ssh <vps> 'ss -tlnp | grep -E ":(80|443) "'
ssh <vps> 'sudo systemctl is-active cloudflared'

# Routing check
tail -10 /tmp/etc/passwall/TCP.log | grep -E "seoul|izRNaKFP"
```

# cloudflare-quick-tunnel

# cloudflare-quick-tunnel

# Cloudflare Quick Tunnel → 自动修复方案

## 背景

Seoul VPS (alibaba.bernarty.xyz) 直连国内带宽仅 **0.75Mbps**，需要通过 Cloudflare 隧道加速。当前使用 **Cloudflare 快速隧道**（cloudflared tunnel --url），每次重启 URL 随机变化。

由于 DNS 在 DNSPod（未迁到 Cloudflare），无法使用命名隧道或 CDN 代理。解决方案：**检测 + 自动修复**。

## 自动修复架构

```
每30分钟 ─→ OpenWrt cron: 测试 Seoul-Cloudflare 代理是否通
                ├── 通 → 安静退出
                └── 不通 → SSH到Seoul查日志取新URL
                          → 替换 OpenClash config.yaml
                          → 重启核心
                          → 记录日志
```

## 部署步骤

### 1. SSH 密钥（OpenWrt → Seoul）

```bash
# OpenWrt 上生成密钥
ssh openwrt-t "ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N '' -q && cat ~/.ssh/id_ed25519.pub"

# 把公钥加到 Seoul 的 authorized_keys
ssh alibaba "echo '<pubkey>' >> ~admin/.ssh/authorized_keys && chmod 600 ~admin/.ssh/authorized_keys"
```

注意：OpenWrt 使用 Dropbear，不支持 `~/.ssh/config`。SSH 命令必须显式指定 `-i` 参数：

```bash
ssh -i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new admin@alibaba.bernarty.xyz "command"
```

### 2. OpenWrt 上部署自愈脚本

脚本见 `scripts/tunnel-watch.sh`。部署并加入 crontab：

```bash
chmod +x /usr/bin/seoul-tunnel-watch
echo '*/30 * * * * /usr/bin/seoul-tunnel-watch' >> /etc/crontabs/root
/etc/init.d/cron restart
```

脚本每 30 分钟：
1. 通过 OpenClash 代理测试 Seoul-Cloudflare 连通性（curl generate_204）
2. 如果失败，SSH 到 Seoul 查 `/var/log/cloudflared.log` 提取新 URL
3. 替换 OpenClash config.yaml 中的旧 URL
4. 重启 clash 核心
5. 记录日志到 `/var/log/seoul-tunnel.log`

### 3. Seoul VPS cloudflared 服务

cloudflared service 已配置日志写入 `/var/log/cloudflared.log`：

```
ExecStart=/bin/sh -c "/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:80 2>&1 | tee /var/log/cloudflared.log"
```

### 4. OpenClash 中 Seoul 节点配置

```yaml
- name: Seoul-Cloudflare
  type: vmess
  server: <tunnel-url>.trycloudflare.com
  port: 443
  uuid: ac6aa939-156c-452f-a7da-4ddd79b7d5c9
  alterId: 0
  cipher: auto
  tls: true
  servername: <tunnel-url>.trycloudflare.com
  network: ws
  ws-opts:
    path: /ws-seoul
    headers:
      Host: <tunnel-url>.trycloudflare.com
```

该节点会通过 Google-Auth 代理组用于 Google 认证分流。

## 手动修复（等不及自动时）

```bash
# 1. 查 Seoul 上的新 URL
ssh alibaba "sudo cat /var/log/cloudflared.log | grep https:// | grep trycloudflare | tail -1"

# 2. 替换 OpenWrt 上的配置
OLD_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /etc/openclash/config/config.yaml | head -1)
NEW_URL="https://xxx.trycloudflare.com"
sed -i "s|$OLD_URL|$NEW_URL|g" /etc/openclash/config/config.yaml
cp /etc/openclash/config/config.yaml /etc/openclash/config.yaml

# 3. 重启核心
killall clash 2>/dev/null; sleep 2
/etc/openclash/clash -d /etc/openclash -f /etc/openclash/config/config.yaml > /dev/null 2>&1 &
```

## 与其他技能的关系

- `openclash-debug` — 覆盖 OpenClash 通用调试，可引用本技能的自动修复作为 Seoul 节点的维护手段
- `cloudflare-proxy-acceleration` — 覆盖 CDN/隧道方案对比，本技能专攻快速隧道 + OpenClash 侧的自动维护

## 自定义节点管理

添加自定义节点（尤其是 VLESS+Reality）到 OpenClash 的完整步骤、YAML 格式、BusyBox 陷阱和 API 调用方式见 `references/openclash-custom-nodes.md`。

## 故障排查

1. **脚本不执行**: 检查 `/var/log/seoul-tunnel.log` 和 crond 状态
2. **SSH 失败**: 确认 OpenWrt 上的 `~/.ssh/id_ed25519` 权限为 600，公钥在 Seoul 的 authorized_keys 中
3. **隧道 URL 相同仍不通**: 检查 Seoul xray 进程是否在运行
4. **OpenClash 启动后马上退出 (Core Initial Configuration Timeout)**: 检查是否有残留 clash 进程（`killall -9 clash`），以及 `external-ui` 路径是否在 SAFE_PATHS 内（见 `references/openclash-custom-nodes.md` "Clash Meta 兼容性问题"）
5. **OpenClash start 静默跳过 (Disabled)**: 多次启动失败后 OpenClash 进入禁用状态，执行 `uci set openclash.config.enable=1 && uci commit openclash` 恢复
6. **Seoul xray 重启后 VMess 客户端配置丢失**: x-ui 在启动/重启时会从 SQLite 数据库重新生成 `/usr/local/x-ui/bin/config.json`，手动添加的 port 80 VMess 客户端（`clients`）会被覆盖为 `null`。如果需要同时使用 port 40001 (VLESS+Reality, x-ui 管理) 和 port 80 (VMess+WS, CF 隧道后端)，需停止 x-ui 并直接运行 xray（见 `self-hosted-proxy` 技能的 standalone xray 章节）。