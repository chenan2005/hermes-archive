---
name: todo-list
description: 待办管理（增删查改）+ 想法记录 + 持续关注会话。回家/周末/一般/想法分类。用户说"待办""待处理""近期待处理工作""想法""关注会话""最近工作""近期重要对话"时命中。
---

# TODO List

## ⚠️ 关键规则（必须遵守）

**不要碰 `todo()` 工具。** 待办存于本 SKILL.md，不是会话绑定的 `todo()` 工具。

**用户问待办时——立刻直接 `skill_view(name='todo-list')`。**
"问待办"包括任何询问未完成工作、待处理事项、近期任务的问法（如"待办""待处理""最近工作""近期待处理工作""近期待办""还有什么没做""看看有什么要做的"），即使不包含"待办"二字也算。不要等 auto-trigger 命中——语义相近就主动 load。
不要查 `todo()` 工具、不要翻 cron、不要搜文件、不要翻记忆！
唯一来源就是本 SKILL.md，走任何弯路用户都会反感。

写：`patch()` 或 `write_file()` 编辑 SKILL.md
永远不要调 `todo()` 来查待办

⚠️ 这个规则被用户反复纠正过，别重犯。

**常见弯路（禁止）** — 用户反馈过这些问题：
- ❌ 先查 `todo()` 工具 → 一定为空，浪费时间
- ❌ 搜 hindsight recall 找"近期待办" → 混淆记忆中的片段与待办清单
- ❌ 查 cron job 列表 → 和待办内容无关
- ❌ 搜文件 `*todo*` / `*待办*` → 唯一来源就是 skill_view
- ❌ 等 auto-trigger 命中 → 语义相近（近期待处理工作/还有什么没做/最近工作）就应该主动 load
- ✅ **一步到位：直接 `skill_view(name='todo-list')`**，其他什么都不查

## 编辑规则

### 新增待办
When user says "记一条<类别>待办：xxx" 或 "记一个<类别>想法：xxx":
1. 扫描整个文件所有 `- tN` 行，找出最大编号
2. 新条目编号为 t(最大+1)
3. 追加到匹配的 `## <类别>` header 下，格式：`- t<N> [ ] [标签] 内容`
4. **若用户未指定 <类别>，默认归入「一般待办」**
5. **类别「想法」无需 tN 编号，用日期做标识**

### 查看
When user says "查看待办" / "还有什么待办", read full file via `skill_view(name='todo-list')` and present grouped by category.
When user asks "最近工作" / "近期待办" / "最近重要对话", show both `## 待办` 各分类 + `## 持续关注会话`。

### 完成/删除
When user says "完成了" / "删掉" for an item:
- 支持 tN 引用（如 "t3完成了"），通过编号精确定位条目
- 标记完成：`- tN [ ]` → `- tN [x]`
- 删除：移除整行；**不要重新编号**，中间跳号是正常的（用户明确接受"跳号"）

### 持续关注会话
**当用户说"关注本会话"或类似表达时，结束后添加到 `## 持续关注会话`**。格式：
`- s<N> [YYYY-MM-DD] 主题 | session:<session_id> | 存放位置 | 关键结论`
- sN 自增编号（用已有会话的最大 sN+1），用于交流时引用
- session_id 从当前会话的 session_id 获取（方法见 `references/session-id-retrieval.md`），可通过 `session_search(session_id="...")` 恢复
- 只记有可追溯成果的对话，不记琐碎问答和讨论过程。
**分类名必须用「持续关注会话」，不要用"近期重要对话"或其他命名。**

### ⚠️ 陷阱
- 不要合并条目。即使用户说把几条待办"放到一起"，默认也是放入同一分类下作为独立条目保留。
- 不要重新编号。删除/完成只改状态或移除行，tN 永远不回收。

## 格式约定

### 待办
- 每条待办以 `- [ ] [标签]` 开头，标签 = 类别名，如 `[回家]`、`[周末]`
- 每条待办有自增编号 `tN`（如 `t1`、`t2`），放在行首，用于交流时引用
- 已完成项改为 `- [x] [标签]` 而非删除，除非用户明确说删掉
- 按 `## 类别` 分组，每类一个二级标题
- 允许跳号（如 t3 完成后直接跳过 t5），不回收编号

### 持续关注会话
- 每条会话以 `- s<N> [YYYY-MM-DD] 主题 | session:<session_id> | 存放位置 | 关键结论` 格式记录
- sN 自增编号（如 s1、s2），与 tN 同类机制，用于交流时引用
- session_id 用于 `session_search(session_id="...")` 恢复完整会话

For the reminder system architecture and how to add new categories, see `references/reminder-system.md`.

## 一般待办

- t1 [ ] [一般] 十字链表实现测试
- t2 [ ] [一般] 研究量化炒股

- t3 [x] [一般] 打通 192.168.71.9 作为网关的连接及代理可用
- t4 [x] [一般] 旁路由迁移（11→9，ImmortalWrt 接管）
- t6 [ ] [一般] Seoul Reality dest 域名从 bing 换更冷门的（如 amazon.com），并考虑定期轮换
## 回家待办

- t5 [x] [回家] 搞定 9900K PC 登录，实现免密连接

## 周末待办

（暂无）

## 持续关注会话

每条记录格式：`- s<N> [YYYY-MM-DD] 主题 | session:<session_id> | 存放位置 | 关键结论`
- sN 编号用于交流时引用（如"s3怎么resume"），与待办 tN 同类机制
- session_id 可直接用于 `session_search(session_id="...")` 读取完整会话

- s1 [2026-06-23] 十字链表 2D 空间索引 | session:20260623_073737_b89954 | ~/mywork/cross-linked-list/ | 三方案对比：纯网格(N=5000) 0.019ms/frame 最佳，269x 快于纯链表。git 已初始化，docs/architecture.md 有完整实现文档。
- s2 [2026-06-25] 量化炒股入门 | session:20260625_222409_5144ca | ~/mywork/quant-trading/ | baostock 数据源跑通，双均线策略(MA5×MA20)回测平安银行 5.5年42次交易微亏0.01%，胜率31%。git 已初始化，src/run_backtest.py 纯终端版可用。
- s5 [2026-06-27] 归档系统开发 + 知识体系整理 | session:20260627_085902_772212 | ~/.hermes/archive/ + SOUL.md + skills | 归档系统 v4 重构成 src/data/docs，中英文工具描述，session_archive_records 索引。Memory 从 27 条精简约 8 条（72%）。确立三层组织：SOUL.md（行为原则）/ Memory（环境事实）/ Skills（流程细则）。归档系统推送到 github.com/chenan2005/hermes-archive。watchdog 测试后删除（cron 不支持 CLI）。当前手动归档。
- s6 [2026-07-04] 个人笔记系统方案调研 | session:20260704_195700_9039a1 | ~/notes/ (计划中) | 调研 Mem/Fabric/Recall/Tana/Obsidian/Notion/NotebookLM/Capacities/Anytype 共 9 款。结论：Obsidian 核心（本地 Markdown + Smart Connections 本地向量 + 可插拔 LLM），自建 Python pipeline 抓取中文平台（B站/头条/CSDN），Hindsight 做语义索引层，NotebookLM 做分析加工站。三层架构：Obsidian（内容层）+ Hindsight（索引层）+ Python（采集层）。已确认方案，待初始化 vault。
- s7 [2026-07-05] Coding Agent Loop Engineering 概念调研 | session:20260705_101805_bf4d6c | 无持久文件（纯会话讨论） | 2026年6月爆火：不再手动prompt agent，设计循环系统让agent自主迭代。两层loop：内部ReAct循环(老概念) + 外部Harness Loop/loop specification(新热点)。关键模式：Ralph Wiggum Loop、TDD AI Agent Loop、Andrew Ng三层框架、Self-Healing CI Loop。核心资料：arXiv 2607.00038论文、Loop Library(50个真实loop)、Armin Ronacher "The Coming Loop"警示文。风险：代码质量退化、token成本4-15x、理解债务。
- s8 [2026-07-06] Memex 个人知识助手方案设计 | session:20260706_201822_0dfb10 | 暂无持久文件（方案讨论中） | 定名 Memex。定位收敛：不新建存储系统，Hermes+Hindsight 即为外脑界面。Memex 补齐两个缺口：①外部内容采集 adapter（头条/B站/飞书/PDF）②主动推送（定时摘要/异常告警/知识缺口/关联发现）。从资料收集起步。待定：采集方式、视频处理深度、MVP 边界。
