import os
import itertools
import pandas as pd
import numpy as np
import yfinance as yf
import matplotlib.pyplot as plt
import seaborn as sns
import multiprocessing
from functools import partial

from engine import Backtester


def fetch_history(symbol, period='3y', interval='1d'):
    ticker = yf.Ticker(symbol)
    df = ticker.history(period=period, interval=interval)
    if df.empty:
        raise RuntimeError(f'No data for {symbol}')
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
    return df


def _worker_task(args):
    # args: (df, symbol, short, long, ps, com, slip, capital, build_steps, sell_steps, stop_loss, take_profit)
    df, symbol, short, long, ps, com, slip, capital, build_steps, sell_steps, stop_loss, take_profit = args
    try:
        bt = Backtester(df, capital=capital, position_size=ps, commission=com, slippage=slip, 
                        build_steps=build_steps, sell_steps=sell_steps, 
                        stop_loss_pct=stop_loss, take_profit_pct=take_profit)
        _, stats, trades = bt.run(short=short, long=long)
        return {
            'symbol': symbol,
            'short': short,
            'long': long,
            'position_size': ps,
            'commission': com,
            'slippage': slip,
            'total_return': stats['total_return'],
            'annualized_return': stats['annualized_return'],
            'sharpe': stats['sharpe'],
            'max_drawdown': stats['max_drawdown'],
            'trades': stats.get('trades', 0),
            'buy_trades': stats.get('buy_trades', 0),
            'sell_trades': stats.get('sell_trades', 0)
        }
    except Exception as e:
        return {'symbol': symbol, 'short': short, 'long': long, 'error': str(e)}


def run_grid(symbols, shorts, longs, position_sizes, commissions, slippages, capital=1_000_000, out_dir='grid_results', build_steps=1, sell_steps=1, stop_loss_pct=None, take_profit_pct=None, processes=None):
    os.makedirs(out_dir, exist_ok=True)
    rows = []

    for symbol in symbols:
        print(f'Fetching {symbol}...')
        df = fetch_history(symbol)

        combos = list(itertools.product(shorts, longs, position_sizes, commissions, slippages))
        args = []
        for short, long, ps, com, slip in combos:
            args.append((df.copy(), symbol, short, long, ps, com, slip, capital, build_steps, sell_steps, stop_loss_pct, take_profit_pct))

        proc_count = processes or max(1, (multiprocessing.cpu_count() or 2) - 1)
        print(f'Running grid with {proc_count} processes, {len(args)} jobs...')
        with multiprocessing.Pool(proc_count) as pool:
            results = pool.map(_worker_task, args)

        for r in results:
            rows.append(r)

        # 为该 symbol 生成 short x long 的热力图（以年化收益为指标）
        df_rows = [r for r in rows if r.get('symbol') == symbol and 'annualized_return' in r]
        if df_rows:
            res_df = pd.DataFrame(df_rows)
            pivot = res_df.pivot_table(index='short', columns='long', values='annualized_return', aggfunc='mean')
            plt.figure(figsize=(8, 6))
            sns.heatmap(pivot, annot=True, fmt='.2f', cmap='RdYlGn', center=0)
            plt.title(f'annualized_return heatmap {symbol}')
            png = os.path.join(out_dir, f'heatmap_{symbol}.png')
            plt.savefig(png, bbox_inches='tight')
            plt.close()

        # 生成报告（top 10）并对 top 3 运行策略以提取交易频率和回撤期明细
        if df_rows:
            res_df = pd.DataFrame(df_rows)
            topn = res_df.sort_values('annualized_return', ascending=False).head(10)
            report_md = os.path.join(out_dir, f'report_{symbol}.md')
            with open(report_md, 'w', encoding='utf-8') as f:
                f.write(f'# Grid Report for {symbol}\n\n')
                f.write('Top 10 parameter combos by annualized_return\n\n')
                f.write(topn.to_markdown(index=False))

            # 对 top 3 参数组合运行回测以输出交易频率直方图与回撤明细
            top3 = topn.head(3).to_dict(orient='records')
            for idx, combo in enumerate(top3, start=1):
                short = int(combo['short'])
                long = int(combo['long'])
                ps = float(combo['position_size'])
                com = float(combo['commission'])
                slip = float(combo['slippage'])
                # 运行回测获取逐日权益与逐笔交易
                bt = Backtester(df, capital=capital, position_size=ps, commission=com, slippage=slip, 
                                build_steps=build_steps, sell_steps=sell_steps,
                                stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct)
                d, stats, trades = bt.run(short=short, long=long)

                # 交易频率：按月统计交易次数
                if trades:
                    t_df = pd.DataFrame(trades)
                    t_df['index'] = pd.to_datetime(t_df['index'])
                    t_df['month'] = t_df['index'].dt.to_period('M')
                    freq = t_df.groupby('month').size()
                    plt.figure(figsize=(8, 3))
                    freq.plot(kind='bar')
                    plt.title(f'Trade frequency per month ({symbol}) - combo {idx}')
                    plt.tight_layout()
                    pngf = os.path.join(out_dir, f'trade_freq_{symbol}_combo{idx}.png')
                    plt.savefig(pngf)
                    plt.close()

                    # 保存交易明细 CSV
                    t_csv = os.path.join(out_dir, f'trades_{symbol}_combo{idx}.csv')
                    t_df.to_csv(t_csv, index=False)

                # 回撤期间明细
                eq = d['equity']
                roll_max = eq.cummax()
                dd = eq / roll_max - 1
                ddPeriods = []
                in_dd = False
                start_date = None
                for dt, val in dd.items():
                    if val < 0 and not in_dd:
                        in_dd = True
                        start_date = dt
                        min_dd = val
                    elif val < 0 and in_dd:
                        if val < min_dd:
                            min_dd = val
                    elif val == 0 and in_dd:
                        # 回撤结束
                        end_date = dt
                        ddPeriods.append({'start': start_date, 'end': end_date, 'max_drawdown': min_dd})
                        in_dd = False

                # 若以历史结尾仍在回撤中，记录到最后
                if in_dd:
                    ddPeriods.append({'start': start_date, 'end': dd.index[-1], 'max_drawdown': min_dd})

                dd_csv = os.path.join(out_dir, f'drawdowns_{symbol}_combo{idx}.csv')
                if ddPeriods:
                    pd.DataFrame(ddPeriods).to_csv(dd_csv, index=False)

    out_csv = os.path.join(out_dir, 'grid_results.csv')
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print('Grid run complete. Results saved to', out_csv)
    return out_csv


if __name__ == '__main__':
    # 示例：对单只股票做短/长均线网格扫描
    symbols = ['600519.SS']
    shorts = [20, 50, 100]
    longs = [100, 150, 200]
    position_sizes = [0.1]
    commissions = [0.001]
    slippages = [0.001]
    run_grid(symbols, shorts, longs, position_sizes, commissions, slippages)
