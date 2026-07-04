---
name: sing-box-linux
description: 在 Linux 上管理 sing-box 代理 — 配置结构（扁平 outbound/route.final）、节点切换、系统代理开关、TUN 踩坑、端口绑定、5G 加速流程。适用于本机（Linux Mint, sing-box v1.13+ systemd user service）。
tags:
  - sing-box
  - proxy
  - linux
  - socks5
related_skills:
  - it-assets
  - 5g-mode
  - sing-box-ctrl
---

# sing-box 管理（Linux）

> 本机: Linux Mint 22, sing-box v1.13+, systemd user service, linger=yes
> 源码仓库: `~/myscript/`（git repo, master branch）
> 管理脚本: `~/myscript/sing-box-ctrl.py`（~650 行，stdlib only，跨平台 Linux/Windows）
> 快捷命令: `sing-box-ctrl`（`~/.local/bin/` 下软链指向 `~/myscript/sing-box-ctrl.py`）
> 开发日志: `~/myscript/.changelog.log`（gitignore，不入库，格式: `YYYY-MM-DD [模块] 内容`）
> 规范: 脚本改完先 commit 到 myscript，~/.local/bin/ 只保留软链不存源码

## 配置结构

**扁平 outbound 模式**（无 selector）：

```
outbounds: [VMISS-HK, 233boy-KVM, Alibaba-Seoul-VLESS, direct, block]
route.final: "VMISS-HK"   # 指向当前默认节点
```

节点切换通过修改 `route.final` + `systemctl --user reload` 实现，无需 selector。

配置路径：`~/.config/sing-box/config.json`
规则集路径：`~/.config/sing-box/ruleset/geoip-cn.srs` + `geosite-cn.srs`

## 常用命令

```bash
sing-box-ctrl status            # 运行状态 + 当前节点
sing-box-ctrl switch [节点名]    # 查看或切换节点（支持模糊匹配）
sing-box-ctrl proxy on|off      # 系统代理开关（GUI gsettings + CLI env file）
sing-box-ctrl test [--all|节点] # 测速（临时进程，不影响当前代理）
sing-box-ctrl start|stop|restart
```

## 端口绑定

| 端口 | 类型 | 范围 | 用途 |
|------|------|------|------|
| 10880 | SOCKS5 | 0.0.0.0 (LAN) | 区域网设备直连 |
| 10881 | Mixed | 0.0.0.0 (LAN) | HTTP CONNECT + SOCKS5 自动识别 |
| 9090 | Clash API | 127.0.0.1 | 本地管理（已启用，clash_api.external_controller） |

防火墙放行了 `192.168.71.0/24` 和 `192.168.37.0/24`（ufw）。

## 系统代理开关

`proxy on/off` 同时控制：
- **GUI**：通过 gsettings 设置 Cinnamon 手动代理 / 无代理
- **CLI**：写入 `~/.config/proxy-env`，bashrc 自动 source

注意：切换后**当前终端不立即生效**，需要 `source ~/.config/proxy-env`。

## TUN 模式（已放弃）

三次尝试均导致断网，根因推测为 Linux Mint 的 NetworkManager 与 sing-box nftables 路由规则冲突。不可恢复的断网类型：
1. `dns_mode: "hijack"`（1.14+ 才有）→ 崩溃，nftables 规则残留
2. `strict_route: false` → 无 fwmark 绕过，节点连接循环
3. `strict_route: true` → nftables 冲突

结论：**本机不走 TUN 模式**，用 SOCKS5/Mixed 端口 + 系统代理即可。

## 5G 加速模式

`~/.local/bin/5g-mode` — 一键切换 5G 加速 / 恢复家庭网络（含预检+后检+自动回退）：

```bash
5g-mode accelerate    # 加速（预检热点→OpenClash→VLESS→热点→后检翻墙→自动回退）
5g-mode revert        # 恢复（光猫WiFi→VMISS-HK→OpenClash→VMISS-HK）
5g-mode status        # 查看三方状态
```

加速流程内建：
- **预检**：扫描 WiFi 确认热点可见，不可见则直接回退
- **后检**：切换后通过 SOCKS5 测 Google 204，不通则自动回退
- **回退**：任意步骤失败 → 切回光猫 + VMISS-HK

配置在 `~/.config/5g-mode.conf`（含 OpenClash API secret）。

## Pitfalls

- **`systemctl --user reload` = SIGHUP** — sing-box 1.x 的 systemd unit 配置了 `ExecReload=/bin/kill -HUP $MAINPID`，SIGHUP 热重载配置无需重启进程。Windows 不支持 SIGHUP，脚本实现为 `taskkill` + `Popen` 重新拉起。
- **测速时节点切换用 SIGHUP 热重载** — `test` 子命令通过 `os.kill(proc.pid, signal.SIGHUP)` 热切换节点，不再 kill+restart（每个节点省 2 秒启动等待）。
- **测速下行源** — `speed.cloudflare.com/__down?bytes=10000000`（正确端点，`/cf` 返回 404）。
- **测速上行** — POST 5MB 文件到 `speed.cloudflare.com/upload`。
- **测速延迟指标** — SOCKS5 代理下 curl 的 `time_connect` 只测到本地代理连接（~0.4ms），**必须用 `time_starttransfer`**（首字节时间）作为延迟指标。
- **测速代理参数** — curl 加 `-x socks5://...` 时**不能加 `--noproxy all`**，该参数会覆盖 `-x` 导致请求走直连。
- **`switch` 匹配优先级** — 精确匹配 > 不区分大小写的子串匹配，未匹配时列出可用节点。
- **配置文件 JSON 损坏** — `load_config()` 捕获 `JSONDecodeError` 并输出文件路径和错误位置。
- **`status` 代理入口动态读取** — 从 `inbounds` 读实际 listen/bind 地址，不再硬编码 `127.0.0.1`。
- **Hermes 终端 HOME 覆盖问题** — 在 Hermes 会话中 `$HOME` 被 profile 目录覆盖，脚本直接运行会找错路径；用户真实终端不受影响。
- **TUN 模式开机崩溃导致全断** → 删除配置回退、配合 nftables 残留可能导致完全断连，只能手动 service stop 后恢复 SOCKS 配置
- **`5g-mode accelerate` 后检失败** → 检查 curl SOCKS5 端口是否为 10880（可能被其他进程占用），确认热点已开启且可用
- **`oc_set_proxy` 验证通过但 OpenClash 未生效** → PUT 后轮询 GET 重试 3 次（每次 1s），避免 API 延迟导致的误判