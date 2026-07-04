---
name: cloudflare-quick-tunnel
title: Cloudflare Quick Tunnel
description: Seoul VPS Cloudflare 快速隧道维护、自动修复脚本与 OpenClash 配置同步
---

# Cloudflare Quick Tunnel → 自动修复方案

## 背景

Seoul VPS (alibaba.bernarty.xyz) 直连国内带宽仅 **0.75Mbps**，需要通过 Cloudflare 隧道加速。当前使用 **Cloudflare 快速隧道**（cloudflared tunnel --url），每次重启 URL 随机变化。

由于 DNS 在 DNSPod（未迁到 Cloudflare），无法使用命名隧道或 CDN 代理。解决方案：**检测 + 自动修复**。

## 自动修复架构

```
每30分钟 ─→ OpenWrt cron: 测试 Seoul-Cloudflare 代理是否通
                ├── 通 → 安静退出
                └── 不通 → SSH到Seoul查日志取新URL
                          → 替换 OpenClash config.yaml
                          → 重启核心
                          → 记录日志
```

## 部署步骤

### 1. SSH 密钥（OpenWrt → Seoul）

```bash
# OpenWrt 上生成密钥
ssh openwrt-t "ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N '' -q && cat ~/.ssh/id_ed25519.pub"

# 把公钥加到 Seoul 的 authorized_keys
ssh alibaba "echo '<pubkey>' >> ~admin/.ssh/authorized_keys && chmod 600 ~admin/.ssh/authorized_keys"
```

注意：OpenWrt 使用 Dropbear，不支持 `~/.ssh/config`。SSH 命令必须显式指定 `-i` 参数：

```bash
ssh -i ~/.ssh/id_ed25519 -o StrictHostKeyChecking=accept-new admin@alibaba.bernarty.xyz "command"
```

### 2. OpenWrt 上部署自愈脚本

脚本见 `scripts/tunnel-watch.sh`。部署并加入 crontab：

```bash
chmod +x /usr/bin/seoul-tunnel-watch
echo '*/30 * * * * /usr/bin/seoul-tunnel-watch' >> /etc/crontabs/root
/etc/init.d/cron restart
```

脚本每 30 分钟：
1. 通过 OpenClash 代理测试 Seoul-Cloudflare 连通性（curl generate_204）
2. 如果失败，SSH 到 Seoul 查 `/var/log/cloudflared.log` 提取新 URL
3. 替换 OpenClash config.yaml 中的旧 URL
4. 重启 clash 核心
5. 记录日志到 `/var/log/seoul-tunnel.log`

### 3. Seoul VPS cloudflared 服务

cloudflared service 已配置日志写入 `/var/log/cloudflared.log`：

```
ExecStart=/bin/sh -c "/usr/local/bin/cloudflared tunnel --url http://127.0.0.1:80 2>&1 | tee /var/log/cloudflared.log"
```

### 4. OpenClash 中 Seoul 节点配置

```yaml
- name: Seoul-Cloudflare
  type: vmess
  server: <tunnel-url>.trycloudflare.com
  port: 443
  uuid: ac6aa939-156c-452f-a7da-4ddd79b7d5c9
  alterId: 0
  cipher: auto
  tls: true
  servername: <tunnel-url>.trycloudflare.com
  network: ws
  ws-opts:
    path: /ws-seoul
    headers:
      Host: <tunnel-url>.trycloudflare.com
```

该节点会通过 Google-Auth 代理组用于 Google 认证分流。

## 手动修复（等不及自动时）

```bash
# 1. 查 Seoul 上的新 URL
ssh alibaba "sudo cat /var/log/cloudflared.log | grep https:// | grep trycloudflare | tail -1"

# 2. 替换 OpenWrt 上的配置
OLD_URL=$(grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' /etc/openclash/config/config.yaml | head -1)
NEW_URL="https://xxx.trycloudflare.com"
sed -i "s|$OLD_URL|$NEW_URL|g" /etc/openclash/config/config.yaml
cp /etc/openclash/config/config.yaml /etc/openclash/config.yaml

# 3. 重启核心
killall clash 2>/dev/null; sleep 2
/etc/openclash/clash -d /etc/openclash -f /etc/openclash/config/config.yaml > /dev/null 2>&1 &
```

## 与其他技能的关系

- `openclash-debug` — 覆盖 OpenClash 通用调试，可引用本技能的自动修复作为 Seoul 节点的维护手段
- `cloudflare-proxy-acceleration` — 覆盖 CDN/隧道方案对比，本技能专攻快速隧道 + OpenClash 侧的自动维护

## 自定义节点管理

添加自定义节点（尤其是 VLESS+Reality）到 OpenClash 的完整步骤、YAML 格式、BusyBox 陷阱和 API 调用方式见 `references/openclash-custom-nodes.md`。

## 故障排查

1. **脚本不执行**: 检查 `/var/log/seoul-tunnel.log` 和 crond 状态
2. **SSH 失败**: 确认 OpenWrt 上的 `~/.ssh/id_ed25519` 权限为 600，公钥在 Seoul 的 authorized_keys 中
3. **隧道 URL 相同仍不通**: 检查 Seoul xray 进程是否在运行
4. **OpenClash 启动后马上退出 (Core Initial Configuration Timeout)**: 检查是否有残留 clash 进程（`killall -9 clash`），以及 `external-ui` 路径是否在 SAFE_PATHS 内（见 `references/openclash-custom-nodes.md` "Clash Meta 兼容性问题"）
5. **OpenClash start 静默跳过 (Disabled)**: 多次启动失败后 OpenClash 进入禁用状态，执行 `uci set openclash.config.enable=1 && uci commit openclash` 恢复
6. **Seoul xray 重启后 VMess 客户端配置丢失**: x-ui 在启动/重启时会从 SQLite 数据库重新生成 `/usr/local/x-ui/bin/config.json`，手动添加的 port 80 VMess 客户端（`clients`）会被覆盖为 `null`。如果需要同时使用 port 40001 (VLESS+Reality, x-ui 管理) 和 port 80 (VMess+WS, CF 隧道后端)，需停止 x-ui 并直接运行 xray（见 `self-hosted-proxy` 技能的 standalone xray 章节）。
