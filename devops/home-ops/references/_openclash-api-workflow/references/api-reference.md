# OpenClash REST API 参考

## 认证
- Secret 位置: `/etc/openclash/config.yaml` → `secret: xxx`
- 安全读取: `S=$(awk '/^secret:/{print $2}' /etc/openclash/config.yaml)`

## 构建 Auth Header（避免 Hermes 引号被吞）
```sh
H=$(printf 'Authorization: Bearer %s' "$S")
```
不要写 `"Authorization: Bearer $S"`（`$S"` 会被 Hermes 吃掉引号）。

## API 端点
- `GET /proxies` — 所有代理列表
- `GET /proxies/{name}` — 单节点状态
- `GET /proxies/{name}/delay?url=...&timeout=...` — 延迟测试（需 auth）
- `PUT /proxies/{group}` — 切换代理组选择（body: `{"name":"NodeName"}`）

## 通过代理测试（免 API auth）
```sh
curl -sx "http://Clash:3Ypy6ovV@127.0.0.1:7890" --max-time 10 https://cp.cloudflare.com/generate_204
```

## 常见问题
- **external-ui SAFE_PATHS 报错**: 新版 Mihomo 要求 `external-ui` 路径在 home directory 内，改到 `/etc/openclash/ui`
- **端口冲突**: `killall -9 clash` 后再启动
- **OpenClash 标记为 disabled**: `uci set openclash.config.enable=1 && uci commit openclash`