# sing-box v1.13.14 Deprecation Pitfalls (2026-07-01)

## 环境
- sing-box v1.13.14, Linux Mint 22, home fiber (光猫直连, no proxy)
- Nodes: VMISS-HK (VMess+WS), 233boy-KVM (VMess+WS), Alibaba-Seoul-VLESS (VLESS+Reality)

## 错误记录和修复

### 1. legacy DNS servers 废弃
**错误:**
```
ERROR legacy DNS servers is deprecated in sing-box 1.12.0 and will be removed in 1.14.0
FATAL to continuing using this feature, set environment variable ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true
```

**触发条件:** DNS server 定义中有 `detour` 字段:
```json
{ "address": "223.5.5.5", "detour": "direct" }
```

**修复:** 在 systemd service 中设环境变量:
```ini
[Service]
Environment=ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true
```

### 2. dns outbound 已移除
**错误:**
```
FATAL decode: outbounds[5]: dns outbound is deprecated in 1.11.0 and removed in 1.13.0, use rule actions instead
```

**修复:** 删除整个 `{"type": "dns", "tag": "dns-out"}` outbound 及其 route rule:
```json
{ "protocol": "dns", "outbound": "dns-out" }
```

### 3. outbound DNS rule item 废弃
**错误:**
```
ERROR outbound DNS rule item is deprecated in 1.12.0 and will be removed in 1.14.0
FATAL set environment variable ENABLE_DEPRECATED_OUTBOUND_DNS_RULE_ITEM=true
```

**触发条件:** DNS server rules 中有 `"outbound": "any"` 无 `default_domain_resolver`

**修复:** 在 route 中加 `default_domain_resolver`:
```json
"route": { "default_domain_resolver": "remote-dns" }
```
和/或在 systemd service 中设 env 变量。

### 4. missing domain_resolver 废弃
**错误:**
```
ERROR missing route.default_domain_resolver or domain_resolver in dial fields is deprecated
FATAL set environment variable ENABLE_DEPRECATED_MISSING_DOMAIN_RESOLVER=true
```

**触发条件:** 配置了 remote DNS 但没有 `default_domain_resolver`。

**修复:** 加 `route.default_domain_resolver` 字段指向默认 DNS server tag。

### 5. cache_file clash_api 迁移
**错误:**
```
FATAL create clash-server: cache_file and related fields in Clash API is deprecated
use experimental.cache_file instead
```

**修复:** 把 `store_selected` 从 `clash_api` 移出:
```json
{
  "experimental": {
    "cache_file": { "enabled": true, "path": "/path/to/cache.db" },
    "clash_api": { "external_controller": "127.0.0.1:9090" }
  }
}
```

### 6. store_selected 不在 cache_file 中
**错误:**
```
FATAL decode: experimental.cache_file.store_selected: json: unknown field "store_selected"
```

**触发条件:** 把 `store_selected` 放在 `experimental.cache_file` 内。

**修复:** `store_selected` 只在 `clash_api` 下有效（或直接删除，没有也不影响）。

### 7. rule_set remote 下载 404 / 超时
**错误:**
```
FATAL initialize rule-set[0]: initial rule-set: geoip-cn: unexpected status: 404 Not Found
```

**根因:** `SagerNet/sing-geoip` 和 `SagerNet/sing-geosite` 的 `rule-set/` 目录不直接提供 JSON 文件。需要用 `release` 的 `.db` 文件或从社区源 (17mon, v2fly) 自行编译。

**解决方案:** 用 `type: "local"` + 自行编译 .srs 文件。

### 8. DNS 死锁 (rule_set 下载 vs DNS 解析)
**时序:** sing-box 启动时:
1. rule_set 远程下载 → 需要 DNS 解析 `raw.githubusercontent.com`
2. DNS 使用 `https://dns.google/dns-query` → 需要 proxy 才能出国
3. proxy 需要 rule_set 下载完毕 → 死锁

**解决方案:** 本地编译 rule_set + `type: "local"`，或全程用 223.5.5.5 直连。

## 推荐 systemd service 配置

```ini
[Service]
Type=simple
Environment=ENABLE_DEPRECATED_LEGACY_DNS_SERVERS=true
Environment=ENABLE_DEPRECATED_OUTBOUND_DNS_RULE_ITEM=true
ExecStart=/usr/local/bin/sing-box run -c %h/.config/sing-box/config.json
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
LimitNOFILE=65535
```

## 清理后文件清单

```
~/.config/sing-box/
├── config.json                    # 完整配置
├── ruleset/
│   ├── geoip-cn.srs               # China IP (7456 CIDR)
│   └── geosite-cn.srs             # China domains (6009 × domain+domain_suffix)

~/.config/systemd/user/
└── sing-box.service               # systemd 用户服务

~/.local/bin/
└── sing-box-switch                 # 切节点脚本

~/.local/share/sing-box/
├── access.log
└── cache.db
```

## 带宽测试记录

| 网络 | 节点 | 目标 | 速度 |
|------|------|------|------|
| 5G hotspot | Alibaba-Seoul-VLESS | Ookla (Shanghai Unicom) | **300.92 Mbps** |
| 5G hotspot | Alibaba-Seoul-VLESS | OVH France (200MB) | 42.11 Mbps |
| 5G hotspot | VMISS-HK | OVH France (25MB) | 66.67 Mbps |
| 家宽直连 | — | — | ~0.43 Mbps (出口限速) |
