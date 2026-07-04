---
name: qwen-service
description: Use when starting, stopping, or checking status of the Qwen3.6-27B llama-server on 9950x3d (192.168.71.41:8080). Covers remote process management via SSH, desktop bat scripts, and health verification.
version: 1.0.0
author: Hermes Agent
license: MIT
metadata:
  hermes:
    tags: [qwen, llama.cpp, 9950x3d, local-llm, service-management]
    related_skills: [it-assets, windows-remote-control, llama-cpp]
---

# Qwen3.6-27B Service Management

## Overview

Manages the Qwen3.6-27B llama-server running on the 9950x3d Windows workstation (192.168.71.41).
The server exposes an OpenAI-compatible API on `http://192.168.71.41:8080/v1`.

Key facts:
- **Model**: Qwen3.6-27B Q4_K_M GGUF (~15.7 GB)
- **Context**: 262144 tokens, Q6_K KV cache
- **GPU**: RTX 5090 32 GB, all layers offloaded (`-ngl 99`)
- **Process**: `llama-server.exe` (shows as "llama" in task manager)
- **Logs**: `C:\llama\server.log`
- **Desktop scripts**: `C:\Users\chen_\Desktop\qwen-start.bat` / `qwen-stop.bat`

## When to Use

- User says "start Qwen", "stop Qwen", "restart Qwen", "check if Qwen is running"
- User asks about the local model status or wants to free up VRAM
- User mentions 9950x3d model, llama-server, or port 8080 in context of local LLM

## Status Check

Check if the server is running and healthy:

```bash
# Check process
ssh 9950x3d 'powershell -NoProfile -Command "Get-Process -Name llama -ErrorAction SilentlyContinue | Format-Table Id,@{Label=\"Memory(GB)\";Expression={[math]::Round(`$_.WorkingSet64/1GB,1)}},StartTime"'

# Check port
ssh 9950x3d 'powershell -NoProfile -Command "netstat -ano | Select-String \":8080.*LISTENING\""'

# Quick API test (local on 9950x3d)
ssh 9950x3d 'curl.exe -s -o nul -w "%{http_code}" http://localhost:8080/health'
```

**Completion criterion**: Process exists AND port 8080 is LISTENING AND API returns 200.

### Interpret results

- No process + no port → server is **stopped**
- Process exists + port LISTENING + health 200 → server is **running healthy**
- Process exists but health != 200 → **warming up** (wait 10-30s for model load)

## Start Qwen

### Method 1: Remote start (preferred — headless, no desktop needed)

```bash
ssh 9950x3d 'cmd /c start /B "" C:\Users\chen_\Desktop\qwen-start.bat'
```

Note: `start /B` runs in background without a new window. The cmd window will close after launch but llama-server continues running. Logs go to `C:\llama\server.log`.

### Method 2: Desktop double-click

Tell the user to double-click `qwen-start.bat` on the 9950x3d desktop. A terminal window opens showing server output. Closing the window stops the server.

### After starting

Wait ~30s for model to load into VRAM, then verify with status check.

## Stop Qwen

### Method 1: Remote stop (preferred)

```bash
ssh 9950x3d 'powershell -NoProfile -Command "Stop-Process -Name llama -Force -ErrorAction SilentlyContinue; if(`$?){Write-Host \"stopped\"}else{Write-Host \"was not running\"}"'
```

### Method 2: Desktop double-click

Tell the user to double-click `qwen-stop.bat` on the 9950x3d desktop.

### After stopping

Verify port 8080 is freed (~5s for GPU memory release):

```bash
ssh 9950x3d 'powershell -NoProfile -Command "netstat -ano | Select-String \":8080\""'
```

Empty output = port freed. Exit code 0 with no matches = port freed.

## Restart Qwen

```bash
# Stop first
ssh 9950x3d 'powershell -NoProfile -Command "Stop-Process -Name llama -Force -ErrorAction SilentlyContinue"'
sleep 5
# Start
ssh 9950x3d 'cmd /c start /B "" C:\Users\chen_\Desktop\qwen-start.bat'
# Wait for load
sleep 30
# Verify
ssh 9950x3d 'curl.exe -s -o nul -w "%{http_code}" http://localhost:8080/health'
```

## VRAM Impact

| State | VRAM Used | Desktop Impact |
|-------|-----------|----------------|
| Qwen running | ~25 GB (model 15.7 + KV 6.2 + overhead ~3) | Dual 4K fine, 7 GB headroom |
| Qwen stopped | ~2 GB (desktop compositing only) | Full 32 GB available |

When the user wants to game or run other GPU workloads, stop Qwen to free VRAM.

## Common Pitfalls

1. **SSH process shows different name**: Windows truncates `llama-server.exe` to "llama" in process list. Use `-Name llama` for `Get-Process`/`Stop-Process`.

2. **Model load time**: First start after reboot takes ~30-60s for model to load into VRAM. Subsequent restarts are faster (~15s) because the file is cached in RAM.

3. **Port conflict**: If port 8080 is already in use, llama-server will fail to start. Check with netstat first.

4. **Windows Defender**: May delay first launch by 5-10s while scanning the executable. Subsequent launches are instant.

5. **start /B quirk**: The `start /B "" C:\Users\chen_\Desktop\qwen-start.bat` command appears to hang in SSH because `start /B` detaches from the console. This is normal — the server is starting. Wait 30s then check health.

6. **Desktop scripts need interactive session**: The bat scripts with `pause` require a logged-in desktop session. Use Method 1 (remote start) for headless operation.

7. **GPU memory release lag**: After stopping, VRAM may take 5-10s to fully release. Check with `nvidia-smi` if available.

## Verification Checklist

- [ ] Status check returns consistent state (process + port match)
- [ ] After start: health endpoint returns 200 within 60s
- [ ] After stop: port 8080 is freed within 10s
- [ ] Desktop scripts exist and are accessible at `C:\Users\chen_\Desktop\qwen-*.bat`
