# PassWall to OpenClash Config Migration

Converts PassWall proxy nodes (stored in UCI `/etc/config/passwall`) to Clash YAML format (`proxies:` section).

## PassWall Node Fields → Clash YAML Mapping

| PassWall Option | Clash YAML Field | Notes |
|----------------|-----------------|-------|
| `address` | `server` | Hostname/IP |
| `port` | `port` | Integer |
| `uuid` | `uuid` | VMess UUID |
| `security` | `cipher` | `auto` → `auto` |
| `transport` | `network` | `ws` → `ws`, `tcp` → `tcp` |
| `tls` | `tls` | `1` → `true` |
| `tls_serverName` | `servername` | TLS SNI |
| `ws_path` | `ws-opts.path` | WebSocket path |
| `ws_host` | `ws-opts.headers.Host` | WebSocket Host header |

## Extraction Script

```bash
# Extract all VMess nodes from PassWall config
awk -v RS='' '/^config nodes/{print}' /etc/config/passwall
```

Each block corresponds to one proxy node. Translate each to Clash format:

```yaml
proxies:
  - name: "233boy-KVM"
    type: vmess
    server: kvm.bernarty.xyz
    port: 30717
    uuid: f2586607-5bbd-4947-a1cb-db23f48aaf0c
    alterId: 0
    cipher: auto
    tls: true
    servername: kvm.bernarty.xyz
    network: ws
    ws-opts:
      path: "/f2586607-5bbd-4947-a1cb-db23f48aaf0c"
      headers:
        Host: kvm.bernarty.xyz
```

## PassWall Shunt Rules → Clash Rules Mapping

PassWall uses named "shunt rules" with `domain_list` / `ip_list`. In Clash these become `rules:` entries:

```yaml
# PassWall shunt_rules Direct → Clash rule
- GEOSITE,cn,DIRECT
- GEOIP,cn,DIRECT

# PassWall shunt_rules AD
- GEOSITE,category-ads-all,REJECT

# PassWall shunt_rules Proxy
- GEOSITE,geolocation-!cn,PROXY

# PassWall shunt_rules ProxyGame
- GEOSITE,category-games@!cn,Manual-Select

# PassWall shunt_rules Netflix / OpenAI
- GEOSITE,netflix,Manual-Select
- GEOSITE,openai,Manual-Select

# PassWall proxy_host entries (direct domain list)
- DOMAIN-SUFFIX,accounts.google.com,Google-Auth
# ... repeat for each proxy_host entry
```

## Default Node Migration

PassWall's `tcp_node` becomes the default proxy group selection:

```bash
# PassWall
option tcp_node 'izRNaKFP'

# Clash - this is just a proxy name used in the default group
```

```yaml
proxy-groups:
  - name: "PROXY"
    type: select
    proxies:
      - node1
      - node2
      - AUTO
  - name: "AUTO"
    type: url-test
    url: https://cp.cloudflare.com/generate_204
    interval: 300
    tolerance: 100
    proxies:
      - node1
      - node2
```

## Auto Switch → Clash Groups

PassWall `auto_switch` with `tcp_redir_node` and `tcp_fallback_node` maps to a `fallback` or `url-test` group in Clash:

```yaml
  - name: "Google-Auth"
    type: select
    proxies:
      - Seoul-Cloudflare
      - VMISS-HK
      - 233boy-KVM
```

## Verification After Migration

```bash
# 1. Test config
/etc/openclash/clash -d /etc/openclash -t -f /etc/openclash/config/config.yaml

# 2. Start core
/etc/openclash/clash -d /etc/openclash -f /etc/openclash/config/config.yaml &

# 3. Test each node via REST API
for node in node1 node2 node3; do
  curl -s -XPUT http://127.0.0.1:9090/proxies/PROXY \
    -H "Authorization: Bearer <secret>" \
    -H "Content-Type: application/json" \
    -d "{\"name\":\"$node\"}"
  sleep 4
  curl -s --connect-timeout 15 -x http://user:pass@127.0.0.1:7890 \
    https://cp.cloudflare.com/generate_204 -o /dev/null \
    -w "$node: HTTP %{http_code} %{time_total}s\n"
done
```
