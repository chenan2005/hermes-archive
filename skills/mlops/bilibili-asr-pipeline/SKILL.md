---
name: bilibili-asr-pipeline
description: B 站视频 ASR 转写完整流水线：yt-dlp 提取音频 → faster-whisper 转写 → LLM 整理为 Memex Markdown → Hindsight 入库。触发词：B站字幕、视频转写、ASR流水线、B站入库、视频内容采集
---

# B 站视频 ASR 转写流水线

## 触发条件

需要把 B 站视频内容（无字幕或字幕不完整）转写、整理、入库 Memex。

## 完整流程

```
1. 定位视频 BV 号 → 2. 下载音频(yt-dlp) → 3. ASR转写(faster-whisper) → 4. LLM整理 → 5. 入库Memex
```

### Step 1: 获取 BV 号

B 站收藏夹通过浏览器 DOM 提取（需 Cookie）：
- 访问 `space.bilibili.com/<UID>/favlist`
- 从 DOM 中提取链接，获取 BV 号（如 `BV1M7796VEHj`）
- Cookie 提取见 prior context（Edge CDP 方式）

### Step 2: 获取视频 CID

```bash
# view API 不需要 WBI 签名
curl -s "https://api.bilibili.com/x/web-interface/view?bvid=BV1M7796VEHj" | python3 -c "import sys,json; d=json.load(sys.stdin)['data']; print(f'title: {d[\"title\"]}, cid: {d[\"cid\"]}')"
```

### Step 3: 检查是否已有字幕

```bash
curl -s "https://api.bilibili.com/x/player/v2?bvid=BV1M7796VEHj&cid=<CID>" | python3 -c "import sys,json; subs=json.load(sys.stdin)['data'].get('subtitle',{}); print('subtitles:', subs.get('subtitles', 'none'))"
```

有字幕则直接下载，无字幕走 ASR。

### Step 4: 下载音频

```bash
yt-dlp --extract-audio --audio-format mp3 --no-playlist "https://www.bilibili.com/video/BV1xxx"
```

### Step 5: ASR 转写

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
    print(f"[{seg.start:.1f}s - {seg.end:.1f}s] {seg.text}")
```

### Step 6: LLM 整理为 Memex Markdown

转写文本 → LLM 整理为带时间戳的 Markdown：

```markdown
---
source: bilibili
url: https://www.bilibili.com/video/BV1xxx
title: <视频标题>
author: <UP主>
date: <发布日期>
collected: <采集日期>
duration: 00:27:15
language: en
tags: [tag1, tag2]
summary: <一句话摘要>
---

# <标题>

## 概述
<LLM 生成的内容概述>

## 内容详情
[0:00] 第一段...
[2:30] 第二段...
...

## 关键观点
1. ...
2. ...
```

### Step 7: 入库

```bash
# 写入 ~/memex/unread/<日期>-<标题>.md
# Hindsight 保留摘要
hindsight_retain "视频标题: ... 作者: ... 关键内容: ..."
```

## 部署位置

- **9950x3d** — faster-whisper large-v3 CPU 推理（~0.1s/min）
- **Lenovo** — yt-dlp 下载 + 音频预处理

## 相关 Skill

- `faster-whisper-deploy` — 模型部署与推理