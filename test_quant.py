"""Quick test of quant_engine functions"""
import sys, os, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quant_engine import score_factors, generate_tech_signals, calc_market_breadth, calc_risk_metrics, backtest_sma_cross

# ---- Test 1: Multi-factor scoring ----
print("=== TEST 1: Multi-Factor Scoring ===")
stocks = [
    {'code':'600519','name':'茅台','pe':25,'pb':8,'market_cap':2e12,'roe':30,'revenue_growth':15,'profit_growth':18,'gross_margin':92,'net_margin':52,'debt_ratio':20,'return_1m':0.05,'return_3m':0.12,'rsi':55},
    {'code':'000858','name':'五粮液','pe':20,'pb':6,'market_cap':8e11,'roe':25,'revenue_growth':12,'profit_growth':14,'gross_margin':75,'net_margin':38,'debt_ratio':15,'return_1m':0.02,'return_3m':0.08,'rsi':48},
    {'code':'000568','name':'泸州老窖','pe':22,'pb':7,'market_cap':3e11,'roe':28,'revenue_growth':20,'profit_growth':25,'gross_margin':80,'net_margin':42,'debt_ratio':25,'return_1m':0.08,'return_3m':0.20,'rsi':65},
    {'code':'601318','name':'中国平安','pe':8,'pb':1.2,'market_cap':8e11,'roe':12,'revenue_growth':-3,'profit_growth':-5,'gross_margin':20,'net_margin':8,'debt_ratio':75,'return_1m':-0.03,'return_3m':-0.10,'rsi':35},
]
scored = score_factors(stocks)
for s in scored:
    print(f"  #{s['rank']} {s['name']}({s['code']}): 综合={s['composite_score']:.3f} 价值={s['factor_scores']['value']:.3f} 成长={s['factor_scores']['growth']:.3f} 动量={s['factor_scores']['momentum']:.3f} 质量={s['factor_scores']['quality']:.3f}")

# ---- Test 2: Technical signals ----
print("\n=== TEST 2: Technical Signals ===")
random.seed(42)
klines = []
price = 100
for i in range(80):
    chg = (random.random() - 0.5) * 4
    price = max(50, price + chg)
    klines.append({'date': f'2026-{(i//22)+3:02d}-{(i%22)+1:02d}', 'open': price-chg/2, 'close': price, 'high': price+random.random()*2, 'low': price-random.random()*2, 'volume': int(random.random()*1e7+5e6)})

sig = generate_tech_signals(klines)
print(f"  综合分: {sig['aggregate_score']}  强度: {sig['strength']}  信号数: {len(sig['signals'])}")
for s in sig['signals'][:5]:
    emoji = "+" if s['type'] == 'bullish' else "-"
    print(f"  {emoji} {s['name']} (强度:{s['strength']})")

# ---- Test 3: Market breadth ----
print("\n=== TEST 3: Market Breadth ===")
north_flows = [
    {'date':'2026-06-13', 'net_flow':20}, {'date':'2026-06-12', 'net_flow':15},
    {'date':'2026-06-11', 'net_flow':-5}, {'date':'2026-06-10', 'net_flow':30},
    {'date':'2026-06-09', 'net_flow':10}
]
mb = calc_market_breadth(25, 15, 8, 2, north_flows, 1.5, 1.3)
print(f"  恐贪指数: {mb['fear_greed_index']}/100 ({mb['composite_signal']})")
print(f"  涨跌比: {mb['advance_decline_ratio']}  涨跌停比: {mb['limit_up_down_ratio']}")
print(f"  北向5日: {mb['north_bound']['cum_5d']}  趋势: {mb['north_bound']['trend']}")

# ---- Test 4: Risk metrics ----
print("\n=== TEST 4: Risk Metrics ===")
prices_list = [k['close'] for k in klines]
risk = calc_risk_metrics(prices_list)
print(f"  年化波动率: {risk['historical_volatility_20d']:.1f}%")
print(f"  VaR(95%): {risk['var_95']:.2f}%  VaR(99%): {risk['var_99']:.2f}%")
print(f"  夏普比率: {risk['sharpe_annual']:.2f}")
print(f"  最大回撤: {risk['max_drawdown_all']:.1f}%")
print(f"  胜率(上涨日): {risk['win_rate']:.1f}% ({risk['up_days']}涨/{risk['down_days']}跌)")

# ---- Test 5: Backtest ----
print("\n=== TEST 5: Backtest ===")
result = backtest_sma_cross(klines, fast_period=5, slow_period=20, initial_capital=100000)
m = result['metrics']
print(f"  策略收益: {m['total_return_pct']:.1f}%  买入持有: {m['buy_hold_return_pct']:.1f}%")
print(f"  夏普: {m['sharpe_ratio']:.2f}  最大回撤: {m['max_drawdown_pct']:.1f}%")
print(f"  胜率: {m['win_rate']:.0f}%  交易次数: {m['trade_count']}  盈亏比: {m['profit_factor']}")

print("\n=== ALL 5 TESTS PASSED ===")
