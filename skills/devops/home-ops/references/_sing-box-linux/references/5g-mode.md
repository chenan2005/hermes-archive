# 5G 加速模式

本机通过 `~/.local/bin/5g-mode` 脚本一键切换加速/恢复。

## 加速流程

```bash
5g-mode accelerate
```

完整流程（含预检+后检+回退）：

1. **[预检]** 扫描 WiFi，确认热点 `realme GT 7 FDC6` 可见（不可见→回退）
2. **[1/3]** OpenClash 默认节点 → `lenovo-socks`（HTTP PUT /proxies/PROXY；重复验证 3 次）
3. **[2/3]** 本机 sing-box → `Alibaba-Seoul-VLESS`（VLESS+Reality，走手机 5G 出口）
4. **[3/3]** WiFi → 手机热点 `realme GT 7 FDC6`（已在热点上则跳过）
5. **[后检]** 等待 4s 后，通过 SOCKS5 测 Google 204（8s 超时，不通→回退）

效果：家庭局域网所有流量经 OpenClash → 本机 SOCKS5 (0.0.0.0:10880) → VLESS 节点 → 手机 5G 出口

## 恢复流程

```bash
5g-mode revert
```

顺序：
1. **[1/3]** WiFi 切换 → 光猫 `ChinaNet-pfwQ-5G`
2. **[2/3]** 本机 sing-box → `VMISS-HK`（回到家庭 VMess 节点）
3. **[3/3]** OpenClash 默认节点 → `VMISS-HK`

## 回退机制

任意步骤失败时自动调用 `rollback(tag)`：
1. 切 WiFi → 光猫
2. 切 sing-box → VMISS-HK
3. 切 OpenClash → VMISS-HK

失败类型：
- 热点预检失败 → 热点未发现
- OpenClash 切换失败（不连通或 API 无响应）
- sing-box 切换失败（脚本异常）
- WiFi 切换失败（nmcli 超时）
- 翻墙后检失败（Google 204 无响应）

## 配置

- 脚本: `~/.local/bin/5g-mode.py`（~280 行，stdlib only + configparser）
- 别名: `5g-mode`（PATH 可执行）；`alias mode5g`（~/.bashrc）
- 配置: `~/.config/5g-mode.conf`（含 OpenClash API secret，生成后不回显）

配置项：
```
OPENCLASH_SECRET=       # OpenClash API secret
OPENCLASH_HOST=         # 192.168.71.9
OPENCLASH_PORT=         # 9090
HOME_WIFI=              # ChinaNet-pfwQ-5G
HOTSPOT_WIFI=           # realme GT 7 FDC6
RL_NODE=                # Alibaba-Seoul-VLESS（VLESS+Reality）
HK_NODE=                # VMISS-HK
LENOVO_NODE=            # lenovo-socks（OpenClash 端）
```

## 重要实现细节

- **oc_set_proxy**：PUT 后轮询 GET 3 次（每次间隔 1s）验证生效，应对 API 延迟
- **proxy_working**：8s curl 超时 + 5s subprocess 余量，总 13s 极限
- **hotspot_available**：`nmcli dev wifi list` 扫描，12s 超时，`TimeoutExpired` 视为不可见
- **edge case（已在热点上）**：跳过预检/OpenClash/WiFi 三步，只执行后端节点切换 + 翻墙后检

## 网络拓扑说明

| 模式 | 本机 WiFi | 本机节点 | OpenClash 出口 | 外网路径 |
|------|-----------|---------|--------------|---------|
| 家庭 | 光猫 71.x | VMISS-HK | VMISS-HK | 家宽光纤 |
| 加速 | 手机热点 192.168.x | Alibaba-Seoul-VLESS | lenovo-socks→本机 | 手机 5G |
