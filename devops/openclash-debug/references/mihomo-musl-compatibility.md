# mihomo 核心 musl 兼容性记录

## 问题

OpenWrt 24.10.0+ 使用 musl libc (v1.2.5)，而非 glibc。新版 mihomo (v1.18+) 不再提供 musl 编译版本，仅有 glibc 版（linux-amd64-v1/v2/v3）。

在 musl 系统上直接运行 glibc 版 mihomo 会导致 **Bus error**（非段错误/信号问题，而是 musl 动态链接不兼容导致的崩溃）。

## 症状

- Clash 核心进程存在但立即退出
- `/etc/openclash/core/clash_meta -v` 输出 `Bus error`
- OpenClash 日志：`[Error] Core Start Failed, Please Check The Log Infos!`
- `netstat -tlnp | grep 789` 无输出

## 解决方案

### Compatible 版本（已验证可用）

mihomo 提供 `linux-amd64-compatible` 变体，该版本使用较老的 Go 编译选项，兼容性更好，可在 musl 系统上运行。

| 版本 | 下载 URL |
|------|---------|
| v1.19.27 (latest) | https://github.com/MetaCubeX/mihomo/releases/download/v1.19.27/mihomo-linux-amd64-compatible-v1.19.27.gz |

验证结果：
```
Mihomo Meta v1.19.27 linux amd64 with go1.26.4 Sat Jun  6 07:43:19 UTC 2026
Use tags: with_gvisor
```

### 2. 禁用 OpenClash 自动更新

OpenClash 的 `openclash_update.sh`（位于 `/usr/share/openclash/openclash_update.sh`）会在后台运行并自动下载最新核心。如果启用了自动更新，该脚本会定期将 core 覆盖为不兼容的版本。

**操作：** LUCI → OpenClash → 全局设置 → 内核更新 → 关闭自动更新

也可以通过运行 `killall openclash_update.sh` 立即停止正在进行的更新。

### 3. 版本演变

- mihomo v1.18+：取消 musl 编译版本
- mihomo v1.17.x 及更早：可能还有 musl 版本
- 「compatible」变体从 v1.18 左右开始提供，取代了 musl 版本的角色
