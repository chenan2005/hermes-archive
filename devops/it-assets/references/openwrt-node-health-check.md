# OpenWrt 代理节点健康检查指南

> 用于 `it-assets` — 远程检查 OpenWrt 上 PassWall 节点的联通性

## 适用场景

- 用户反馈某个网站打不开
- 怀疑某个节点掉线
- 确认出口 IP 是否正确
- 新配节点后的验证

## 检查流程

### 1. 确认代理软件和节点清单

```bash
# 查看运行的代理进程
ps | grep -E 'passwall|xray|v2ray|trojan|hysteria' | grep -v grep

# 列出所有 PassWall 节点名称+地址+协议
for node in $(uci show passwall | grep '=nodes' | grep -v backup | grep -v server | cut -d= -f1); do
  r=$(uci get $node.remarks 2>/dev/null)
  a=$(uci get $node.address 2>/dev/null)
  p=$(uci get $node.port 2>/dev/null)
  proto=$(uci get $node.protocol 2>/dev/null)
  echo "$r | $a:$p | $proto"
done
```

### 2. 检查当前活跃节点

```bash
# 当前 TCP 节点
uci get passwall.@global[0].tcp_node

# 分流默认节点  
uci get passwall.myshunt.default_node
```

### 3. 检查服务器可达性 (ping)

```bash
ping -c 2 -W 5 <server_ip>
```

### 4. 检查端口可达性

**OpenWrt BusyBox 限制**：`nc` 不支持 `-z` 和 `-w` 参数。用 `curl` 替代：

```bash
# HTTP 端口测试
curl -s --connect-timeout 5 -o /dev/null -w 'HTTP=%{http_code} CONNECT=%{time_connect}s\n' http://<ip>:<port>/

# HTTPS 端口测试
curl -s --connect-timeout 5 -o /dev/null -w 'HTTP=%{http_code} CONNECT=%{time_connect}s\n' https://<ip>:<port>/ --insecure
```

**HTTP_CODE 含义**：200/301/302/404=端口可达但无预期的HTTP响应（正常，xray回调不是标准HTTP服务）; 000=连接失败或超时

### 5. 通过透明代理测试外网

```bash
# 透明代理自动走当前 TCP 节点
curl -s --connect-timeout 5 -o /dev/null -w 'HTTP=%{http_code} TIME=%{time_total}s IP=%{remote_ip}\n' https://www.google.com

# 查看出口 IP
curl -s --connect-timeout 5 https://ip.sb
```

### 6. 通过独立 SOCKS 代理测试（如有）

一些场景下有独立运行的 xray/v2ray SOCKS 代理（如 xray-seoul 监听 127.0.0.1:1071）：

```bash
curl -sx socks5h://127.0.0.1:1071 --connect-timeout 5 https://ip.sb
```

两个出口 IP 应一致（指向同一台服务器）。

### 7. Cloudflare Tunnel 节点检查

对于走 CF Tunnel 的节点：

```bash
# DNS 解析
nslookup <tunnel-domain>.trycloudflare.com

# 直接连接测试（指定 IP 避免 DNS 污染）
curl -s --connect-timeout 5 --resolve '<domain>:443:<cf_ip>' -o /dev/null -w 'HTTP=%{http_code}\n' https://<domain>/ --insecure

# 检查服务器端 cloudflared 状态
ssh <user>@<server> "sudo systemctl is-active cloudflared"
```

## Pitfalls

| 问题 | 表现 | 对策 |
|------|------|------|
| BusyBox nc 参数缺失 | `nc -zv` 报错 Usage | 用 `curl` 代替端口检测 |
| BusyBox ssh 选项忽略 | `-o ConnectTimeout=5` 无效果 | 用本机 ssh 直连（完整 OpenSSH） |
| PassWall 节点名是哈希 | `cfgXXXXXX` 形式 | 用 `uci show passwall.$node.remarks` 获取备注名 |
| VLESS+Reality 非HTTP | HTTP_CODE=000 但节点正常 | Reality 协议不是 HTTP，需要用实际代理流量验证 |
| x-ui 动态生成 config | `clients: null` 出现在文件 | 检查 x-ui.db SQLite 数据库为准：`sudo sqlite3 /etc/x-ui/x-ui.db 'SELECT * FROM inbounds;'` |
