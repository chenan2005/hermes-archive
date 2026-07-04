---
name: linux-proxy-client
description: '在 Linux 上部署纯 CLI 代理客户端（sing-box）—— 配置三节点、DNS防污染、大陆分流、Clash API 切节点、systemd 用户服务、系统代理开关。姊妹技能: windows-proxy-client。'
---

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
