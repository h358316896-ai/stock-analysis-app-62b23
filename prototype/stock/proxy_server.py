from flask import Flask, request, jsonify
from flask_cors import CORS
import yfinance as yf

app = Flask(__name__)
CORS(app)


@app.route('/quote')
def quote():
    symbol = request.args.get('symbol', '')
    market = request.args.get('market', 'cn')
    if not symbol:
        return jsonify({'error':'missing symbol'}), 400

    # 转换为 Yahoo 风格代码（简单映射，按需扩展）
    ticker = symbol
    if market == 'hk':
        ticker = symbol + '.HK'
    elif market == 'us':
        ticker = symbol

    try:
        t = yf.Ticker(ticker)
        info = t.history(period='1d')
        if info.empty:
            return jsonify({'error':'no data'}), 404
        last = info['Close'].iloc[-1]
        prev = info['Close'].iloc[0]
        delta = (last - prev) / prev * 100 if prev != 0 else 0
        return jsonify({
            'symbol': symbol,
            'ticker': ticker,
            'price': float(round(last, 2)),
            'change_percent': round(delta, 2)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/history')
def history():
    symbol = request.args.get('symbol', '')
    market = request.args.get('market', 'cn')
    period = request.args.get('period', '60d')
    interval = request.args.get('interval', '1d')
    if not symbol:
        return jsonify({'error':'missing symbol'}), 400

    ticker = symbol
    if market == 'hk':
        ticker = symbol + '.HK'

    try:
        t = yf.Ticker(ticker)
        df = t.history(period=period, interval=interval)
        if df.empty:
            return jsonify({'error':'no data'}), 404
        # Return OHLC in simple JSON list
        records = []
        for idx, row in df.iterrows():
            ts = int(idx.timestamp() * 1000)
            records.append({
                't': ts,
                'o': float(round(row['Open'],2)),
                'h': float(round(row['High'],2)),
                'l': float(round(row['Low'],2)),
                'c': float(round(row['Close'],2)),
                'v': int(row.get('Volume',0)) if 'Volume' in row else 0
            })
        return jsonify({'symbol': symbol, 'ticker': ticker, 'records': records})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
