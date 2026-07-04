# PassWall VLESS+Reality 节点 UCI 配置

## 背景
OpenWrt PassWall 通过 UCI 管理节点配置，然后自动生成 xray JSON 配置文件。Reality 协议的 UCI 字段映射有特殊要求，容易遗漏导致生成的 JSON 缺少 `security: "reality"` 和 `realitySettings` 块。

## 关键 UCI 字段

| 字段 | 值 | 必须 | 说明 |
|:--|:--:|:--:|:--|
| `type` | `Xray` | ✅ | Reality 仅 Xray 支持 |
| `protocol` | `vless` | ✅ | |
| `security` | `reality` | ✅ | 告知 UI 是 Reality |
| `reality` | `1` | ✅ | **标记字段**——告诉 config 生成器写入 Reality settings |
| `tls` | `1` | ✅ | `reality` Flag 的 `depends` 条件依赖 `tls=true` |
| `transport` | `tcp` | ✅ | Reality 通常走 TCP |
| `tls_serverName` | (目标域名) | ✅ | 如 `www.microsoft.com` |
| `reality_publicKey` | (公钥) | ✅ | 服务器公钥 |
| `reality_shortId` | (shortId) | ✅ | 如 `a1b2c3d4` |
| `fingerprint` | `chrome` | ✅ | 指纹 |

## 常见错误

### 错误1：只设 `security='reality'`，漏了 `reality='1'`
PassWall 的 config 生成器（`util_xray.lua`）检查的是 `node.reality == "1"`，不是 `node.security`。只设 `security` 不会生成 Reality 配置。

### 错误2：漏了 `tls='1'`
UCI 模型中 `reality` 字段的 `depends` 条件包含 `tls = true`。没有 `tls='1'`，Reality 配置块不会被生成。

### 错误3：DNS 解析问题
在 OpenWrt 上，如果 xray 的 outbound 使用域名（如 `alibaba.bernarty.xyz`），可能由于 DNS 经过 chinadns-ng/代理链导致解析失败。**使用 IP 地址作为 `address`** 更可靠。

## 完整 UCI 命令示例

```bash
cfg=$(uci add passwall nodes)
uci set passwall.$cfg.remarks='Alibaba-Seoul-VLESS-Reality'
uci set passwall.$cfg.type='Xray'
uci set passwall.$cfg.protocol='vless'
uci set passwall.$cfg.address='43.108.41.245'   # 用 IP 不用域名
uci set passwall.$cfg.port='40001'
uci set passwall.$cfg.uuid='a5fa1889-1316-4115-a866-96c8f30523ef'
uci set passwall.$cfg.transport='tcp'
uci set passwall.$cfg.security='reality'
uci set passwall.$cfg.reality='1'               # ★ 必须
uci set passwall.$cfg.tls='1'                   # ★ 必须
uci set passwall.$cfg.tls_serverName='www.microsoft.com'
uci set passwall.$cfg.reality_publicKey='...'
uci set passwall.$cfg.reality_shortId='a1b2c3d4'
uci set passwall.$cfg.fingerprint='chrome'
uci set passwall.$cfg.add_mode='1'
uci commit passwall
```

## 验证方法
切到该节点后，检查 `/tmp/etc/passwall/TCP_SOCKS.json` 中 streamSettings 是否包含 `"security": "reality"` 和 `"realitySettings": {...}`。
如果只有 `"security": "tls"` 或没有 security/realitySettings，说明 UCI 字段有遗漏。
