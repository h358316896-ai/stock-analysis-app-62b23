#!/usr/bin/env python3
"""
简单均线交叉回测示例
用法示例：
  python backtest.py --symbol 600519 --market cn --period 3y --short 50 --long 200

输出：在当前目录生成 equity_<<symbol>>.png，并在终端打印回测指标。
"""
import argparse
import sys
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib.pyplot as plt
from datetime import datetime


def map_ticker(symbol, market):
    s = symbol.strip()
    if market == 'hk':
        return s + '.HK'
    if market == 'us':
        return s
    # 简单处理 A 股：以 6 开头视为上证（.SS），其他视为深证（.SZ）
    if market == 'cn':
        if s.startswith('6'):
            return s + '.SS'
        return s + '.SZ'
    return s


def fetch_history(ticker, period):
    # 使用 yfinance 下载历史数据
    try:
        df = yf.download(ticker, period=period, progress=False)
    except Exception as e:
        print('数据下载失败:', e)
        return None
    if df is None or df.empty:
        print('没有抓取到历史数据')
        return None
    return df


def run_backtest(df, short=50, long=200, commission=0.001, slippage=0.001):
    """
    基于简单均线信号的回测，带交易成本与滑点模拟。
    commission, slippage: 以交易额的比例表示（例如 0.001 = 0.1%）。
    返回带有 'equity' 与 'buy_hold' 列的数据和统计指标。
    """
    data = df.copy()
    data = data.dropna(subset=['Close'])
    data['ret'] = data['Close'].pct_change().fillna(0)
    data['sma_s'] = data['Close'].rolling(short).mean()
    data['sma_l'] = data['Close'].rolling(long).mean()
    data['signal'] = 0
    data.loc[data['sma_s'] > data['sma_l'], 'signal'] = 1

    # 按日仿真组合价值（近似）：按当日收盘计算持仓回报，交易在当日发生并扣除费用（近似）
    data['position'] = data['signal'].shift(0).fillna(0)  # desired position at day t

    equity = 1.0
    equities = []
    buy_hold = []
    position = 0

    for i in range(len(data)):
        row = data.iloc[i]
        ret = row['ret']
        desired = int(row['position'])

        # 在持仓变更时估算交易成本（使用当天收盘作为交易基准的近似）
        if desired != position:
            turnover = abs(desired - position) * equity
            trade_cost = turnover * (commission + slippage)
            equity -= trade_cost
            position = desired

        # 应用当日回报（按收盘到收盘）
        equity = equity * (1 + position * ret)
        equities.append(equity)

        # buy and hold benchmark
        if len(buy_hold) == 0:
            bh = 1.0 * (1 + ret)
        else:
            bh = buy_hold[-1] * (1 + ret)
        buy_hold.append(bh)

    data = data.assign(equity=pd.Series(equities, index=data.index), buy_hold=pd.Series(buy_hold, index=data.index))

    total_return = data['equity'].iloc[-1] - 1
    # 计算年化基于交易日
    n_days = len(data)
    annualized_return = (data['equity'].iloc[-1]) ** (252.0 / n_days) - 1 if n_days > 0 else 0
    strategy_rets = data['equity'].pct_change().fillna(0)
    ann_vol = strategy_rets.std() * np.sqrt(252)
    sharpe = (annualized_return / ann_vol) if ann_vol != 0 else np.nan

    roll_max = data['equity'].cummax()
    drawdown = data['equity'] / roll_max - 1
    max_dd = drawdown.min()

    stats = {
        'total_return': total_return,
        'annualized_return': annualized_return,
        'annual_volatility': ann_vol,
        'sharpe': sharpe,
        'max_drawdown': max_dd
    }
    return data, stats


def plot_equity(data, symbol, out_file):
    plt.style.use('seaborn-v0_8')
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(data.index, data['equity'], label='Strategy Equity')
    ax.plot(data.index, data['buy_hold'], label='Buy & Hold', alpha=0.7)
    ax.set_title(f'Equity Curve — {symbol}')
    ax.set_ylabel('Cumulative Return')
    ax.legend()
    fig.autofmt_xdate()
    plt.tight_layout()
    fig.savefig(out_file)
    plt.close(fig)


def print_stats(stats):
    print('回测结果：')
    print(f"总收益: {stats['total_return']*100:.2f}%")
    print(f"年化收益: {stats['annualized_return']*100:.2f}%")
    print(f"年化波动: {stats['annual_volatility']*100:.2f}%")
    print(f"Sharpe: {stats['sharpe']:.2f}")
    print(f"最大回撤: {stats['max_drawdown']*100:.2f}%")


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--symbol', required=True, help='股票代码，例如 600519 或 AAPL')
    p.add_argument('--market', default='cn', choices=['cn', 'hk', 'us'], help='市场: cn/hk/us')
    p.add_argument('--period', default='3y', help='历史数据周期，例如 1y, 3y')
    p.add_argument('--short', type=int, default=50, help='短期均线窗口')
    p.add_argument('--long', type=int, default=200, help='长期均线窗口')
    args = p.parse_args()

    ticker = map_ticker(args.symbol, args.market)
    print('使用 ticker:', ticker)
    df = fetch_history(ticker, args.period)
    if df is None:
        sys.exit(1)

    data, stats = run_backtest(df, short=args.short, long=args.long)
    out_file = f'equity_{args.symbol}.png'
    plot_equity(data, args.symbol, out_file)
    print_stats(stats)
    print('图表已保存为', out_file)


if __name__ == '__main__':
    main()
