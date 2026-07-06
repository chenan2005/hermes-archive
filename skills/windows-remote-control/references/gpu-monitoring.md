# GPU 监控（Windows + nvidia-smi）

查询 9950x3d 的 RTX 5090 状态和 llama-server 进程。通过 SSH 执行 nvidia-smi + PowerShell。

## 单次查询命令

```bash
# GPU 状态（CSV 格式，无表头）
ssh 9950x3d 'nvidia-smi --query-gpu=temperature.gpu,utilization.gpu,utilization.memory,memory.used,memory.total,power.draw,power.limit,clocks.sm --format=csv,noheader'
# 输出: 78, 90 %, 65 %, 30137 MiB, 32607 MiB, 580.32 W, 575.00 W, 2767 MHz
```

字段顺序：温度, GPU利用率, 显存带宽利用率, 显存已用, 显存总量, 功耗, 功耗上限, SM频率

```bash
# llama-server 进程信息
ssh 9950x3d "powershell -NoProfile -Command \"\$p=Get-Process llama-server -ErrorAction SilentlyContinue; if(\$p){ Write-Output \\\"PID=\$(\$p.Id) CPU=\$([math]::Round(\$p.CPU,1))s WS=\$([math]::Round(\$p.WorkingSet64/1MB))MB\\\" } else { Write-Output 'NOT RUNNING' }\""
# 输出: PID=19600 CPU=789.4s WS=29278MB
```

## 引号模式

PowerShell 命令通过 SSH 执行时，外层用双引号（`"`），内层 PowerShell 的 `$` 转义为 `\$`，PowerShell 字符串内的双引号转义为 `\\\"`：

```
ssh target "powershell -NoProfile -Command \"\$var=...; Write-Output \\\"text\\\"\""
```

不使用 `& { }` 包装器——简单脚本不需要。

## gpu-mon 脚本

快捷脚本 `~/.local/bin/gpu-mon`：

```bash
gpu-mon          # 单次快照
gpu-mon -w       # 持续监控（每秒）
gpu-mon -w 5     # 每 5 秒
```

输出格式：
```
GPU: 78°C | 96 % util | 70 % mem-util | VRAM 30137/32607MB (92%) | 554W/575W | 2722 MHz
     llama-server: PID=19600 CPU=789.4s WS=29278MB
```

环境变量 `GPU_MON_TARGET` 可覆盖目标主机（默认 `9950x3d`）。
