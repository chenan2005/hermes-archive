# jnMetaCode/agency-agents-zh 仓库导航

**URL**: https://github.com/jnMetaCode/agency-agents-zh
**Stars**: 15.7k
**角色数**: 266（含 50 个中国市场原创）
**支持工具**: Hermes Agent / Claude Code / Cursor / Copilot 等 18 种
**覆盖部门**: 20 个

## 目录结构

| 目录 | 角色数(约) | 子目录 |
|---|---|---|
| `academic/` | 5+ | 学业规划、考试备考、留学 |
| `design/` | 10+ | UI/UX、平面设计、字体 |
| `engineering/` | 50+ | AI工程、后端、前端、DevOps、代码审查、数据库、嵌入式、FPGA、Git 工作流、CMS |
| `finance/` | 10+ | 财务分析、风控、审计 |
| `game-development/` | 10+ | **Unity/** (architect, editor-tool, multiplayer, shader-graph)、**Unreal/**、**Godot/**、**Blender/**、game-designer、level-designer、narrative-designer、technical-artist |
| `hr/` | 5+ | 招聘、绩效 |
| `integrations/` | 10+ | 飞书、钉钉、企业微信 |
| `legal/` | 5+ | 合同、合规 |
| `marketing/` | 15+ | 小红书运营、抖音投放、SEO、内容营销 |
| `paid-media/` | 5+ | 广告投放 |
| `product/` | 10+ | 产品经理、需求分析 |
| `project-management/` | 5+ | PMO、敏捷教练 |
| `sales/` | 5+ | 销售策略 |
| `security/` | 5+ | 安全审计、渗透测试 |

## 模板文件结构（通用）

每个 `.md` 文件格式：

```yaml
---
name: <角色中文名>
description: <一句话描述>
emoji: <单emoji>
color: <颜色名>
---
<角色名>

**身份与记忆**
角色定义、性格、经验

**核心使命**
主要职责、关注领域

**关键规则**
行为准则、红线

**<技术名称>**
语言/框架特定的代码示例和反模式

**工作流程**
1. 步骤一
2. 步骤二
...

**沟通风格**
语言特点示例

**成功标准/常见反模式**
量化验收条件
```

## 如何从模板获取内容

### 方法：通过浏览器查看

```python
# 在 execute_code 或 browser_console 中使用
# 1. 打开 GitHub 文件页面
# 2. 用 JS 提取内容：
document.querySelector('article').innerText
```

### 关键链接

- 仓库根: https://github.com/jnMetaCode/agency-agents-zh
- 工程类: https://github.com/jnMetaCode/agency-agents-zh/tree/main/engineering
- Unity 类: https://github.com/jnMetaCode/agency-agents-zh/tree/main/game-development/unity
- 游戏开发: https://github.com/jnMetaCode/agency-agents-zh/tree/main/game-development
- 中国市场: https://github.com/jnMetaCode/agency-agents-zh/tree/main/marketing
