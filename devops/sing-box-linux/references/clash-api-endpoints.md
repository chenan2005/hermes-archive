# sing-box Clash API 端点实测

> 版本: sing-box v1.13.14
> 测试时间: 2026-07-03
> 配置: `experimental.clash_api.external_controller = "127.0.0.1:9090"`

## 支持的端点

| 方法 | 路径 | 状态 | 用途 |
|------|------|------|------|
| GET | `/` | 200 | 健康检查，返回 `{"hello":"clash"}` |
| GET | `/proxies` | 200 | 列出所有出站节点（含 type, now 字段） |
| GET | `/connections` | 200 | 当前活跃连接 |

## 不支持的端点（返回 404）

| 路径 | 说明 |
|------|------|
| `POST /reboot` | 不存在，sing-box 不实现此端点 |
| `POST /reload` | 不存在，sing-box 不实现此端点 |
| `GET /config` | 不存在 |
| `GET /rules` | 未测试，clash 兼容层可能缺失 |
| `GET /providers` | 未测试 |

## 流式端点

| 路径 | 行为 |
|------|------|
| `GET /traffic` | SSE 流式响应，`curl` 会挂起等待 stream — 不适合脚本抓取 |

## 配置热重载

sing-box 1.x **不支持**通过 Clash API 热重载配置。唯一方式：

1. **systemd 管理**: `systemctl --user reload sing-box` → 发送 SIGHUP（unit 中 `ExecReload=/bin/kill -HUP $MAINPID`）
2. **独立进程**: `os.kill(pid, signal.SIGHUP)`

Windows 不支持 SIGHUP，需要 stop + start。

## 实测命令

```bash
# 健康检查
curl -s http://127.0.0.1:9090/
# → {"hello":"clash"}

# 列出所有节点
curl -s http://127.0.0.1:9090/proxies | python3 -m json.tool

# 查看活跃连接
curl -s http://127.0.0.1:9090/connections | python3 -m json.tool
```
