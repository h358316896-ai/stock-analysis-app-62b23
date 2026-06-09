# 回测说明

这是一个简单的均线交叉回测示例，使用 `yfinance` 拉取历史数据并运行 SMA(short/long) 策略。

准备与运行：

```bash
cd prototype/stock/backtest
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt

# 运行回测（示例）：
python backtest.py --symbol 600519 --market cn --period 3y --short 50 --long 200

# 输出：在当前目录生成 equity_600519.png 并在终端显示回测统计。
```

说明：
- 本示例仅为教学演示，未包含交易成本、滑点、持仓限制和资金管理等真实要素。建议在生产回测中加入这些因素并做更全面的风险控制与参数检验。

新增参数（交易成本与滑点）：
- `--commission`：按交易额比例的手续费（默认 0.001，即 0.1%）。
- `--slippage`：按交易额比例的滑点估算（默认 0.001，即 0.1%）。

示例：带费用运行

```bash
python backtest.py --symbol 600519 --market cn --period 3y --short 50 --long 200 --commission 0.001 --slippage 0.001
```

说明：当前实现为近似模型，会在每日持仓变化时基于当日组合市值扣除交易成本（turnover*(commission+slippage)），以简化交易执行时点对回报的影响。在生产级回测中建议使用逐笔成交价格（开盘/滑点模型）与资本分配规则进行更精细模拟。

新增高级回测工具：逐笔执行引擎与网格批量回测
- `engine.py`：实现 `Backtester` 类，使用次日开盘价执行成交，支持 `capital`, `position_size`, `commission`, `slippage`, `fixed_fee` 参数，并返回逐日权益曲线、交易列表与统计指标。
- `grid.py`：对一组 `short`/`long`/`position_size`/`commission`/`slippage` 参数做批量回测，输出 `grid_results/grid_results.csv` 与每只代码的年化收益热力图 `heatmap_<symbol>.png`。

运行示例：网格回测

```bash
cd prototype/stock/backtest
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python grid.py
```

说明：`grid.py` 的默认示例使用 `600519.SS`（如果你需要其它市场代码，请按 yfinance 的标识传入，如 `600519.SS` 或 `000001.SZ`）。运行后检查 `grid_results/` 目录以获得 CSV 与热图。

并行化与报告：
- `grid.py` 现在支持多进程并行执行（自动使用可用 CPU 核心减 1），通过 `build_steps` 参数与 `Backtester` 的设置保持一致。
- 运行后会在 `grid_results/` 中生成 `grid_results.csv`、每只股票的热力图（`heatmap_<symbol>.png`）以及参数排名报告 `report_<symbol>.md`（包含 top 10 参数组合）。
- 对 top 3 参数组合的详细分析包括：
  - `trade_freq_<symbol>_combo{1,2,3}.png`：按月统计交易频率直方图。
  - `trades_<symbol>_combo{1,2,3}.csv`：所有逐笔交易明细（包括买卖类型、价格、手续费等）。
  - `drawdowns_<symbol>_combo{1,2,3}.csv`：回撤期间明细（开始日期、结束日期、最大回撤幅度）。

可选参数（分批卖出与止损/止盈）：

新增 `sell_steps`（卖出分批数，默认 1）、`stop_loss_pct`（止损比例，如 0.05=5%）、`take_profit_pct`（止盈比例，如 0.5=50%）。

```bash
python -c "from grid import run_grid; run_grid(['600519.SS'], [20,50],[100,150], [0.1],[0.001],[0.001], build_steps=3, sell_steps=2, stop_loss_pct=0.1, take_profit_pct=0.5)"
```

注意：并行时会将 DataFrame 传递给子进程（通过序列化），在极大参数组合时会消耗较多内存。可通过减少 `processes` 或缩小参数网格来控制资源使用。

卖出分批、止损与止盈：
- `Backtester` 支持额外参数 `sell_steps`、`stop_loss_pct`、`take_profit_pct`（在 `engine.py` 的 `Backtester.__init__` 中）。
- `sell_steps`：卖出分批数量（默认 1，即次日开盘全部卖出）；若设置为 >1，会将卖出金额按份额分配到后续开盘执行。
- `stop_loss_pct` / `take_profit_pct`：以持仓平均入场价为基准触发止损/止盈（例如 `0.05` 表示 5%），触发后按 `sell_steps` 分批卖出。

额外报告位置（`grid_results/`）：
- `grid_results.csv`：所有参数组合的汇总。  
- `heatmap_<symbol>.png`：短/长均线年化收益热力图。  
- `report_<symbol>.md`：Top10 参数组合；对 Top3 会生成：  
	- `trade_freq_<symbol>_combo{n}.png`：交易频率直方图。  
	- `trades_<symbol>_combo{n}.csv`：交易明细（逐笔）。  
	- `drawdowns_<symbol>_combo{n}.csv`：回撤期间列表（开始/结束/最大回撤）。
