# OpenWrt 跨版本 dnsmasq 配置移植

> 场景：把 DHCP 静态绑定和 *.lan.11 内网 DNS 解析从旧 OpenWrt 搬到新 OpenWrt
> 涉及版本：22.03（旧）→ 24.10（新）

## 核心差异

| 特性 | OpenWrt 22.03 | OpenWrt 24.10+ |
|------|---------------|-----------------|
| `list host` 行为 | 自动生成 FQDN 可解析的 `host-record=` | 生成 bare `host-record=`，不含 domain 后缀 |
| DHCP disabled 时的 `/tmp/hosts` | `/tmp/hosts/dhcp` 仍有 DHCP host 条目 | 无条目（DHCP 关闭时不写文件） |
| `expand-hosts` 作用域 | `/etc/hosts` + addn-hosts 文件 | 同左，对 `host-record` 无效 |

## 问题现象

在 24.10 上配了 `list host 'minipc,192.168.37.224'` 后：
- `nslookup minipc` → ✅ 正确解析
- `nslookup minipc.lan.11` → ❌ NXDOMAIN

生成的 `/var/etc/dnsmasq.conf.cfg*` 中有 `host-record=minipc,192.168.37.224` 但无 `domain=lan.11` 后缀展开。

## 根因

OpenWrt 的 `/etc/init.d/dnsmasq` 中，`list host` 走 `dhcp_hostrecord_add()` 函数生成 `host-record=name,ip`。dnsmasq 的 `domain=lan.11` + `expand-hosts` 只对 `/etc/hosts` 和 `addn-hosts` 文件生效，**不展开 host-record 条目**。

不能依赖 22.03 上的行为在新版本上照搬。

## 修复方案

### 方案 A：`list address`（推荐）

```bash
uci add_list dhcp.@dnsmasq[0].address="/laptop.lan.11/192.168.37.234"
uci add_list dhcp.@dnsmasq[0].address="/minipc.lan.11/192.168.37.224"
...

uci commit dhcp && /etc/init.d/dnsmasq restart
```

生成的配置行：`address=/laptop.lan.11/192.168.37.234`
效果：`laptop.lan.11` 和 `laptop` 都解析（后者靠 `host-record` 或 DHCP lease）

### 方案 B：`config hostrecord` 节

```bash
uci add dhcp hostrecord
uci set dhcp.@hostrecord[-1].name="laptop"
uci set dhcp.@hostrecord[-1].ip="192.168.37.234"
...
uci commit dhcp && /etc/init.d/dnsmasq restart
```

生成的配置行：`host-record=laptop,192.168.37.234`
效果：仅 `laptop`（裸名）解析，`laptop.lan.11` 仍 NXDOMAIN，除非同时加 address 条目。

### 方案 C：DHCP 启用状态下（生产环境）

如果新机器上 DHCP 已启用（非 `ignore=1`），则 `/tmp/hosts/dhcp` 会被 DHCP lease 脚本填充，配合 `expand-hosts` 自动展开 domain 后缀。方案 A 仍推荐作为防御性配置。

## 调试命令

```bash
# 查看生成的 dnsmasq 配置中是否有 host-record 和 address
cat /var/etc/dnsmasq.conf.cfg* | grep -E "host-record|^address="

# 查看 dnsmasq 命令行（是否有额外的 --host-record 参数）
cat /proc/$(pgrep -f "dnsmasq" | head -1)/cmdline | tr "\0" " "

# 查看 dnsmasq 日志中的查询结果
logread -e dnsmasq | grep "NXDOMAIN\|reply"

# 测试短名和 FQDN
nslookup laptop 127.0.0.1
nslookup laptop.lan.11 127.0.0.1

# 从本机测试
nslookup laptop.lan.11 <目标路由IP>
```

## 注意事项

- `option noresolv '1'` 表示 dnsmasq 不从 `/tmp/resolv.conf` 读上游 DNS，而是用 `server=127.0.0.1#7874`（OpenClash）或 `#6353`（PassWall）
- **短名 vs FQDN 都要验证**，缺一不可
- `list interface 'lan'` 保证 dnsmasq 在 LAN 接口上监听
