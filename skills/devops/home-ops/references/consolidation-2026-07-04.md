# Skill 合并与拆分记录 (2026-07-04)

## 第一阶段：Memory 整理

MEMORY.md: 16条(95%) → 7条(35%)
USER.md:   12条(94%) → 9条(66%)

核心方法：查重复 → 迁SOUL.md(行为原则) → 迁Skill(操作细节) → 查覆盖 → 合并同类 → 迁USER → 删凭证。
指针规则：skill description 覆盖功能域则不留 memory pointer；仅当触发词 gap 或路由交叉时才留最短 pointer。

## 第二阶段：33→1 Hub 合并

33 个 devops 独立 skill → 1 个 home-ops hub + 7 个 references。
最大的 proxy.md 达 182K，导致 agent 加载时必须吞入全部内容。

## 第三阶段：拆分过大 reference

proxy.md (182K) → proxy-sing-box(54K) + proxy-openclash(79K) + proxy-self-hosted(42K) + proxy-test(20K)
network.md (67K) → network-pitfalls(47K) + network-frp(20K) + network-wol(18K)
system.md (76K) → system-hermes(44K) + system(32K, 归档/Android/脚本)

拆分原则：
- 单文件控制在 ~80K 以下（约 20K tokens），agent 可一次性完整加载
- 按功能域边界拆分（sing-box / OpenClash / VPS / 测速）
- 导航表保持扁平（14行），不引入多层嵌套

## 基础设施

- ~/hermes-archive/ — Git 仓库，统一管理 skills/ + SOUL.md + MEMORY.md + USER.md
- SOUL.md 新增 Memory Maintenance + Skill Git Sync 章节
- GitHub: https://github.com/chenan2005/hermes-archive
