import math
import pandas as pd
import numpy as np


class Backtester:
    """逐笔执行回测引擎（基于次日开盘成交）。

    关键假设：
    - 策略信号基于收盘价计算的短/长均线。
    - 当信号在 t 发生变化时（cross），在 t+1 的开盘价执行全部开/平仓操作（若存在 t+1）。
    - 以手续费（commission）和滑点（slippage）按成交额比例计入交易成本，可选固定手续费（fixed_fee）。
    - 使用固定仓位比例（position_size）表示每次建仓占当时净值的比例。
    """

    def __init__(self, df, capital=1_000_000, position_size=0.1, commission=0.001, slippage=0.001, fixed_fee=0.0, build_steps=1, sell_steps=1, stop_loss_pct=None, take_profit_pct=None):
        """逐笔执行回测引擎（基于次日开盘成交）。
        
        参数：
        - build_steps: 买入分批数（默认1）
        - sell_steps: 卖出分批数（默认1）
        - stop_loss_pct: 止损比例，如 0.05 表示 5% 亏损时止损
        - take_profit_pct: 止盈比例，如 0.5 表示 50% 盈利时止盈
        """
        self.df = df.copy().dropna(subset=['Open', 'Close'])
        self.capital = float(capital)
        self.position_size = float(position_size)
        self.commission = float(commission)
        self.slippage = float(slippage)
        self.fixed_fee = float(fixed_fee)
        self.build_steps = int(build_steps) if build_steps >= 1 else 1
        self.sell_steps = int(sell_steps) if sell_steps >= 1 else 1
        self.stop_loss_pct = float(stop_loss_pct) if stop_loss_pct is not None else None
        self.take_profit_pct = float(take_profit_pct) if take_profit_pct is not None else None

    def _prepare_signals(self, short, long):
        d = self.df.copy()
        d['sma_s'] = d['Close'].rolling(short).mean()
        d['sma_l'] = d['Close'].rolling(long).mean()
        d['signal'] = (d['sma_s'] > d['sma_l']).astype(int)
        d['signal_change'] = d['signal'].diff().fillna(0).astype(int)
        return d

    def run(self, short=50, long=200):
        d = self._prepare_signals(short, long)

        cash = float(self.capital)
        shares = 0
        equity_curve = []
        trades = []
        pending_orders = {}  # index -> list of tranche dollar allocations
        avg_entry_price = 0.0
        total_shares_bought = 0
        sell_pending_flag = False

        idxs = list(d.index)

        for i, idx in enumerate(idxs):
            row = d.loc[idx]

            # 当日先执行任何到期的挂单（在当天开盘以挂单中指定的开盘价成交）
            if idx in pending_orders:
                # use today's Open as execution price for these tranches
                exec_open = row['Open']
                for tranche_alloc in pending_orders[idx]:
                    # positive -> buy tranche (dollar amount), negative -> sell tranche (dollar amount)
                    if tranche_alloc == 0:
                        continue
                    if tranche_alloc > 0:
                        size = math.floor(tranche_alloc / exec_open)
                        if size <= 0:
                            continue
                        trade_value = size * exec_open
                        cost = trade_value * (self.commission + self.slippage) + self.fixed_fee
                        cash -= (trade_value + cost)
                        # 更新平均入场价与累计买入量
                        prev_total = total_shares_bought
                        prev_cost = avg_entry_price * prev_total
                        new_total = prev_total + size
                        if new_total > 0:
                            avg_entry_price = (prev_cost + trade_value) / new_total
                        total_shares_bought = new_total
                        shares += size
                        trades.append({'type': 'buy', 'price': exec_open, 'size': size, 'cost': cost, 'index': idx})
                    else:
                        # 卖出 tranche: tranche_alloc is negative dollar amount to sell
                        sell_dollar = abs(tranche_alloc)
                        size = math.floor(sell_dollar / exec_open)
                        if size <= 0 or shares <= 0:
                            continue
                        size = min(size, shares)
                        trade_value = size * exec_open
                        cost = trade_value * (self.commission + self.slippage) + self.fixed_fee
                        cash += (trade_value - cost)
                        # 更新平均入场价与累计买入量
                        prev_total = total_shares_bought
                        if prev_total > 0:
                            # 假设 FIFO: reduce total_shares_bought proportionally
                            remaining = max(prev_total - size, 0)
                            # 不调整 avg_entry_price 以保持简洁；仅减少持仓计数
                            total_shares_bought = remaining
                            if remaining == 0:
                                avg_entry_price = 0.0
                        shares -= size
                        trades.append({'type': 'sell', 'price': exec_open, 'size': size, 'cost': cost, 'index': idx})
                del pending_orders[idx]

            # 如果在最后一行无法在 next open 成交，则 next_open 为 None
            if i < len(idxs) - 1:
                next_idx = idxs[i + 1]
                next_open = d.at[next_idx, 'Open']
            else:
                next_idx = None
                next_open = None

            change = row['signal_change']

            # 买入信号（0 -> 1），按 build_steps 分批在接下来的若干开盘执行
            if change == 1 and next_open is not None:
                net_worth = cash + shares * row['Close']
                alloc = net_worth * self.position_size
                if alloc > 0:
                    tranche = alloc / self.build_steps
                    for j in range(self.build_steps):
                        target_i = i + 1 + j
                        if target_i >= len(idxs):
                            # 如果超出历史范围，则把剩余部分安排在最后可用日
                            target_i = len(idxs) - 1
                        target_idx = idxs[target_i]
                        pending_orders.setdefault(target_idx, []).append(tranche)

            # 卖出信号（1 -> 0），按 sell_steps 分批在接下来的若干开盘执行
            if change == -1 and next_open is not None and shares > 0:
                # 将当前持仓按 sell_steps 分批卖出
                total_value = shares * next_open
                tranche_value = total_value / self.sell_steps
                for j in range(self.sell_steps):
                    target_i = i + 1 + j
                    if target_i >= len(idxs):
                        target_i = len(idxs) - 1
                    target_idx = idxs[target_i]
                    # represent sell by negative allocation
                    pending_orders.setdefault(target_idx, []).append(-tranche_value)
                # mark that sells scheduled
                sell_pending_flag = True

            # 检查止损/止盈条件（基于当前持仓平均入场价与当日收盘价）
            if total_shares_bought > 0 and avg_entry_price > 0:
                cur_close = row['Close']
                pnl_pct = (cur_close - avg_entry_price) / avg_entry_price
                if self.stop_loss_pct is not None and pnl_pct <= -abs(self.stop_loss_pct) and next_open is not None:
                    # 全部平仓（或也可按 sell_steps 分批，这里做全部或分批均支持：按 sell_steps 分批）
                    total_value = shares * next_open
                    tranche_value = total_value / self.sell_steps if self.sell_steps > 1 else total_value
                    for j in range(self.sell_steps):
                        target_i = i + 1 + j
                        if target_i >= len(idxs):
                            target_i = len(idxs) - 1
                        target_idx = idxs[target_i]
                        pending_orders.setdefault(target_idx, []).append(-tranche_value)
                    sell_pending_flag = True
                elif self.take_profit_pct is not None and pnl_pct >= abs(self.take_profit_pct) and next_open is not None:
                    total_value = shares * next_open
                    tranche_value = total_value / self.sell_steps if self.sell_steps > 1 else total_value
                    for j in range(self.sell_steps):
                        target_i = i + 1 + j
                        if target_i >= len(idxs):
                            target_i = len(idxs) - 1
                        target_idx = idxs[target_i]
                        pending_orders.setdefault(target_idx, []).append(-tranche_value)
                    sell_pending_flag = True

            # 当日按收盘价标记净值
            equity = cash + shares * row['Close']
            equity_curve.append(equity)

        equity_series = pd.Series(equity_curve, index=d.index)
        d = d.assign(equity=equity_series)

        # 统计指标
        total_return = equity_series.iloc[-1] / self.capital - 1
        n_days = len(d)
        annualized_return = (equity_series.iloc[-1] / self.capital) ** (252.0 / n_days) - 1 if n_days > 0 else 0
        daily_rets = equity_series.pct_change().fillna(0)
        ann_vol = daily_rets.std() * np.sqrt(252)
        sharpe = (annualized_return / ann_vol) if ann_vol != 0 else np.nan
        roll_max = equity_series.cummax()
        drawdown = equity_series / roll_max - 1
        max_dd = drawdown.min()

        stats = {
            'initial_capital': self.capital,
            'final_equity': equity_series.iloc[-1],
            'total_return': total_return,
            'annualized_return': annualized_return,
            'annual_volatility': ann_vol,
            'sharpe': sharpe,
            'max_drawdown': max_dd,
            'n_days': n_days,
            'trades': len(trades),
            'buy_trades': len([t for t in trades if t['type'] == 'buy']),
            'sell_trades': len([t for t in trades if t['type'] == 'sell']),
        }

        return d, stats, trades


def simple_run_from_df(df, short=50, long=200, capital=1_000_000, position_size=0.1, commission=0.001, slippage=0.001, build_steps=1, sell_steps=1, stop_loss_pct=None, take_profit_pct=None):
    bt = Backtester(df, capital=capital, position_size=position_size, commission=commission, slippage=slippage, build_steps=build_steps, sell_steps=sell_steps, stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct)
    return bt.run(short=short, long=long)
