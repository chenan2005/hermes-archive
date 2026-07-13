---
name: faster-whisper-deploy
description: faster-whisper ASR 环境部署、模型下载、CPU 推理、视频转写。触发词：ASR、faster-whisper、语音转写、字幕、Whisper、large-v3
---

# faster-whisper 部署与 ASR 转写

## 触发条件

部署 faster-whisper ASR 转写环境、下载模型、CPU 推理、批量视频字幕提取。

## 硬件选择

| 设备 | CPU | 内存 | large-v3 int8 速度 | 推荐度 |
|------|-----|------|---------------------|--------|
| 9950x3d | 9950X3D (16C/32T) | 64GB | 0.1s/min (含 warm-up) | ★★★★★ |
| miniPC | Ryzen 9 7940HS (8C/16T) | 48GB | ~0.3s/min | ★★★★ |
| Lenovo | Ryzen 5 3550H (4C/8T) | 14GB | ~1s/min | ★★ |

**推荐 9950x3d** — 纯 CPU 推理不碰显存，与 Qwen3.6-27B 完全隔离。

## 部署步骤（9950x3d Windows 11）

### 1. 创建虚拟环境

```powershell
# SSH: ssh 9950x3d
python -m venv C:\faster_whisper_env
C:\faster_whisper_env\Scripts\python.exe -m pip install faster-whisper huggingface_hub[cli]
```

### 2. 下载模型（关键：走直连，不用代理）

**问题**：OpenClash 全局代理（MATCH,PROXY）使 hf-mirror.com DNS 解析到 Cloudflare CDN 而非阿里云直连 IP（160.16.86.14），下载限速至 3MB/s 或触发 308 重定向。

**解决**：将 OpenClash rules 中 `MATCH,PROXY` 改为 `MATCH,DIRECT`（见 home-ops skill），未匹配的域名直连。

**模型文件**：`C:\whisper_models\large-v3\`

```powershell
# model.bin 是 Git LFS 文件（~3GB），必须用 curl.exe（Python urllib SSL 报错）
curl.exe -s -L -o C:\whisper_models\large-v3\model.bin `
  "https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main/model.bin"

# 小文件
curl.exe -s -L -o C:\whisper_models\large-v3\config.json `
  "https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main/config.json"
curl.exe -s -L -o C:\whisper_models\large-v3\tokenizer.json `
  "https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main/tokenizer.json"
curl.exe -s -L -o C:\whisper_models\large-v3\vocabulary.json `
  "https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main/vocabulary.json"
curl.exe -s -L -o C:\whisper_models\large-v3\preprocessor_config.json `
  "https://hf-mirror.com/Systran/faster-whisper-large-v3/resolve/main/preprocessor_config.json"
```

### 3. 验证

```python
from faster_whisper import WhisperModel
model = WhisperModel(
    "C:/whisper_models/large-v3",
    device="cpu",
    compute_type="int8",
    num_workers=1
)
segments, info = model.transcribe("audio.mp3", language="en")
for seg in segments:
    print(f"[{seg.start:.1f}s] {seg.text}")
```

## 远程执行脚本（SSH + Windows）

SSH 到 9950x3d 是 PowerShell 环境，复杂脚本通过 base64 传输：

```bash
# 本地
B64=$(base64 -w0 /tmp/script.py)
ssh 9950x3d "powershell -NoProfile -Command \"[System.IO.File]::WriteAllBytes('C:\\Users\\chen_\\script.py', [System.Convert]::FromBase64String('$B64'))\""
ssh 9950x3d "powershell -NoProfile -Command \"C:\\faster_whisper_env\\Scripts\\python.exe C:\\Users\\chen_\\script.py\""
```

## 音频提取（B 站视频）

```bash
# 获取视频 CID（view API 不需要 WBI 签名）
curl -s "https://api.bilibili.com/x/web-interface/view?bvid=BV1xxx" | python3 -c "import sys,json; print(json.load(sys.stdin)['data']['cid'])"

# 下载音频
yt-dlp --extract-audio --audio-format mp3 --no-playlist "https://www.bilibili.com/video/BV1xxx"
```

## 转写结果整理

```
1. faster-whisper 转写 → 带时间戳的 SRT/文本
2. LLM 整理为 Memex Markdown
3. hindsight_retain 缓存摘要
```

## 坑点

1. **模型文件名**：`vocabulary.json`（不是 `.txt`），无 `generation_config.json` 和 `model.yaml`
2. **Git LFS**：model.bin 是 LFS 指针文件，`hf-mirror.com/.../resolve/main/model.bin` 返回 302 → Cloudflare CDN，curl -L 自动跟随
3. **Python 3.14**：`urlretrieve` 不接受 `Request` 对象（3.12 可以），改用 `opener.open(req)` + `resp.read()`
4. **SSH 超时**：长音频转写（27 分钟）超过 SSH 5 分钟超时，后台跑用 `Start-Process`
5. **代理环境变量**：Linux 终端有 `http_proxy`/`https_proxy` 环境变量，curl 默认走代理；清除：`env -u http_proxy -u https_proxy ...`
6. **hf-mirror DNS**：OpenClash 劫持 DNS → Cloudflare CDN → 速度慢；改 `MATCH,DIRECT` 后直连阿里云 IP
7. **num_workers**：Windows 下默认可能 fork 问题，显式设 `num_workers=1`
8. **首次运行 warm-up**：第一次 transcribe 有初始化开销（0.1s 含 warm-up），后续更快