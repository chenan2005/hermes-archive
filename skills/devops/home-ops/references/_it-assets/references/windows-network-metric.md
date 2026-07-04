# Windows 网络接口优先级管理

## 查看接口 Metric

```cmd
netsh interface ip show interfaces
route print -4
```

## 设置接口 Metric（持久化）

```cmd
netsh interface ip set interface "WLAN" metric=5000
```

- 值越小优先级越高
- 设置后写入注册表，重启/WiFi 断开重连后不会重置
- 除非手动改成"自动跃点数"才会恢复

## 典型场景

| 接口 | Metric | 说明 |
|------|--------|------|
| 有线 (Ethernet) | 25 或默认 (74) | 作为默认路由 |
| WiFi | 5000 | 仅供显式绑定的应用（VPN/代理客户端）使用 |

## sing-box + Hyper-V 路由冲突

**现象：** sing-box 配置了 `bind_interface: "WLAN"` 但流量仍然走有线网卡。`sing-box.log` 显示 `default interface vEthernet (wan), index 56`。

**原因：**
1. Hyper-V 创建外部虚拟交换机（`vEthernet (wan)`）并绑定到物理网卡时，Windows 路由表中该虚拟接口的 metric 远低于 WLAN（以太网 74 vs 热点 5000）
2. sing-box 配置 `auto_detect_interface: true` 时，路由层优先用系统默认接口（vEthernet），覆盖了 outbound 上的 `bind_interface`
3. `bind_interface: "WLAN"` 本身在 Windows 上实现不彻底——`SO_BINDTODEVICE` 并非原生 Windows API，sing-box 通过间接方式绑定，可靠性不如 Linux

**修复步骤：**

1. **关闭 `auto_detect_interface`** — 从 route 段移除该选项（默认即 false）：
   ```json
   "route": {
     "rules": [],
     "final": "select"
   }
   ```

2. **添加静态路由** — 把代理节点服务器 IP 单独路由至 WLAN 接口，不改变系统默认路由：
   ```cmd
   route add 43.108.41.245 mask 255.255.255.255 10.192.244.122 metric 50
   ```
   - `43.108.41.245` = 阿里云首尔节点 IP
   - `10.192.244.122` = 手机热点网关（从 `route print -4 0.0.0.0` 查）
   - /32 主机路由优先级高于默认路由，metric 不影响匹配

3. **持久化** — Windows 临时 `route add` 重启后丢失。用 `-p` 参数持久化：
   ```cmd
   route add -p 43.108.41.245 mask 255.255.255.255 10.192.244.122 metric 50
   ```

**验证：**
```cmd
tracert -d -h 3 43.108.41.245
```
第一跳应为手机热点网关（`10.192.244.x`）而非家庭网络网关（`192.168.71.x`）。

**带宽实测对比（同一台 minipc，同一 5G 热点）：**
| 客户端 | 协议 | 速度 |
|--------|------|------|
| 平板 v2rayNG (Android) | Reality | 快（用户描述） |
| Windows sing-box | SOCKS5 → Reality | ~2.8 Mbps |
| Windows curl 直连 5G（不走代理） | - | 需对比 |

结论：瓶颈在 sing-box on Windows 处理 Reality 协议的性能，非路由问题。
