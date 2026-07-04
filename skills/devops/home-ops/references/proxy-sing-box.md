## 目录

- [sing-box-linux](#sing-box-linux)
- [linux-proxy-client](#linux-proxy-client)

---



# sing-box-linux

# sing-box-linux-client

# sing-box Linux Client

## Overview

Deploy sing-box as a local proxy client on Linux. Supports multiple remote nodes (VMess, VLESS+Reality), DNS anti-pollution via direct upstream, China IP/domain bypass via compiled rule-sets, a Clash API for node switching, and systemd user service for auto-start.

## Prerequisites

- Linux with systemd (user services)
- `systemctl --user` available, `loginctl enable-linger $USER` done (so user services start at boot)
- `jq` installed (`apt install jq`)
- Existing proxy nodes with protocol details (server, port, uuid, tls config, transport)

## Step 1 — Install sing-box binary

```bash
# Download from router (has proxy) and pipe to local machine
ssh root@<router-ip> 'curl -sL -o /tmp/sing-box.tar.gz \
  "https://github.com/SagerNet/sing-box/releases/download/v1.13.14/sing-box-1.13.14-linux-amd64.tar.gz"'
ssh root@<router-ip> 'cat /tmp/sing-box.tar.gz' > /tmp/sing-box.tar.gz
cd /tmp && tar xzf sing-box.tar.gz
sudo mv sing-box-*/sing-box /usr/local/bin/
rm -rf /tmp/sing-box* ~/.config/sing-box # clean old
```

Verify: `sing-box version`

## Step 2 — Directory structure

```
~/.config/sing-box/
├── config.json          # Main configuration
├── ruleset/
│   ├── geoip-cn.srs     # Compiled China IP rule-set
│   └── geosite-cn.srs   # Compiled China domain rule-set
~/.config/systemd/user/
└── sing-box.service     # systemd user service
~/.local/bin/
└── sing-box-ctrl        # Unified management script
~/.local/share/sing-box/
└── cache.db             # Auto-created by experimental.cache_file
```

## Step 3 — Config template (modern format, no deprecation warnings)

### DNS — New format (v1.12+)

```json
"dns": {
  "servers": [
    {
      "tag": "dns",
      "type": "udp",
      "server": "223.5.5.5"
    }
  ],
  "final": "dns",
  "strategy": "prefer_ipv4"
}
```

Key differences from legacy (`"address": "IP"` + `"detour"`):
- Use `"type": "udp"` / `"type": "tcp"` / `"type": "https"` instead of `"address"`
- Use `"server": "IP"` instead of `"address": "IP"`
- `"detour"` field entirely removed in new format
- `"independent_cache"` field removed in 1.14
- `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true` env var no longer needed

### Outbounds — VMess+WS+TLS

```json
{
  "type": "vmess",
  "tag": "VMISS-HK",
  "server": "your-server.com",
  "server_port": 443,
  "uuid": "uuid-here",
  "security": "auto",
  "tls": { "enabled": true, "server_name": "your-server.com" },
  "transport": { "type": "ws", "path": "/ws-path", "headers": { "Host": "your-server.com" } }
}
```

### Outbounds — VLESS+Reality

```json
{
  "type": "vless",
  "tag": "Seoul-VLESS",
  "server": "1.2.3.4",
  "server_port": 40002,
  "uuid": "uuid-here",
  "tls": {
    "enabled": true,
    "server_name": "www.bing.com",
    "utls": { "enabled": true, "fingerprint": "chrome" },
    "reality": {
      "enabled": true,
      "public_key": "base64-public-key",
      "short_id": "hex-short-id"
    }
  }
}
```

### Route — China bypass with local rule-sets

```json
"route": {
  "rules": [
    { "rule_set": "geoip-cn", "outbound": "direct" },
    { "rule_set": "geosite-cn", "outbound": "direct" }
  ],
  "rule_set": [
    {
      "tag": "geoip-cn",
      "type": "local",
      "path": "/home/USER/.config/sing-box/ruleset/geoip-cn.srs"
    },
    {
      "tag": "geosite-cn",
      "type": "local",
      "path": "/home/USER/.config/sing-box/ruleset/geosite-cn.srs"
    }
  ],
  "auto_detect_interface": true,
  "final": "VMISS-HK"
}
```

Use `"type": "local"` for locally compiled rule-sets (immune to GitHub download failures on restricted networks). `"type": "remote"` with `"download_detour"` is also possible but requires GitHub access.

### Clash API — for node switching

```json
"experimental": {
  "cache_file": { "enabled": true, "path": "/home/USER/.local/share/sing-box/cache.db" },
  "clash_api": {
    "external_controller": "127.0.0.1:9090",
    "default_mode": "rule"
  }
}
```

`cache_file` is required for `clash_api` to work. `store_selected` is NOT a valid field inside `cache_file` (causes startup error).

## Step 4 — Build rule-sets from community data

Rule-set `.db` files were **removed** in sing-box 1.12. Compile your own `.srs` files.

### China IP list

```bash
# Download CIDR list
curl -sL -o /tmp/china_ip_list.txt \
  "https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt"

# Create JSON source
python3 -c "
import json
with open('/tmp/china_ip_list.txt') as f:
    ips = [line.strip() for line in f if line.strip()]
source = {'version': 1, 'rules': [{'ip_cidr': ips}]}
with open('/tmp/geoip-cn.json', 'w') as f:
    json.dump(source, f, separators=(',', ':'))
"

# Compile to .srs
sing-box rule-set compile /tmp/geoip-cn.json
mv /tmp/geoip-cn.srs ~/.config/sing-box/ruleset/
```

### China domain list

```bash
# Download domain list (v2fly format: "domain:xxx")
curl -sL -o /tmp/cn_domains.txt \
  "https://raw.githubusercontent.com/v2fly/domain-list-community/release/cn.txt"

# Create JSON with BOTH domain (exact) and domain_suffix (subdomain) matching
# This is critical — bare "domain" only matches exact domain, not www.* subdomains
python3 -c "
import json
with open('/tmp/cn_domains.txt') as f:
    domains = [l.strip().replace('domain:', '') for l in f if l.strip() and not l.startswith('#')]
source = {
    'version': 1,
    'rules': [
        {'domain': domains},                    # exact match: 'baidu.com' → baidu.com
        {'domain_suffix': ['.'+d for d in domains]}  # suffix match: '.baidu.com' → www.baidu.com
    ]
}
with open('/tmp/geosite-cn.json', 'w') as f:
    json.dump(source, f, separators=(',', ':'))
"

sing-box rule-set compile /tmp/geosite-cn.json
mv /tmp/geosite-cn.srs ~/.config/sing-box/ruleset/
```

⚠️ **Pitfall**: Using only `domain` (exact) matching means `www.baidu.com` is NOT matched — all Chinese subdomain traffic goes through the proxy. Always use `domain_suffix` alongside `domain`.

## Step 5 — systemd user service

File: `~/.config/systemd/user/sing-box.service`

```ini
[Unit]
Description=sing-box proxy
Documentation=https://sing-box.sagernet.org
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/sing-box run -c %h/.config/sing-box/config.json
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=default.target
```

Enable and start:

```bash
systemctl --user daemon-reload
systemctl --user enable --now sing-box.service
systemctl --user status sing-box.service
```

## Step 6 — Unified management: sing-box-ctrl

**推荐使用 Python 版（跨平台）:** `windows-proxy-client` skill 的 `scripts/sing-box-ctrl.py`
可同时在 Linux 和 Windows 上运行，自动检测平台差异，共用一份代码。

已弃用的 bash 版 `~/.local/bin/sing-box-ctrl` 保留做兼容，新环境直接用 Python 版。

### Features (Python 版)

| Subcommand | Purpose |
|---|---|
| `python sing-box-ctrl.py` / `help` | Show help |
| `python sing-box-ctrl.py switch` | Show current node + available list |
| `python sing-box-ctrl.py switch <tag>` | Switch to a specific node (hot-reload via SIGHUP on Linux) |
| `python sing-box-ctrl.py start` | Start sing-box service |
| `python sing-box-ctrl.py stop` | Stop sing-box service |
| `python sing-box-ctrl.py restart` | Restart sing-box service |
| `python sing-box-ctrl.py status` | Show runtime status, node, proxy ports |
| `python sing-box-ctrl.py proxy [on|off]` | Toggle system proxy (GUI + CLI). See "System Proxy Toggle" below. |
| `python sing-box-ctrl.py test` | Test current node bandwidth (temp instance, no disruption) |
| `python sing-box-ctrl.py test <tag>` | Test specific node |
| `python sing-box-ctrl.py test --all` | Test all proxy nodes + direct baseline |


### Flat outbound switching (no selector needed)

The `switch` command works with **flat** outbound configs (no selector outbound). It changes `route.final` directly:

```python
route = cfg.setdefault("route", {})
route["final"] = new_node
save_config(cfg)
PLAT.reload(pid)
```

If the config uses a `selector` type outbound, `switch` is compatible with that too (via `current_node` fallback), but the primary mechanism is `route.final`.

### System Proxy Toggle (`proxy` subcommand)

The `proxy on/off/status` subcommand toggles both GUI and CLI proxy settings simultaneously.

**GUI** (gsettings, affects browsers and Electron apps):
```bash
gsettings set org.gnome.system.proxy mode 'manual'
# HTTP -> 127.0.0.1:10881 (mixed port, handles CONNECT)
# SOCKS -> 127.0.0.1:10880
```

**CLI** (sourced env file):
- On → writes `~/.config/proxy-env` with `export http_proxy=...`
- Off → writes `~/.config/proxy-env` with `unset http_proxy ...`
- `~/.bashrc` sources: `[ -f "$HOME/.config/proxy-env" ] && . "$HOME/.config/proxy-env"`

**Current terminal limitation**: Env vars can't propagate from child to parent process. Toggle script always prints:
```
  ⚠ 当前终端环境变量未更新
  请运行:
    source ~/.config/proxy-env
  或直接开一个新终端
```

### Dynamic node list

Node list comes **directly from config.json** — no hardcoded array. The script reads proxy outbounds by filtering out `direct` / `block`:

```bash
list_nodes() {
  jq -r '.outbounds[] | select(.type != "direct" and .type != "block") | .tag' "$CONFIG"
}
```

This means adding/removing a node in config.json automatically updates the list visible to `sing-box-ctrl` — no script edits needed.

### Pitfall: `set -e` in multi-node test loops

⚠️ **Crucial**: When a script with `set -e` calls a function inside a `for` loop, the loop stops at the first function that returns non-zero. This bites `sing-box-ctrl test --all` — if a node's test fails (e.g. Cloudflare 403), the remaining nodes are skipped.

**Fix**: Always append `|| true` when calling a test function in a loop:

```bash
for node in "${nodes[@]}"; do
  _test_one "$node" "$temp_dir" || true   # ← prevents set -e from exiting the loop
done
```

### Pitfall: `exit` vs `return` in helper functions

⚠️ **Crucial**: In `cmd_start()` / `cmd_stop()`, use **`return`** (not `exit`) on early-termination paths. The `restart` subcommand chains `cmd_stop; cmd_start` — if either uses `exit`, the chain breaks mid-way (the whole script terminates before reaching the second call).

### Backward compat (optional)

```bash
ln -s sing-box-ctrl ~/.local/bin/sing-box-switch
```
Linking the old name preserves muscle memory. Both names share the same code.

## Node Bandwidth Testing (`sing-box-ctrl test`)

## TUN Mode (Auto-Route)

### ⚠️ Risk Warning

**TUN mode (`auto_route`) on Linux is fragile.** It modifies system routing tables and nftables rules. On NetworkManager-managed systems (Linux Mint, Ubuntu Desktop), it can cause complete network outages if the config has any version-incompatible fields or if sing-box crashes with nftables rules still active.

If SOCKS5/Mixed port mode covers your use case, **prefer it over TUN**.

### Prerequisites

```bash
# CAP_NET_ADMIN is required for TUN device creation
sudo setcap cap_net_admin+ep /usr/local/bin/sing-box
getcap /usr/local/bin/sing-box  # Verify: cap_net_admin=ep
```

Without this cap, sing-box cannot create the TUN interface even when run via systemd --user.

### Minimum Viable TUN Inbound (sing-box 1.12–1.13)

```json
{
  "type": "tun",
  "tag": "tun-in",
  "interface_name": "sing-box-tun",
  "address": ["198.18.0.1/30"],    ← ARRAY format, NOT "inet4_address" (removed 1.12.0)
  "auto_route": true,
  "strict_route": true,
  "route_exclude_address_set": ["geoip-cn"]
}
```

**Field rules (version-specific):**

| Field | Status | Notes |
|---|---|---|
| `"address": [".../30"]` | ✅ Current (1.10+) | Must be an **array**. `"inet4_address"` removed in 1.12.0. |
| `"auto_route"` | ✅ Current | Creates TUN + routing table (table 2022) |
| `"strict_route"` | ✅ 1.12–1.13 | Adds nftables rules + fwmark bypass. **Required** for preventing routing loops. |
| `"sniff"` / `"sniff_override_destination"` | ❌ Removed 1.13.0 | Causes `legacy inbound fields` fatal. Use route rule actions instead. |
| `"dns_mode": "hijack"` | ❌ 1.14+ only | Causes fatal on 1.13.x. Not available. |

### `strict_route: true` vs `false`

| Setting | fwmark bypass | nftables rules | Result |
|---|---|---|---|
| `true` | ✅ Added | ✅ Added | Sing-box own traffic bypasses TUN. Node connections work. **But** if sing-box crashes, rules remain → full network outage. |
| `false` | ❌ Not added | ❌ Not added | Sing-box own traffic enters TUN → routing loop to node → international traffic hangs. Domestic (direct) works. |

**Chose `true`.** Without it, node connection packets re-enter TUN causing a routing loop.

### `route_exclude_address_set`

```json
"route_exclude_address_set": ["geoip-cn"]
```

In `strict_route: true` mode, this adds iproute2 rules to make Chinese IP traffic bypass TUN entirely. DNS server (223.5.5.5 is a Chinese IP) bypasses TUN → DNS works normally.

**Without this setting**, ALL IPs go through TUN. Domestic traffic still works (sing-box route rules route geosite-cn → direct), but adds extra overhead.

**Naming note**: `route_exclude_address_set` references a rule_set tag (the `tag` field in `route.rule_set[]`), not a file path.

### DNS: DO NOT use fakeip in TUN mode

Adding a fakeip DNS server for TUN mode on Linux Desktop is a common recommendation but caused repeated outages. Specific issues:

1. **`final` cannot be `dns-fakeip`** — sing-box 1.13 rejects `"default server cannot be fakeip"`
2. **DNS rules complexity** — You need `query_type: ["A", "AAAA"]` as a catch-all, but this breaks when non-Chinese domains are accessed through domestic DNS resolvers
3. **System DNS caching mismatch** — systemd-resolved sees fake IPs, caches them, and subsequent connections fail

**Simpler and safer**: Keep DNS unchanged (real DNS only, AliDNS 223.5.5.5). No fakeip. DNS takes the `route_exclude_address_set` bypass so it always resolves correctly. Sing-box's route rules (geosite-cn → direct, rest → proxy) handle everything.

### `route.default_domain_resolver` (required for 1.12+)

```json
"route": {
  "default_domain_resolver": "dns",
  ...
}
```

sing-box 1.12+ requires this field. Without it sing-box outputs:
```
missing `route.default_domain_resolver` or `domain_resolver` in dial fields
```
And refuses to start. Set to the tag of your real DNS server.

### Safety Auto-Rollback Pattern

Since TUN mode can cause complete network loss (and when the network goes down, the LLM agent also loses connectivity), always pair changes with a safety net:

```bash
# 1. Create a rollback script at ~/.hermes/scripts/
cat > ~/.hermes/scripts/sing-box-tun-rollback.sh << 'SCRIPT'
#!/bin/bash
# Uses TCP/HTTP check (ICMP/ping doesn't work through TUN).
CFG_DIR="$HOME/.config/sing-box"
BACKUP="$CFG_DIR/config.json.socks"
TARGET="$CFG_DIR/config.json"
tcp_ping() { timeout 3 bash -c "echo > /dev/tcp/$1/$2" >/dev/null 2>&1; }
http_check() { timeout 5 curl -s -o /dev/null --max-time 5 "$1" >/dev/null 2>&1; }
for round in 1 2 3; do
    ok=false
    tcp_ping 192.168.71.1 80 && ok=true
    http_check http://www.baidu.com && ok=true
    if $ok; then exit 0; fi
    [ "$round" -ge 3 ] && break
    sleep 5
done
if [ -f "$BACKUP" ]; then
    cp "$BACKUP" "$TARGET"
    systemctl --user reset-failed sing-box 2>/dev/null
    systemctl --user restart sing-box 2>/dev/null
fi
SCRIPT

# 2. Schedule BEFORE running tun on
cronjob action=create name=tun-rollback schedule=3m \
  no_agent=true script=sing-box-tun-rollback.sh

# 3. Execute tun on
cd ~/.local/bin && python3 sing-box-ctrl.py tun on

# 4. If network is fine, cancel the cron
cronjob action=list | grep tun-rollback  # get job_id
cronjob action=remove job_id=<id>
```

**⚠️ Important caveats**:
- The rollback process itself causes ~30-120s of network interruption while sing-box closes the TUN inbound and restarts with SOCKS config
- ICMP ping does NOT work through TUN (sing-box routes ICMP to the proxy outbound which doesn't support it). Use **TCP connect** or HTTP/curl for connectivity checks, never ping.
- The rollback cron must be scheduled **before** the `tun on` command executes, not after — you may lose connectivity before the cron is registered.

### Known Failure Modes on Linux Mint / NetworkManager Systems

| Symptom | Likely Root Cause | Fix |
|---|---|---|
| Complete outage after `tun on` | Version-incompatible field (e.g. `dns_mode`, `sniff`) crashed sing-box. nftables rules from `strict_route` remain active despite process death. | **Prevent**: Always validate with `sing-box check -c config.json` before applying. Use safety rollback cron. |
| Complete outage after `tun on` | nftables rules conflict with existing system rules (NetworkManager, firewall, or docker). | Try `strict_route: false` but see routing loop issue above. TUN mode may not work on this system. |
| Domestic works, international fails (000) | Without `strict_route: true`, node connection re-enters TUN → routing loop. | Add `strict_route: true`. |
| ping fails but HTTP works | ICMP routed to proxy outbound, which doesn't support it. Normal. | Don't use ping for connectivity checks. |
| sing-box crashes right after TUN close | TUN inbound takes too long to close connections. | Ignore warning. Avoid rapid tun on/off cycles. |

### TUN Mode Checklist

Before enabling TUN:

1. [ ] `sing-box version` — confirm 1.12–1.13.x (dns_mode is 1.14+)
2. [ ] `getcap /usr/local/bin/sing-box` — has `cap_net_admin=ep`
3. [ ] `sing-box check -c config.json` — TUN-inclusive config passes
4. [ ] Backup exists: `cp config.json config.json.socks`
5. [ ] `route.default_domain_resolver` is set (1.12+ requirement)
6. [ ] Safety rollback cron is scheduled
7. [ ] NO `dns_mode`, NO `sniff`, NO `inet4_address` in config
8. [ ] DNS uses real servers only (no fakeip)

### Quick toggle via sing-box-ctrl (REMOVED July 2026)

The Python `sing-box-ctrl.py` previously had built-in `tun on/off/status` subcommands. After repeated TUN failures on Linux Mint (see Known Failures below), the TUN code was **removed** from the script. The `tun` subcommand is no longer available.

Re-adding TUN support is possible by copying the TUN inbound template and safety rollback pattern above, but all version pitfalls (`dns_mode`, `sniff`, `address` array format) must be respected.

## System Proxy Configuration (Post-TUN)

After TUN mode was abandoned (2026-07-01), the user opted for system-wide proxy based on SOCKS5/Mixed ports. This works reliably with sing-box's built-in auto-routing (geosite-cn/geoip-cn → direct, rest → proxy).

### GUI (Linux Mint Cinnamon / GNOME)

```bash
# Switch from 'none' to 'manual' proxy
gsettings set org.gnome.system.proxy mode 'manual'

# HTTP/S through the mixed port (handles CONNECT tunneling)
gsettings set org.gnome.system.proxy.http host '127.0.0.1'
gsettings set org.gnome.system.proxy.http port 10881
gsettings set org.gnome.system.proxy.https host '127.0.0.1'
gsettings set org.gnome.system.proxy.https port 10881

# SOCKS5
gsettings set org.gnome.system.proxy.socks host '127.0.0.1'
gsettings set org.gnome.system.proxy.socks port 10880

# Bypass local/private networks
gsettings set org.gnome.system.proxy ignore-hosts \
  "['localhost', '127.0.0.0/8', '::1', '192.168.0.0/16', '10.0.0.0/8', '172.16.0.0/12']"
```

Affects: browsers (Firefox, Chrome), Electron apps, Snap/Flatpak that respect gsettings.

### CLI (~/.bashrc)

```bash
# Add to ~/.bashrc for all interactive terminal sessions
export http_proxy=http://127.0.0.1:10881
export https_proxy=http://127.0.0.1:10881
export all_proxy=socks5://127.0.0.1:10880
export HTTP_PROXY=$http_proxy
export HTTPS_PROXY=$https_proxy
export ALL_PROXY=$all_proxy
export no_proxy=localhost,127.0.0.1,::1,192.168.0.0/16,10.0.0.0/8
export NO_PROXY=$no_proxy
```

Affects: curl, wget, pip, npm, git, apt (with Acquire::http::Proxy), and any CLI tool that reads `http_proxy`.

### Why Mixed port for http/https_proxy

The mixed port (10881) accepts both SOCKS5 and HTTP CONNECT. Most CLI tools expect an HTTP proxy URL for `http_proxy`/`https_proxy` — they don't support SOCKS5 URLs. The mixed port handles the HTTP CONNECT protocol for HTTPS destinations, so `https_proxy=http://127.0.0.1:10881` works correctly.

The SOCKS5 port (10880) is set as `all_proxy` for tools that do support SOCKS5 natively.

**LAN access note**: When using `0.0.0.0`, ensure firewall allows incoming connections from LAN subnets. On Linux Mint with ufw:
```bash
sudo ufw allow from 192.168.0.0/16 to any port 10880 proto tcp
sudo ufw allow from 192.168.0.0/16 to any port 10881 proto tcp
```

### Verification

```bash
curl -s -o /dev/null -w "baidu=%{http_code}\n" https://www.baidu.com      # 200 (direct)
curl -s -o /dev/null -w "google=%{http_code}\n" https://www.google.com    # 302 (via proxy)
```

### Risk note

If sing-box stops, all system proxy traffic will fail (connections to 127.0.0.1:10881 time out). The systemd user service has `Restart=on-failure` with a short `RestartSec=5`, so brief blips auto-recover. Extended outages require:
- Browser: shows "proxy server unreachable" — user can temporarily switch to "no proxy" in browser settings
- CLI: `unset http_proxy https_proxy all_proxy` to restore direct access

The `test` subcommand runs bandwidth/latency tests through each proxy node **without disrupting the running proxy**.

### How it works (dual approach)

| Test target | Method | Rationale |
|---|---|---|
| **Proxy node** | `curl --socks5` + Cloudflare 50MB (`speed.cloudflare.com/__down?bytes=52428800`) | Measures international path through proxy — single reliable source, avoids speedtest server selection bias |
| **Direct** | `curl` + Google Chrome CDN (`dl.google.com`, 133MB, domestic edge) | China domestic CDN gives real ISP bandwidth; Ookla speedtest servers from China are often server-side throttled |

### Detailed flow

**For proxy nodes (curl + Cloudflare 50MB):**
1. Extract the target outbound from `config.json` via `jq`
2. **Node existence check**: Before spinning up sing-box, verify the node tag exists in `config.json`'s outbounds (via `list_nodes | grep -qxF "$node"`). Unknown nodes fail immediately (~10ms) instead of waiting 5s for sing-box timeout.
3. Build a minimal sing-box config: SOCKS5 inbound on `127.0.0.1:10882` + single outbound + direct fallback
4. Start a *separate* sing-box process in background (using `-D` for isolated data dir)
5. Wait for proxy readiness (curl SOCKS5 handshake to `www.gstatic.com/generate_204`)
6. **Latency + Jitter**: 10 `curl --socks5` requests measuring `time_starttransfer` (time to first byte — closer to real network RTT than `time_total`). First 3 attempts go to `www.google.com/generate_204` — Google is the preferred target because it's a reliable low-latency endpoint, but is often blocked by China's firewall and only reachable through the proxy. If all 3 fail (3-strike), the script immediately falls back to `http://www.gstatic.com/generate_204` (HTTP, no TLS overhead) for all 10 samples. This avoids wasting 80s on 10 Google timeouts when the endpoint is unreachable. Results are passed to `_lat_stats()`, which insertion-sorts them in awk, trims highest and lowest, then computes trimmed mean (latency) and mean signed deviation (jitter).
7. **Throughput** (bwtest-style): Download Cloudflare 50MB to temp file, timing with `date +%s%N`, capturing HTTP status code (`-w '%{http_code}'`). Then `wc -c < file` for exact bytes, `awk` for Mbps. 60-second timeout (`--max-time 60`). If the downloaded file is ≤ 1000 bytes (indicating a 403 error page or connection failure), the script reports the specific HTTP status code: `403` → "Cloudflare 拒绝（403），IP 被限", `000` → "连接失败", other codes → "Cloudflare 下载失败（HTTP X）".
8. Kill temp sing-box, clean up temp files

The `_lat_stats()` function is shared between proxy and direct tests — a 40-line awk block extracted to avoid duplication:
```bash
_lat_stats() {
  printf '%s\n' "$@" | awk '{
    v[NR]=$1
  } END {
    n = NR
    for (i = 2; i <= n; i++) {
      k = v[i]; j = i - 1
      while (j >= 1 && v[j] > k) { v[j+1] = v[j]; j-- }
      v[j+1] = k
    }
    if (n < 3) {
      s=0; for(i=1;i<=n;i++) s+=v[i]
      a=s/n; d=0
      for(i=1;i<=n;i++) d+=v[i]<a?a-v[i]:v[i]-a
      printf "%.0f %.1f", a*1000, d/n*1000
    } else {
      s=0; for(i=2;i<n;i++) s+=v[i]
      m=n-2; a=s/m; d=0
      for(i=2;i<n;i++) d+=v[i]<a?a-v[i]:v[i]-a
      printf "%.0f %.1f", a*1000, d/m*1000
    }
  }')
}
```
Key: uses manual insertion sort instead of gawk's `asort()` — Ubuntu's default awk is `mawk`, which lacks `asort`.

**For direct test (curl + domestic CDN):**
1. **Latency + Jitter**: Same 10-sample `time_starttransfer` measurement to `http://www.gstatic.com/generate_204` (HTTP — pure RTT, no TLS overhead). Trimmed mean + MSD.
2. **Throughput**: `curl -s --max-time 15 -o /dev/null -w '%{speed_download}' https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb` (133MB file, Google's China CDN edge). Convert B/s to Mbps: `speed * 8 / 1000000`.

The direct test deliberately avoids speedtest-ookla because from within China, Ookla servers (even Shanghai nodes at ~7ms) are often server-side bandwidth-limited — reporting 10-30 Mbps when the real ISP bandwidth is 130-200 Mbps.

### Latency sampling technique

Both proxy and direct tests use the same `awk`-based trimmed-mean calculation:

```awk
# 1. Collect all values into array v[]
# 2. Insertion-sort v[] (compatible with mawk — no gawk asort)
# 3. If >= 3 samples: trim index 1 (min) and index n (max)
# 4. Compute trimmed mean (latency) and MSD (jitter)
# 5. If < 3 samples: fall back to full-sample arithmetic mean + MSD
```

Key choices:
- **`time_starttransfer`** instead of `time_total` — `time_total` includes full HTTP response download time; `time_starttransfer` stops at first byte, much closer to real RTT through the proxy.
- **10 samples** — statistically meaningful jitter; 3 samples is too few (cold DNS outlier skews the average badly).
- **Trim min/max** — removes the cold-start outlier (first request through a new proxy always does DNS upstream) and one-tailed latency spikes.
- **Insertion sort in awk** — avoids dependency on gawk's `asort()`; Ubuntu ships `mawk` as default `awk`.

### Usage

```bash
sing-box-ctrl test                    # Test current node
sing-box-ctrl test Alibaba-Seoul-VLESS  # Test specific node
sing-box-ctrl test --all              # Test all proxy nodes + direct baseline
```

### Output format

```
  节点                 延迟(ms) 抖动(ms)       下载       上传
  ────────────────────── ─────── ─────── ──────────── ────────────
  VMISS-HK                   377    74.5   59.7 Mbps         —
                         Cloudflare CDN (50MB)
  Alibaba-Seoul-VLESS        678   363.8    0.6 Mbps         —
                         Cloudflare CDN (50MB)
  direct                      52    15.2  218.6 Mbps         —
                         Google CDN (国内节点)
```

### Known issues

| Symptom | Likely cause | Workaround |
|---------|-------------|------------|
| Proxy node fails with `✗ Cloudflare 下载失败（HTTP 403）` | Cloudflare is rate-limiting the proxy IP on 50MB downloads | Script detects HTTP 403 via `-w '%{http_code}'`. Try again later or switch to OVH (`proof.ovh.net`) as fallback source. |
| Proxy node fails with `✗ Cloudflare 拒绝（403），IP 被限` | Same as above, but the HTTP 403 is identified by the script's `case` statement and reported with a specific message | The script's HTTP status detection distinguishes: `403` → "IP 被限", `000` → "连接失败", other codes → "下载失败（HTTP X）" |
| Proxy node fails with `✗ 连接失败` | curl returned HTTP 000 (no HTTP response at all) — connection refused, DNS failure, or network timeout | Check if the node is reachable: `curl -s --socks5 127.0.0.1:10880 --max-time 5 https://www.google.com` |
| Proxy node latency > 2000ms or jitter > 500ms | Node is unresponsive or has high packet loss; 10 samples captured a mix of timeouts and successes | Check with `curl --socks5` to a simple endpoint first |
| All proxy nodes fail with `✗ Cloudflare 下载失败` or `✗ 延迟测试超时` | Firewall or connection issue to Cloudflare; or all 10 latency samples timed out | Try `ALL_PROXY=socks5://127.0.0.1:10880 speedtest-ookla` as fallback |
| `direct` shows 10-30 Mbps instead of expected 100+ | You ran the old speedtest-ookla based version (deprecated) | Use `sing-box-ctrl test direct` which now uses Google Chrome CDN |
| Latency numbers seem high (300-900ms for proxy) | Normal — `time_starttransfer` includes SOCKS5 negotiation + remote DNS + TCP + TLS through the proxy. Raw RTT is a subset of this. 10-sample trimmed mean filters out cold-start spikes. |
| Jitter is high (100-500ms) for some nodes | Genuine instability — these are real MSD values from 10 samples (min/max removed). High jitter nodes may drop packets or route inconsistently. |

### Why curl instead of speedtest-ookla

The original implementation used `speedtest-ookla` (official Ookla CLI) for proxy testing and direct testing. This was changed to curl for two reasons:

1. **Ookla server selection is unpredictable** — The CLI auto-selects the lowest-latency server, which varies between runs and between nodes. Different nodes hit different servers, making results incomparable.
2. **Ookla servers in China are throttled** — Direct tests hitting Shanghai Telecom (7ms) reported 10-30 Mbps, while domestic CDN downloads showed 130-200 Mbps matching real-world usage (Bilibili 4K, Baidu Netdisk).
3. **Single reproducible source** — Cloudflare 50MB and Google Chrome CDN give consistent, repeatable results across runs.

curl (`--socks5` for proxy, `--max-time` for timeout) is available everywhere and needs no external service selection.

## Common Pitfalls

### ❌ DNS deadlock at startup
**Symptom**: `lookup domain: context deadline exceeded` or `missing address resolver for server`
**Cause**: DNS server's traffic goes through proxy route, which needs DNS resolution → circular dependency.
**Fix**: Ensure DNS server uses direct path. In new format (type+server), traffic goes via system stack naturally. In legacy format use `"detour": "direct"` with `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true`.

### ❌ Legacy geoip/geosite .db files fail
**Symptom**: `geosite database is deprecated in sing-box 1.8.0 and removed in sing-box 1.12.0`
**Cause**: .db files removed entirely. Use compiled `.srs` rule-sets instead.
**Fix**: Compile rule-sets from community data (Step 4).

### ❌ DNS server deprecated format
**Symptom**: `legacy DNS servers is deprecated` requiring `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true`
**Cause**: Using old DNS format (`"address": "IP"` + `"detour"`).
**Fix**: Use new format (`"type": "udp"`, `"server": "IP"`) — no env variable needed. Also remove `"independent_cache": true` (removed in 1.14). Server-level `"strategy"` must move to DNS top-level.

### ❌ rule_set download fails at startup
**Symptom**: `unexpected status: 404` or `context canceled` when initializing rule-set
**Cause**: Remote rule-set download fails (GitHub blocked, DNS deadlock, wrong URL).
**Fix**: Use `"type": "local"` rule-sets compiled beforehand.

### ❌ `--data-directory` flag does not exist

**Symptom**: `FATAL[0000] unknown flag: --data-directory` when running `sing-box run --data-directory /tmp/dir`

**Cause**: sing-box's `-D` / `--directory` flag sets the *working directory*, not a separate data directory. There is no `--data-directory` flag.

**Fix**: Use `-D /tmp/dir` or `--directory /tmp/dir` instead. This sets the working directory where sing-box stores runtime data (cache.db, etc.).
**Symptom**: `experimental.cache_file.store_selected: json: unknown field`
**Fix**: `store_selected` is NOT a field in `cache_file`. Remove it; persistence is automatic.

### ❌ Mixed up `"final": "dns"` with `"final": "VMISS-HK"`
The DNS section also has a `"final"` field (selects which DNS server when no rule matches). Keep it as `"final": "dns"` to use the direct DNS server for all queries. The route section's `"final"` selects the default proxy outbound. They're independent.

### ❌ geosite-cn domain exact-match bypasses most Chinese traffic
**Symptom**: Chinese sites load slowly through proxy despite having geosite-cn rule.
**Cause**: Using only `"domain": ["baidu.com"]` (exact match) — matches only `baidu.com`, NOT `www.baidu.com`.
**Fix**: Always use both `domain` (exact) and `domain_suffix` (prefix with `.` for subdomain matching):
```json
"rules": [
  {"domain": ["baidu.com"]},
  {"domain_suffix": [".baidu.com"]}
]
```

### ❌ `set -e` stops multi-node test loop on first failure
**Symptom**: `sing-box-ctrl test --all` exits early after one node fails, skipping remaining nodes.
**Cause**: `set -e` at the top of the script propagates the function's non-zero return.
**Fix**: Append `|| true` to the function call inside the for loop:
```bash
_test_one "$node" "$temp_dir" || true
```

### ❌ Ookla speedtest misleading results from China

**Symptom**: `speedtest-ookla` reports 10-30 Mbps, but real-world experience (Bilibili 4K, Baidu Netdisk) shows 100+ Mbps.

**Cause**: From within China, Ookla speedtest servers (even Shanghai nodes at 7ms latency) are often server-side bandwidth-limited or peak-hour congested. The 10-30 Mbps reflects the speedtest server's quota, not the user's real ISP bandwidth.

**Fix**: For direct (non-proxy) bandwidth testing, download from a domestic CDN instead:
- Google Chrome CDN: `https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb` (133MB, Google's China edge, typically 180-200 Mbps)
- VS Code (Azure CDN): `https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64` (199MB, Microsoft's China CDN, typically 130-170 Mbps)

`sing-box-ctrl test direct` and `sing-box-ctrl test --all` already use this approach.

### ❌ proxy env vars break sing-box restart API calls

**Symptom**: After modifying sing-box config, restarting the service causes network outage — all API calls (including the restart command itself) fail because the shell's `http_proxy`/`https_proxy` env vars still point to the now-dead sing-box SOCKS5/Mixed port.

**Cause**: When `http_proxy=http://127.0.0.1:10881` is set, curl/wget and even systemctl communication go through the proxy. During restart, sing-box shuts down → proxy port closes → all proxy-routed commands hang/error → restart itself gets stuck.

**Fix**: Always unset ALL proxy env vars before modifying or restarting sing-box:
```bash
unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY all_proxy ALL_PROXY
systemctl --user restart sing-box
```
After restart completes, re-source the proxy env: `source ~/.config/proxy-env` or use the `proxy on` function.

### ❌ rule-set initialization slow warning
**Symptom**: `WARN router: initialize rule-set take too much time to finish!`
**Cause**: Large rule-sets (7000+ CIDR + 6000+ domains x 2) take extra time to load.
**Impact**: Harmless warning — service starts fine. Ignore it.

## Debugging & Verification

### Verify rule-set contents

```bash
# Decompile .srs to inspect rules (outputs to <name>.json by default)
cd ~/.config/sing-box && sing-box rule-set decompile ruleset/geosite-cn.srs

# Check what's inside
python3 -c "
import json
d = json.load(open('ruleset/geosite-cn.json'))
rules = d.get('rules', [])
for r in rules:
    for k, v in r.items():
        print(f'{k}: {len(v)} entries')
        if len(v) > 0: print(f'  sample: {v[0]}')
"
```

Use this to confirm geosite-cn has both `domain` and `domain_suffix` keys.

### Test if China bypass actually works

```bash
# Time a Chinese site through proxy vs direct
time curl -s --socks5 127.0.0.1:10880 -o /dev/null https://www.baidu.com
time curl -s --no-proxy -o /dev/null https://www.baidu.com
```

If proxy path is significantly slower, the geosite-cn rule is not matching subdomains.

### SOCKS5 vs Mixed port

| Port | Type | Purpose |
|------|------|---------|
| `127.0.0.1:10880` | SOCKS5 only | Legacy clients. Change to `0.0.0.0:10880` for LAN access. |
| `127.0.0.1:10881` | Mixed (SOCKS5 + HTTP CONNECT) | Universal. Change to `0.0.0.0:10881` for LAN access. |
|------|------|---------|
| 127.0.0.1:10880 | SOCKS5 only | Legacy clients that only support SOCKS5 |
| 127.0.0.1:10881 | Mixed (SOCKS5 + HTTP CONNECT) | Universal, accepts both SOCKS5 and HTTP proxy requests |

Mixed port is more convenient for browsers (can be set as HTTP proxy). Both route through the same engine.

## Testing node connectivity

```bash
# Basic test
curl -s --max-time 15 --socks5 127.0.0.1:10880 -o /dev/null -w "%{http_code}\n" https://www.google.com

# Bandwidth test — curl through SOCKS5 to Cloudflare 50MB
curl -s --socks5 127.0.0.1:10880 -o /dev/null -w "%{speed_download}\n" \
  "https://speed.cloudflare.com/__down?bytes=52428800"

# Bandwidth test — curl through SOCKS5 via temp instance
sing-box-ctrl test
```

## Adding a New Node

1. Add the outbound block to `outbounds[]` in config.json
2. `systemctl --user restart sing-box`
3. Verify with `curl -s --socks5 127.0.0.1:10880 https://www.google.com`

No script to update — `sing-box-ctrl` reads the node list dynamically from `outbounds[]` (filtering out `direct` / `block`).

## Updating Rule-sets (weekly)

Schedule a cron to refresh:

```bash
# ~/.config/systemd/user/sing-box-update-rules.timer + .service
# Or use hermes cronjob action='create'
```

The cron should:
1. Download fresh IP list + domain list
2. Compile new .srs files
3. `systemctl --user restart sing-box`

# linux-proxy-client

# linux-proxy-client

# Linux Proxy Client Deployment (sing-box)

## 适用场景
- Linux 机器直连光猫（无路由器翻墙），需要本地 sing-box 做代理
- sing-box v1.13+ 后端运维（配置文件管理、节点切换、DNS策略）
- 替代 Clash GUI，纯 CLI 管理

---

## 1. 安装 sing-box

```bash
# 从 GitHub Releases 下载 Linux amd64
curl -sL -o /tmp/sing-box.tar.gz "https://github.com/SagerNet/sing-box/releases/download/v1.13.14/sing-box-1.13.14-linux-amd64.tar.gz"
cd /tmp && tar xzf sing-box.tar.gz
sudo cp sing-box-*/sing-box /usr/local/bin/
rm -rf /tmp/sing-box*
```

**如果本机网络无法访问 GitHub（GFW 阻断）：**
通过有翻墙能力的机器（OpenWrt 路由器等）下载后 scp/cat 传输：
```bash
# 在路由器上下载
ssh root@openwrt 'curl -sL -o /tmp/sing-box.tar.gz "https://github.com/SagerNet/sing-box/releases/download/v1.13.14/sing-box-1.13.14-linux-amd64.tar.gz"'

# 传回本机
ssh root@openwrt 'cat /tmp/sing-box.tar.gz' > /tmp/sing-box.tar.gz
cd /tmp && tar xzf sing-box.tar.gz
sudo cp sing-box-*/sing-box /usr/local/bin/
```

---

## 2. ⚠️ sing-box v1.13+ 版本兼容性

| 问题 | 症状 | 修复 |
|---|---|---|
| `legacy DNS servers` 废弃 | `FATAL: legacy DNS servers is deprecated` | 设 `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true` 环境变量 |
| `dns` outbound 被移除 | `outbounds[N]: dns outbound is deprecated in 1.11, removed in 1.13` | 删除 `{type: "dns"}` outbound + 相关 route rule |
| `cache_file` 迁移 | `cache_file and related fields in Clash API is deprecated` | `store_selected` 移出 `clash_api`，用 `experimental.cache_file.enabled: true` |
| geosite/geoip 数据库移除 | geosite database is deprecated in 1.8.0 and removed in 1.12.0 | 用 rule_set 格式（remote JSON 在线下载）替代旧 .db 文件 |
| DNS server detour 字段废弃 | outbound DNS rule item is deprecated | 设 ENABLE_DEPRECATED_OUTBOUND_DNS_RULE_ITEM=true |
| store_selected 不在 cache_file 中 | json: unknown field store_selected | store_selected 只在 clash_api 下有效，不在 experimental.cache_file 中 |
| sing-box --version 返回错误 | Error: unknown flag: --version | version 在 v1.13+ 是子命令非 flag：sing-box version |

**推荐做法：在 systemd 服务中设两个 env 变量延续 v1.13 兼容性，v1.14 前迁到新格式：**

```ini
[Service]
Environment=ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true
Environment=ENABLE_DEPRECATED_OUTBOUND_DNS_RULE_ITEM=true
```

---

## 3. DNS 陷阱

### 3a. DNS 死锁问题
如果远程 DNS server 使用 `https://dns.google/dns-query`，需要用 `address_resolver` 指定一个能解析 `dns.google` 的本地 DNS：

```json
{
  "tag": "remote-dns",
  "address": "https://dns.google/dns-query",
  "address_resolver": "local-dns",
  "strategy": "prefer_ipv4"
}
```

但若本地网络（光猫直连）也无法解析 `dns.google`，则出现 DNS 死锁。**解决方案：全程用国内 DNS（223.5.5.5 AliyunDNS），不走远程 DNS。**

### 3b. rule_set 下载死锁
`rule_set` 使用 `download_detour: "direct"` 从 GitHub 下载 JSON 规则，但 GitHub 从国内网络直连不可达。**解决方案：**
- 初次配置跳过 `rule_set`，只在路由可达的网络才启用（如通过 5G 热点）
- 或通过有翻墙能力的机器下载规则文件后本地引用

### 3c. 推荐配置（国内直连 DNS + 本地 rule_set 分流，新格式）

**版本注意**：sing-box v1.12+ 弃用了旧 DNS 格式（`"address"` + `"detour"`）。必须使用新格式（`"type": "udp"` + `"server": "IP"`），不再需要 `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS` 环境变量。

```json
{
  "dns": {
    "servers": [
      {
        "tag": "dns",
        "type": "udp",
        "server": "223.5.5.5"
      }
    ],
    "final": "dns",
    "strategy": "prefer_ipv4"
  }
}
```

**关键变化（对比旧格式）：**
- `"address": "223.5.5.5"` → `"type": "udp"` + `"server": "223.5.5.5"`
- `"detour": "direct"` → 移除（新格式 DNS 查询直接走系统网络栈，不再需要显式指定）
- `"independent_cache": true` → 移除（1.14 起删除，缓存策略自动以传输名称作键）

AliyunDNS 从国内网络能同时正确解析国内外域名，避免 DNS 死锁。

### 3d. 本地 rule_set 生成（GitHub 不可达时的方案）

当 VM 网络无法访问 GitHub 时（光猫直连、GFW 阻断），不能用 `type: "remote"` 下载规则。解决：从其他开放源拉取中国 IP CIDR + 域名列表，本地编译为 `.srs` 文件。

```bash
mkdir -p ~/.config/sing-box/ruleset

# 1. 中国 IP 列表（17mon）
curl -s -o ~/.config/sing-box/ruleset/china_ip_list.txt \
  "https://raw.githubusercontent.com/17mon/china_ip_list/master/china_ip_list.txt"

# 2. 中国域名列表（v2fly domain-list-community）
curl -s -o ~/.config/sing-box/ruleset/cn_domains.txt \
  "https://raw.githubusercontent.com/v2fly/domain-list-community/release/cn.txt"

# 3. 编译规则源（JSON → .srs）
python3 -c "
import json
with open('ruleset/china_ip_list.txt') as f:
    ips = [line.strip() for line in f if line.strip()]
with open('ruleset/geoip-cn.json', 'w') as f:
    json.dump({'version': 1, 'rules': [{'ip_cidr': ips}]}, f, separators=(',', ':'))
"
with open('ruleset/cn_domains.txt') as f:
    domains = [line.strip().replace('domain:', '') for line in f if line.strip() and not line.startswith('#')]
# ⚠️ 必须含 domain + domain_suffix 双重匹配!
# domain('baidu.com') 只精确匹配裸域, domain_suffix('.baidu.com') 才匹配子域
source = {'version': 1, 'rules': [
    {'domain': domains},
    {'domain_suffix': ['.' + d for d in domains]}
]}
with open('ruleset/geosite-cn.json', 'w') as f:
    json.dump(source, f, separators=(',', ':'))
"

# 4. compile 生成 .srs 二进制
cd ~/.config/sing-box
sing-box rule-set compile ruleset/geoip-cn.json
sing-box rule-set compile ruleset/geosite-cn.json
# 产物：ruleset/geoip-cn.srs, ruleset/geosite-cn.srs

# 5. 清理源文件（.srs 保留）
rm -f ruleset/*.txt ruleset/geoip-cn.json ruleset/geosite-cn.json
```

**在配置中引用：**
```json
"rule_set": [
  { "tag": "geoip-cn", "type": "local", "path": "/home/chenan/.config/sing-box/ruleset/geoip-cn.srs" },
  { "tag": "geosite-cn", "type": "local", "path": "/home/chenan/.config/sing-box/ruleset/geosite-cn.srs" }
]
```

**优势**：零外部依赖，离线可用，无 DNS 死锁。更新时重新编译即可。

---

## 4. 完整配置骨架

```json
{
  "log": { "level": "warn" },
  "dns": {
    "servers": [
      { "tag": "dns", "type": "udp", "server": "223.5.5.5" }
    ],
    "final": "dns",
    "strategy": "prefer_ipv4"
  },
  "inbounds": [
    { "type": "socks", "tag": "socks-in", "listen": "127.0.0.1", "listen_port": 10880 },
    { "type": "mixed", "tag": "mixed-in", "listen": "127.0.0.1", "listen_port": 10881 }
  ],
  "outbounds": [
    // 节点配置（见 §5）
    { "type": "direct", "tag": "direct" },
    { "type": "block", "tag": "block" }
  ],
  "route": {
    "rules": [
      { "rule_set": "geoip-cn", "outbound": "direct" },
      { "rule_set": "geosite-cn", "outbound": "direct" }
    ],
    "rule_set": [
      { "tag": "geoip-cn", "type": "local", "path": "/home/chenan/.config/sing-box/ruleset/geoip-cn.srs" },
      { "tag": "geosite-cn", "type": "local", "path": "/home/chenan/.config/sing-box/ruleset/geosite-cn.srs" }
    ],
    "auto_detect_interface": true,
    "final": "VMISS-HK"
  },
  "experimental": {
    "cache_file": { "enabled": true, "path": "/home/chenan/.local/share/sing-box/cache.db" },
    "clash_api": {
      "external_controller": "127.0.0.1:9090",
      "default_mode": "rule"
    }
  }
}
```

**注意**：`rule_set` 可以自由组合——没有分流需求时整个 `route.rules` + `route.rule_set` 块可以省略。两种模式都支持：
- **全部走代理**（最简单）：去掉 `route.rules` 和 `route.rule_set`，所有流量经 `route.final`
- **分流模式**（节省 VPS 带宽）：本地 rule_set 做大陆直连，其余走代理

---

## 5. 节点配置模板

### VLESS + Reality
```json
{
  "type": "vless",
  "tag": "Alibaba-Seoul-VLESS",
  "server": "43.108.41.245",
  "server_port": 40002,
  "uuid": "a5fa1889-1316-4115-a866-96c8f30523ef",
  "tls": {
    "enabled": true,
    "server_name": "www.bing.com",
    "utls": { "enabled": true, "fingerprint": "chrome" },
    "reality": {
      "enabled": true,
      "public_key": "...",
      "short_id": "a1b2c3d4"
    }
  }
}
```

### VMess + WebSocket + TLS
```json
{
  "type": "vmess",
  "tag": "VMISS-HK",
  "server": "vmiss.bernarty.xyz",
  "server_port": 443,
  "uuid": "...",
  "security": "auto",
  "tls": { "enabled": true, "server_name": "vmiss.bernarty.xyz" },
  "transport": {
    "type": "ws",
    "path": "/ws-vmiss",
    "headers": { "Host": "vmiss.bernarty.xyz" }
  }
}
```

---

## 6. systemd 用户服务

```ini
[Unit]
Description=sing-box proxy
Documentation=https://sing-box.sagernet.org
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/sing-box run -c %h/.config/sing-box/config.json
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
LimitNOFILE=65535

[Install]
WantedBy=default.target
```

```bash
# 部署
mkdir -p ~/.config/systemd/user/
cp sing-box.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now sing-box.service
# 查看状态
systemctl --user status sing-box.service
# 查看日志
journalctl --user -u sing-box.service -n 50 --no-pager
```

---

## 7. 统一管理脚本：sing-box-ctrl

> **注意：** 现推荐使用跨平台 Python 版（见 `windows-proxy-client` 技能的 `scripts/sing-box-ctrl.py`），Linux/Windows 通用，功能更完整（含 `test` 测速子命令和 `proxy` 系统代理开关）。



替代旧版 `sing-box-switch`，增加 start/stop/restart/status 子命令，节点列表从 config.json 动态读取。

```bash
#!/bin/bash
# ~/.local/bin/sing-box-ctrl
set -e

CONFIG="$HOME/.config/sing-box/config.json"

list_nodes() {
  jq -r '.outbounds[] | select(.type != "direct" and .type != "block") | .tag' "$CONFIG"
}
current_node() { jq -r '.route.final // "?"' "$CONFIG" 2>/dev/null; }
pid_of() { pgrep -x "sing-box" 2>/dev/null || true; }

case "${1:-}" in
  help|--help|-h|"")
    echo "sing-box-ctrl switch|start|stop|restart|status|help" ;;
  switch)
    shift; local cur="$(current_node)"
    if [ $# -eq 0 ]; then
      echo "Current: $cur"
      while IFS= read -r n; do echo "  $([ "$n" = "$cur" ] && echo → || echo " ") $n"; done < <(list_nodes)
    else
      local target="$1" found=0
      while IFS= read -r n; do [ "$n" = "$target" ] && found=1 && break; done < <(list_nodes)
      [ "$found" -ne 1 ] && { echo "未知节点 '$target'"; exit 1; }
      jq ".route.final = \"$target\"" "$CONFIG" > "${CONFIG}.tmp" && mv "${CONFIG}.tmp" "$CONFIG"
      kill -HUP "$(pid_of)" 2>/dev/null || true; sleep 1
      echo "已切换 → $target"
    fi ;;
  start) systemctl --user start sing-box.service; sleep 2
    [ -n "$(pid_of)" ] && echo "已启动" || echo "启动失败" ;;
  stop) systemctl --user stop sing-box.service; sleep 1
    [ -z "$(pid_of)" ] && echo "已停止" || kill -9 "$(pid_of)" 2>/dev/null ;;
  status)
    echo "状态: $([ -n "$(pid_of)" ] && echo "运行中" || echo "已停止")"
    echo "节点: $(current_node)" ;;
  restart) systemctl --user restart sing-box.service; sleep 2
    [ -n "$(pid_of)" ] && echo "已重启" || echo "重启失败" ;;
  *) echo "未知子命令"; exit 1 ;;
esac
```

```bash
chmod +x ~/.local/bin/sing-box-ctrl
# 使用
sing-box-ctrl              # 帮助
sing-box-ctrl switch       # 查看当前节点+列表
sing-box-ctrl switch VMISS-HK  # 切到香港
sing-box-ctrl start        # 启动
sing-box-ctrl stop         # 停止
sing-box-ctrl status       # 状态
sing-box-ctrl restart      # 重启
sing-box-ctrl proxy on     # 开启系统代理（GUI gsettings + CLI env）
sing-box-ctrl proxy off    # 关闭系统代理
sing-box-ctrl proxy        # 查看代理状态
```



`sing-box-ctrl proxy on/off` 切换系统级代理设置，同时作用于：
- **GUI**：通过 `gsettings` 设置 Cinnamon/GNOME 系统代理（HTTP 127.0.0.1:10881 / SOCKS5 127.0.0.1:10880）
- **CLI**：写入 `~/.config/proxy-env` 文件，新终端自动 `source` 加载

**注意：** 环境变量不能从子进程传给父 shell。切换后当前终端需要手动 `source ~/.config/proxy-env` 才能生效。

```bash
~/.bashrc 中的加载逻辑：
if [ -f "$HOME/.config/proxy-env" ]; then
    . "$HOME/.config/proxy-env"
fi
```

---

## 8. 验证测试

```bash
# 基本连通测试
curl -s --max-time 15 --socks5 127.0.0.1:10880 -o /dev/null -w "%{http_code}" https://www.google.com
curl -s --max-time 15 --socks5 127.0.0.1:10880 -o /dev/null -w "%{http_code}" https://x.com

# 带宽测试（用公开源，不用自建 VPS）
curl -s --max-time 300 --socks5 127.0.0.1:10880 -r 0-209715199 -o /dev/null -w "%{http_code}" https://proof.ovh.net/files/1Gb.dat
# 或用 speedtest-cli
ALL_PROXY=socks5://127.0.0.1:10880 speedtest --accept-license --accept-gdpr
```

---

## 10. 运维命令

| 操作 | 命令 |
|---|---|
| 查看状态 | `systemctl --user status sing-box.service` |
| 查看日志 | `journalctl --user -u sing-box.service -n 50 --no-pager` |
| 重启 | `systemctl --user restart sing-box.service` |
| 停止 | `systemctl --user stop sing-box.service` |
| 校验配置 | `ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true sing-box check -c ~/.config/sing-box/config.json` |
| 热重载 | `systemctl --user reload sing-box.service` 或 `kill -HUP $(pgrep -x sing-box)` |

---

## 9. TUN 模式陷阱（auto_route）

> **⚠️ 不推荐使用 TUN 模式。** 以下为失败经验记录，如果日后必须 TUN，必须先理解这些坑。

### 9a. sing-box v1.13.x 兼容性

| 废弃字段 | 替代 | 说明 |
|---|---|---|
| `inet4_address: "198.18.0.1/30"` | `address: ["198.18.0.1/30"]` | 1.12+ 改为数组 |
| `sniff: true` (在 inbound 中) | 移入 route actions | 1.13 中已移除 |
| `dns_mode: "hijack"` | 无替代（1.14+ 才有） | 1.13 中不识别，会崩溃 |
| `route.default_domain_resolver` | 需要显式设置 | 1.12+ TUN + fakeip 必须 |

### 9b. 断网风险（核心）

TUN + `auto_route` + `strict_route` 在 Linux 上依赖 **nftables** 规则做流量标记和绕过，容易导致：

1. **sing-box 崩溃后 nftables 规则残留** → 全部流量黑洞，手动停 sing-box 也无法恢复，必须清 nftables
2. **DNS 配置错误** → fakeip/真实 DNS 配置不当 → 域名解析失败 → 所有网络请求超时
3. **路由循环** — 代理节点出站连接也走 TUN → 死循环
4. **ICMP 不支持** — ping 走 TUN 后被路由到代理 outbound → 代理不支持 ICMP → ping 全部失败

### 9c. 如果必须 TUN（最低安全配置）

```json
{
  "type": "tun",
  "tag": "tun-in",
  "interface_name": "sing-box-tun",
  "address": ["198.18.0.1/30"],
  "auto_route": true,
  "strict_route": true,
  "route_exclude_address_set": ["geoip-cn"]
}
```

同时：
- 不加 fakeip DNS（保持原有 type:udp+server 格式）
- 不加 `dns_mode`（1.13 不支持）
- `route.default_domain_resolver` 必须设
- 用 `sing-box check` 预验配置后再部署

### 9d. 安全网设计规则

如果切换 TUN 时需自动回滚保护：

- **连通性检测必须用 TCP/HTTP，不能用 ICMP ping**（ICMP 走 TUN 后会被路由到代理 outbound 导致失败）
- 检测目标：网关（192.168.71.1:80）+ 国内网站（baidu.com）
- 回滚动作：恢复备份配置 + `systemctl --user restart sing-box`

详细 TUN 失败记录见 `references/tun-mode-pitfalls.md`。

---

## 参考

- [sing-box 官方文档](https://sing-box.sagernet.org)
- [Migration: DNS 新格式](https://sing-box.sagernet.org/migration/#migrate-to-new-dns-server-formats)
- [Migration: outbound DNS rule → domain_resolver](https://sing-box.sagernet.org/migration/#migrate-outbound-dns-rule-items-to-domain-resolver)

## 关联文件

- `scripts/update-rulesets.sh` — 定期更新 geoip/geosite 规则集（建议 cron）
- `references/sing-box-v113-deprecation-pitfalls.md` — v1.13 迁移错误记录和修复