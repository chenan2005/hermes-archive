# PassWall DNS Architecture (SmartDNS + chinadns-ng)

How PassWall routes DNS queries when using GFWList mode with chinadns-ng + SmartDNS.

## Port Layout

All DNS ports served by a single SmartDNS instance with group-based routing:

```
                     dnsmasq (port 53)
                          │
                          ▼
               chinadns-ng (port 15354)
                 ┌────────┴────────┐
                 │                 │
         国内域名              海外域名
                 │                 │
                 ▼                 ▼
       SmartDNS :6153      SmartDNS :6253
       (cn group)          (oversea group)
       ┌────┴────┐         ┌────┴────┐
   223.6.6.6  223.5.5.5  8.8.8.8  Cloudflare DoH
   (直连解析)              (走代理出去)

旁路（不走 chinadns-ng）：
  白名单/节点域名 → SmartDNS :6353 (cn-doh group)
  → dns.alidns.com / doh.pub (DoH 直连，防污染)
```

- **6153** (`-group cn speed-check-mode ping,tcp:80`): 国内 DNS 组，上游 223.6.6.6 / 223.5.5.5 / 119.29.29.29 / 180.76.76.76，测速竞速，直连无代理
- **6253** (`-group oversea -no-speed-check -no-cache -force-aaaa-soa`): 海外 DNS 组，上游 8.8.8.8 / Cloudflare DoH，**实际走代理隧道**（xray），不缓存不测速
- **6353** (`-group cn-doh -no-cache`): 国内 DoH 组，上游 dns.alidns.com / doh.pub，用于白名单和 VPS 节点域名。**必须直连**（否则循环依赖：解析代理服务器需要代理服务器），走 HTTPS 加密防污染
- **15354**: chinadns-ng 监听口，dnsmasq 转发所有非白名单/非节点查询到这里做分流

## GFWList Mode DNS Flow

在 GFWList 模式下：
1. dnsmasq 收到查询 → 白名单/节点域名直送 6353
2. 其余发往 chinadns-ng (15354)
3. chinadns-ng 查 GFWList：
   - 域名在 GFWList → 走 6253（海外 DNS，经代理）→ 返回海外 IP → PassWall 走代理
   - 域名不在 GFWList → 走 6153（国内 DNS）→ 返回 IP 后由 chnroute 判断是国内还是海外

## direct_host 与 GFWList 模式的交互

`direct_host` 列表告诉 PassWall **路由层面**直连某个域名，但不改变 **DNS 解析**路径：

- 域名在 `direct_host` → PassWall 不把它送代理（iptables 规则绕过）
- 但如果该域名不在 GFWList 中，chinadns-ng 仍会用 6153（国内 DNS）解析
- 如果域名是国内 IP 且国内 DNS 能正确解析 → 正常工作
- 如果域名是海外 IP 但国内 DNS 解析出错/被污染 → 直连到错误 IP → 失败

**典型案例**：`api.deepseek.com` 是国内 IP 的服务。在 GFWList 模式下：
- 不在 GFWList → chinadns-ng 用 6153 国内 DNS 解析 → 拿到国内 IP
- **如果走代理**（出国）→ DeepSeek 检测到请求来自海外 → 拒绝（`403/Forbidden`）
- **如果直连**（国内 IP 直连）→ 正常工作
- 所以必须在 `direct_host` 中确保直连路由，DNS 反而是次要问题

核心矛盾：`api.deepseek.com` 的**路由**（不能走代理）和 **DNS**（走 6153 国内 DNS 可以正常解析）没有冲突。问题出在 PassWall 状态异常（反复重启导致 iptables/xray 半残）时，`direct_host` 的路由规则未生效，请求被错误地走了代理隧道，DeepSeek 识别为海外来源后拒绝。

**解决方案**：
1. 确保 `api.deepseek.com` 在 `direct_host` 列表中（路由直连）
2. 确保 PassWall 状态健康（xray 正常运行，iptables 规则完整）
3. 如 GFWList 模式下仍不稳定，可切到 `direct/proxy` 模式：只用显式列表路由，不再依赖 GFWList + chnroute 自动判断

## chinadns-ng 命令行参考

```
chinadns-ng -v -b 127.0.0.1 -l 15354
  -c 127.0.0.1#6153    # 国内 DNS upstream
  -t 127.0.0.1#6253    # 可信 DNS upstream（海外）
  -g /tmp/etc/passwall/chinadns_gfwlist   # GFWList
  -A passwall_gfwlist,passwall_gfwlist6   # ipset 名称
  -d chn               # 使用 chnroute 做 IP 判断
  -f -N=gt             # 过滤模式
```

## 相关配置文件

- `/etc/smartdns/custom.conf` — SmartDNS 端口绑定和上游服务器定义
- `/tmp/etc/passwall/script_func` — chinadns-ng 启动命令
- `/usr/share/passwall/rules/direct_host` — 直连域名列表
- `/usr/share/passwall/rules/chnlist` — 国内域名列表
- `/usr/share/passwall/rules/gfwlist` — GFW 域名列表
