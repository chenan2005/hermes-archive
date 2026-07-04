# bwtest 测速脚本架构

## 部署位置

`/root/.local/bin/bwtest`（ImmortalWrt 路由器）

## 工作原理

1. **读取 API 密钥**：从 `/etc/openclash/config.yaml` 通过 `awk '/^secret:/{print $2}'` 自动读取
2. **循环测试**：遍历 PROXY 组 `all` 数组中的所有节点（动态获取，无需硬编码），过滤掉 `AUTO`
3. **每个节点的测试流程**：
   - 通过 OpenClash API 切换 PROXY 组到该节点
   - 等待 2 秒让连接建立
   - 下载测速文件（首选 Cloudflare 25MB，降级 Tele2 10MB）
   - 计算带宽（实际下载字节数 × 8 / 耗时 / 1048576）
4. **恢复**：测试前记下原节点，结束后仅当节点被切换过才恢复原节点，无变化时不操作

## 关键实现细节

- **强制走代理端口**：下载 curl 使用 `-x http://127.0.0.1:7890 --proxy-user Clash:密码`，不依赖 TPROXY
- **实际字节数**：超时时用 `wc -c < /tmp/b.bin` 获取实际下载字节数，不是默认文件大小
- **浮点计算**：使用 `awk -v sz=$sz -v d=$d 'BEGIN {printf "%.2f", sz * 8 / d / 1048576}'` 保留 2 位小数
- **认证头**：使用 OpenClash 配置文件的 API secret 自动构造，无硬编码密码

## 配套脚本

同目录下的 `wol`（网络唤醒）和 `isonline`（设备在线检测）也是稳定的路由器端工具。

## 避坑记录

- BusyBox 无 `stat -c%s` → 用 `wc -c < file`
- BusyBox 无 `bc` → 用 `awk` 做浮点运算
- `ip neigh del` 在 ImmortalWrt 上可能卡住 → 去掉该命令，只用 ping + ARP 检测
- OpenClash 重启会覆盖 `config.yaml` → 修改后用 API reload 而不是 `init.d` 重启
