# OpenClash YAML → sing-box JSON 配置映射

将 Clash Meta (mihomo) 格式的代理节点配置转换为 sing-box JSON 格式。

## VLESS + Reality

### Clash YAML（OpenClash 格式）

```yaml
- name: Alibaba-Seoul-VLESS-Reality
  type: vless
  server: 43.108.41.245
  port: 40002
  uuid: a5fa1889-1316-4115-a866-96c8f30523ef
  tls: true
  servername: www.bing.com
  reality-opts:
    public-key: 0o3XsyApUXA0_1Ns2GZPbzLCbUW8zpAarRxCbb0gr1g
    short-id: "a1b2c3d4"
  udp: true
  network: tcp
  client-fingerprint: chrome
```

### sing-box JSON

```json
{
  "type": "vless",
  "tag": "Alibaba-Seoul-VLESS-Reality",
  "server": "43.108.41.245",
  "server_port": 40002,
  "uuid": "a5fa1889-1316-4115-a866-96c8f30523ef",
  "flow": "",
  "tls": {
    "enabled": true,
    "server_name": "www.bing.com",
    "utls": {
      "enabled": true,
      "fingerprint": "chrome"
    },
    "reality": {
      "enabled": true,
      "public_key": "0o3XsyApUXA0_1Ns2GZPbzLCbUW8zpAarRxCbb0gr1g",
      "short_id": "a1b2c3d4"
    }
  }
}
```

### 字段映射对照

| Clash YAML | sing-box JSON | 说明 |
|------------|---------------|------|
| `type: vless` | `"type": "vless"` | 类型一致 |
| `server` | `"server"` | 一致 |
| `port` | `"server_port"` | 注意字段名不同 |
| `uuid` | `"uuid"` | 一致 |
| `flow` | `"flow": ""` | VLESS flow（如"xtls-rprx-vision"），无则空字符串 |
| `tls: true` | `"tls": {"enabled": true}` | YAML 布尔值 → JSON 对象 |
| `servername` | `"tls": {"server_name": "..."}` | Reality 必须设置 servername |
| `client-fingerprint` | `"tls": {"utls": {"fingerprint": "..."}}` | 放在 utls 下 |
| `reality-opts.public-key` | `"tls": {"reality": {"public_key": "..."}}` | 注意字段名 public-key → public_key |
| `reality-opts.short-id` | `"tls": {"reality": {"short_id": "..."}}` | 字段名 short-id → short_id |
| `udp: true` | 不需要（sing-box 默认开 UDP） | 删掉 |
| `network: tcp` | 不需要（sing-box 默认 tcp） | 删掉 |

---

## VMess + WebSocket + TLS

### Clash YAML（OpenClash 格式）

```yaml
- name: VMISS-HK
  type: vmess
  server: vmiss.bernarty.xyz
  port: 443
  uuid: ac6aa939-156c-452f-a7da-4ddd79b7d5c9
  alterId: 0
  cipher: auto
  tls: true
  servername: vmiss.bernarty.xyz
  network: ws
  ws-opts:
    path: "/ws-vmiss"
    headers:
      Host: vmiss.bernarty.xyz
```

### sing-box JSON

```json
{
  "type": "vmess",
  "tag": "VMISS-HK",
  "server": "vmiss.bernarty.xyz",
  "server_port": 443,
  "uuid": "ac6aa939-156c-452f-a7da-4ddd79b7d5c9",
  "security": "auto",
  "tls": {
    "enabled": true,
    "server_name": "vmiss.bernarty.xyz"
  },
  "transport": {
    "type": "ws",
    "path": "/ws-vmiss",
    "headers": {
      "Host": "vmiss.bernarty.xyz"
    }
  }
}
```

### 字段映射对照

| Clash YAML | sing-box JSON | 说明 |
|------------|---------------|------|
| `type: vmess` | `"type": "vmess"` | 一致 |
| `cipher: auto` | `"security": "auto"` | 字段名不同：cipher → security |
| `alterId: 0` | **删掉** | sing-box 自动处理，不需要指明 |
| `network: ws` | `"transport": {"type": "ws"}` | Clash 的 flat network 字段 → sing-box transport 对象 |
| `ws-opts.path` | `"transport": {"path": "..."}` | WS path |
| `ws-opts.headers.Host` | `"transport": {"headers": {"Host": "..."}}` | WS HTTP 头部，注意大小写 "Host" |
| `servername` | `"tls": {"server_name": "..."}` | 一致 |

---

## 完整 mininal sing-box config（Socks5 inbound + VLESS 出站）

```json
{
  "log": { "level": "warn" },
  "inbounds": [
    {
      "type": "socks",
      "tag": "socks-in",
      "listen": "127.0.0.1",
      "listen_port": 10880
    },
    {
      "type": "mixed",
      "tag": "mixed-in",
      "listen": "127.0.0.1",
      "listen_port": 10881
    }
  ],
  "outbounds": [
    {
      "type": "vless",
      "tag": "Alibaba-Seoul-VLESS-Reality",
      "server": "43.108.41.245",
      "server_port": 40002,
      "uuid": "a5fa1889-1316-4115-a866-96c8f30523ef",
      "tls": {
        "enabled": true,
        "server_name": "www.bing.com",
        "utls": { "enabled": true, "fingerprint": "chrome" },
        "reality": {
          "enabled": true,
          "public_key": "0o3XsyApUXA0_1Ns2GZPbzLCbUW8zpAarRxCbb0gr1g",
          "short_id": "a1b2c3d4"
        }
      }
    },
    {
      "type": "direct",
      "tag": "direct"
    }
  ],
  "route": {
    "rules": [
      { "outbound": "Alibaba-Seoul-VLESS-Reality" }
    ],
    "auto_detect_interface": true
  }
}
```

## 测试方式

```bash
# 检查配置
sing-box check -c config.json

# 启动（保持前台，看日志）
sing-box run -c config.json

# 后台启动
sing-box run -c config.json 2>/path/to/sb.log &

# 通过 SOCKS5 代理测试
curl -s --socks5 127.0.0.1:10880 -o /dev/null -w "%{http_code} %{time_total}s\n" https://www.google.com

# 带宽测试 (25MB)
curl -s --max-time 120 --socks5 127.0.0.1:10880 -o /tmp/test.bin \
  -w "%{http_code}" "https://speed.cloudflare.com/__down?bytes=26214400"
# 计算带宽（用 wc -c 代替 stat，兼容 BusyBox）
sz=$(wc -c < /tmp/test.bin)
mbps=$(awk -v sz="$sz" -v d="$elapsed" 'BEGIN {printf "%.2f", sz * 8 / d / 1048576}')
```

## 安装（GitHub 被墙时）

本机直连 GitHub 超时时，通过 ImmortalWrt（有 OpenClash）下载并传回本机：

```bash
# 1. 路由器上下载
ssh root@192.168.71.9 'cd /tmp && \
  curl -sLO https://github.com/SagerNet/sing-box/releases/download/v1.13.14/sing-box-1.13.14-linux-amd64.tar.gz'

# 2. 通过 SSH cat 管道传回本机（scp 不可用——无 sftp-server）
ssh root@192.168.71.9 'cat /tmp/sing-box-1.13.14-linux-amd64.tar.gz' > /tmp/sing-box-1.13.14-linux-amd64.tar.gz

# 3. 解压安装
cd /tmp && tar xzf sing-box-1.13.14-linux-amd64.tar.gz
sudo cp sing-box-1.13.14-linux-amd64/sing-box /usr/local/bin/
rm -rf /tmp/sing-box-1.13.14-linux-amd64*
```

ARM64 (平板 Termux) 用 `linux-arm64` 版本或 `pkg install sing-box`。
