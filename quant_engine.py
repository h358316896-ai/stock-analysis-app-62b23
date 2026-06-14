# ============================================================
# Quant Engine — Pure Python computation module for StockAI
# Zero dependencies beyond math + statistics + datetime
# All functions are stateless: pure input → output computation
# ============================================================

import math
import statistics
from datetime import datetime


# ============================================================
# 1. STATISTICS UTILITIES
# ============================================================

def safe_div(a, b, default=0.0):
    """Safe division, returns default if denominator is 0 or None."""
    if b is None or a is None:
        return default
    try:
        b = float(b)
        a = float(a)
        if b == 0:
            return default
        return a / b
    except (ValueError, TypeError):
        return default


def zscore(values):
    """Compute z-scores for a list of values. Returns [0.0,...] if std is 0."""
    if not values or len(values) < 2:
        return [0.0] * len(values)
    clean = []
    for v in values:
        try:
            clean.append(float(v) if v is not None else 0.0)
        except (ValueError, TypeError):
            clean.append(0.0)
    mean = statistics.mean(clean)
    std = statistics.stdev(clean)
    if std == 0:
        return [0.0] * len(clean)
    return [(x - mean) / std for x in clean]


def minmax_norm(values, inverse=False):
    """
    Min-max normalize to [0, 1].
    If inverse=True, higher raw value -> lower normalized score (for PE/PB/debt).
    """
    if not values:
        return []
    clean = []
    for v in values:
        try:
            clean.append(float(v) if v is not None else 0.0)
        except (ValueError, TypeError):
            clean.append(0.0)
    mn = min(clean)
    mx = max(clean)
    if mx == mn:
        return [0.5] * len(clean)
    norm = [(x - mn) / (mx - mn) for x in clean]
    if inverse:
        norm = [1.0 - n for n in norm]
    return norm


def winsorize(values, low_pct=0.05, high_pct=0.95):
    """Cap extreme values at given percentiles."""
    if not values or len(values) < 3:
        return [float(v) if v is not None else 0.0 for v in values]
    clean = []
    for v in values:
        if v is not None:
            try:
                clean.append(float(v))
            except (ValueError, TypeError):
                clean.append(0.0)
    if len(clean) < 3:
        return [float(v) if v is not None else 0.0 for v in values]
    clean_sorted = sorted(clean)
    lo = clean_sorted[int(len(clean_sorted) * low_pct)]
    hi = clean_sorted[min(int(len(clean_sorted) * high_pct), len(clean_sorted) - 1)]
    result = []
    for v in values:
        if v is None:
            result.append(0.0)
        else:
            try:
                fv = float(v)
            except (ValueError, TypeError):
                result.append(0.0)
                continue
            if fv < lo:
                result.append(lo)
            elif fv > hi:
                result.append(hi)
            else:
                result.append(fv)
    return result


def log_returns(prices):
    """Compute logarithmic returns from a list of prices."""
    if not prices or len(prices) < 2:
        return []
    rets = []
    for i in range(1, len(prices)):
        try:
            p0 = float(prices[i - 1]) if prices[i - 1] is not None else 0
            p1 = float(prices[i]) if prices[i] is not None else 0
        except (ValueError, TypeError):
            rets.append(0.0)
            continue
        if p0 > 0 and p1 > 0:
            rets.append(math.log(p1 / p0))
        else:
            rets.append(0.0)
    return rets


def simple_returns(prices):
    """Compute simple percentage returns from a list of prices."""
    if not prices or len(prices) < 2:
        return []
    rets = []
    for i in range(1, len(prices)):
        try:
            p0 = float(prices[i - 1]) if prices[i - 1] is not None else 0
            p1 = float(prices[i]) if prices[i] is not None else 0
        except (ValueError, TypeError):
            rets.append(0.0)
            continue
        if p0 > 0:
            rets.append((p1 - p0) / p0)
        else:
            rets.append(0.0)
    return rets


def period_return(prices, n):
    """Return n-period return. e.g., 20-day return from last price vs price n bars ago."""
    if not prices or len(prices) <= n:
        return None
    if prices[-1] is None or prices[-(n + 1)] is None or prices[-(n + 1)] == 0:
        return None
    return (prices[-1] - prices[-(n + 1)]) / prices[-(n + 1)]


# ============================================================
# 2. TECHNICAL INDICATOR CALCULATIONS
# ============================================================

def _calc_ema(data, period):
    """Calculate Exponential Moving Average."""
    if len(data) < period:
        return [None] * len(data)
    k = 2.0 / (period + 1)
    ema = []
    # Seed with SMA
    first_ema = sum(data[:period]) / period
    for i in range(period - 1):
        ema.append(None)
    ema.append(first_ema)
    for i in range(period, len(data)):
        val = data[i] * k + ema[-1] * (1 - k)
        ema.append(val)
    return ema


def _calc_sma(data, period):
    """Calculate Simple Moving Average."""
    if len(data) < period:
        return [None] * len(data)
    sma = [None] * (period - 1)
    window_sum = sum(data[:period])
    sma.append(window_sum / period)
    for i in range(period, len(data)):
        window_sum = window_sum - data[i - period] + data[i]
        sma.append(window_sum / period)
    return sma


def calc_macd(closes, fast=12, slow=26, signal=9):
    """Calculate MACD indicator.
    Returns dict with lists: dif, dea, histogram (same length as closes).
    """
    ema_fast = _calc_ema(closes, fast)
    ema_slow = _calc_ema(closes, slow)

    dif = []
    for i in range(len(closes)):
        if ema_fast[i] is not None and ema_slow[i] is not None:
            dif.append(ema_fast[i] - ema_slow[i])
        else:
            dif.append(None)

    # DEA = signal-period EMA of DIF
    dea = [None] * len(closes)
    valid_dif = [d for d in dif if d is not None]
    if len(valid_dif) >= signal:
        dea_valid = _calc_ema(valid_dif, signal)
        offset = len(dif) - len(dea_valid)
        for j in range(len(dea_valid)):
            dea[offset + j] = dea_valid[j]

    histogram = []
    for i in range(len(closes)):
        if dif[i] is not None and dea[i] is not None:
            histogram.append((dif[i] - dea[i]) * 2)
        else:
            histogram.append(None)

    return {"dif": dif, "dea": dea, "histogram": histogram}


def calc_rsi(closes, period=14):
    """Calculate RSI indicator."""
    if len(closes) < period + 1:
        return [None] * len(closes)

    rsi = [None] * (period + 1)
    gains, losses = [], []
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i - 1]
        gains.append(chg if chg > 0 else 0.0)
        losses.append(-chg if chg < 0 else 0.0)

    if len(gains) < period:
        return [None] * len(closes)

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    if avg_loss == 0:
        rsi.append(100.0)
    else:
        rs = avg_gain / avg_loss
        rsi.append(100.0 - 100.0 / (1.0 + rs))

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0:
            rsi.append(100.0)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100.0 - 100.0 / (1.0 + rs))

    return rsi


def calc_bollinger(closes, period=20, std_dev=2.0):
    """Calculate Bollinger Bands."""
    if len(closes) < period:
        return {"upper": [None] * len(closes), "middle": [None] * len(closes), "lower": [None] * len(closes)}

    upper, middle, lower = [], [], []
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(None)
            middle.append(None)
            lower.append(None)
        else:
            window = closes[i - period + 1 : i + 1]
            ma = statistics.mean(window)
            std = statistics.stdev(window) if len(window) > 1 else 0.0
            upper.append(ma + std_dev * std)
            middle.append(ma)
            lower.append(ma - std_dev * std)

    return {"upper": upper, "middle": middle, "lower": lower}


def calc_kdj(highs, lows, closes, period=9):
    """Calculate KDJ indicator."""
    n = len(closes)
    if n < period:
        return {"k": [None] * n, "d": [None] * n, "j": [None] * n}

    k_vals = [50.0] * (period - 1)
    d_vals = [50.0] * (period - 1)
    j_vals = [50.0] * (period - 1)
    prev_k, prev_d = 50.0, 50.0

    for i in range(period - 1, n):
        high_max = max(highs[i - period + 1 : i + 1])
        low_min = min(lows[i - period + 1 : i + 1])
        if high_max != low_min:
            rsv = (closes[i] - low_min) / (high_max - low_min) * 100.0
        else:
            rsv = 50.0
        k = 2.0 / 3.0 * prev_k + 1.0 / 3.0 * rsv
        d = 2.0 / 3.0 * prev_d + 1.0 / 3.0 * k
        j = 3.0 * k - 2.0 * d
        k_vals.append(round(k, 2))
        d_vals.append(round(d, 2))
        j_vals.append(round(j, 2))
        prev_k, prev_d = k, d

    return {"k": k_vals, "d": d_vals, "j": j_vals}


# ============================================================
# 3. TECHNICAL SIGNAL GENERATION
# ============================================================

def generate_tech_signals(klines):
    """
    Generate buy/sell/hold signals from K-line data.

    Input: list of dicts [{date, open, close, high, low, volume}, ...] (at least 60)
    Returns: {
        "signals": [{name, type: "bullish"|"bearish", strength: int, detail}, ...],
        "aggregate_score": int,
        "strength": "strong_bullish"|"bullish"|"neutral"|"bearish"|"strong_bearish",
        "latest_values": dict
    }
    """
    if not klines or len(klines) < 30:
        return {
            "signals": [],
            "aggregate_score": 0,
            "strength": "neutral",
            "latest_values": {},
            "error": f"Insufficient data: {len(klines) if klines else 0} bars (need >= 30)"
        }

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    volumes = [k["volume"] for k in klines]

    # Compute indicators
    macd_d = calc_macd(closes)
    rsi = calc_rsi(closes, 14)
    boll = calc_bollinger(closes, 20, 2.0)
    kdj = calc_kdj(highs, lows, closes, 9)
    ma5 = _calc_ema(closes, 5)
    ma10 = _calc_ema(closes, 10)
    ma20 = _calc_ema(closes, 20)
    ma60 = _calc_ema(closes, 60)

    signals = []

    def _cross_above(a, b):
        """True if a crosses above b in the last 2 bars."""
        for i in range(len(a) - 1, max(0, len(a) - 3), -1):
            if i > 0 and a[i] is not None and b[i] is not None and a[i - 1] is not None and b[i - 1] is not None:
                if a[i - 1] <= b[i - 1] and a[i] > b[i]:
                    return True
        return False

    def _cross_below(a, b):
        """True if a crosses below b in the last 2 bars."""
        for i in range(len(a) - 1, max(0, len(a) - 3), -1):
            if i > 0 and a[i] is not None and b[i] is not None and a[i - 1] is not None and b[i - 1] is not None:
                if a[i - 1] >= b[i - 1] and a[i] < b[i]:
                    return True
        return False

    def _last(lst):
        """Get last non-None value."""
        for v in reversed(lst):
            if v is not None:
                return v
        return None

    def _prev(lst):
        """Get second-to-last non-None value."""
        found = 0
        for v in reversed(lst):
            if v is not None:
                if found == 1:
                    return v
                found += 1
        return None

    n = len(closes)

    # --- MACD Signals ---
    if _cross_above(macd_d["dif"], macd_d["dea"]):
        signals.append({"name": "MACD金叉", "type": "bullish", "strength": 3, "detail": "DIF上穿DEA，短期看涨信号"})
    if _cross_below(macd_d["dif"], macd_d["dea"]):
        signals.append({"name": "MACD死叉", "type": "bearish", "strength": -3, "detail": "DIF下穿DEA，短期看跌信号"})

    last_hist = _last(macd_d["histogram"])
    prev_hist = _prev(macd_d["histogram"])
    if last_hist is not None and prev_hist is not None:
        if prev_hist < 0 and last_hist >= 0:
            signals.append({"name": "MACD柱转正", "type": "bullish", "strength": 1, "detail": "MACD柱由负转正，动能转多"})
        if prev_hist > 0 and last_hist <= 0:
            signals.append({"name": "MACD柱转负", "type": "bearish", "strength": -1, "detail": "MACD柱由正转负，动能转空"})

    # --- RSI Signals ---
    last_rsi = _last(rsi)
    prev_rsi = _prev(rsi)
    if last_rsi is not None:
        if last_rsi < 30:
            signals.append({"name": "RSI超卖", "type": "bullish", "strength": 2, "detail": f"RSI={last_rsi:.1f} 进入超卖区域，有反弹需求"})
        elif last_rsi > 70:
            signals.append({"name": "RSI超买", "type": "bearish", "strength": -2, "detail": f"RSI={last_rsi:.1f} 进入超买区域，有回调压力"})
        if prev_rsi is not None and prev_rsi <= 30 and last_rsi > 30:
            signals.append({"name": "RSI脱离超卖", "type": "bullish", "strength": 1, "detail": "RSI从超卖区回升，反弹启动"})
        if prev_rsi is not None and prev_rsi >= 70 and last_rsi < 70:
            signals.append({"name": "RSI脱离超买", "type": "bearish", "strength": -1, "detail": "RSI从超买区回落，回调开始"})

    # --- Bollinger Band Signals ---
    last_upper = _last(boll["upper"])
    last_lower = _last(boll["lower"])
    last_middle = _last(boll["middle"])
    if last_upper and last_lower and last_middle and last_upper > last_lower:
        bandwidth = (last_upper - last_lower) / last_middle if last_middle > 0 else 0
        # Estimate historical bandwidth
        hist_widths = []
        for i in range(max(0, n - 20), n):
            if boll["upper"][i] and boll["lower"][i] and boll["middle"][i] and boll["middle"][i] > 0:
                hist_widths.append((boll["upper"][i] - boll["lower"][i]) / boll["middle"][i])
        avg_width = statistics.mean(hist_widths) if hist_widths else bandwidth
        if bandwidth < avg_width * 0.5:
            signals.append({"name": "布林带收窄", "type": "bullish", "strength": 1, "detail": "布林带极度收窄，变盘在即"})
        if closes[-1] >= last_upper:
            signals.append({"name": "触及布林上轨", "type": "bearish", "strength": -1, "detail": "价格触及上轨，短期有回调压力"})
        if closes[-1] <= last_lower:
            signals.append({"name": "触及布林下轨", "type": "bullish", "strength": 1, "detail": "价格触及下轨，短期有反弹需求"})

    # --- KDJ Signals ---
    if _cross_above(kdj["k"], kdj["d"]):
        signals.append({"name": "KDJ金叉", "type": "bullish", "strength": 2, "detail": "K线上穿D线，短线看涨"})
    if _cross_below(kdj["k"], kdj["d"]):
        signals.append({"name": "KDJ死叉", "type": "bearish", "strength": -2, "detail": "K线下穿D线，短线看跌"})
    last_j = _last(kdj["j"])
    if last_j is not None:
        if last_j < 0:
            signals.append({"name": "KDJ超卖(J<0)", "type": "bullish", "strength": 1, "detail": f"J值={last_j:.1f} 严重超卖"})
        if last_j > 100:
            signals.append({"name": "KDJ超买(J>100)", "type": "bearish", "strength": -1, "detail": f"J值={last_j:.1f} 严重超买"})

    # --- MA Crossover Signals ---
    if _cross_above(ma5, ma10):
        signals.append({"name": "MA5金叉MA10", "type": "bullish", "strength": 2, "detail": "短线均线金叉，短期走强"})
    if _cross_below(ma5, ma10):
        signals.append({"name": "MA5死叉MA10", "type": "bearish", "strength": -2, "detail": "短线均线死叉，短期走弱"})
    if _cross_above(ma10, ma20):
        signals.append({"name": "MA10金叉MA20", "type": "bullish", "strength": 1, "detail": "中期均线金叉，趋势向好"})
    if _cross_below(ma10, ma20):
        signals.append({"name": "MA10死叉MA20", "type": "bearish", "strength": -1, "detail": "中期均线死叉，趋势转弱"})
    if _cross_above(ma20, ma60):
        signals.append({"name": "MA20金叉MA60", "type": "bullish", "strength": 2, "detail": "长期均线金叉，趋势逆转看多"})
    if _cross_below(ma20, ma60):
        signals.append({"name": "MA20死叉MA60", "type": "bearish", "strength": -2, "detail": "长期均线死叉，趋势逆转看空"})

    # --- Volume Signals ---
    if len(volumes) >= 21:
        avg_vol_20 = statistics.mean(volumes[-21:-1])
        last_vol = volumes[-1]
        if avg_vol_20 > 0:
            if last_vol > avg_vol_20 * 1.5:
                # Volume spike — check if it's on an up day
                if closes[-1] >= closes[-2] if len(closes) >= 2 else True:
                    signals.append({"name": "放量上涨", "type": "bullish", "strength": 1, "detail": f"成交量{last_vol/avg_vol_20:.1f}倍均量，放量上攻"})
                else:
                    signals.append({"name": "放量下跌", "type": "bearish", "strength": -1, "detail": f"成交量{last_vol/avg_vol_20:.1f}倍均量，放量下杀"})
            if last_vol < avg_vol_20 * 0.5:
                signals.append({"name": "缩量", "type": "bearish", "strength": -1, "detail": "成交萎缩，市场参与度低"})

    # --- Price Position ---
    last_ma20 = _last(ma20)
    last_ma60 = _last(ma60)
    if last_ma20 and last_ma60:
        if closes[-1] > last_ma20 > last_ma60:
            signals.append({"name": "多头排列", "type": "bullish", "strength": 2, "detail": "价格>MA20>MA60，均线多头排列"})
        if closes[-1] < last_ma20 < last_ma60:
            signals.append({"name": "空头排列", "type": "bearish", "strength": -2, "detail": "价格<MA20<MA60，均线空头排列"})

    # Aggregate
    aggregate_score = sum(s["strength"] for s in signals)

    if aggregate_score > 10:
        strength = "strong_bullish"
    elif aggregate_score >= 3:
        strength = "bullish"
    elif aggregate_score > -2:
        strength = "neutral"
    elif aggregate_score > -10:
        strength = "bearish"
    else:
        strength = "strong_bearish"

    # Latest values for display
    latest_values = {
        "price": round(closes[-1], 2),
        "rsi": round(_last(rsi), 1) if _last(rsi) else None,
        "macd_dif": round(_last(macd_d["dif"]), 3) if _last(macd_d["dif"]) else None,
        "macd_dea": round(_last(macd_d["dea"]), 3) if _last(macd_d["dea"]) else None,
        "macd_histogram": round(_last(macd_d["histogram"]), 3) if _last(macd_d["histogram"]) else None,
        "boll_upper": round(_last(boll["upper"]), 2) if _last(boll["upper"]) else None,
        "boll_middle": round(_last(boll["middle"]), 2) if _last(boll["middle"]) else None,
        "boll_lower": round(_last(boll["lower"]), 2) if _last(boll["lower"]) else None,
        "kdj_k": _last(kdj["k"]),
        "kdj_d": _last(kdj["d"]),
        "kdj_j": _last(kdj["j"]),
        "ma5": round(_last(ma5), 2) if _last(ma5) else None,
        "ma10": round(_last(ma10), 2) if _last(ma10) else None,
        "ma20": round(_last(ma20), 2) if _last(ma20) else None,
        "ma60": round(_last(ma60), 2) if _last(ma60) else None,
    }

    return {
        "signals": signals,
        "aggregate_score": aggregate_score,
        "strength": strength,
        "latest_values": latest_values,
    }


# ============================================================
# 4. MULTI-FACTOR STOCK SCORING
# ============================================================

# Default category weights (sum to 1.0 within each category)
DEFAULT_VALUE_WEIGHTS = {"pe_inv": 0.35, "pb_inv": 0.30, "ps_inv": 0.20, "yield_direct": 0.15}
DEFAULT_GROWTH_WEIGHTS = {"revenue_growth": 0.35, "profit_growth": 0.35, "roe": 0.30}
DEFAULT_MOMENTUM_WEIGHTS = {"return_1m": 0.45, "return_3m": 0.30, "rsi": 0.25}
DEFAULT_QUALITY_WEIGHTS = {"gross_margin": 0.30, "net_margin": 0.30, "debt_ratio_inv": 0.25, "asset_turnover": 0.15}
DEFAULT_SIZE_WEIGHT = {"market_cap_log": 1.0}

# Default composite weights (sum to 1.0)
DEFAULT_COMPOSITE_WEIGHTS = {
    "value": 0.30,
    "growth": 0.25,
    "momentum": 0.20,
    "quality": 0.15,
    "size": 0.10,
}


def score_factors(stocks, composite_weights=None):
    """
    Score a list of stocks using multi-factor model.

    Each stock dict should have:
        pe, pb, market_cap, roe, revenue_growth, profit_growth,
        gross_margin, net_margin, debt_ratio, eps,
        return_1m, return_3m (optional: computed from klines),
        rsi (optional: latest RSI value)

    Returns: list of stock dicts with added fields:
        "factor_scores": dict of category → score
        "composite_score": float 0-1
        "rank": int
    """
    if not stocks:
        return []

    composite_weights = composite_weights or DEFAULT_COMPOSITE_WEIGHTS

    def _extract(key, default=0.0):
        vals = [s.get(key, default) for s in stocks]
        # Convert None to default
        return [v if v is not None else default for v in vals]

    # --- Value Factors ---
    pe_vals = winsorize(_extract("pe", 999))
    pb_vals = winsorize(_extract("pb", 999))
    # Calculate PS from market_cap and revenue
    ps_vals = []
    for s in stocks:
        mkt_cap = s.get("market_cap", 0) or 0
        revenue = s.get("revenue", 0) or 0
        if revenue > 0 and mkt_cap > 0:
            ps_vals.append(mkt_cap / revenue)
        else:
            ps_vals.append(999.0)
    ps_vals = winsorize(ps_vals)

    # Invert PE, PB, PS (lower is better)
    pe_score = minmax_norm(pe_vals, inverse=True)
    pb_score = minmax_norm(pb_vals, inverse=True)
    ps_score = minmax_norm(ps_vals, inverse=True)
    # Yield (eps/price) — higher is better, but we don't have div_yield reliably
    yield_score = [0.5] * len(stocks)  # neutral placeholder

    value_scores = []
    for i in range(len(stocks)):
        sc = (
            pe_score[i] * DEFAULT_VALUE_WEIGHTS["pe_inv"]
            + pb_score[i] * DEFAULT_VALUE_WEIGHTS["pb_inv"]
            + ps_score[i] * DEFAULT_VALUE_WEIGHTS["ps_inv"]
            + yield_score[i] * DEFAULT_VALUE_WEIGHTS["yield_direct"]
        )
        value_scores.append(round(sc, 4))

    # --- Growth Factors ---
    rev_growth = winsorize(_extract("revenue_growth", 0))
    prof_growth = winsorize(_extract("profit_growth", 0))
    roe_vals = winsorize(_extract("roe", 0))

    rev_score = minmax_norm(rev_growth, inverse=False)
    prof_score = minmax_norm(prof_growth, inverse=False)
    roe_score = minmax_norm(roe_vals, inverse=False)

    growth_scores = []
    for i in range(len(stocks)):
        sc = (
            rev_score[i] * DEFAULT_GROWTH_WEIGHTS["revenue_growth"]
            + prof_score[i] * DEFAULT_GROWTH_WEIGHTS["profit_growth"]
            + roe_score[i] * DEFAULT_GROWTH_WEIGHTS["roe"]
        )
        growth_scores.append(round(sc, 4))

    # --- Momentum Factors (tent-shaped: moderate returns are best) ---
    ret_1m = winsorize(_extract("return_1m", 0))
    ret_3m = winsorize(_extract("return_3m", 0))
    rsi_raw = winsorize(_extract("rsi", 50))

    # Tent function: score peaks at target, drops to 0 at extremes
    def tent_score(val, target, half_width):
        """Score 1.0 at target, 0 at target±half_width, linear in between."""
        if half_width == 0:
            return 0.5
        dist = abs(val - target) / half_width
        return max(0.0, min(1.0, 1.0 - dist))

    def tent_score_list(vals, target, half_width):
        return [tent_score(v, target, half_width) for v in vals]

    mom1m_score = tent_score_list(ret_1m, 0.03, 0.20)   # optimal ~3% monthly, wide tolerance
    mom3m_score = tent_score_list(ret_3m, 0.10, 0.35)    # optimal ~10% quarterly
    rsi_mom_score = tent_score_list(rsi_raw, 55, 50)      # optimal RSI ~55 (mildly bullish)

    momentum_scores = []
    for i in range(len(stocks)):
        sc = (
            mom1m_score[i] * DEFAULT_MOMENTUM_WEIGHTS["return_1m"]
            + mom3m_score[i] * DEFAULT_MOMENTUM_WEIGHTS["return_3m"]
            + rsi_mom_score[i] * DEFAULT_MOMENTUM_WEIGHTS["rsi"]
        )
        momentum_scores.append(round(sc, 4))

    # --- Quality Factors ---
    gross_m = winsorize(_extract("gross_margin", 0))
    net_m = winsorize(_extract("net_margin", 0))
    debt_r = winsorize(_extract("debt_ratio", 50))
    # Asset turnover = revenue / total_assets (approximated from market_cap / PB relation)
    asset_to = []
    for s in stocks:
        mkt_cap = s.get("market_cap", 0) or 1
        revenue = s.get("revenue", 0) or 0
        asset_to.append(safe_div(revenue, mkt_cap, 0) * 100)

    gross_score = minmax_norm(gross_m, inverse=False)
    net_score = minmax_norm(net_m, inverse=False)
    debt_score = minmax_norm(debt_r, inverse=True)  # lower debt = better
    asset_score = minmax_norm(winsorize(asset_to), inverse=False)

    quality_scores = []
    for i in range(len(stocks)):
        sc = (
            gross_score[i] * DEFAULT_QUALITY_WEIGHTS["gross_margin"]
            + net_score[i] * DEFAULT_QUALITY_WEIGHTS["net_margin"]
            + debt_score[i] * DEFAULT_QUALITY_WEIGHTS["debt_ratio_inv"]
            + asset_score[i] * DEFAULT_QUALITY_WEIGHTS["asset_turnover"]
        )
        quality_scores.append(round(sc, 4))

    # --- Size Factor (log market cap, z-score, then sigmoid to [0,1]) ---
    mkt_caps = _extract("market_cap", 1e8)
    log_caps = [math.log(max(c, 1)) for c in mkt_caps]
    z_caps = zscore(log_caps)
    # Sigmoid: 1 / (1 + exp(-z)) maps to [0,1]
    size_scores = [round(1.0 / (1.0 + math.exp(-z)), 4) for z in z_caps]

    # --- Composite Score ---
    for i, s in enumerate(stocks):
        s["factor_scores"] = {
            "value": value_scores[i],
            "growth": growth_scores[i],
            "momentum": momentum_scores[i],
            "quality": quality_scores[i],
            "size": size_scores[i],
        }
        s["composite_score"] = round(
            value_scores[i] * composite_weights.get("value", 0.30)
            + growth_scores[i] * composite_weights.get("growth", 0.25)
            + momentum_scores[i] * composite_weights.get("momentum", 0.20)
            + quality_scores[i] * composite_weights.get("quality", 0.15)
            + size_scores[i] * composite_weights.get("size", 0.10),
            4
        )

    # Sort and rank
    stocks.sort(key=lambda x: x["composite_score"], reverse=True)
    for i, s in enumerate(stocks):
        s["rank"] = i + 1

    return stocks


# ============================================================
# 5. MARKET BREADTH & SENTIMENT
# ============================================================

def calc_market_breadth(
    advance_count,
    decline_count,
    limit_up_count,
    limit_down_count,
    north_bound_flows,     # list of {"date": str, "net_flow": float} (net_flow in 亿元 or raw)
    csi300_change_pct,     # today's CSI 300 return as percentage
    volume_ratio,          # today's total volume / 20-day avg
):
    """
    Calculate market breadth and Fear & Greed index.

    Returns: {
        "advance_decline_ratio": float,
        "advance": int, "decline": int,
        "limit_up_down_ratio": float,
        "limit_up": int, "limit_down": int,
        "north_bound": {today, cum_3d, cum_5d, trend},
        "volume_ratio": float,
        "fear_greed_index": int (0-100),
        "composite_signal": "extreme_greed"|"greed"|"neutral"|"fear"|"extreme_fear",
    }
    """
    # 1. Advance/Decline
    total_ad = advance_count + decline_count
    ad_ratio = safe_div(advance_count, decline_count, 1.0) if decline_count > 0 else (2.0 if advance_count > 0 else 1.0)

    # 2. Limit up/down ratio
    lu_ld_ratio = safe_div(limit_up_count, limit_down_count, 1.0) if limit_down_count > 0 else (3.0 if limit_up_count > 0 else 1.0)

    # 3. North-bound flow analysis
    nb_today = north_bound_flows[-1]["net_flow"] if north_bound_flows else 0.0
    nb_3d = sum(f["net_flow"] for f in north_bound_flows[-3:]) if len(north_bound_flows) >= 3 else nb_today
    nb_5d = sum(f["net_flow"] for f in north_bound_flows[-5:]) if len(north_bound_flows) >= 5 else nb_today
    if nb_5d > 20:
        nb_trend = "strong_inflow"
    elif nb_5d > 5:
        nb_trend = "inflow"
    elif nb_5d > -5:
        nb_trend = "neutral"
    elif nb_5d > -20:
        nb_trend = "outflow"
    else:
        nb_trend = "strong_outflow"

    # 4. Fear & Greed Index (0-100)
    # Sub-indicator 1: Stock Price Breadth (0-20)
    if ad_ratio >= 3:     fg1 = 20
    elif ad_ratio >= 2:   fg1 = 16
    elif ad_ratio >= 1.5: fg1 = 12
    elif ad_ratio >= 1.0: fg1 = 8
    elif ad_ratio >= 0.7: fg1 = 4
    else:                 fg1 = 0

    # Sub-indicator 2: Limit Up/Down (0-20)
    if lu_ld_ratio >= 5:     fg2 = 20
    elif lu_ld_ratio >= 3:   fg2 = 16
    elif lu_ld_ratio >= 2:   fg2 = 12
    elif lu_ld_ratio >= 1:   fg2 = 8
    elif lu_ld_ratio >= 0.5: fg2 = 4
    else:                     fg2 = 0

    # Sub-indicator 3: North-bound Flow (0-20)
    if nb_5d > 100:        fg3 = 20
    elif nb_5d > 50:       fg3 = 16
    elif nb_5d > 0:        fg3 = 12
    elif nb_5d > -30:      fg3 = 6
    else:                  fg3 = 0

    # Sub-indicator 4: Volume (0-20)
    vr = volume_ratio if volume_ratio else 1.0
    if vr > 2.0:      fg4 = 20
    elif vr > 1.5:    fg4 = 16
    elif vr > 1.2:    fg4 = 12
    elif vr >= 0.8:   fg4 = 8
    elif vr >= 0.5:   fg4 = 4
    else:             fg4 = 0

    # Sub-indicator 5: Market Momentum (0-20)
    cp = csi300_change_pct if csi300_change_pct is not None else 0
    if cp > 3:       fg5 = 20
    elif cp > 2:     fg5 = 17
    elif cp > 1:     fg5 = 14
    elif cp > 0.5:   fg5 = 12
    elif cp > 0:     fg5 = 10
    elif cp > -0.5:  fg5 = 7
    elif cp > -1:    fg5 = 5
    elif cp > -2:    fg5 = 3
    else:            fg5 = 0

    fear_greed = min(100, max(0, fg1 + fg2 + fg3 + fg4 + fg5))

    # Composite signal
    if fear_greed >= 75:
        signal = "extreme_greed"
    elif fear_greed >= 60:
        signal = "greed"
    elif fear_greed >= 40:
        signal = "neutral"
    elif fear_greed >= 25:
        signal = "fear"
    else:
        signal = "extreme_fear"

    return {
        "advance_decline_ratio": round(ad_ratio, 2),
        "advance": advance_count,
        "decline": decline_count,
        "limit_up_down_ratio": round(lu_ld_ratio, 2),
        "limit_up": limit_up_count,
        "limit_down": limit_down_count,
        "north_bound": {
            "today": round(nb_today, 2),
            "cum_3d": round(nb_3d, 2),
            "cum_5d": round(nb_5d, 2),
            "trend": nb_trend,
        },
        "volume_ratio": round(vr, 2),
        "fear_greed_index": fear_greed,
        "fear_greed_parts": {"breadth": fg1, "limits": fg2, "north_bound": fg3, "volume": fg4, "momentum": fg5},
        "composite_signal": signal,
    }


# ============================================================
# 6. RISK METRICS
# ============================================================

def calc_risk_metrics(prices, market_prices=None, risk_free_rate=0.02):
    """
    Calculate risk metrics for a stock.

    Input:
        prices: list of closing prices (at least 20)
        market_prices: list of benchmark closing prices (optional, for beta)
        risk_free_rate: annual risk-free rate (default 2%)

    Returns: dict of risk metrics
    """
    if not prices or len(prices) < 5:
        return {"error": f"Insufficient price data: {len(prices) if prices else 0} points (need >= 5)"}

    rets = simple_returns(prices)
    if not rets:
        return {"error": "Cannot compute returns"}

    # Daily stats
    avg_daily = statistics.mean(rets)
    daily_std = statistics.stdev(rets) if len(rets) > 1 else 0.0

    # Historical volatility (annualized)
    hist_vol_20d = daily_std * math.sqrt(252)

    # Sharpe Ratio (annualized)
    if daily_std > 0:
        sharpe = (avg_daily * 252 - risk_free_rate) / (daily_std * math.sqrt(252))
    else:
        sharpe = 0.0

    # Max Drawdown
    def max_dd(prices_list, window=None):
        if window:
            prices_list = prices_list[-window:]
        peak = prices_list[0]
        max_dd_val = 0.0
        for p in prices_list:
            if p > peak:
                peak = p
            dd = (peak - p) / peak if peak > 0 else 0.0
            if dd > max_dd_val:
                max_dd_val = dd
        return max_dd_val

    max_dd_20d = max_dd(prices, 20) if len(prices) >= 20 else max_dd(prices, None)
    max_dd_60d = max_dd(prices, 60) if len(prices) >= 60 else max_dd(prices, None)
    max_dd_all = max_dd(prices, None)

    # VaR (Historical simulation)
    sorted_rets = sorted(rets)
    var_95_idx = max(0, int(len(sorted_rets) * 0.05))
    var_99_idx = max(0, int(len(sorted_rets) * 0.01))
    var_95 = abs(sorted_rets[var_95_idx]) * 100  # as percentage
    var_99 = abs(sorted_rets[var_99_idx]) * 100

    # Beta (vs market)
    beta = None
    if market_prices and len(market_prices) >= len(prices) - 1:
        # Align lengths
        mkt_prices_aligned = market_prices[-len(prices):]
        mkt_rets = simple_returns(mkt_prices_aligned)
        if len(mkt_rets) == len(rets) and len(rets) > 1:
            mean_r = statistics.mean(rets)
            mean_m = statistics.mean(mkt_rets)
            cov = sum((r - mean_r) * (m - mean_m) for r, m in zip(rets, mkt_rets)) / (len(rets) - 1)
            var_m = statistics.variance(mkt_rets) if len(mkt_rets) > 1 else 0
            if var_m > 0:
                beta = round(cov / var_m, 3)

    # Rolling volatility (for chart)
    rolling_vol = []
    window = 20
    for i in range(len(prices)):
        if i < window - 1:
            rolling_vol.append(None)
        else:
            w_rets = simple_returns(prices[i - window + 1 : i + 1])
            if w_rets and len(w_rets) > 1:
                rolling_vol.append(round(statistics.stdev(w_rets) * math.sqrt(252) * 100, 2))
            else:
                rolling_vol.append(None)

    # Win/loss stats
    up_days = sum(1 for r in rets if r > 0)
    down_days = sum(1 for r in rets if r < 0)
    win_rate = safe_div(up_days, up_days + down_days, 0.5)

    return {
        "historical_volatility_20d": round(hist_vol_20d * 100, 2),  # as percentage
        "beta": beta,
        "max_drawdown_20d": round(max_dd_20d * 100, 2),
        "max_drawdown_60d": round(max_dd_60d * 100, 2),
        "max_drawdown_all": round(max_dd_all * 100, 2),
        "var_95": round(var_95, 2),
        "var_99": round(var_99, 2),
        "sharpe_annual": round(sharpe, 3),
        "daily_std": round(daily_std * 100, 2),
        "avg_daily_return": round(avg_daily * 100, 2),
        "win_rate": round(win_rate * 100, 1),
        "rolling_volatility_20d": rolling_vol,
        "up_days": up_days,
        "down_days": down_days,
        "total_days": len(rets),
    }


# ============================================================
# 7. BACKTEST ENGINE
# ============================================================

def backtest_strategy(klines, signal_func, initial_capital=100000.0, commission=0.0003, slippage=0.001):
    """
    Generic backtest engine.

    Input:
        klines: [{date, open, close, high, low, volume}, ...]
        signal_func: callable(klines) → list of ints (same length as klines)
                     -1 = sell, 0 = hold, 1 = buy
        initial_capital: starting capital
        commission: per-trade commission rate
        slippage: buy at close*(1+slippage), sell at close*(1-slippage)

    Returns: {
        "metrics": dict,
        "equity_curve": [{date, equity, position, cash}, ...],
        "trades": [{entry_date, entry_price, exit_date, exit_price, return_pct, win}, ...],
        "signals": [{date, type, price}, ...],
    }
    """
    if not klines or len(klines) < 2:
        return {"error": "Insufficient kline data for backtesting"}

    # Empty signal_func means no signals
    try:
        raw_signals = signal_func(klines)
    except Exception as e:
        return {"error": f"Signal function error: {str(e)}"}

    # Trim signals to match klines
    if len(raw_signals) < len(klines):
        raw_signals = [0] * (len(klines) - len(raw_signals)) + raw_signals
    elif len(raw_signals) > len(klines):
        raw_signals = raw_signals[-len(klines):]

    cash = initial_capital
    shares = 0
    equity_curve = []
    trades = []
    signal_log = []

    in_position = False
    entry_price = 0.0
    entry_date = ""

    for i, k in enumerate(klines):
        close = k["close"]
        signal = raw_signals[i] if i < len(raw_signals) else 0

        # Record signal
        if signal == 1:
            signal_log.append({"date": k["date"], "type": "buy", "price": close})
        elif signal == -1:
            signal_log.append({"date": k["date"], "type": "sell", "price": close})

        # Execute trades
        if signal == 1 and not in_position:
            # Buy
            buy_price = close * (1.0 + slippage)
            shares = int(cash * 0.95 / buy_price)  # 95% position
            cost = shares * buy_price * (1.0 + commission)
            cash -= cost
            in_position = True
            entry_price = buy_price
            entry_date = k["date"]

        elif signal == -1 and in_position:
            # Sell
            sell_price = close * (1.0 - slippage)
            proceeds = shares * sell_price * (1.0 - commission)
            cash += proceeds
            ret_pct = (sell_price - entry_price) / entry_price * 100 if entry_price > 0 else 0
            trades.append({
                "entry_date": entry_date,
                "entry_price": round(entry_price, 2),
                "exit_date": k["date"],
                "exit_price": round(sell_price, 2),
                "return_pct": round(ret_pct, 2),
                "win": ret_pct > 0,
            })
            shares = 0
            in_position = False

        # Daily equity
        equity = cash + shares * close
        equity_curve.append({
            "date": k["date"],
            "equity": round(equity, 2),
            "position": shares > 0,
            "cash": round(cash, 2),
        })

    # Close any remaining position at last close
    if in_position:
        last_close = klines[-1]["close"]
        proceeds = shares * last_close * (1.0 - commission)
        cash += proceeds
        ret_pct = (last_close - entry_price) / entry_price * 100 if entry_price > 0 else 0
        trades.append({
            "entry_date": entry_date,
            "entry_price": round(entry_price, 2),
            "exit_date": klines[-1]["date"],
            "exit_price": round(last_close, 2),
            "return_pct": round(ret_pct, 2),
            "win": ret_pct > 0,
        })
        shares = 0

    final_equity = cash

    # --- Metrics ---
    total_return_pct = (final_equity - initial_capital) / initial_capital * 100

    # Buy & hold return
    first_close = klines[0]["close"]
    last_close_val = klines[-1]["close"]
    buy_hold_return_pct = (last_close_val - first_close) / first_close * 100 if first_close > 0 else 0

    # Equity returns
    equity_values = [e["equity"] for e in equity_curve]
    eq_rets = simple_returns(equity_values)

    # Sharpe
    if eq_rets and len(eq_rets) > 1:
        eq_std = statistics.stdev(eq_rets)
        eq_avg = statistics.mean(eq_rets)
        sharpe = (eq_avg / eq_std * math.sqrt(252)) if eq_std > 0 else 0
    else:
        sharpe = 0

    # Max drawdown
    peak = equity_values[0]
    max_dd_val = 0.0
    for e in equity_values:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0
        if dd > max_dd_val:
            max_dd_val = dd

    # Trade stats
    win_count = sum(1 for t in trades if t["win"])
    trade_count = len(trades)
    win_rate = safe_div(win_count, trade_count, 0) * 100 if trade_count > 0 else 0

    avg_trade_return = statistics.mean([t["return_pct"] for t in trades]) if trades else 0
    gross_profit = sum(t["return_pct"] for t in trades if t["return_pct"] > 0)
    gross_loss = abs(sum(t["return_pct"] for t in trades if t["return_pct"] < 0))
    profit_factor = safe_div(gross_profit, gross_loss, float("inf"))

    return {
        "metrics": {
            "total_return_pct": round(total_return_pct, 2),
            "buy_hold_return_pct": round(buy_hold_return_pct, 2),
            "sharpe_ratio": round(sharpe, 3),
            "max_drawdown_pct": round(max_dd_val * 100, 2),
            "win_rate": round(win_rate, 1),
            "trade_count": trade_count,
            "avg_trade_return_pct": round(avg_trade_return, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else "∞",
        },
        "equity_curve": equity_curve,
        "trades": trades,
        "signals": signal_log,
    }


def backtest_sma_cross(klines, fast_period=5, slow_period=20, initial_capital=100000.0, commission=0.0003, slippage=0.001):
    """Backtest SMA crossover strategy."""

    def sma_signal_func(klines_data):
        closes = [k["close"] for k in klines_data]
        sma_fast = _calc_sma(closes, fast_period)
        sma_slow = _calc_sma(closes, slow_period)

        signals = [0] * len(klines_data)
        for i in range(1, len(klines_data)):
            if sma_fast[i] is not None and sma_slow[i] is not None and sma_fast[i - 1] is not None and sma_slow[i - 1] is not None:
                # Golden cross: fast crosses above slow
                if sma_fast[i - 1] <= sma_slow[i - 1] and sma_fast[i] > sma_slow[i]:
                    signals[i] = 1
                # Death cross: fast crosses below slow
                elif sma_fast[i - 1] >= sma_slow[i - 1] and sma_fast[i] < sma_slow[i]:
                    signals[i] = -1
        return signals

    return backtest_strategy(klines, sma_signal_func, initial_capital, commission, slippage)


def backtest_macd_cross(klines, initial_capital=100000.0, commission=0.0003, slippage=0.001):
    """Backtest MACD golden cross / death cross strategy."""

    def macd_signal_func(klines_data):
        closes = [k["close"] for k in klines_data]
        macd_data = calc_macd(closes)
        dif = macd_data["dif"]
        dea = macd_data["dea"]

        signals = [0] * len(klines_data)
        for i in range(1, len(klines_data)):
            if dif[i] is not None and dea[i] is not None and dif[i - 1] is not None and dea[i - 1] is not None:
                if dif[i - 1] <= dea[i - 1] and dif[i] > dea[i]:
                    signals[i] = 1
                elif dif[i - 1] >= dea[i - 1] and dif[i] < dea[i]:
                    signals[i] = -1
        return signals

    return backtest_strategy(klines, macd_signal_func, initial_capital, commission, slippage)
