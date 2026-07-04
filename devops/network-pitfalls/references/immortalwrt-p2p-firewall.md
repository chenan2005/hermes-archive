# ImmortalWrt P2P 防火墙配置（Tailscale / ZeroTier）

## 现象

移动 5G 手机 x 电信家宽之间，Tailscale 和 ZeroTier 都无法建立 P2P 直连，只能走中继。

```
tailscale status → relay "tok"
zerotier-cli peers → RELAY -1
```

中继下 TLS/SSL 握手失败（exit 35），国际 HTTPS 不可用，国内 HTTP 正常。

## 根因

ImmortalWrt 24.10（kernel 6.6, nftables 1.1.1）不支持 full-cone NAT：

| 尝试 | 结果 |
|------|------|
| `kmod-nft-fullcone` | ❌ opkg 中不存在 |
| `masquerade fullcone` | ❌ nftables 1.1.1 不支持此选项 |
| `masq_fullcone=1` | ❌ UCI 不存在此选项 |

默认 masquerade（对称 NAT）对 UDP 打洞不利。叠加移动 5G CGNAT，P2P 成功率很低。

## 改善方法（不完全解决）

### 1. 放行 VPN 入站 UDP 端口

```bash
# Tailscale (WireGuard)
uci add firewall rule
uci set firewall.@rule[-1].name="Allow-Tailscale-UDP"
uci set firewall.@rule[-1].src="wan"
uci set firewall.@rule[-1].dest_port="41641"
uci set firewall.@rule[-1].proto="udp"
uci set firewall.@rule[-1].target="ACCEPT"
uci set firewall.@rule[-1].family="ipv4"

# ZeroTier
uci set firewall.@rule[-1].name="Allow-ZeroTier-UDP"
uci set firewall.@rule[-1].dest_port="9993"
# ... 其他同上
uci commit firewall
fw4 reload
```

### 2. VPN 流量跳过 NAT（保留源端口）

```bash
nft insert rule inet fw4 srcnat_wan ip daddr 100.64.0.0/10 return
nft insert rule inet fw4 srcnat_wan ip daddr 10.183.232.0/24 return
```

这使 Tailscale（100.x.x.x）和 ZeroTier（10.183.x.x）的流量不做 Masquerade。

### 3. 虚拟接口加入 LAN zone

```bash
uci add_list firewall.@zone[0].network="tailscale0"
uci add_list firewall.@zone[0].network="ztpp6pyh3a"
uci commit firewall
fw4 reload
```

## OpenClash SOCKS5 节点添加：用 API reload

避免 `restart` 触发 watch 进程覆写配置文件：

```bash
curl -s -X PUT http://127.0.0.1:9090/configs \
  -H @/tmp/auth3 \
  -H "Content-Type: application/json" \
  -d '{"path":"/etc/openclash/config.yaml"}'
```

## 结论

即使做了全部改善，移动 5G CGNAT x 电信家宽对称 NAT 之间打洞成功率仍然很低。最终解决方案是境内中继服务器（腾讯云自建 DERP 或 ZeroTier Moon）。
