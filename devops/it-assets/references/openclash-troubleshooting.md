# OpenClash 节点故障排查

## 常见问题：DNS Fake-IP 劫持导致节点不通

**现象：** 代理节点（尤其是通过 Cloudflare Tunnel 回源的节点）延迟高、测速超时，但节点本身配置正确、服务端正常运行。

**原因：** OpenClash 的 fake-IP 模式劫持了节点服务器的域名 DNS 解析，返回 `198.18.x.x` 网段的假 IP，导致连接流量再次进入 OpenClash 代理循环而非直连节点服务器。

**检查方法：**
```bash
# 查看节点域名是否被 fake-IP
dig +short trycloudflare.com  # 返回 198.18.x.x = 被劫持
dig +short your-proxy-server.com

# 绕过代理直接查真实 IP
curl -s --noproxy '*' --connect-timeout 10 -w "%{http_code} %{time_total}s\n" -o /dev/null https://your-server.com/path
```

**修复方法：**

1. **添加直连规则** — 把节点域名加入 OpenClash 的 DIRECT 规则：
```yaml
rules:
  - DOMAIN-SUFFIX,trycloudflare.com,DIRECT
  - DOMAIN-SUFFIX,your-custom-domain.com,DIRECT
```

2. **或者用 IP 替换域名** — 在节点配置中直接使用服务器 IP 而非域名（仅适用于 IP 固定的节点）。

3. **重启 OpenClash** 使新规则生效：
```bash
/etc/init.d/openclash restart
```

## 常见问题：msiexec 安装 OpenSSH 后 sshd-session.exe 被删

**现象：** SSH 端口 22 可 TCP 连接但 `kex_exchange_identification` 阶段被 reset，sshd 服务 ExitCode 1067。

**原因：** `Register-ScheduledTask -LogonType Interactive` 从 SSH Session 0 触发 Windows Defender ASR，隔离 `sshd-session.exe`。

**修复：** 通过 WinRM 重新下载并安装 GitHub MSI（详见 `devops/winrm-ssh-recovery` skill）。

## 常见问题：sh: out of range（启动时 6 次）

**现象：** OpenClash 启动时 stderr 出现 `sh: out of range` 恰好 6 次，不影响核心运行（mihomo 仍能启动），但会干扰调试。

**原因：** `/etc/init.d/openclash` 中 `add_cron()` 等函数使用 `[ "$(uci_get_config some_option)" -eq 1 ]` 判断 UCI 选项是否开启。如果该 UCI 选项未设置（返回空字符串），BusyBox ash 的 `[ "" -eq 1 ]` 会报 `sh: out of range`。

**涉及选项：**
- `geo_auto_update`
- `geosite_auto_update`
- `geoip_auto_update`
- `geoasn_auto_update`
- `lgbm_auto_update`
- `chnr_auto_update`
- `auto_restart`

**修复：** 给这些 UCI 选项设置默认值 0：
```bash
for key in geo_auto_update geosite_auto_update geoip_auto_update \
           geoasn_auto_update lgbm_auto_update chnr_auto_update auto_restart; do
  uci set openclash.config.$key=0
done
uci commit openclash
```

**注意：** 不要在脚本内用 `sed` 删 `start_service()` 相关行，删除后启动代码会裸跑在脚本顶层，导致 procd 失去服务管理能力。

## 延迟/带宽测试

```bash
# 延迟测试（通过 OpenClash API）
curl -s "http://127.0.0.1:9090/proxies/{节点名}/delay?url=https://cp.cloudflare.com/generate_204&timeout=10000" -H "Authorization: Bearer *** # 带宽测试（直接在 VM 上，不走代理）
wget -q -O /dev/null --timeout=60 http://speedtest.tele2.net/10MB.zip

# 通过特定节点测试（切到该节点后）
curl -s -X PUT "http://127.0.0.1:9090/proxies/PROXY" -H "Authorization: Bearer *** -H "Content-Type: application/json" -d '{"name":"节点名"}'
```
