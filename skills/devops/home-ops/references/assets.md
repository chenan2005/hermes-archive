# IT 资产清单

> 最后更新: 2026-07-05
> 变更:
>   - 2026-07-05: minipc xray 独立进程已停用 + Xray-SOCKS5 计划任务已删除；等待通过 v2rayN GUI 手动配置；OpenClash 节点名 lenovo-socks → minipc-socks(21:10808)
>   - 2026-07-04: minipc 已部署 Xray v26.6.1（VLESS+Reality SOCKS5 10808），计划任务 SYSTEM 持久化；OOB 章节确认 PowerShell 可连 WiFi
>   - 2026-07-04: minipc 连 CMCC-C46N-5G（家庭移动宽带 192.168.1.2），sing-box 已删除，计划装 v2rayN；OOB 章节新增 SSH+PowerShell 连 WiFi 的方法
>   - 2026-07-04: 本机 DNS 更新：新增 223.5.5.5 作为系统 DNS（与光猫 71.1 并列，当前实际使用 223.5.5.5）；静态路由 37.x 曾丢失，已恢复并验证
>   - 2026-07-04: 9950x3d sing-box 已删除，静态路由已清理
>   - 2026-07-01: 本机添加 sing-box 代理完整配置（三节点、分流、DNS新格式、管理脚本），更新 DNS 链路说明
>   - 2026-07-01: 9950x3d 添加 sing-box + 双路径路由方案（有线默认/WiFi热点走VLESS静态路由），测速 930Mbps VLESS+Reality 通过<br>
>   - 2026-07-01: 本机添加永久静态路由 `192.168.37.0/24 via 192.168.71.9`（nmcli con mod +ipv4.routes），从 71.x 可直达 37.1
>   - 2026-07-01: 真我 GT7 添加 5G 热点信息（SSID/密码）
>   - 2026-06-30: minipc 网络架构修正: 移除无效 `bind_interface` 引用, 改为静态路由 `43.108.41.245 → 192.168.1.1` 方案, 已验证 855KB 代理数据经 WLAN
>   - 2026-06-28: 在 ImmortalWrt 部署 /root/.local/bin/（bwtest + wol），统一通过路由器执行
>   - 2026-06-28: minipc 取消 37 网段辅助 IP，仅保留 71.21
>   - ImmortalWrt 24.10 接替 OpenWrt 22.03.5 成为生产路由（旧OpenWrt已关停）
>   - WAN网关改71.1(OLT), LAN IP改37.1, 本机WiFi切光猫71.x, minipc+9950x3d网关改71.9
>   - 71↔37网段互通已验证（新VM已有lan→wan+wan→lan双向转发, NAT可用）
> 新增: DESKTOP-EC5NQUM (i9-9900K)、GreeNet 光猫、光猫WiFi密码、minipc OOB管理通道

## 网络架构

```
运营商光纤
    │
    ├── 光猫华为HN8145X6N (PON桥接模式)
    │   ├── WAN: 192.168.71.5 (PON侧管理IP)
    │   ├── 管理/WiFi: 192.168.1.1 (独立管理通道)
    │   └── LAN口直接桥接PON侧71.x网段
    │
    71网段 (192.168.71.0/24) — 光猫/OLT 直连
    │  网关: 71.1 (GreeNet OLT侧设备)
    │  光猫WiFi (ChinaNet-pfwQ-5G) 分配71.x IP，非隔离192.168.1.x
    │
    ├── minipc (71.21)      Ryzen 7940HS / Win11 / Hyper-V 宿主机
    ├── 9950x3d (71.41)     Ryzen 9950X3D / Win11 / RTX 5090
    ├── 本机 (71.24)         Linux Mint / WiFi (光猫直连) / sing-box
    ├── 光猫自身 (71.5)      PON侧管理IP
    ├── 光猫/OLT (71.1)      网关
    ├── 71.17               未知设备
    │
    ├── ImmortalWrt 生产 (71.9) → 网关 71.1 → OpenClash
    │   └── LAN: 192.168.37.1 → DHCP → 37网段设备 (37↔71互通, 新VM双向转发+NAT)
    │   └── OpenClash面板: http://192.168.71.9:9090/ui
    ═══ 以下设备已关停 ═══
    ✗ OpenWrt 22.03.5 (71.11) — 2026-06-26 退役，接替者 ImmortalWrt 24.10 (71.9)

    37网段 (192.168.37.0/24) — 家庭局域网 (通过ImmortalWrt访问)
    │
    ├── DESKTOP-EC5NQUM (37.200)  i9-9900K / Win11 / WOL可用
    ├── 真我 GT7 (37.205:8022)    Android / FRP:30205
    └── 荣耀平板 (37.177:8022)    Android / FRP:30177
```

### DNS 链路

```
直连流量:
  应用 → systemd-resolved(127.0.0.53) → 光猫(71.1) → 电信DNS → 国内站正常/国外站可能污染

代理流量:
  走SOCKS5/Mixed的应用 → sing-box → 223.5.5.5(AliDNS, UDP直发) → 代理节点 → 真实解析
```

- 系统 DNS：192.168.71.1（光猫/电信默认） + 223.5.5.5（AliDNS），当前 resolvectl 实际使用 223.5.5.5
- sing-box 独立管理 DNS：`type: "udp" server: "223.5.5.5"`，直发不经过光猫
- AliDNS 不污染，无论国内国外域名都返回真实 IP
- 代理流量拿到真实 IP 后通过 VLESS 隧道出去，可到达被封锁站点
- systemd-resolved 已配置 `.lan.11` 域名走 71.9 解析

### 本机代理链路 (sing-box)

```
本机(71.24) ← 光猫WiFi
    │
    └── sing-box (systemd user service, 开机自启, linger=yes)
        ├── SOCKS5  0.0.0.0:10880  (LAN 可访问)
        ├── Mixed   0.0.0.0:10881  (SOCKS5 + HTTP CONNECT 自动识别, LAN 可访问)
        └── Clash API  127.0.0.1:9090
        │
        ├── 默认节点: VMISS-HK (VMess+WS+TLS, vmiss.bernarty.xyz:443)
        ├── 备选:     233boy-KVM (VMess+WS+TLS, kvm.bernarty.xyz:30717)
        └── 备选:     Alibaba-Seoul-VLESS (VLESS+Reality, 43.108.41.245:40002)

分流策略:
  规则集 geoip-cn (7456条中国CIDR)  → direct 直连
  规则集 geosite-cn (6009中国域名 ×2) → direct 直连
  其余流量 → 走默认节点

管理: ~/.local/bin/sing-box-ctrl
  无参数/help    → 帮助
  switch         → 看当前节点
  switch <节点>   → 切节点
  start/stop/restart/status → 管理服务
外网穿透 (腾讯云 bernarty.xyz 122.51.232.209)
    ├─ bernarty:30234 → 本机:22     (SSH内网跳板)
    ├─ bernarty:30389 → minipc:3389 (RDP)
    ├─ bernarty:30205 → 手机:8022   (SSH)
    └─ bernarty:30177 → 平板:8022   (SSH)
```

### 代理节点优先级

| 优先级 | 节点 | 说明 |
|--------|------|------|
| 1 | VMISS 香港 (38.47.108.89 / vmiss.bernarty.xyz) | VMess-WS-TLS 443, BGP接入, 本机默认出口, ~29Mbps |
| 2 | KVM (154.40.40.38 / kvm.bernarty.xyz) | VMess-WS-TLS 30717, 最快最稳, 主力备选 |
| 3 | 阿里云首尔 (43.108.41.245) | VLESS+Reality 40002, 直连时家宽~40Mbps/5G~120Mbps |

### 带宽说明

家庭宽带为**电信**，对韩（阿里云首尔）回程出口拥挤。实测对比：
- 家宽出站：~40Mbps（电信韩线出口瓶颈）
- 手机 5G（移动）：~120Mbps
- 结论：电信韩线出口是瓶颈，非节点质量问题

本机 sing-box 通过 **5G** 测速 **300Mbps**（Speedtest 上海联通），VMISS-HK 节点非瓶颈。

## SSH 免密登录总览

所有设备统一使用 `~/.ssh/id_ed25519`。已配置免密登录的设备：

| 设备 | SSH Alias | 用户名 | 方式 |
|------|-----------|--------|------|
| 9950x3d (71.41) | `ssh 9950x3d` | chen_ | authorized_keys |
| minipc (71.21) | `ssh minipc` | chen_ | authorized_keys |
| ImmortalWrt 生产 (37.1/71.9) | `ssh openwrt` → 37.1（仅 37 子网可达，从 71.x 直连超时）; 通用用 `ssh root@192.168.71.9` | root | authorized_keys |
| 本机笔记本 (71.24) | 本地 | chenan | 本地 |
| DESKTOP-EC5NQUM (37.200) | `ssh chenan@192.168.37.200`（无独立 Host alias） | chenan | administrators_authorized_keys |
| 腾讯云 (122.51.232.209) | `ssh bernarty` | ubuntu | authorized_keys |
| KVM VPS (154.40.40.38) | `ssh kvm` | root | authorized_keys |
| 阿里云 ECS | `ssh alibaba` | admin | authorized_keys |
| VMISS 香港 | `ssh root@vmiss.bernarty.xyz` | root | authorized_keys |
| 阿里云首尔 | `ssh alibaba`（同阿里云ECS） | admin | authorized_keys |
| Android 手机 直连(37.205:8022) | `ssh realme` | chen_ | authorized_keys |
| Android 手机 FRP(bernarty:30205) | `ssh realme-frp` | chen_ | authorized_keys |
| 荣耀平板 直连(37.177:8022) | `ssh magicpad` | u0_a250 | authorized_keys |
| 荣耀平板 FRP(bernarty:30177) | `ssh magicpad-frp` | u0_a250 | authorized_keys |

### Windows 免密登录要点

1. 普通用户: `%USERPROFILE%\\.ssh\\authorized_keys`
2. **管理员用户**: 必须用 `C:\\ProgramData\\ssh\\administrators_authorized_keys`
3. 该文件必须是 **UTF-8 无 BOM** 编码，仅含 SYSTEM + Administrators 权限
4. 写完后重启 sshd: `Restart-Service sshd`

### 反向 SSH：Android Termux → 本机

Android 设备通过 FRP 隧道回连本机，用于在手机上操作本机 tmux。

| 设备 | Termux连接方式 | 公钥位置 | FRP入口 |
|------|---------------|---------|---------|
| 荣耀平板 | `ssh laptop` / `rta` / `rtc` | id_ed25519@平板 → laptop authorized_keys | bernarty:30234 |
| 真我GT7 | `ssh laptop` / `rta` / `rtc` | id_ed25519@手机 → laptop authorized_keys | bernarty:30234 |

设备上配置：
- `~/.ssh/config` → `Host laptop`（指向 FRP server:30234）
- `~/.bashrc` → `rta()` / `rtc()` 函数（tmux attach/create 快捷指令）

详见 `android-termux-dev` skill 的 "Reverse SSH: Termux → Laptop via FRP" 章节。

## 设备清单

### 设备1: 9950x3d 工作站

| 项目 | 详情 |
|------|------|
| IP | 192.168.71.41 |
| 局域网域名 | 9950x3d.lan.11 |
| 主机名 | 9950x3d |
| 类型 | Windows 11 Pro |
| CPU | AMD Ryzen 9 9950X3D (16C/32T) |
| RAM | 96 GB DDR5-5600 (2×48GB) |
| GPU | NVIDIA RTX 5090 (32GB) + AMD Radeon iGPU |
| 硬盘 | Predator GM9 NVMe 2TB + WDC 16TB HDD + TO External 18TB |
| 主板 | MSI MPG X870E CARBON WIFI |
| 网卡 | 有线: Realtek PCIe 2.5GbE, WiFi: Qualcomm FastConnect 7800 Wi-Fi 7 HBS（5个虚拟WLAN，用基础WLAN连WiFi） |
| 用户 | chen_ |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh 9950x3d` |
| Hermes | 已卸载 |
| sing-box | 已删除 (2026-07-04)，VLESS 静态路由已清理 |
| 代理 | 走 71.9 OpenClash（有线 metric 40 默认路由） |
| 本地 LLM | Qwen3.6-27B Q4_K_M on llama.cpp, port 8080, ~25GB VRAM → `qwen-service` skill |

### 设备2: 本机笔记本

| 项目 | 详情 |
|------|------|
| IP | 192.168.71.24（固定） |
| 局域网域名 | lenovo.lan.11 |
| 主机名 | chenan-Lenovo-XiaoXinPro-13API-2019 |
| 类型 | Linux Mint 22.3 Cinnamon, kernel 6.8.0-124 |
| CPU | AMD Ryzen 5 3550H (4C/8T) |
| RAM | 16 GB |
| 硬盘 | Kingston SA2000 NVMe 1TB (/ 181G, /data 600G) |
| 网卡 | WiFi: ChinaNet-pfwQ-5G, 71.24/24（固定IP，不走DHCP） |
| Hermes | 默认 profile |
| 角色 | 内网跳板机 + FRP 入口 + sing-box 代理 |
| FRPC 配置 | `/etc/frp/frpc.toml` — systemd 服务 (root), 单隧道: 本机:22 → bernarty.xyz:30234, 默认 auto-reconnect |
| DNS 配置 | systemd-resolved, `resolvectl domain wlp1s0 ~lan.11` 让 `.lan.11` 走 71.9 解析; 系统DNS: 192.168.71.1 + 223.5.5.5（resolvectl 当前实际使用 223.5.5.5） |
| 静态路由 | `192.168.37.0/24 via 192.168.71.9` — 永久写入 ChinaNet-pfwQ-5G 连接（`nmcli con mod +ipv4.routes`）。从 71.x 访问 37.x 子网（含 ImmortalWrt LAN 口 37.1）必经此路由 |
| **sing-box** | `systemctl --user sing-box.service` 开机自启（linger=yes）|
| SOCKS5 端口 | `0.0.0.0:10880`（LAN 可访问） |
| Mixed 端口 | `0.0.0.0:10881`（LAN 可访问） |
| Clash API | `127.0.0.1:9090` |
| 默认节点 | VMISS-HK (VMess+WS+TLS, vmiss.bernarty.xyz:443) |
| 备选节点 | 233boy-KVM (VMess+WS+TLS, kvm.bernarty.xyz:30717) |
| 备选节点 | Alibaba-Seoul-VLESS (VLESS+Reality, 43.108.41.245:40002) |
| 配置路径 | `~/.config/sing-box/config.json` |
| 规则集 | `~/.config/sing-box/ruleset/geoip-cn.srs` (7456 CIDR) + `geosite-cn.srs` (6009域名×2) |
| 管理脚本 | `~/.local/bin/sing-box-ctrl`（switch/start/stop/restart/status） |
| 节点来源 | 从 config.json outbounds 动态读取（排除 direct/block） |

### 设备3: ImmortalWrt 24.10 (生产路由) [接替旧OpenWrt]

| 项目 | 详情 |
|------|------|
| IP | WAN: 192.168.71.9, LAN: 192.168.37.1 |
| 局域网域名 | immort.lan.11 |
| CPU | AMD Ryzen 9 7940HS (2 核) |
| RAM | 680 MB (Hyper-V 动态内存, 可扩展至 ~1 GB) |
| OS | ImmortalWrt 24.10.0 x86/64 |
| SSH | root, key auth, `ssh root@192.168.71.9` 通用（71.x/37.x 两边都通）；`ssh openwrt` → 37.1（已配本机静态路由 `37.0/24 via 71.9`，71.x 也可直达 37.1） |
| WAN 防火墙 | 71.0/24 全端口开放（`Allow-WAN-Device-lan71`），含 22/80/443/9090/7874 |
| 代理 | OpenClash (已启用) |
| DHCP | 37.100-250, 12h 租约, dnsmasq |
| 本地脚本 | `/root/.local/bin/` 已加入 PATH，含 `bwtest`(测速) `wol`(唤醒) `isonline`(在线检测) |
| 宿主机 | 设备4 minipc |

### 设备4: minipc 迷你主机

| 项目 | 详情 |
|------|------|
| IP | 192.168.71.21 |
| 局域网域名 | minipc.lan.11 |
| 主机名 | minipc |
| 类型 | Windows 11 Pro |
| CPU | AMD Ryzen 9 7940HS (8C/16T) |
| RAM | 64 GB |
| GPU | AMD Radeon 780M |
| 硬盘 | ZHITAI TiPlus7100 NVMe 1TB |
| 主板 | Shenzhen Meigao F7BSC |
| 用户 | chen_ |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh minipc` |
| 备注 | Hyper-V 单 ImmortalWrt VM（原双 OpenWrt VM，旧已退役）；WinRM (5985, Session 1) 可调 WiFi 无线电开关（见下方#带外管理通道） |
| **网络架构** | **有线（Realtek 2.5GbE）= 默认上网通道，走到网关 71.9（OpenClash），metric ~25。WiFi（WLAN）= 连 CMCC-C46N-5G（家庭移动宽带，192.168.1.2/24），metric 5000 不干扰默认路由。** |
| **代理** | ⚠️ **已停用**（2026-07-05）— xray 进程已终止 + Xray-SOCKS5 计划任务已删除。待通过 v2rayN GUI 手动配置。保留配置文件: `C:\Users\chen_\v2rayN\guiConfigs\5g-seoul.json`（VLESS+Reality → 43.108.41.245:40002，SOCKS5 10808）。静态路由 `route -p add 43.108.41.245 → 192.168.1.1 metric 50` 仍有效。曾用 Xray v26.6.1（schtasks SYSTEM 管理，v2rayN v7.22.7 GUI 未用）、sing-box（8897/8890，已删）。 |

### 设备5: 腾讯云服务器

| 项目 | 详情 |
|------|------|
| 域名 | www.bernarty.xyz |
| 公网 IP | 122.51.232.209 |
| 主机名 | VM-4-17-ubuntu |
| 类型 | 腾讯云轻量服务器 |
| CPU | 2 核 |
| RAM | 2 GB |
| 硬盘 | 50 GB |
| OS | Ubuntu 20.04.6 LTS |
| 用户 | ubuntu |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh bernarty` |
| 用途 | FRP 穿透入口 |

### 设备6: Android 手机 (真我 GT7) — 5G 热点源

| 项目 | 详情 |
|------|------|
| IP | 192.168.37.205 |
| 局域网域名 | realme.lan.11 |
| SSH 端口 | 8022 |
| 类型 | Android aarch64 |
| CPU | MediaTek 天玑 9400+ |
| RAM | 12 GB + 12G 虚拟 |
| 存储 | 512 GB |
| 用户 | chen_ |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh realme`（直连）/ `ssh realme-frp`（FRP） |
| FRP | bernarty:30205 → 8022 |
| FRPC 恢复 | frpc 卡死时，ssh 进手机执行 `pkill -f \\\"proot.*frpc\\\" && sleep 1 && nohup proot -b ~/my-etc:/etc ~/frp/frpc -c ~/frp/frpc.ini > ~/frp/frpc.log 2>&1 &` |
| 5G 热点 | SSID: `realme GT 7 FDC6`, 密码: `iehx7624` |
| Termux 配置 | extra-keys 布局/脚本约定→`android-termux-dev` skill |

### 设备7: 荣耀平板

| 项目 | 详情 |
|------|------|
| IP | 192.168.37.177 |
| 局域网域名 | magicpad.lan.11 |
| SSH 端口 | 8022 |
| 类型 | Android aarch64 |
| 主机名 | rong-yaoMagicPad3-Pro-12-3 |
| 用户 | u0_a250 |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh magicpad`, 反向免密: `ssh -p 30234 chenan@www.bernarty.xyz` |
| FRP | bernarty:30177 → magicpad:8022 |
| 备注 | 荣耀 MagicPad 3 Pro 12.3", Termux sshd 需手动重启「sshd」 |
| Termux 配置 | extra-keys 布局/脚本约定→`android-termux-dev` skill |

### 设备8: KVM VPS

| 项目 | 详情 |
|------|------|
| 域名 | kvm.bernarty.xyz |
| IP | 154.40.40.38 |
| 类型 | KVM VPS |
| CPU | 2 核 |
| RAM | 2 GB |
| 硬盘 | 20 GB |
| OS | Ubuntu 20.04.6 LTS |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh kvm` |
| 用途 | 翻墙代理 (V2Ray VMess-WS-TLS + Caddy) |
| 到期 | ⚠️ 计划 2026年9月后不续费（IP段被Google屏蔽） |

### 设备9: 阿里云 ECS

| 项目 | 详情 |
|------|------|
| 域名 | alibaba.bernarty.xyz |
| 主机名 | iZmj75torp3cd3kibv0bd6Z |
| 类型 | 阿里云 ECS |
| CPU | 2 核 |
| RAM | 2 GB |
| 硬盘 | 40 GB |
| OS | Ubuntu 24.04.2 LTS |
| 用户 | admin |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh alibaba` |

### 设备10: VMISS 香港 VPS

| 项目 | 详情 |
|------|------|
| 域名 | vmiss.bernarty.xyz |
| IP | 38.47.108.89 |
| 类型 | VMISS Hong Kong BGP DC1 |
| CPU | 1 核 |
| RAM | 1 GB |
| 硬盘 | 10 GB |
| OS | Ubuntu 24.04 LTS |
| 用户 | root |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh root@vmiss.bernarty.xyz` |
| xray | 手动运行，VMess+WS+TLS 443 /ws-vmiss |
| 用途 | **主力代理** (29Mbps, TTFB 0.5s) |

### 设备11: 阿里云首尔 ECS

| 项目 | 详情 |
|------|------|
| IP | 43.108.41.245 |
| 类型 | 阿里云 ECS Seoul |
| CPU | 2 核 |
| RAM | 2 GB |
| 硬盘 | 40 GB |
| OS | Ubuntu 24.04.2 LTS |
| 用户 | admin |
| SSH | key: ~/.ssh/id_ed25519, alias: `ssh alibaba` |
| xray (x-ui) | 80(VMess+WS, CF Tunnel回源) / 40001(VLESS+Reality) |
| cloudflared | systemd |
| 用途 | Google 认证分流 (Cloudflare Tunnel) |

### 设备12: 旧 OpenWrt 22.03.5 (已退役) [见设备3]

| 项目 | 详情 |
|------|------|
| 状态 | ❌ **已退役** — 2026-06-26 关停，由设备3 (ImmortalWrt 24.10) 接管 |
| IP | WAN: 192.168.71.11, LAN: 192.168.37.1 (均已释放) |
| 历史 OS | OpenWrt 22.03.5 x86/64 |
| 退役原因 | PassWall → OpenClash 迁移 + 系统版本升级 |
| 历史服务 | PassWall, v2ray, xray, smartdns, alist, nginx, zerotier |

### 设备13: DESKTOP-EC5NQUM (i9-9900K 台式机) [新增]

| 项目 | 详情 |
|------|------|
| IP | 192.168.37.200 |
| 主机名 | DESKTOP-EC5NQUM |
| MAC | e0:d5:5e:d3:d7:4e (Intel) |
| 类型 | Windows |
| CPU | Intel Core i9-9900K |
| 用户 | chenan |
| SSH | key: ~/.ssh/id_ed25519, `ssh chenan@192.168.37.200`（无独立 Host alias） |
| WOL | ✅ 已验证支持 |
| 网段 | 192.168.37.0/24 |

### 设备14: 华为 HN8145X6N 光猫 (天翼网关)

| 项目 | 详情 |
|------|------|
| IP | 192.168.71.1 (OLT侧网关) |
| 光猫自身 WAN IP | 192.168.71.5 (PON侧管理IP) |
| 光猫自身 MAC | B8:56:00:E1:1E:71 (华为) |
| OLT侧网关 MAC | 7c:c9:26:ef:03:16 (GreeNet) |
| 管理页面 | http://192.168.1.1 |
| 管理用户/密码 | useradmin / 7nia7 |
| 超级管理员 | telecomadmin / nE7jA%5m (推测) |
| 型号 | HN8145X6N (10G-EPON, 双频WiFi6) |
| 软件版本 | V5.23.C00S120 |
| 类型 | 光猫 ONU/ONT (PON桥接模式) |
| 角色 | 互联网入口，连接运营商光纤 |
| 连接设备 | minipc/9950x3d/OpenWrt×2 + 1未知 (71.x网段) |
| WiFi | ChinaNet-pfwQ (2.4G) / ChinaNet-pfwQ-5G（密码: 36ugq6ra） |
| SSH | ❌ 不支持 |

> 之前以为光猫 WiFi（192.168.1.x）是隔离管理通道。2026-06-26 实测：**光猫 WiFi 分配 71.x 网段 IP**，LAN 与 WiFi 在同一 71.x 广播域（已验证互通）。
> **桥接模式注意**：光猫 LAN 口桥接到 PON 光纤（71.x），WiFi 同样分配 71.x 网段 IP，LAN 与 WiFi 可互通（已验证）。

### 带外管理通道 (OOB)

minipc 通过 Killer AX1675x WiFi 连光猫 ChinaNet-pfwQ-5G，作为 OpenWrt 崩溃时的救场通道。

| 组件 | 详情 |
|------|------|
| 管理端 | minipc (WLAN, 71.x) |
| 场景 | OpenWrt 37.x/71.x 全断时，从 minipc WiFi (71.x) 直连光猫侧网络 → Hyper-V 操作 OpenWrt VM |
| 路由策略 | WiFi 跃点数 9999，已删默认网关（不走光猫上外网） |
| 自动启用 | Run密钥 `HKCU:\...\Run\EnableWiFi` → `enable-wifi-startup.ps1`（需桌面 Session 登录触发） |

**WiFi 切换脚本模板**：`templates/switch-wifi-template.sh` — 用于本机切换到光猫 WiFi。验证条件从 ping 改为 **FRP 隧道端口 (www.bernarty.xyz:30234)** 可达性检查，含 180s 看门狗自动回退，nohup+disown 确保 SSH 断连后仍生效。

**WiFi 控制（Session 0 vs Session 1）**：
- **SSH（Session 0）直接 `netsh wlan connect`** — ❌ 报错"系统上没有此类无线接口"。
- **SSH（Session 0）+ PowerShell 包装** — ✅ `powershell -Command "netsh wlan connect name='SSID'"` 可以成功连接已保存的 WiFi 配置（已验证 2026-07-04，minipc 连 CMCC-C46N-5G）。
- **WinRM（5985）** — ✅ 可调用 WinRT Radio API 开关 WiFi，因为 WinRM 运行在 Session 1（交互会话）。
- **Run 密钥** — ✅ `HKCU:\...\Run\EnableWiFi` → `enable-wifi-startup.ps1`（需桌面 Session 登录时触发）。
- WinRM 切换 WiFi 的具体方法见 `devops/winrm-ssh-recovery` skill 中的 "Toggle WiFi radio" 章节。

## WOL 唤醒命令

| 设备 | MAC | 命令 | 说明 |
|------|-----|------|------|
| DESKTOP-EC5NQUM (37.x) | e0:d5:5e:d3:d7:4e | `ssh openwrt 'wol e0:d5:5e:d3:d7:4e'` | br-lan → 37.x |
| 9950x3d (71.x) | 34:5a:60:b5:8d:13 | `ssh openwrt 'wol 34:5a:60:b5:8d:13 eth1'` | eth1 → 71.x |
| 9950x3d（备选） | 34:5a:60:b5:8d:13 | `ssh minipc 'powershell -ExecutionPolicy Bypass -File C:\\\\Users\\\\chen_\\\\wol.ps1'` | 经minipc中继 |

> WOL 后验证：`ssh openwrt 'isonline <MAC>'`（见 Step 1 验证在线节）

## 子技能索引（按设备类型引用）

- OpenClash / ImmortalWrt 配置修改技巧: `references/immortalwrt-config-tricks.md`

| 设备/操作类型 | 子 skill | 说明 |
|-------------|---------|------|
| Android Termux 开发环境 | `software-development/android-termux-dev` | 安装、tmux、extra-keys、脚本约定、反向SSH |
| Windows SSH 恢复（Defender 杀 sshd） | `devops/winrm-ssh-recovery` | WinRM 重连、WiFi 无线电、MD4 补丁 |
| Windows 远程管理（WiFi/SSH/RDP） | `windows-remote-control` | 远程 PowerShell、FreeRDP headless、WiFi 无线电 API |
| WOL 远程唤醒 | `devops/wol-wake` | ARP 探测、魔术包发送、排坑 |
| 会话归档系统 | `devops/archive-system` | 项目文档 + 操作指南 + watchdog |
| 家庭网络运维排坑 | `devops/network-pitfalls` | 常见错误汇总 |
| 路由器脚本（bwtest/wol/isonline） | `devops/proxy-bandwidth-test` | `/root/.local/bin/` 下的 bwtest、wol、isonline |

**路由器的 `/root/.local/bin/` 脚本：**
- `bwtest` — OpenClash 节点带宽测速
- `wol <MAC> [iface]` — WOL 唤醒，默认 `br-lan`（37.x），`eth1` 用于 71.x
- `isonline <MAC|IP>` — 检查设备是否在线（ping + ARP）
- 这些脚本已加入 PATH（`/etc/profile`），SSH 登录后可直接执行
- ⚠️ **非交互 SSH**：`/etc/profile` 只对 login shell 生效，`ssh root@ip 'isonline ...'` 会报 `ash: isonline: not found`。必须显式加 PATH：`ssh root@ip 'PATH=$PATH:/root/.local/bin isonline ...'`

**分层访问路径**：设备操作→it-assets（本 skill）→按设备类型查子 skill→执行具体操作。

## 维护原则

### 远程改网安全原则

- **改前先看脚本**：任何远程网络变更（WiFi 切换、网关修改、路由调整），先完整过一遍脚本逻辑再执行
- **必有回退机制**：每个变更操作必须有明确的回退方案（脚本内含 180s 看门狗自动回滚）
- **断网可恢复**：在外不能接触本机时，方案必须保证即使断网也能自动恢复
- **不依赖本机**：本机只做触发，目标设备上的自治方案持续运行

### 维护脚本设计原则

**状态变更脚本必须记原值，仅变化时恢复**
临时修改路由器状态（如 bwtest 切 OpenClash 节点）的脚本必须：
1. 执行前记录原始状态（`orig=$(get_current())`）
2. 执行后检查是否漂移（`if [ "$now" != "$orig" ]`）
3. 仅漂移时才恢复，否则静默跳过
不要无条件恢复固定值（如总是恢复 AUTO），这会在原状态不是该值时造成额外切换。

### 维护脚本部署策略

**维护脚本应部署在目标设备上**（如 OpenWrt cron），而非本机 Hermes cron。
本机只做触发（如 SSH 调用），不应作为中间人定时调度。这样即使本机关机或断网，目标设备上的自治方案继续运行。

### 资产清单更新触发条件

有新设备上线、IP 变动、SSH 配置变化时，**立即更新本 SKILL.md**（用 `skill_manage patch`）。
资产清单是 all devices 的唯一来源（`references/` 目录下有详细文档）。

## 网络管理规则

> **跨版本注意**：OpenWrt 24.10+ 的 dnsmasq 处理 `list host` 的方式与 22.03 不同 — FQDN（\*.lan.11）默认不解析。迁移静态 DNS 记录到新版本时参见 `references/openwrt-dnsmasq-migration.md`。

### DHCP 静态绑定原则

**只有资产清单里登记的设备才加 OpenWrt DHCP 静态绑定。** 其他临时设备（访客手机、IoT 设备等）使用动态 DHCP 即可，不要往路由器的里加静态 host。

批量添加命令（SSH 到 ImmortalWrt 192.168.71.9）：

```bash
# 新增单个绑定
uci add dhcp host
uci set dhcp.@host[-1].name='设备名'
uci set dhcp.@host[-1].mac='xx:xx:xx:xx:xx:xx'
uci set dhcp.@host[-1].ip='192.168.37.xxx'
uci commit dhcp
/etc/init.d/dnsmasq reload

# 批量添加（用 for 循环）
for entry in "设备名 mac ip"; do
  name=$(echo $entry | cut -d" " -f1)
  mac=$(echo $entry | cut -d" " -f2)
  ip=$(echo $entry | cut -d" " -f3)
  uci add dhcp host
  uci set dhcp.@host[-1].name="$name"
  uci set dhcp.@host[-1].mac="$mac"
  uci set dhcp.@host[-1].ip="$ip"
done
uci commit dhcp
/etc/init.d/dnsmasq reload

# 删除绑定（从后往前删避免索引漂移）
uci delete dhcp.@host[索引]
uci commit dhcp
/etc/init.d/dnsmasq reload
```

**Pitfall**: OpenWrt 的 ash 不支持 `/dev/tcp` 或 `seq`。端口扫描用 `nc -z` 或 `curl`。删除 host 必须从后往前删索引。添加完成后必须 `uci commit dhcp && /etc/init.d/dnsmasq reload` 才能生效。

## 新设备上架流程

### Template: WiFi switch with auto-fallback

When remotely switching WiFi (e.g. from OpenWrt LAN to 光猫 WiFi), use `templates/switch-wifi-template.sh`. It records the current connection, switches, and runs a nohup-based watchdog that auto-rolls back after 180s if connectivity fails. This survives SSH disconnect.

发现新设备（如新电脑、服务器）上线时，按这个流程操作：

### Step 1: 唤醒 & 发现
```
1. 确定设备 IP（从路由器 DHCP 租约 / ARP 表查）
2. 如需 WOL：查 MAC（从 it-assets 或路由器 ARP 表），发魔术包
   - 37.x同子网: sudo etherwake -i wlp1s0 <MAC>
   - 71.x跨子网: 通过 minipc 中继 (PowerShell wol.ps1) 或 OpenWrt 直接广播
3. 等待 60-90s 让机器开机
4. 验证在线 — 用路由器上的 `isonline` 脚本（不受 Windows 防火墙影响）：
   ```bash
   ssh openwrt 'isonline <MAC>'
   # 示例：
   ssh openwrt 'isonline e0:d5:5e:d3:d7:4e'   # DESKTOP-EC5NQUM
   ssh openwrt 'isonline 34:5a:60:b5:8d:13'    # 9950x3d
   ```
   - 输出 `ONLINE  IP  MAC` → 在线
   - 输出 `OFFLINE` → 不在线

   > ⚠️ 不要用 `ip neigh del` 探测——该命令在 ImmortalWrt 上会永久挂起。
```

### Step 2: 配置 SSH 免密登录

**方向 A: 本机 → 新设备 (inbound SSH)**
本机 SSH 到新设备，适合本机能直接或通过 FRP 连到新设备的情况。
```

**确认方向** — "配置免密登录"可能指两个方向，必须先确认：
- **正向（本机→设备）**: 把本机的公钥 push 到设备上
- **反向（设备→本机）**: 在设备上生成密钥，把设备的公钥加进本机 authorized_keys

正向（本机→设备）：
```
1. 向用户索要密码（存在 /tmp/tmp-passwd）
2. 读取本机公钥: cat ~/.ssh/id_ed25519.pub
3. 用 sshpass 传公钥到目标设备
4. 测试免密登录: ssh <user>@<IP> "hostname"
5. 删除密码文件: rm /tmp/tmp-passwd
```

**反向（设备→本机）** — 设备需要能 SSH 回到本机：
```
1. SSH 进目标设备（用已有正向免密或 FRP 隧道）
2. 检查设备上是否已有密钥对: ls ~/.ssh/id_ed25519
3. 如无则生成: ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519 -N '' -q
4. 读取设备的公钥: cat ~/.ssh/id_ed25519.pub
5. 追加到本机 ~/.ssh/authorized_keys
6. 测试反向免密: 从设备 ssh chenan@<本机IP> "hostname"
```

**连接落点选择** — 设备可能不在同一局域网：
- 优先 FRP 隧道（公网穿透，不依赖局域网可达）
- 局域网直连在设备离线或跨网段时会超时
- 有 FRP 隧道时直接走 FRP SSH 进设备做反向配置

Windows 管理员用户见 `references/windows-ssh-admin-setup.md`。

### Step 3: 登记 DHCP 静态绑定 (SSH 到 OpenWrt 37.1)
```
仅限资产清单里登记的设备。
uci add dhcp host
uci set dhcp.@host[-1].name='设备名'
uci set dhcp.@host[-1].mac='xx:xx:xx:xx:xx:xx'
uci set dhcp.@host[-1].ip='192.168.37.xxx'
uci commit dhcp && /etc/init.d/dnsmasq reload
```

### Step 4: 更新资产清单 skill
```
用 skill_manage patch 更新 it-assets skill：
  1. 更新"最后更新"日期
  2. 添加新设备条目（跟在设备14之后）
  3. 如有 WOL 能力，追加到 WOL 唤醒命令表
  4. 如有 SSH，追加到 SSH 免密登录总览表
```

### Step 5: 清理
```
rm /tmp/tmp-passwd
```

## Pitfalls

> 💡 常见问题汇总见 `devops/network-pitfalls` skill（SSH崩溃修复、OpenClash fake-IP劫持、nmcli中文编码、光猫WiFi网段勘误、安全机制***误杀等）。

> - **设备信息引用前先加载本 skill 确认**：不要凭上下文记忆推测设备参数（如网卡数量、IP、OS），这里是唯一权威源。
>
> - **查设备可访问性前，先检查 SSH config + 本 skill**：不要凭端口扫描（22不通、443不通）就判定设备不可 SSH。`~/.ssh/config` 里可能有非常规端口（如 Android 8022）或 FRP 隧道别名（`ssh realme-frp`）。本 skill 的 SSH 表里列出了所有设备的正确登录方式。**先查再断言，避免错误结论。**
- **nmcli 连接名含中文编码**...
- **Windows ICMP block**
- **SSH username differs per device**: Android devices use different usernames. Don't assume the same username works across devices.
- **FRP may be down**: If a port shows `Connection refused`, the device's frpc client isn't running. Tell the user to restart it — don't attempt creative routing through other devices.
- **Reverse SSH direction**: When user says "配置免密登录"，先确认方向 — 正向（本机→设备）还是反向（设备→本机）？反向需要：在设备上生成密钥对 → 取公钥 → 加入本机 authorized_keys。正向 vs 反向的步骤完全不同，不要默认走正向。
- **FRP double-hop for reverse SSH**: 如果设备不在局域网内（LAN SSH 超时），可以用 FRP 隧道先 SSH 进设备做反向配置。设备上的 SSH 回连也走 FRP（本机 FRP 端口 30234），这是最可靠的方案。
- **SSH_CLIENT 在 FRP 隧道中不可靠**: 通过 FRP 连接到一个同时有局域网 SSH 服务的机器时，`SSH_CLIENT` 可能显示局域网 IP（如 192.168.37.1）而非 FRP 隧道预期的 `127.0.0.1`。不要靠 `SSH_CLIENT` 判断会话是否走 FRP 隧道，有疑虑时直接问用户。
- **路由器脚本非交互 SSH 需要显式 PATH**: `/etc/profile` 只对 login shell 生效，`ssh root@ip 'isonline ...'` 会报 `ash: isonline: not found`。显式指定：`ssh root@ip 'PATH=$PATH:/root/.local/bin isonline ...'`。或改用 `ssh root@ip '/root/.local/bin/isonline ...'` 绝对路径。
- **Windows 关机通过 SSH 有延迟**: `shutdown /s /t 0 /f` 即使设 0 秒超时，Windows 实际完全断电可能需要 30+ 秒。关机中间态 SSH 会返回 "系统正在关机中"（`Stop-Computer` 同理）。验证关机需等 30 秒后重试 SSH，不要用路由器 `isonline`（ARP 缓存残留可能误报 ONLINE）。