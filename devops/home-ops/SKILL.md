---
name: home-ops
description: 家庭网络运维与设备管理 — 代理(sing-box/Xray/OpenClash)、路由器(OpenWrt/ImmortalWrt)、DNS/WiFi/WOL/FRP/Cloudflare、Windows远程管理、VPS自建代理、设备资产、归档监控、Android Termux、Hermes配置。触发：用户提到路由器/代理/节点/WiFi/DNS/WOL/远程桌面/FRP/OpenWrt/OpenClash/VPS/资产/sing-box/翻墙/带宽/测速时。
category: devops
---

# home-ops

家庭网络运维与设备管理。一个 hub 覆盖全部运维域，按需加载 references。

## 导航

| 域 | reference | 覆盖内容 |
|----|-----------|---------|
| 代理 & 翻墙 | [proxy](references/proxy.md) | sing-box 部署/配置/TUN、OpenClash API/调试/迁移、节点测速、自建 VPS 代理(Xray/3X-UI)、带宽测试 |
| 网络基础设施 | [network](references/network.md) | 排坑汇总、FRP 内网穿透、Cloudflare Tunnel/CDN、WiFi 切换(minipc)、WOL 远程唤醒 |
| 路由器 | [openwrt](references/openwrt.md) | Hyper-V 部署 OpenWrt/ImmortalWrt、PassWall 分流/加速、DNS 架构 |
| Windows 管理 | [windows](references/windows.md) | 代理客户端(Xray/sing-box)、SSH 崩溃恢复(WinRM+MD4)、WiFi 无线电 |
| 设备资产 | [assets](references/assets.md) | 全设备清单(IP/MAC/SSH)、网络拓扑、DNS 链路、WOL 命令、新设备上架流程 |
| 系统运维 | [system](references/system.md) | Hermes 配置优化(token/内存/升级)、归档系统、Android Termux、远程脚本、Webhook |
| Kanban 工作流 | [kanban](references/kanban.md) | 编排者 playbook、worker 指南 |

## 使用方式

1. 从导航表找到对应域 → `skill_view(name='home-ops', file_path='references/xxx.md')`
2. 每个 reference 自带目录，agent 按需阅读具体章节
3. 跨域问题（如代理+网络排坑）→ 加载多个 reference
