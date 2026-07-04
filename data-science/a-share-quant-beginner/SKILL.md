---
name: a-share-quant-beginner
description: 从零开始做 A 股量化交易研究 — 数据获取(baostock)、回测(backtrader)、纯终端模式、指标解读。
---

# A 股量化入门工作流

## 触发条件

用户说"研究量化炒股""学量化""跑股票数据"等，且是新手。

## 用户偏好（此用户）

- **纯终端** — Termux 远程操作，无 GUI/Jupyter/matplotlib 图表，所有输出打印在终端
- **中国大陆网络** — 电信宽带，akshare(东方财富API) 可能被重置连接；首选 **baostock** 数据源
- **先从 A 股开始** — 选流动性好的蓝筹股入门
- **编程背景** — Unity C#/Lua，不惧看代码，但股票概念是全新的

## 项目脚手架

```
~/mywork/quant-trading/
├── README.md
├── data/
├── src/
│   └── run_backtest.py
└── (optional) notebooks/
```

初始化：`git init && git branch -m main`

## 数据源选择

| 库 | 费用 | 推荐度 | 说明 |
|---|---|---|---|
| **baostock** | 免费免注册 | ⭐ 首选 | 国内直连稳定，sz/sh 前缀区分深交所/上交所 |
| akshare | 免费 | 备选 | 基于东方财富，国内有时连接被重置 |
| Tushare Pro | 基础免费 | 备选 | 需注册 token，API 更规范 |

### baostock 关键点

- **股票代码前缀**：上海 `sh.600xxx`，深圳 `sz.000xxx`/`sz.300xxx`
- `adjustflag="2"` = 前复权（推荐初学使用）
- 字段：`date,open,high,low,close,volume,amount`
- 用完必须 `bs.logout()` 释放连接

```python
import baostock as bs
bs.login()
rs = bs.query_history_k_data_plus(
    "sz.000001",  # 平安银行
    fields="date,open,high,low,close,volume,amount",
    start_date="2020-01-01", end_date="2025-06-24",
    frequency="d", adjustflag="2",
)
rows = []
while rs.next():
    rows.append(rs.get_row_data())
bs.logout()
```

## 回测框架

| 框架 | 推荐场景 |
|---|---|
| **backtrader** | 新手首选，事件驱动，策略代码直观 |
| vectorbt | 进阶后，向量化更快但门槛高 |

### backtrader 核心结构

```
Cerebro (引擎)
  ├── adddata(PandasData)   ← 数据
  ├── addstrategy(策略类)    ← 交易逻辑
  ├── addanalyzer(分析器)    ← 绩效指标
  └── run()                 ← 跑回测
```

### 策略模板（双均线金叉死叉）

```python
class MaCrossStrategy(bt.Strategy):
    params = (("short_period", 5), ("long_period", 20))

    def __init__(self):
        self.sma_short = bt.ind.SMA(period=self.params.short_period)
        self.sma_long = bt.ind.SMA(period=self.params.long_period)

    def next(self):
        if not self.position:
            # 金叉：短期均线上穿长期均线 → 买入
            if self.sma_short[0] > self.sma_long[0] and self.sma_short[-1] <= self.sma_long[-1]:
                self.buy()
        else:
            # 死叉：短期均线下穿长期均线 → 卖出
            if self.sma_short[0] < self.sma_long[0] and self.sma_short[-1] >= self.sma_long[-1]:
                self.sell()
```

## 纯终端输出格式

避免 GUI 依赖：
- `matplotlib.use("Agg")` 环境变量防止报错
- 交易明细用表格打印（买入日期/买入价/卖出日期/卖出价/盈亏%）
- 回测指标：总收益率 / 年化收益率 / 夏普比率 / 最大回撤

## 指标解读（面向新手）

| 指标 | 解释 |
|---|---|
| **胜率** | 赚钱交易次数占比。30-40% 对趋势策略算正常 |
| **盈亏比** | 平均盈利 ÷ 平均亏损。> 1.5 较好 |
| **夏普比率** | 风险调整后收益。> 1 好，> 2 很好，负值 = 不如无风险利率 |
| **最大回撤** | 从最高点到最低点的最大跌幅。越小越好 |

重要：**胜率低 ≠ 策略差**。趋势策略常胜率低但盈亏比高（亏小钱赚大钱）。

## 第一个项目推荐

**步骤**：选股 → 拉数据 → 算均线 → 跑回测 → 读结果

推荐起步股票（流动性好、数据长）：
- `000001` 平安银行（深交所，数据最全）
- `600519` 贵州茅台（A 股标杆，趋势性强）
- `600036` 招商银行（蓝筹代表）
- `600887` 伊利股份（消费龙头）
- `600900` 长江电力（极其平稳，做基准）

## 典型陷阱

- ❌ akshare 东方财富接口在国内某些网络下 `RemoteDisconnected` → 换 baostock
- ❌ baostock 股票代码前缀：`000001` 是深交所 `sz.000001`，不是 `sh.000001`（那是上证指数）
- ❌ 境外网络下部分国内数据源不可用 → 用模拟数据或换数据源
- ❌ matplotlib 在 Termux 无 GUI 环境下报错 → 设 `MPLBACKEND=Agg`，不走 `plt.show()`

## 参考

- `references/terminology.md` — 量化交易术语解释
