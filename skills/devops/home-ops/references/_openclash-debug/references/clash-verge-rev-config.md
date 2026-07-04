# Clash Verge Rev Proxy Configuration Reference

## Config File Hierarchy

| File | Path (under %APPDATA%\roaming\io.github.clash-verge-rev.clash-verge-rev) | Persistence |
|------|-----------------------------------------------------------------|:-----------:|
| Runtime config | `clash-verge.yaml` | ❌ 每次启动从 profile + overlay 合并生成 |
| Profile source | `profiles/<name>.yaml` | ✅ |
| Profile index | `profiles.yaml` | ✅ |
| App settings | `verge.yaml` | ✅ |

Runtime config regenerated on startup. Direct edits overwritten. Kill both processes before editing.

## Key Settings for SOCKS5 Proxy

```yaml
mixed-port: 7897              # SOCKS5 + HTTP mixed port
allow-lan: true               # 0.0.0.0 监听，允许局域网连接
interface-name: WLAN           # 代理连接强制走 WiFi
mode: global                   # 无分流规则
```

allow-lan 也可在 UI → Settings → 允许局域网连接 开启。interface-name 仅在配置文件中可设。

## File Transfer via SSH Pipe

```bash
cat config.yaml | ssh win 'powershell -NoProfile -Command "$i=[Console]::In.ReadToEnd(); [IO.File]::WriteAllText(\"$env:APPDATA\path\file.yaml\",\"$i\"); echo ok"'
```

## Process Management

```cmd
taskkill /F /IM "clash-verge.exe"
taskkill /F /IM "verge-mihomo.exe"
```

## Verification

```cmd
netstat -an | findstr 7897
# 0.0.0.0:7897 LISTENING → allow-lan: true
# 127.0.0.1:7897 LISTENING → allow-lan: false
```

## Pitfalls

- allow-lan: false → SOCKS5 only 127.0.0.1, 外部设备无法连接
- interface-name 设了但 WiFi 断开 → mihomo 绑定失败，所有代理连接超时
- Clash Verge 运行时编辑 clash-verge.yaml → 会被覆盖，必须先杀进程
