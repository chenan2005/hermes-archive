# Hindsight Configuration Tuning

How to tune `~/.hermes/hindsight/config.json` for better memory quality. The
defaults are conservative — observation-only recall, concise extraction, no
mission. Tuning these makes a large difference in what gets stored and what gets
returned.

## Quick Reference: What Goes Where

```
┌─────────────────────────────────────────────────────────┐
│ 存入侧 (retain — 控制"存什么"):                          │
│   retain_mission         提取关注范围                    │
│   retain_extraction_mode concise / verbose / custom      │
│   retain_every_n_turns   频率 (默认每轮)                  │
│   retain_tags            默认标签                        │
│                                                          │
│ 处理侧 (consolidation — 控制"怎么合并"):                 │
│   observations_mission   合并目标 (bank config API)       │
│   consolidation 频率     auto / manual (server-side)      │
│                                                          │
│ 取出侧 (recall — 控制"取什么"):                          │
│   recall_types           observation / world / experience │
│   recall_budget          low / mid / high                 │
│   recall_max_tokens      返回上限 (默认 4096)             │
│   recall_prefetch_method recall / reflect                 │
└─────────────────────────────────────────────────────────┘
```

Retain 和 Recall 是**完全独立的两端**:
- Retain 没有类型过滤 — LLM 提取时总是产生 world 和 experience，不存在"只存 world 不存 experience"
- Recall 的 `recall_types` 决定取回哪些类型
- 两端各自可控的杠杆不同

## recall_types — 取回哪些类型的记忆

**默认值变更为 `observation` only (Hindsight 0.7+)。**

### 三种类型的角色

| 类型 | 是什么 | 什么时候命中 |
|------|-------|------------|
| **observation** | 合并后的知识结论（多个 raw fact 合成） | "用户偏好哪种架构风格？" |
| **world** | 关于外部世界/用户的单个事实 | "用户说他用的是什么代理节点？" |
| **experience** | Agent 自己的行动记录 | "我之前推荐过什么方案？" |

### observation-only 的问题

1. **时延**: 刚 retain 的对话事实还没完成 background consolidation，立即 recall 返回空
2. **信息丢失**: consolidation 是抽象过程，具体细节（IP、端口、节点名）可能被丢弃
3. **孤立事实**: 不形成 pattern 的冷门信息永不出现

### 建议配置

对综合个人知识库（尤其需要记住技术细节的场景），扩到全部三种：

```json
"recall_types": "observation,world,experience"
```

`max_tokens` 仍控制总返回量，不变。observation 不再独占配额，多样性更高。

## recall_max_tokens — 返回容量

有两个层级：

| 位置 | 作用 | 设置方式 |
|------|------|---------|
| Bank API (`overrides.recall_max_tokens`) | 服务端硬限制 | `curl -X PATCH ...banks/main/config -d '{"updates":{"recall_max_tokens":8192}}'` |
| Plugin config.json (`recall_max_tokens`) | 插件请求参数 | 直接写在 config.json |

**Bank 层的值会覆盖插件设置**。如果 bank 设了 2048 而插件设了 8192，实际只返回 2048 tokens。检查方式：

```bash
curl -s -X PATCH http://localhost:8888/v1/default/banks/main/config \
  -H "Content-Type: application/json" \
  -d '{"updates": {}}'   # 空 update = 只读，返回当前 bank config
```

实际看到的值在 `config.recall_max_tokens` 和 `overrides.recall_max_tokens`（override 优先）。

### 选择建议

| tokens | 适合 |
|--------|------|
| 2048 | 轻量聊天，上下文紧张 |
| 4096 (默认) | 通用 |
| 8192 | 多 recall_types + 技术细节密集场景 |

三种 recall types 分 2048 tokens 每种只能塞几条。8192 每种分到 ~2700 tokens，技术排障的完整诊断链、项目经验、个人偏好都能被捞上来。

## retain_extraction_mode — 提取深度

| 模式 | 效果 | 适合 |
|------|------|------|
| `concise` (默认) | 选择性提取，只抓主要事实 | 通用聊天 |
| `verbose` | 提取更多事实，保留完整上下文和关系 | 技术讨论、需要保留细节 |
| `custom` | 完全自定义提取规则 | 高度定制场景 |

默认 `concise` 会把"9950x3d 的 sing-box 配了三节点：东京、新加坡、洛杉矶"简化为"用户有多节点代理配置"，丢掉节点名。技术知识库应设 `verbose`。

```json
"retain_extraction_mode": "verbose"
```

## retain_mission — 告诉 LLM 提取引擎关注什么

这是最直接影响存储质量的参数。默认不设，LLM 提取所有"显著"事实。设了之后，LLM 只关注指定范围。

### 编写原则

好的 retain_mission 需要：
1. **明确类别结构** — 第一类/第二类/忽略，让 LLM 知道粒度差异
2. **给出具体示例** — "提取 IP 地址、端口号、版本号、精确命令"比"保留细节"有效
3. **标注反例** — "忽略寒暄、问候、元讨论"防止噪音
4. **区分粒度** — 技术类"保留原文不抽象化"，非技术类"可概括但保留结论"

### 示例：综合个人知识库

```
This memory bank is a comprehensive, multi-domain personal knowledge base.

CATEGORY 1: IT / Computer Technology (PRIMARY — full detail, all technical work types)
- Project experience: architecture decisions, development pitfalls, bug fixes,
  refactoring lessons, failed attempts
- Troubleshooting: verbatim error messages, diagnostic output, root cause,
  successful fixes AND failed attempts
- System context: OS, tool versions, hardware specs, network topology, IPs, ports
- Configuration decisions: config file contents, parameter choices and rationale
- Toolchain & preferences: build systems, package management, version pitfalls
- AI/ML: model benchmarks, VRAM, inference speed, memory system tuning

CATEGORY 2: Personal Decisions & Preferences
- Consumer preferences, work habits, information consumption, tech preferences

CATEGORY 3: Life Assistance
- Health (checkups, exercise, medication), family, daily routines

CATEGORY 4: Other Interests
- Finance, entertainment, sports, history, any sustained interest

RULES:
- Tech: preserve raw specifics. Do not abstract.
- Non-tech: summarize acceptable, retain conclusions and reasoning.
- User statements → 'world' facts. Assistant statements → 'experience' facts.
- When assistant quotes tool output (error messages, config contents) in its
  response, extract as separate facts with verbatim text preserved.
- IGNORE: greetings, acknowledgments, repeated resolved issues, smooth coding
  with no debugging.
```

### retain_mission 设置方式（⚠️ 注意插件行为）

`retain_mission` 是 bank 级属性。虽然 Hermes Hindsight 插件在 config.json 中声明并读取了 `bank_retain_mission` 字段（`__init__.py` line 1309），但 `_build_retain_kwargs()` 不会把它传给 retain API，也没有在启动时调用 bank config PATCH。因此 **config.json 里写 `bank_retain_mission` 不会生效**——Hindsight bank 端仍然是 `null`。

**唯一生效方式：直接调 Hindsight bank config API。** 写入后持久化，容器重启不受影响。

```bash
# 写入 retain_mission（一次性，持久生效）
curl -X PATCH http://localhost:8888/v1/default/banks/main/config \
  -H "Content-Type: application/json" \
  -d '{"updates": {"retain_mission": "..."}}'

# 验证是否写入成功
curl -s http://localhost:8888/v1/default/banks/main/config | python3 -c "
import json,sys; d=json.load(sys.stdin)
print('retain_mission:', d['config']['retain_mission'])
"
```

**历史背景**：此问题发现于 2026-07-04。config.json 在上一轮会话中已写入完整的 `bank_retain_mission` 文本，重启 Hermes 后检查 bank：`retain_mission: null`。比对插件源码确认 `_build_retain_kwargs()` 不传此参数。

**重要区分**：`retain_extraction_mode` 也不是 config.json 支持的字段，只能通过 bank API 设置。

## Tool Output 未被自动捕获的问题

Hermes 的 auto-retain 机制只保留 `user` 和 `assistant` 角色的消息（`retain_roles: ["user", "assistant"]`）。Tool role 的命令输出、错误消息、配置文件内容**不进入 Hindsight**。

这意味着：
- 我执行 `ping 8.8.8.8` 返回 100% packet loss — **丢失**
- 我读取 `/etc/resolv.conf` 发现 `nameserver 127.0.0.1` — **丢失**
- 我在回复中说"ping 返回 100% loss，resolv.conf 指向 127.0.0.1" — **进入**

### 弥补方案

**方案 A（推荐）**: 在系统提示/SOUL.md 中要求 assistant 在回复中内联关键工具输出：
```
排障回复时，必须在回答中明确引用实际的错误消息、诊断命令输出和配置文件内容。
不要只说"发现 X 有问题"，要说"执行 ping 返回 100% packet loss"。
```

**方案 B**: 排障完成后主动调用 `hindsight_retain` 补写完整诊断链。

## 完整 config.json 示例

```json
{
  "mode": "local_external",
  "api_url": "http://localhost:8888",
  "bank_id": "main",
  "recall_types": "observation,world,experience",
  "bank_retain_mission": "This memory bank is...
}
```

## Record of This Session's Iterations

The retain_mission above went through multiple rounds of user correction:

1. **Initial attempt** — too focused on "避免踩坑" (avoiding mistakes), treated as the sole purpose
2. **First correction** — broaden to comprehensive knowledge base; IT primary but finance/entertainment/sports also covered
3. **Second correction** — technical scope too narrow (game dev + networking); expanded to C/C++/C#/Go/Python/Lua/graphics/architecture/ops
4. **Third correction** — troubleshooting over-emphasized; added project experience, bug fixes, refactoring across all project types (games, quant, apps, infra)
5. **Fourth correction** — missing life/health/family domain; user is 48, cares about personal and family health

**Lesson**: When writing a retain_mission for a user with broad interests, start with category structure (primary/secondary/life/other) rather than a single purpose statement. The user will correct narrow framing — iterate quickly.

## Re-Extracting Historical Data — Decision Framework

When you change extraction-related bank config (`retain_extraction_mode`, `retain_mission`), the old facts were extracted with old settings. Question: should you re-extract all 210+ documents?

### How Re-Extraction Works

Hindsight stores raw text per document (`original_text` field). Re-retaining with the same `document_id` deletes old facts and re-extracts with current bank config. No built-in "re-extract all" — must be scripted.

### Decision Factors

| Factor | Impact |
|--------|--------|
| Verbose vs Concise | Incremental gain. Embedding model (BGE-small) is the semantic recall bottleneck, not fact verbosity. Extra detail may not change recall ranking. |
| New retain_mission | Changes *what* gets extracted (scope/focus), so old facts may miss categories the mission now covers. |
| Recall params (max_tokens, types) | Affect retrieval only — no re-extraction needed. |
| Switching LLM | Unverified extraction quality with untested model. Hindsight's prompt format tuned for known providers. |
| Cost | 210 docs × 2-3 chunks × 2K tokens ≈ 840K tokens. Qwen3.6-27B ~75 tok/s ≈ 3-4 hours pure generation. |

### Recommendation

**Usually not worth it.** The "向前看" strategy is better: old concise facts remain searchable; new sessions benefit from verbose+mission extraction. Mixed-quality facts don't degrade recall because results are ranked by relevance, not verbosity.

Exceptions where re-extraction IS justified:
- `retain_mission` added a major new category that old sessions clearly contain (e.g., health records now needed but old extraction ignored them)
- Switching to a *significantly better* extraction model with proven Hindsight compatibility
- Starting a fresh bank from scratch (delete bank, re-import all sessions)

### Dry-Run Before Committing

Before any re-extraction, compare extraction quality on sample content:

```
POST /v1/default/banks/{bank_id}/extract-preview
{
  "content": "<sample conversation>",
  "retain_extraction_mode": "verbose",
  "retain_mission": "<new mission>"
}
```

Returns candidate facts WITHOUT persisting — safe to experiment.

When Hindsight is already running but the deployment method is unknown, check:

```bash
# Is it a Docker container?
docker ps --filter name=hindsight --format "{{.Names}} {{.Image}} {{.Status}}"

# Is it a system process?
ps aux | grep hindsight | grep -v grep

# What's listening on the port?
sudo lsof -i :8888
```

If Docker, get full config:
```bash
docker inspect hindsight --format '{{range .Config.Env}}{{println .}}{{end}}' | grep HINDSIGHT
docker inspect hindsight --format '{{range .Mounts}}{{.Source}} -> {{.Destination}} ({{.Type}}) {{end}}'
```

This reveals: extraction LLM provider/model, data directory, port mappings, restart policy.
