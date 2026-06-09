#!/usr/bin/env python3
"""
Backtest API — Flask microservice for StockAI strategy backtesting.
Usage: python backtest_api.py
Default port: 5001
"""

import os
import sys
import json
import argparse
from datetime import datetime

import numpy as np
import pandas as pd
from flask import Flask, request, jsonify
from flask_cors import CORS

# Add backtest module to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'prototype', 'stock', 'backtest'))
from engine import Backtester
from grid import run_grid

app = Flask(__name__)
CORS(app)


# ───────────────────────────────────────────────
#  Ticker mapping helpers
# ───────────────────────────────────────────────
def map_ticker(symbol, market):
    s = symbol.strip()
    if market == 'hk':
        return s + '.HK'
    if market == 'us':
        return s
    if market == 'cn':
        if s.startswith('6'):
            return s + '.SS'
        return s + '.SZ'
    return s


def fetch_history(ticker, period='1y'):
    import yfinance as yf
    try:
        df = yf.download(ticker, period=period, progress=False)
    except Exception as e:
        return None, str(e)
    if df is None or df.empty:
        return None, 'No historical data found'
    return df, None


# ───────────────────────────────────────────────
#  API routes
# ───────────────────────────────────────────────
@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'service': 'backtest-api', 'version': '1.0.0'})


@app.route('/backtest/single', methods=['POST'])
def run_single_backtest():
    """Run a single backtest with moving average crossover strategy."""
    data = request.get_json() or {}
    symbol = data.get('symbol', '600519')
    market = data.get('market', 'cn')
    period = data.get('period', '1y')
    short = int(data.get('short', 20))
    long = int(data.get('long', 60))
    capital = float(data.get('capital', 100000))
    position_size = float(data.get('position_size', 0.2))
    commission = float(data.get('commission', 0.001))
    slippage = float(data.get('slippage', 0.001))
    stop_loss_pct = data.get('stop_loss_pct')
    take_profit_pct = data.get('take_profit_pct')

    if stop_loss_pct is not None:
        stop_loss_pct = float(stop_loss_pct)
    if take_profit_pct is not None:
        take_profit_pct = float(take_profit_pct)

    ticker = map_ticker(symbol, market)
    df, err = fetch_history(ticker, period)

    if err:
        return jsonify({'error': f'Data fetch failed: {err}'}), 400

    try:
        bt = Backtester(
            df, capital=capital, position_size=position_size,
            commission=commission, slippage=slippage,
            short=short, long=long,
            stop_loss_pct=stop_loss_pct, take_profit_pct=take_profit_pct
        )
        result = bt.run()
    except Exception as e:
        return jsonify({'error': f'Backtest failed: {str(e)}'}), 500

    # Build response
    trades = []
    for t in result.get('trades', []):
        trades.append({
            'date': str(t.get('date', '')),
            'type': t.get('type', ''),
            'price': round(float(t.get('price', 0)), 2),
            'shares': int(t.get('shares', 0)),
            'value': round(float(t.get('value', 0)), 2),
            'commission': round(float(t.get('commission', 0)), 2),
            'pnl': round(float(t.get('pnl', 0)), 2) if t.get('pnl') is not None else None
        })

    equity_curve = []
    for i, row in result.get('equity_df', pd.DataFrame()).iterrows():
        equity_curve.append({
            'date': str(i.date()) if hasattr(i, 'date') else str(i),
            'equity': round(float(row.get('equity', 0)), 2),
            'benchmark': round(float(row.get('benchmark', row.get('buy_hold', 0))), 2)
        })

    stats = result.get('stats', {})
    response = {
        'symbol': symbol,
        'market': market,
        'ticker': ticker,
        'period': period,
        'params': {
            'short': short, 'long': long,
            'capital': capital, 'position_size': position_size,
            'commission': commission, 'slippage': slippage
        },
        'stats': {
            'total_return': round(float(stats.get('total_return', 0)) * 100, 2),
            'annualized_return': round(float(stats.get('annualized_return', 0)) * 100, 2),
            'annual_volatility': round(float(stats.get('annual_volatility', 0)) * 100, 2),
            'sharpe': round(float(stats.get('sharpe', 0)), 2),
            'max_drawdown': round(float(stats.get('max_drawdown', 0)) * 100, 2),
            'total_trades': int(stats.get('total_trades', 0)),
            'win_rate': round(float(stats.get('win_rate', 0)) * 100, 2),
            'profit_factor': round(float(stats.get('profit_factor', 0)), 2)
        },
        'trades': trades[:50],  # Limit to first 50 trades
        'equity_curve': equity_curve[::max(1, len(equity_curve) // 200)]  # Downsample to ~200 points
    }
    return jsonify(response)


@app.route('/backtest/grid', methods=['POST'])
def run_grid_backtest():
    """Run a grid search backtest to find optimal parameters."""
    data = request.get_json() or {}
    symbol = data.get('symbol', '600519')
    market = data.get('market', 'cn')
    period = data.get('period', '1y')
    short_range = data.get('short_range', [10, 20, 50])
    long_range = data.get('long_range', [50, 100, 200])
    position_sizes = data.get('position_sizes', [0.1, 0.2])
    commission = float(data.get('commission', 0.001))
    slippage = float(data.get('slippage', 0.001))
    capital = float(data.get('capital', 100000))

    ticker = map_ticker(symbol, market)
    df, err = fetch_history(ticker, period)

    if err:
        return jsonify({'error': f'Data fetch failed: {err}'}), 400

    try:
        grid_df = run_grid(
            df, [symbol],
            short_range, long_range,
            position_sizes, [commission], [slippage],
            capital=capital
        )
    except Exception as e:
        return jsonify({'error': f'Grid backtest failed: {str(e)}'}), 500

    if grid_df is None or grid_df.empty:
        return jsonify({'error': 'No valid grid results'}), 404

    # Get top 10 results
    top10 = grid_df.nlargest(10, 'annualized_return') if 'annualized_return' in grid_df.columns else grid_df.head(10)
    results = []
    for _, row in top10.iterrows():
        results.append({
            'short': int(row.get('short', 0)),
            'long': int(row.get('long', 0)),
            'position_size': round(float(row.get('position_size', 0)), 2),
            'total_return': round(float(row.get('total_return', 0)) * 100, 2),
            'annualized_return': round(float(row.get('annualized_return', 0)) * 100, 2),
            'sharpe': round(float(row.get('sharpe', 0)), 2),
            'max_drawdown': round(float(row.get('max_drawdown', 0)) * 100, 2),
            'total_trades': int(row.get('total_trades', 0)),
            'win_rate': round(float(row.get('win_rate', 0)) * 100, 2)
        })

    return jsonify({
        'symbol': symbol,
        'market': market,
        'period': period,
        'total_combinations': len(grid_df),
        'top_results': results
    })


# ───────────────────────────────────────────────
#  Main
# ───────────────────────────────────────────────
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='StockAI Backtest API')
    parser.add_argument('--port', type=int, default=5001, help='Port to listen on')
    parser.add_argument('--debug', action='store_true', help='Enable debug mode')
    args = parser.parse_args()

    print(f'StockAI Backtest API starting on port {args.port}...')
    app.run(host='0.0.0.0', port=args.port, debug=args.debug)
