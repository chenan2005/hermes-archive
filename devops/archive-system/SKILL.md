---
name: archive-system
description: 会话归档系统 — LLM 驱动的话题分组归档。v4引擎, github.com/chenan2005/hermes-archive。src/data/docs 目录结构, install.sh 部署。英文函数调用风格 archive([topicData,...])。用户自主触发归档。
---

# 会话归档系统（Session Archive System）

> 最后更新: 2026-06-27（项目目录重构）

## 项目概况

Hermes 对话历史的**话题归档系统**。LLM 分析会话 → 按主题分组 → 持久化到磁盘。
遵循「零改动 Hermes 核心代码」原则，所有代码以新文件形式存在。

**状态：已上线运行，10 个已归档话题，v4 引擎。用户自主触发归档。**

## 目录结构

```
archive/                          ← 项目根目录（git remote: github:chenan2005/hermes-archive）
├── src/                          ← 源码（git 跟踪）
│   ├── archive.py                ← v4 归档引擎（CLI + stdin）
│   ├── dedup.py                  ← SimHash 语义去重
│   └── archive_tool.py           ← Hermes 工具注册（install.sh 部署到 hermes-agent/tools/）
├── data/                         ← 运行时数据（.gitignore 忽略，git 不跟踪）
│   ├── index.json                ← 全局索引（当前10话题，next_gid=12）
│   └── groups/                   ← 话题组元数据
├── docs/
│   └── ARCHITECTURE.md           ← 完整技术文档（git 跟踪）
├── install.sh                    ← 部署脚本（git 跟踪）
└── .gitignore
```

---

## 架构

```
LLM 分析会话
  │
  ├─ archive(action='archive', groups=[...])
  │     │  source_message_indices → _indices_to_message_ids() → state.db ID
  │     │
  │     └─ subprocess → archive.py (stdin)
  │           │  write_group() / merge_into_group()
  │           └─ index.json + groups/{gid}/{meta.json, sources/*.json}
  │
  ├─ archive(action='load_session')
  │     └─ 直读 state.db SQLite → 全量消息
  │
  ├─ archive(action='ls')
  │     └─ archive.py ls
  │
  ├─ archive(action='show', gid=N)
  │     └─ archive.py show <gid>
  │
  └─ archive(action='delete', gid=N)
        └─ archive.py delete <gid>
```

### 关键设计点

- **check_fn 门控**：`check_archive_requirements()` 检查 `archive.py` 是否存在，不存在时工具自动隐藏
- **文件锁**：`fcntl.flock` 保护 `index.json` 并发写入
- **指标转换**：LLM 传 0-based 数组索引 → handler 转 state.db message_id
- **字段限制**：title ≤20 / description ≤120 / summary ≤3000 chars

---

## 当前状态

### 已归档话题（13 个）

| gid | 标题 | project | 消息数 |
|-----|------|---------|-------|
| 3 | SSH端口转发与VPN隧道 | general | 82 |
| 4 | Hermes记忆机制解析 | hermes-agent | 120 |
| 5 | 系统信息与开发环境配置 | general | 30 |
| 6 | Hermes记忆与Web搜索机制 | general | 30 |
| 7 | SSH+FRP远程访问配置 | general | 30 |
| 8 | V2Ray代理与DNS优化 | general | 30 |
| 9 | 多设备管理与CPU性能对比 | general | 30 |
| 10 | 会话归档系统设计与实现 | hermes-agent | 260（含迭代） |
| 11 | Android远程桌面客户端选型 | general | 38 |
| 13 | 国产运动鞋选购咨询 | general | 2 |

下一个可用 gid: 12

### 已知问题

| 问题 | 严重度 | 说明 |
|------|--------|------|
| 话题不在系统提示中 | 🟡 低 | LLM 需调用 `archive ls/show` 主动发现，无法自动注入 |
| 会话清理后引用失效 | ⚠️ 低 | `sources/{session}.json` 存的是 message_id，会话被清理后引用失效 |

---

## 操作指南

### 操作流程

```
归档前：archive(show, gid=[gid1, gid2, ...]) 一次拉所有待合并话题的当前摘要
归档时：archive([topicData, ...]) 一次写入所有新老话题
```

### 归档当前会话

当会话覆盖了 3+ 个不同技术话题（各 ≥5 轮且有结论）时，用此工具归档：

```python
archive(action='archive', session_id='xxx', groups=[{
    'title': '话题名',
    'description': '一句话描述（≤120 chars）',
    'summary': '学术风格摘要（目标+关键步骤+结论，≤3000 chars）',
    'source_message_indices': [1, 5, 9, ...],  # 0-based，system prompt = 0
    'project': 'hermes-agent',  # 或 None
}])
```

### 合并已有话题

```python
# 1. 先看已有话题
archive(action='show', gid=[3])

# 2. 合并
archive(action='archive', session_id='xxx', groups=[{
    'title': '更新后标题',
    'description': '更新后描述',
    'summary': '合并新旧内容的完整摘要',
    'source_message_indices': [3, 7, ...],
    'merge_into': 3,
}])
```

### 查看/管理

```python
archive(action='ls')                         # 列表
archive(action='show', gid=[3, 5])           # 详情
archive(action='show', title='SSH')          # 模糊搜索
archive(action='delete', gid=[99])           # 删除
```

### load_session（历史会话全量读取）

```python
archive(action='load_session', session_id='xxx')
# 返回含 message_id 的完整消息列表，适合历史会话归档
archive(action='load_session', session_id='xxx', profile='work')  # 跨 profile
```

---

## 数据模型

### 目录结构

```
~/.hermes/archive/data/           # 运行时数据（gitignore）
├── index.json                    # 全局索引（version, next_gid, groups）
└── groups/
    ├── general/{gid}/
    │   ├── meta.json             # title, description, summary, 时间戳, source_sessions
    │   └── sources/{session_id}.json  # 原始 message_ids
    └── projects/{project}/{gid}/
```

### index.json 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| version | int | 数据版本（当前 v4） |
| next_gid | int | 下一个可用话题 ID |
| groups | [group] | 话题摘要列表 |
| **session_archive_records** | {sid: {msg_count, time}} | 会话归档记录（dict keyed by session_id），每次归档自动更新，记录归档时的消息数和时间 |

### meta.json 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| gid | int | 自增唯一 ID |
| title | str (≤20) | 可读话题名 |
| description | str (≤120) | 一句话说明，可注入系统提示 |
| summary | str (≤3000) | 学术风格摘要 |
| project | str\|null | 命名空间（null=general） |
| source_sessions | [str] | 来源会话 ID 列表 |
| versions | [{session, merged_at}] | 合并版本记录 |

---

## 维护命令

```bash
# 验活
cd ~/.hermes/archive && python3 src/archive.py ls

# 手动查看
python3 src/archive.py show 3
python3 src/archive.py show --title 记忆

# 安装/部署
bash install.sh                    # 部署到 hermes-agent/tools/

# 提交文档变更
cd ~/.hermes/archive && git add -A && git commit -m "..."

# 确认工具可用
cd ~/.hermes/hermes-agent && python3 -c "
from tools.registry import discover_builtin_tools, registry
discover_builtin_tools()
e = registry.get_entry('archive')
print('archive tool:', 'registered' if e else 'MISSING')
"
```

---

## Git 仓库

| 远程 | URL |
|------|-----|
| origin | `https://github.com/chenan2005/hermes-archive.git` |

```bash
# 日常开发流程
cd ~/.hermes/archive
git add -A && git commit -m "..."
git push

# 部署到 hermes-agent（改完 src/ 后）
bash install.sh
```

## 设计历史

本系统最初为 v2→v4 演进设计，详细技术文档见 `~/.hermes/archive/docs/ARCHITECTURE.md`（已提交到 git）。

---

## 部署生命周期

```
改 src/ 代码 → bash install.sh → 重启 Hermes（/reset 或 /new 不够）
```

`/reset` 和 `/new` **不会重新加载工具代码**。Python 进程启动时 `discover_builtin_tools()` 扫描一次并缓存。部署后必须完全退出 Hermes 再重新进入。

验证：
```bash
cd ~/.hermes/hermes-agent && python3 -c "
from tools.registry import discover_builtin_tools, registry
discover_builtin_tools()
e = registry.get_entry('archive')
print('archive:', 'OK' if e else 'MISSING')
"
```

## 设计原则

### 工具描述风格

Archive 工具所有 action 的描述使用**英文 + 函数调用风格**：

```
archive([topicData, ...]) — 写入话题组。
topicData = {merge_into?: gid, title, description, summary,
             source_message_indices?: [int], message_ids?: [int], project?: string}
  新建话题：传 title/description/summary + source_message_indices（当前会话）或 message_ids（历史会话）
  合并已有话题：加 merge_into=<gid>，新的 title/description/summary 会覆盖原值
```

语义层级：**title < description < summary**

| 字段 | 限制 | 语义 |
|------|------|------|
| title | ≤20 chars | "这是什么话题" |
| description | ≤120 chars | 一句话标注，用于列表快速识别 |
| summary | ≤3000 chars | 完整内容摘要，学术风格（目标→过程→结论） |

LLM 对这三个词的语义理解是准确的，不会搞混。

## 排坑

- `archive` 工具不可见 → 运行部署命令后必须重启 Hermes 进程（/reset 不够）
- 归档失败 `archive.py timed out` → 确认 `data/index.json` 格式正确无损坏
- 合并时内容被覆盖 → `merge_into` 会完全覆盖 title/description/summary，合并前先 `show` 读取旧摘要
- 指标转换错误 → LLM 传入的是 0-based 数组索引，system prompt = index 0
- **`patch()` 改 Python 源码易转义坏掉** — 用 `read_file` 确认精确字节再写 old_string；复杂大段替换改用 `write_file` 整体写入
