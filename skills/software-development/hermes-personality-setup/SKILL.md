---
name: hermes-personality-setup
description: 配置 Hermes Agent SOUL.md 人格/风格/知识组织原则 — 身份/语气/约束/工作流/Safety/Knowledge Organization。套用 agency-agents-zh 模板或自定义。
---

# Hermes Agent 人格配置

## 触发条件

用户提到「SOUL.md」「人格」「角色」「人设」「personality」「给它一个身份」等关键词，或要求定制 Hermes 的沟通风格。

---

## SOUL.md 是什么

SOUL.md 是 Hermes Agent 的**主身份文件**，位于 `~/.hermes/SOUL.md`（或 `$HERMES_HOME/SOUL.md`）。每次会话自动注入到系统 prompt 的 slot #1，完全替换内置默认身份。

### 放什么 / 不放什么

| ✅ SOUL.md（身份+风格+行为原则） | ❌ AGENTS.md（项目指令） |\n|---|---|\n| 语气、沟通风格 | 一次性项目指令 |\n| 直接程度 | 文件路径 |\n| 默认交互方式 | 仓库约定、编码规范 |\n| 应避免的风格 | 临时工作流细节 |\n| 面对不确定/分歧的态度 | 特定的单次操作步骤 |\n| **行为级工具使用原则**（如工具优先级、排查方式） |  |\n| **知识组织方式**（memory vs skill 划分规则） |  |

**好 SOUL.md 的特征**：跨情境稳定、宽到覆盖多数对话但具体到塑造语气、关注沟通和身份而非任务。

### 官方推荐基础结构

```markdown
# Identity
你是谁。

# Style
你听起来什么样。

# Avoid
你绝对不做什么。

# Defaults
有歧义时你默认怎么做。
```

### 可选扩展章节（按需添加）

```markdown
# Safety
安全原则——凭证传输、敏感操作约束等。

# Workflow
工作流原则——确认方案再动手、遇困难分级处理、排查方式、排障后归档等。

# Knowledge Organization
知识组织方式——memory 只记大方向、细则放 skill、skill description 覆盖功能域确保命中。
```

### 与 /personality 的关系

- **SOUL.md** = 持久默认人格（全局）
- **`/personality <name>`** = 会话级临时切换（如 `/personality teacher`）
- 内置 /personality 包括：helpful, concise, technical, creative, teacher, kawaii, noir 等 14 种

### 与 AGENTS.md 的关系

| SOUL.md | AGENTS.md |
|---|---|
| identity, tone, style, communication defaults | project architecture, coding conventions, tool preferences |
| 跟你到任何项目 | 只属于当前项目仓库 |

> "If it should follow you everywhere, it belongs in SOUL.md. If it belongs to a project, it belongs in AGENTS.md."

---

## 快速开始

### 1. 查看当前 SOUL.md

```bash
cat ~/.hermes/SOUL.md
```

### 2. 编辑

```bash
nano ~/.hermes/SOUL.md
```

修改后**新会话立即生效**，无需重启。

### 3. 写一段简单的试用

```markdown
# Identity
你是务实工程师，主要做 Unity/C# 游戏开发和网络运维。

# Style
直接简洁，不客套。
解释原理而非只给结论。
面对不确定时诚实说不知道。

# Avoid
说大话、假客气、重复显然的东西。
```

---

## 角色模板库：agency-agents-zh

`jnMetaCode/agency-agents-zh`（15.7k stars）提供 **266 个即插即用的 AI 专家角色模板**，覆盖 20 个部门（工程/设计/营销/金融/游戏开发等），含 50 个中国市场原创角色（小红书/抖音/微信运营等）。

### 仓库结构

```
engineering/     — 代码审查员、后端架构师、DevOps 等
game-development/   — Unity（架构师/编辑器工具/多人/Shader）、Unreal、Godot、Blender
design/          — UI/UX、平面设计等
marketing/       — 小红书运营、抖音投放、跨境电商等
finance/         — 财务分析、风险控制等
academic/        — 学业规划、考试备考等
```

### 模板文件结构

每个 `.md` 文件包含：

```yaml
---
name: XXX
description: 一句话描述
emoji: 🎭
color: blue
---
```

正文包含：身份与记忆 → 核心使命 → 关键规则 → 执行清单 → 代码示例 → 工作流程 → 沟通风格 → 成功标准 → 进阶能力

### 从模板应用到 SOUL.md

1. 从 repo 选一个最接近需求的模板文件
2. 复制其**身份描述部分**（YAML 下方到关键规则之前的段落）
3. 根据实际情况调整语言（工程/游戏/运维等）
4. 保存到 `~/.hermes/SOUL.md`

---

## 几种典型风格示例

### 务实工程师风

```markdown
# Identity
你是一个务实的资深工程师。

# Style
- 直接，不搞客套
- 简洁，除非复杂度需要深度
- 认为不对时明确说出来
- 偏好实用取舍而非理想化抽象

# Avoid
- 阿谀奉承
- 夸大其词
- 过度解释显然的事物
```

### 严格审查风

```markdown
# Identity
你是一个严格的评审者。公平，但不软化重要批评。

# Style
- 直接指出薄弱假设
- 正确性优先于和谐
- 明确说明风险和权衡
- 宁可 blunt 也不含糊其辞
```

### 耐心导师风

```markdown
# Identity
你是一个耐心的技术老师。关心的是理解，不是表现。

# Style
- 解释清楚
- 用例子辅助
- 除非用户给出信号，默认不假定先验知识
- 从直觉构建到细节
```

---

## SOUL.md vs MEMORY.md vs USER.md：为什么限额不对称？

用户常见疑问：SOUL.md 看起来没有大小限制，为什么 MEMORY.md（2,200 字符）和 USER.md（1,375 字符）限制这么严？

核心原因：**谁在往里面写东西。**

| 文件 | 上限 | 谁写的 | 超限行为 |
|------|------|--------|----------|
| SOUL.md | **20,000 字符** | 用户手动编辑 | 加载时 head+tail 截断 |
| MEMORY.md | 2,200 字符 | agent（memory 工具自动写） | 写入时报错，强制 agent 先合并/删除 |
| USER.md | 1,375 字符 | agent（memory 工具自动写） | 同上 |

SOUL.md 的 20K 上限与 AGENTS.md / .hermes.md 等所有上下文文件一致，并非"无限制"——只是正常人写的 SOUL.md 通常 500-3,000 字符，离 20K 很远，所以看起来像没限制。

**为什么 MEMORY.md / USER.md 设这么小的硬上限？**

1. **agent 不加约束会无限膨胀**：agent 被训练为每轮对话学到重要信息就往 memory 写。没有硬上限的话，一周后 MEMORY.md 轻松 10KB+，每次新会话都全额注入 system prompt，token 成本持续增长。

2. **system prompt 的 tier 架构不同**：SOUL.md 在 **stable 层**（写一次，prompt prefix cache 长期有效）；MEMORY.md/USER.md 在 **volatile 层**（每会话重新加载为快照，是实打实的 per-session token 开销）。

3. **小上限是触发 curation 的阈值，不是"够用就好"的容量**：当 memory 写满时，agent 必须主动合并或删除旧条目才能写入新条目。官方设计意图是：memory 不自动压缩，由 agent 自行决定保留什么。这是一种**信息密度训练机制**——强迫精炼，禁止当垃圾场。

4. **"Lost in the Middle" 防护**：memory 条目在 system prompt 中间位置，条目越多越容易被模型忽略。严格小上限保持 memory block 紧凑到模型能关注全部内容。

你的 memory 到 95% 时会多次触发 consolidation——这是预期行为，不是 bug。

## Pitfalls

- ❌ **不要把项目指令塞进 SOUL.md**（文件路径、工具使用方式、临时工作流）→ 放 AGENTS.md
- ❌ **写太模糊** — "be helpful" 是默认行为，无价值。要具体、有态度、有观点
- ❌ **期待当前会话生效** — SOUL.md 修改仅影响**新会话**，正在进行的对话不受影响
- ❌ **写太长被截断** — SOUL.md 上限 20,000 字符（与所有上下文文件一致），超长会 head+tail 截断。正常人写的 SOUL.md 500-3,000 字符，几乎不会触及这个上限
- ❌ **混淆文件角色** — 如果用户问"SOUL.md 和 MEMORY.md 有什么区别"或"为什么 memory 限制这么小"，参考上方「SOUL.md vs MEMORY.md vs USER.md」对比表
- ✅ **迭代** — 先写一小段试用，测试后再逐步调整，不用一次写到完美
