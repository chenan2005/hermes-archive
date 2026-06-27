# 会话归档系统 — 技术文档

> 最后更新: 2026-06-27

## 目录

1. [概览](#1-概览)
2. [文件布局](#2-文件布局)
3. [数据模型](#3-数据模型)
4. [引擎层: archive.py](#4-引擎层-archivepy)
5. [去重层: dedup.py](#5-去重层-deduppy)
6. [工具层: archive_tool.py](#6-工具层-archivetoolpy)
7. [操作流程](#7-操作流程)
8. [设计原则](#8-设计原则)
9. [维护指南](#9-维护指南)

---

## 1. 概览

会话归档系统是一个 **LLM 驱动的话题分组归档工具**，用于将 Hermes 对话历史按主题整理和持久化。

```
LLM 分析会话 → 识别话题组 → 调用 archive 工具 → 写入 ~/.hermes/archive/
```

核心定位：**零改动 Hermes 核心代码**。所有代码以新文件形式存在。

---

## 2. 文件布局

```
~/.hermes/archive/                            # 项目根目录（独立 git 仓库）
├── src/                                      # 源码
│   ├── archive.py                            # v4 归档引擎（492 行）
│   ├── dedup.py                              # SimHash 去重模块（95 行）
│   └── archive_tool.py                       # Hermes 工具集成（474 行）
├── data/                                     # 运行时数据
│   ├── index.json                            # 全局索引
│   └── groups/                               # 话题组数据
│       ├── general/{gid}/                    # 无 project 的话题
│       │   ├── meta.json                     # 元数据
│       │   └── sources/{session_id}.json     # 原始消息 ID 引用
│       └── projects/{project}/{gid}/         # project 命名空间
├── docs/
│   └── ARCHITECTURE.md                       # 本文档
├── install.sh                                # 部署脚本
└── .gitignore
```

### git 仓库

| 仓库 | 位置 | 分支 | 最近 commit |
|------|------|------|-------------|
| 归档项目 | `~/.hermes/archive/.git` | `master` | `ddc8a07` refactor: 项目目录重构 |
| Hermes 核心 | `~/.hermes/hermes-agent/.git` | `local/customizations` | `ede35f50d` feat: session archive tool (zero Hermes core modifications) |

---

## 3. 数据模型

### index.json

```json
{
  "version": 4,
  "next_gid": 12,          // 下一个可用 gid（自增）
  "groups": [               // 话题摘要列表
    {
      "gid": 3,
      "title": "SSH端口转发与VPN隧道",
      "description": "通过公司VPN连接开发机SSH(RDP隧道转发)，尝试rdp2tcp方案",
      "project": null,       // null = general, "hermes-agent" = projects
      "created_at": "2026-06-20T23:07:55",
      "updated_at": "2026-06-20T23:07:55",
      "source_sessions": ["20260613_085712_90ad3b"],
      "message_count": 82
    }
  ]
}
```

### groups/{gid}/meta.json

```json
{
  "gid": 3,
  "title": "SSH端口转发与VPN隧道",
  "description": "通过公司VPN连接开发机SSH...",
  "summary": "完整摘要（≤3000 chars）",
  "project": null,
  "created_at": "2026-06-20T23:07:55",
  "updated_at": "2026-06-20T23:07:55",
  "source_sessions": ["20260613_085712_90ad3b"],
  "versions": [{ "session": "20260613_085712_90ad3b", "merged_at": "..." }]
}
```

### sources/{session_id}.json

```json
{
  "session_id": "20260613_085712_90ad3b",
  "message_ids": [1995, 2003, 2012, ...]    // 对应 state.db 的 id
}
```

---

## 4. 引擎层: archive.py

位置：`~/.hermes/archive/src/archive.py`（492 行）

### 文件锁

使用 `fcntl.flock()` 实现进程级互斥，确保并发操作不会损坏 index.json。

```python
with _locked_index() as index:
    # 读 + 写 index.json
    # 退出上下文时自动保存
```

### 核心函数

| 函数 | 职责 | 输入 | 输出 |
|------|------|------|------|
| `init()` | 创建目录结构，初始化 index.json | 无 | 无 |
| `write_group()` | 创建新话题组 | title, description, summary, message_ids, session_id, project | gid (int) |
| `merge_into_group()` | 合并新内容到已有话题组 | gid, title, desc, summary, message_ids, session_id, project | gid (int) |
| `_delete_group()` | 删除话题组 | gid | bool |
| `_group_dir()` | 解析话题组路径 | gid, project | Path |

### CLI 接口

**stdin 模式**（无参数时触发，用于 `archive` action）：

```bash
echo '{"session_id":"...","groups":[...]}' | python3 src/archive.py
```

**子命令模式**：

| 命令 | 用法 |
|------|------|
python3 src/archive.py ls               # 列出所有话题
python3 src/archive.py ls project <name> # 按 project 过滤
python3 src/archive.py show <gid>        # 查看话题详情
python3 src/archive.py show --title <query>   # 按标题模糊搜索
python3 src/archive.py delete <gid>      # 删除话题
python3 src/archive.py delete --title <query> # 按标题模糊删除

### 字段限制

| 字段 | 上限 |
|------|------|
| title | 20 chars |
| description | 120 chars |
| summary | 3000 chars |

---

## 5. 去重层: dedup.py

位置：`~/.hermes/archive/src/dedup.py`（95 行）

基于 **SimHash 指纹** 的语义去重，用于在合并话题时过滤掉重复的摘要内容。

### SimHash 算法

```
文本 → 字符 bigram 分词 → MD5 → 加权位向量 → 64-bit 指纹
```

- 字符 bigram 在中英文混合场景下无需分词依赖
- 汉明距离 < 20 ≈ 66%+ 相似度
- 短消息（<100 chars）跳过去重，避免误杀

### 调用方式

```python
from dedup import dedup_messages

kept_ids, skipped = dedup_messages(
    messages,                # [{id, content}, ...]
    topic_summary,           # 已有摘要
    threshold=20,            # 汉明距离阈值（0-64，越低越严格）
)
```

---

## 6. 工具层: archive_tool.py

位置：`~/.hermes/archive/src/archive_tool.py`（474 行）。`install.sh` 部署到 `hermes-agent/tools/`。

### 注册方式

```python
from tools.registry import registry

registry.register(
    name="archive",
    toolset="session_search",     # 借用已有工具集，不改 toolsets.py
    schema=ARCHIVE_SCHEMA,        # LLM 可见的 JSON schema
    handler=...,                   # 参数处理后分发到 _run_archive_subcommand
    check_fn=check_archive_requirements,  # 条件显示：仅在 src/archive.py 存在时注册
    description="Persist session topics with array-index message references",
    emoji="🗄️",
)
```

### check_fn 门控

```python
def check_archive_requirements() -> bool:
    return ARCHIVE_DIR.exists() and (ARCHIVE_DIR / "archive.py").exists()
return (ARCHIVE_DIR / "src/archive.py").exists() and DATA_DIR.exists()

仅在 `~/.hermes/archive/src/archive.py` 和 `~/.hermes/archive/data/` 都存在时注册。

### 指标 → ID 转换

LLM 看到的消息数组是 0-based：`messages[0] = system prompt`

```python
# LLM 传入: source_message_indices = [1, 5, 9]
# 转换: state_db_position = index - 1
# 实际: 从 state.db 查到的 message_ids = [10439, 10443, 10447]
```

### load_session（替代旧 dump_all）

直读 state.db 的 SQLite，一次调用获取整条会话的全部消息。支持跨 profile 读取。

```python
# 调用
archive(action='load_session', session_id='...')
archive(action='load_session', session_id='...', profile='work')

# 返回
{
  "success": True,
  "messages": [{"id": 1, "role": "user", "content": "..."}, ...],
  "message_count": 141,
  "session_meta": {"title": "...", "source": "...", "model": "...", "when": "..."},
  "truncated": False
}
```

### 工具 Schema（给 LLM 看）

完整的 JSON schema 定义了 5 个 action：

```
archive   — 写入话题组（新建/合并）
ls        — 列出所有话题
show      — 查看话题详情（gid 或 title）
delete    — 删除话题（gid 或 title）
load_session — 读取历史会话全量消息
```

Schema 中的 description 字段承载使用指引（最佳实践、merge_into 用法、project 设置等）。

---

## 7. 操作流程

### 归档当前会话

```python
archive(action='archive', session_id='xxx', groups=[{
    'title': '话题名',           # ≤20 chars
    'description': '一句话描述',  # ≤120 chars
    'summary': '完整摘要',       # ≤3000 chars
    'source_message_indices': [1, 5, 9],  # LLM 看到的数组索引
    'merge_into': None,           # None=新建，int=合并到已有
    'project': 'hermes-agent',    # 或 None 表示 general
}])
```

### 归档历史会话

```python
# 1. 先加载历史会话
data = archive(action='load_session', session_id='xxx')
# data.messages 包含所有消息的 id

# 2. 传入 message_ids（非索引）
archive(action='archive', session_id='xxx', groups=[{
    'title': '...',
    'description': '...',
    'summary': '...',
    'message_ids': [id1, id2, ...],  # state.db 的原始 ID
}])
```

### 合并到已有话题

```python
# 1. 先查看已有话题
archive(action='show', gid=[3])

# 2. 合并新内容（title/description/summary 会被覆盖）
archive(action='archive', session_id='xxx', groups=[{
    'title': '更新后的话题名',
    'description': '更新后的描述',
    'summary': '合并新旧内容的完整摘要',
    'source_message_indices': [3, 7, 15],
    'merge_into': 3,  # 合并到 gid=3
}])
```

---

## 8. 设计原则

1. **零改动核心代码** — 不修改 `agent/`、`toolsets.py`、`prompt_builder.py` 等 Hermes 自带文件
2. **check_fn 门控** — 工具仅在依赖存在时注册，避免空调用
3. **单次写入** — `archive()` 一次调用处理所有话题组，上下文利用率高
4. **文件锁保护** — `fcntl.flock` 防止并发损坏 index.json
5. **LLM 友好的接口** — 0-based 数组索引，无需知道 state.db 内部 ID
6. **自包含** — `archive.py` 无外部依赖（Python 标准库即可运行）
7. **SimHash 去重** — 合并时智能过滤重复信息，不依赖分词器

---

## 9. 维护指南

### 测试归档系统是否正常

```bash
cd ~/.hermes/archive
python3 src/archive.py ls                         # 列出所有话题
python3 src/archive.py show 3                     # 查看 gid=3
python3 src/archive.py show --title SSH           # 标题搜索
```

### 测试 Hermes 工具集成

```bash
cd ~/.hermes/hermes-agent
python3 -c "
from tools.archive_tool import check_archive_requirements
print('check:', check_archive_requirements())
"
```

### 恢复步骤

如果 `archive` 工具在 Hermes 中不可见：

1. 确认 `~/.hermes/archive/src/archive.py` 存在
2. 确认 `~/.hermes/hermes-agent/tools/archive_tool.py` 存在（否则运行 `bash ~/.hermes/archive/install.sh`）
3. `hermes tools list | grep archive`
4. 如果未注册，重启 Hermes（`/reset`）
5. 如果仍不可见，检查 hermes-agent 版本是否包含 archive_tool

### 当前归档状态

| 指标 | 值 |
|------|-----|
| 引擎版本 | v4 |
| 已归档话题 | 9 |
| 下一个 gid | 12 |
| 源码位置 | `~/.hermes/archive/src/` |
| 部署工具 | `~/.hermes/archive/install.sh` |
