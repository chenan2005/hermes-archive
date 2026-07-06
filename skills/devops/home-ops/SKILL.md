---
name: home-ops
description: 家庭网络运维与设备管理 — 代理(sing-box/Xray/OpenClash)、路由器(OpenWrt/ImmortalWrt)、DNS/WiFi/WOL/FRP/Cloudflare、Windows远程管理、VPS自建代理、设备资产、归档监控、Android Termux、Hermes配置。触发：用户提到路由器/代理/节点/WiFi/DNS/WOL/远程/SSH/RDP/FRP/OpenWrt/OpenClash/VPS/资产/sing-box/翻墙/带宽/测速/IPv6，或提到设备名(9950x3d/minipc/lenovo/openwrt/immort/bernarty/realme/magicpad)时。
category: devops
---

# home-ops

家庭网络运维与设备管理。一个 hub 覆盖全部运维域，按需加载 references。

## 导航

| 域 | reference | 覆盖内容 |
|----|-----------|---------|
| 代理 — sing-box | [proxy-sing-box](references/proxy-sing-box.md) | sing-box 部署/配置/DNS/分流/TUN/Clash API/5G加速/systemd |
| 代理 — OpenClash | [proxy-openclash](references/proxy-openclash.md) | OpenClash API 安全调用/诊断调试/redir-host/PassWall迁移坑/当前运行配置 |
| 代理 — 规则提供者 | [mihomo-rule-providers](references/mihomo-rule-providers.md) | mihomo/OpenClash rule-provider 来源与 URL（MetaCubeX MRS / Loyalsoldier / AWAvenue） |
| 代理 — 自建 VPS | [proxy-self-hosted](references/proxy-self-hosted.md) | 3X-UI/Xray/VLESS+Reality 部署/VPS 网络测速 |
| 代理 — 测速 | [proxy-test](references/proxy-test.md) | OpenClash 节点带宽测速(Cloudflare CDN 50MB)/SOCKS5 延迟抖动 |
| 网络 — 排坑 | [network-pitfalls](references/network-pitfalls.md) | DNS劫持/fake-IP/安全过滤/编码/nftables/会话保持 排坑汇总 |
| 网络 — DNS 诊断 | [windows-dns-diagnostics](references/windows-dns-diagnostics.md) | Windows DNS Client 行为：nslookup vs ping 差异、IPv6 DNS 优先、后缀搜索列表、hosts 修复 |
| 网络 — FRP/CF | [network-frp](references/network-frp.md) | FRP 内网穿透/Cloudflare Tunnel+CDN 加速 |
| 网络 — WOL/WiFi | [network-wol](references/network-wol.md) | WOL 远程唤醒(Win+OpenWrt+BIOS)/minipc WiFi 切换 |
| 路由器 | [openwrt](references/openwrt.md) | Hyper-V 部署 OpenWrt/ImmortalWrt/PassWall 分流/SNI路由 |
| Windows 管理 | [windows](references/windows.md) | 代理客户端(Xray/sing-box)/SSH 崩溃恢复(WinRM+MD4) |
| 设备资产 | [assets](references/assets.md) | 全设备清单(IP/MAC/SSH)/网络拓扑/DNS链路/WOL/新设备上架 |
| Android/脚本 | [system](references/system.md) | Android Termux/远程脚本执行 |
| AI 工作站 | [ai-workstation](references/ai-workstation.md) | 9950x3d GPU监控/推理引擎选型/Linux迁移/llama-server配置 |
| IPv6 | [ipv6](references/ipv6.md) | OpenWrt IPv6 relay配置/Hyper-V IPv6阻断排坑/光猫管理页面SSH隧道/电信IPv6行为 |

## 脚本

| 脚本 | 路径 | 说明 |
|------|------|------|
| gpu-mon | `scripts/gpu-mon.sh` | 查询 9950x3d GPU + llama-server 状态，支持 watch 模式 |
| fix-ipv6-dns | `scripts/fix-ipv6-dns.ps1` | Windows IPv6 DNS 污染修复：DisabledComponents=0x20 + IPv4 DNS 指向路由器 |
| network-ctrl | `~/network-ops/network-ctrl` | OpenClash 配置管理：pull-from-router / push-to-router + restart。含 git 仓库 `~/network-ops/` |

## 使用方式

1. 从导航表找到对应域 → `skill_view(name='home-ops', file_path='references/xxx.md')`
2. 每个 reference 自带目录，agent 按需阅读具体章节
3. 跨域问题（如代理+网络排坑）→ 加载多个 reference

## 维护指南

### 如何扩展
- **新增内容** → 找到对应 reference 用 `skill_manage patch` 追加，判断是否属于运维域
- **新增子域** → 在 `references/` 下建新文件 + 更新导航表
- **reference 过大** → 超 ~80K 按子域拆分

### 拆分 reference 的 regex 坑
多个 section header 有前缀关系时（如 `sing-box-linux` vs `sing-box-linux-client`），正则 alternation 中长名必须在前：`ab|a`。`a|ab` 会先匹配短名导致长名内容被吞。

### 从 git 恢复误删/损坏内容
```bash
cd ~/hermes-archive
git show 14bdd4f:devops/<name>/SKILL.md > ~/.hermes/skills/devops/<name>/SKILL.md
```
14bdd4f = 合并前原始状态，007b5ab = 首次合并后。

### 域边界判断
合并前逐条审视：家庭网络/设备管理 → 入 hub；Hermes Agent 内部系统 → 独立 skill。错例：kanban-orchestrator、archive-system、hermes-cost-optimization 被错误合并后恢复。详细流程见 `references/hub-maintenance.md`。

