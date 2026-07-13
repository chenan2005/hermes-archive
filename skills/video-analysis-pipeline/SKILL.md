---
name: video-analysis-pipeline
description: 视频内容分析流水线：ASR转写+关键帧视觉分析+LLM摘要。支持B站视频入库、演讲内容整理。触发词：视频分析、视频摘要、多模态分析、视频入库、关键帧、视觉分析
---

# 视频内容分析流水线

## 触发条件

需要分析视频内容（B站、YouTube、演讲录像等），生成带视觉信息的结构化摘要。

## 完整流程

```
视频URL → 下载视频+音频 → ASR转写 → 关键帧抽取 → 视觉分析 → LLM综合摘要 → 入库
```

### Step 1: 下载视频

```bash
# 完整视频（含音频）
yt-dlp -o "/tmp/video.mp4" --no-playlist "https://www.bilibili.com/video/BV1xxx"

# 仅音频（如果不需要视觉分析）
yt-dlp --extract-audio --audio-format mp3 -o "/tmp/audio.mp3" --no-playlist "URL"
```

### Step 2: ASR 转写

```bash
# 本地（faster-whisper base/int8）
python3 -c "
from faster_whisper import WhisperModel
model = WhisperModel('base', device='cpu', compute_type='int8')
segments, info = model.transcribe('audio.mp3')
for s in segments:
    print(f'[{s.start:.0f}s] {s.text}')
"

# 远程（9950x3d，large-v3 int8 CPU）
scp /tmp/audio.mp3 9950x3d:"C:/Users/chen_/"
ssh 9950x3d "powershell -NoProfile -Command \"C:\\faster_whisper_env\\Scripts\\python.exe C:\\Users\\chen_\\transcribe.py\""
```

### Step 3: 关键帧抽取

```bash
# 先确定关键段落时间戳（从 ASR 转写中识别）
# 然后用 ffmpeg 按时间戳抽帧（1920p 分辨率，确保视觉分析质量）
ffmpeg -y -ss 1538 -i video.mp4 -frames:v 1 -q:v 1 -vf "scale=1920:-1" frame_1538_hq.jpg
```

**关键帧选择策略**：
- 开场/结尾（品牌、标题、结论）
- 架构/图表展示
- 代码/命令截图
- 数据对比/排行榜
- 演讲者表情/情绪转折

### Step 4: 视觉分析

用 Qwen3.6 多模态 API（llama.cpp server）分析每帧：

```python
import base64, json, urllib.request

with open("frame.jpg", "rb") as f:
    b64 = base64.b64encode(f.read()).decode()

payload = json.dumps({
    "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
        {"type": "text", "text": "描述 PPT 内容，重点提取数据"}
    ]}],
    "temperature": 0.1,
    "max_tokens": 4096,
    "stream": False,
    "chat_template_kwargs": {"enable_thinking": False}  # 关键！关闭 thinking
})

req = urllib.request.Request(
    "http://192.168.71.41:8080/v1/chat/completions",
    data=payload.encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST"
)
with urllib.request.urlopen(req, timeout=300) as resp:
    result = json.loads(resp.read())
    print(result["choices"][0]["message"]["content"])
```

### Step 5: LLM 综合摘要

将 ASR 转写 + 视觉分析结果喂给 LLM，生成结构化摘要：

```markdown
## 概述
## 核心论点
## 技术架构
## 数据对比
## 关键发现
```

### Step 6: 入库

```bash
# 写入 Memex
cp summary.md ~/memex/unread/<date>-<title>.md

# Hindsight 保留
hindsight_retain "视频标题: ... 演讲者: ... 核心内容: ..."
```

## 关键参数

| 参数 | 值 | 说明 |
|------|------|------|
| 帧分辨率 | 1920p (`scale=1920:-1`) | 低于此分辨率 Qwen3.6 识别严重偏差 |
| Qwen3.6 thinking | `enable_thinking: False` | thinking 模式把 token 全吃在 reasoning 里，content 为空 |
| max_tokens | 4096 | 单帧分析够用 |
| 每帧间隔 | 30-60s | 演讲视频典型密度 |
| API 超时 | 300s | Qwen3.6 多模态推理较慢 |
| 帧数建议 | 10-16 | 覆盖全文即可，太多浪费 token |

## 硬件分配

| 步骤 | 设备 | 原因 |
|------|------|------|
| yt-dlp 下载 | Lenovo 本机 | B站直连快 |
| ASR 转写 | 9950x3d (large-v3 CPU) | 速度快，准确率最高 |
| 关键帧抽取 | Lenovo 本机（ffmpeg） | 本地视频文件 |
| 视觉分析 | 9950x3d (Qwen3.6 多模态 API) | 本地部署，免费 |
| 综合摘要 | Qwen3.6 或远程 LLM | 长上下文 |

## 坑点

1. **ffmpeg -ss 不精确**：默认按关键帧 seek，抽到的可能不是目标时间。用 `-update 1` 参数解决输出问题
2. **帧分辨率太低**：32KB 的帧 Qwen3.6 把排行榜看成 Mario Levelchart。必须缩放到 1920p+（85KB+）
3. **Qwen3.6 thinking 模式**：默认开启 thinking，输出全在 reasoning_content 里，content 为空。必须传 `chat_template_kwargs: {"enable_thinking": False}`
4. **代理环境变量**：调用 9950x3d API 时清除 `http_proxy` 等变量，否则 curl/python 走系统代理
5. **B站视频无字幕**：`player/v2` API 返回空字幕列表，必须走 ASR
6. **B站 CDN 拦截**：`fav` 接口被 CDN WAF 拦截，`view` API 不需要 WBI 签名可直接调用

## 性能基准

| 任务 | 耗时 | 设备 |
|------|------|------|
| ASR 1min (large-v3 CPU) | 0.1s | 9950X3D |
| ASR 27min (large-v3 CPU) | ~3-5s（纯推理，含 warm-up） | 9950X3D |
| 单帧视觉分析 | 30-60s | Qwen3.6 on RTX 5090 |
| 16 帧批量分析 | 8-12 分钟 | 串行调用 |
| 综合摘要生成 | 10-30s | Qwen3.6 non-thinking |