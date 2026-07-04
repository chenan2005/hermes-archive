# TUN 模式失败记录

> Linux Mint 22 + sing-box v1.13.14 + NetworkManager
> 主机：WiFi 直连光猫（网关 192.168.71.1），无 OpenClash 路由翻墙

## 尝试过程（全部失败）

### 尝试 1：strict_route + dns_mode + sniff

```json
{
  "type": "tun",
  "tag": "tun-in",
  "inet4_address": "198.18.0.1/30",  // ❌ 1.12+ 废弃
  "auto_route": true,
  "strict_route": true,
  "sniff": true,                     // ❌ 1.13 废弃
  "sniff_override_destination": false,
  "dns_mode": "hijack"              // ❌ 1.14 才有
}
```

**结果**：sing-box 崩溃（`"dns_mode"` 不识别，`"sniff"` 废弃）。`strict_route` 留下的 nftables 规则将全部流量黑洞，用户手动停 sing-box 才恢复。

### 尝试 2：strict_route: false（无 fwmark 绕过）

修复了 `address` 数组格式，去掉 `sniff`/`dns_mode`，但用了 `strict_route: false`。

```json
{
  "type": "tun",
  "tag": "tun-in",
  "address": ["198.18.0.1/30"],
  "auto_route": true,
  "strict_route": false
}
```

**结果**：国内 HTTP 正常（Baidu 200），国际 HTTP 超时（Google 000）——因为 `strict_route: false` 不加 nftables fwmark 绕过规则，sing-box 的节点出站连接也走 TUN 循环。

### 尝试 3：strict_route: true + route_exclude_address_set + 无 fakeip

```json
{
  "type": "tun",
  "tag": "tun-in",
  "address": ["198.18.0.1/30"],
  "auto_route": true,
  "strict_route": true,
  "route_exclude_address_set": ["geoip-cn"]
}
```

DNS 保持原有 `type: udp + server: 223.5.5.5` 格式，不加 fakeip。

**结果**：仍导致断网。主因是 `route_exclude_address_set` 在 strict_route 模式下依赖 nftables 处理，可能与 NetworkManager 或系统默认 nftables 规则冲突。

## 安全网坑

切换 TUN 时设计了一个 cron 安全网做自动回滚：

### 版本 1（ICMP ping，失败）

```bash
ping -c 1 -W 3 192.168.71.1  # ❌ 经过 TUN → 被路由到代理 outbound → ICMP 不支持 → 全失败
```

安全网误判为断网，触发不必要的回滚。回滚过程需要关闭 TUN inbound（等待 2 分钟），造成了实际停机窗口。

**教训**：TUN 模式下 ICMP 走代理 outbound 不支持，连通性检测必须用 TCP（/dev/tcp）或 HTTP（curl）。

### 版本 2（TCP/HTTP，修复）

```bash
timeout 3 bash -c "echo > /dev/tcp/192.168.71.1/80"
curl -s -o /dev/null --max-time 5 http://www.baidu.com
```

三个检测轮次，任何一次成功即退出（不触发回滚）。

## 最终结论

- **Linux Mint 上 sing-box TUN 模式不值得花时间** — SOCKS5/Mixed 端口模式配合系统代理设置即可满足需求
- 如果环境不同（例如服务器无桌面环境、有固定路由表），TUN 可能工作，但本机桌面环境（NetworkManager + Cinnamon）不兼容
- 关键配置陷阱已记录于 SKILL.md §9
