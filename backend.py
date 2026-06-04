# AI Workshop - Unified Backend
# 金融分析 + 自媒体助手 + 接单服务

import os
import re
import json
import time
import base64
import requests
from io import BytesIO
from datetime import datetime, timedelta

# Try loading .env, fallback to env vars
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Manual CORS + custom pkg path for optional deps
# (moved below BASE_DIR definition)

from flask import Flask, request, jsonify, send_file, render_template_string, session
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret-key-change-in-prod-2026")

# Session-based auth helper
def current_user_id():
    return session.get("user_id")

def login_required(fn):
    from functools import wraps
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user_id():
            return jsonify({"error": "请先登录", "need_login": True}), 401
        return fn(*args, **kwargs)
    return wrapper

# Manual CORS (replaces flask-cors)
@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    return response

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Custom pkg path for optional deps (e.g. flask-cors, yfinance, fpdf)
_PKG_DIR = os.path.join(BASE_DIR, ".pkg")
if os.path.isdir(_PKG_DIR):
    import sys
    sys.path.insert(0, _PKG_DIR)

DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
KLING_ACCESS_KEY = os.getenv("KLING_ACCESS_KEY", "")
KLING_SECRET_KEY = os.getenv("KLING_SECRET_KEY", "")
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY", "")

# 导入认证数据库模块
import auth_db

# ==========================================================
# HELPER: HTTP JSON fetcher
# ==========================================================
def fetch_json(url, timeout=10):
    """Fetch JSON from URL using Python requests"""
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        return resp.json()
    except Exception as e:
        print(f"[fetch_json] Error for {url[:80]}: {e}")
        return {"error": str(e)}


def fetch_text_gbk(url, timeout=10):
    """Fetch raw text as GBK from URL"""
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=timeout)
        resp.encoding = "gb18030"
        return resp.text
    except Exception as e:
        return None


# ==========================================================
# HOME / NAV
# ==========================================================
@app.route("/")
def home():
    return render_template_string(open(os.path.join(STATIC_DIR, "index.html"), encoding="utf-8").read())

@app.route("/stock")
def stock_page():
    return render_template_string(open(os.path.join(STATIC_DIR, "stock.html"), encoding="utf-8").read())

@app.route("/media")
def media_page():
    return render_template_string(open(os.path.join(STATIC_DIR, "media.html"), encoding="utf-8").read())

@app.route("/services")
def services_page():
    return render_template_string(open(os.path.join(STATIC_DIR, "services.html"), encoding="utf-8").read())


# ==========================================================
# MODULE 1: STOCK ANALYSIS
# ==========================================================
# A-share stock names loaded from stock_names.py (auto-generated, 5499 stocks)
try:
    from stock_names import STOCK_NAMES as _TEMP
    STOCK_NAMES = _TEMP
except ImportError:
    STOCK_NAMES = {}

# HK stock names loaded from hk_stock_names.py (top HK stocks)
try:
    from hk_stock_names import HK_STOCK_NAMES as _TEMP_HK
    HK_STOCK_NAMES = _TEMP_HK
except ImportError:
    HK_STOCK_NAMES = {}


def _fetch_tencent_raw(url):
    """Fetch raw GBK text from Tencent Finance API using Python requests (no curl dependency)"""
    try:
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        resp.encoding = "gb18030"
        return resp.text
    except Exception as e:
        return None


def fetch_cn_quote(code):
    # Tencent Finance real-time quote API
    # Format: https://qt.gtimg.cn/q=sh600519 (returns GBK-encoded JS string)
    prefix = "sh" if code.startswith(("6", "5", "1")) else "sz"
    url = f"https://qt.gtimg.cn/q={prefix}{code}"
    try:
        text = _fetch_tencent_raw(url)
        if not text:
            return {"error": "fetch failed"}
        # Parse: v_sh600519="1~茅台~600519~价格~..."
        match = re.search(r'="([^"]+)"', text)
        if not match:
            return None
        fields = match.group(1).split("~")
        if len(fields) < 35:
            return None
        price      = float(fields[3]) if fields[3] else 0.0
        prev_close = float(fields[4]) if fields[4] else price
        open_price = float(fields[5]) if fields[5] else price
        volume     = int(fields[6]) * 100 if fields[6] else 0   # 手 → 股
        high       = float(fields[33]) if len(fields) > 33 and fields[33] else price
        low        = float(fields[34]) if len(fields) > 34 and fields[34] else price
        chg        = price - prev_close
        chg_pct    = (chg / prev_close * 100) if prev_close else 0.0
        name = fields[1] if len(fields) > 1 and fields[1] else STOCK_NAMES.get(code, code)
        return {
            "code": code, "name": name,
            "price": round(price, 2), "change_pct": round(chg_pct, 2),
            "change": round(chg, 2),
            "open": round(open_price, 2), "high": round(high, 2), "low": round(low, 2),
            "volume": volume, "amount": 0,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_cn_kline(code, days=60):
    # Tencent Finance K-line API (returns JSON)
    # URL: https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param=sh600519,day,,,60,qfq
    prefix = "sh" if code.startswith(("6", "5", "1")) else "sz"
    url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{code},day,,,{days},qfq"
    data = fetch_json(url, 15)
    if isinstance(data, dict) and "error" in data:
        return []
    klines_raw = data.get("data", {}).get(f"{prefix}{code}", {}).get("qfqday", [])
    klines = []
    for k in klines_raw:
        if len(k) >= 6:
            klines.append({
                "date": k[0], "open": float(k[1]), "close": float(k[2]),
                "high": float(k[3]), "low": float(k[4]), "volume": int(float(k[5])) * 100
            })
    return klines


def fetch_hk_quote(code):
    # Tencent Finance HK real-time quote
    # Format: https://qt.gtimg.cn/q=hk00700
    # HK fields: 1=name, 3=price, 4=prev_close, 5=open, 6=vol(shares), 31=change, 32=pct, 33=high, 34=low, 39=pe, 45=market_cap
    code = code.zfill(5)
    url = f"https://qt.gtimg.cn/q=hk{code}"
    try:
        text = _fetch_tencent_raw(url)
        if not text:
            return {"error": "fetch failed"}
        match = re.search(r'="([^"]+)"', text)
        if not match:
            return None
        fields = match.group(1).split("~")
        if len(fields) < 35:
            return None
        price      = float(fields[3]) if fields[3] else 0.0
        prev_close = float(fields[4]) if fields[4] else price
        open_price = float(fields[5]) if fields[5] else price
        volume     = int(float(fields[6])) if fields[6] else 0  # HK already in shares
        change     = float(fields[31]) if len(fields) > 31 and fields[31] else 0.0
        chg_pct    = float(fields[32]) if len(fields) > 32 and fields[32] else 0.0
        high       = float(fields[33]) if len(fields) > 33 and fields[33] else price
        low        = float(fields[34]) if len(fields) > 34 and fields[34] else price
        pe         = float(fields[39]) if len(fields) > 39 and fields[39] else 0.0
        mkt_cap    = float(fields[45]) if len(fields) > 45 and fields[45] else 0.0
        name = fields[1] if len(fields) > 1 and fields[1] else code
        return {
            "code": code, "name": name,
            "price": round(price, 2), "change_pct": round(chg_pct, 2),
            "change": round(change, 2),
            "open": round(open_price, 2), "high": round(high, 2), "low": round(low, 2),
            "volume": volume, "amount": 0,
            "pe": round(pe, 2), "market_cap": mkt_cap, "currency": "HKD",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_us_quote(code):
    """Fetch US stock quote - try yfinance first, fallback to Tencent"""
    # Try yfinance first
    try:
        import yfinance as yf
        t = yf.Ticker(code)
        info = t.info
        price = info.get("currentPrice") or info.get("regularMarketPrice") or 0
        prev = info.get("previousClose") or 0
        if price <= 0 or prev <= 0:
            raise ValueError("yfinance returned zero data")
        chg_pct = ((price - prev) / prev * 100) if prev else 0
        return {
            "code": code, "name": info.get("shortName", code),
            "price": price, "change_pct": round(chg_pct, 2),
            "change": round(price - prev, 2), "currency": "USD",
            "market_cap": info.get("marketCap", 0), "pe": info.get("trailingPE", 0),
            "time": datetime.now().strftime("%Y-%m-%d %H:%M")
        }
    except Exception:
        pass

    # Fallback: Tencent Finance US API (format: usAAPL.OQ)
    try:
        code_up = code.upper()
        text = _fetch_tencent_raw(f"https://qt.gtimg.cn/q=us{code_up}")
        if text:
            match = re.search(r'="([^"]+)"', text)
            if match:
                fields = match.group(1).split("~")
                if len(fields) >= 35:
                    name = fields[1] if len(fields) > 1 else code
                    price = float(fields[3]) if fields[3] else 0.0
                    prev_close = float(fields[4]) if fields[4] else price
                    chg_pct = float(fields[32]) if len(fields) > 32 and fields[32] else 0.0
                    chg = float(fields[31]) if len(fields) > 31 and fields[31] else 0.0
                    high = float(fields[33]) if len(fields) > 33 and fields[33] else price
                    low = float(fields[34]) if len(fields) > 34 and fields[34] else price
                    pe = float(fields[39]) if len(fields) > 39 and fields[39] else 0.0
                    mkt_cap = float(fields[45]) if len(fields) > 45 and fields[45] else 0.0
                    return {
                        "code": code_up, "name": name,
                        "price": round(price, 2), "change_pct": round(chg_pct, 2),
                        "change": round(chg, 2), "currency": "USD",
                        "open": 0, "high": round(high, 2), "low": round(low, 2),
                        "volume": 0, "amount": 0,
                        "pe": round(pe, 2), "market_cap": mkt_cap,
                        "time": datetime.now().strftime("%Y-%m-%d %H:%M")
                    }
    except Exception:
        pass

    return {"error": f"US stock {code} not found"}


def deepseek_chat(messages, temperature=0.7, max_tokens=2000):
    resp = requests.post(
        "https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"},
        json={"model": "deepseek-chat", "messages": messages, "temperature": temperature, "max_tokens": max_tokens},
        timeout=60
    )
    if resp.status_code != 200:
        return {"error": f"DeepSeek API error: {resp.status_code} {resp.text[:200]}"}
    return resp.json()["choices"][0]["message"]["content"]


def _search_online_tencent(keyword, market_type="gp"):
    """Online search via Tencent smartbox API
    market_type: "gp" for A-shares, "hk" for HK, "us" for US
    """
    from urllib.parse import quote
    try:
        gbk_bytes = keyword.encode("gbk")
        encoded = quote(gbk_bytes, safe="")
    except Exception:
        encoded = quote(keyword)
    url = f"https://smartbox.gtimg.cn/s3/?q={encoded}&t={market_type}"
    try:
        text = fetch_text_gbk(url, 10)
        if not text:
            return []
        match = re.search(r'v_hint="([^"]+)"', text)
        if not match or match.group(1).strip() == "N":
            return []
        results = []
        for item in match.group(1).split("|"):
            parts = item.split("~")
            if len(parts) >= 3:
                code = parts[1]
                name = parts[2]
                results.append({"code": code, "name": name, "market": "cn" if market_type == "gp" else market_type})
                if len(results) >= 20:
                    break
        return results
    except Exception:
        return []


def _search_us_stocks(keyword):
    """Search US stocks: use Tencent smartbox API"""
    results = []
    from urllib.parse import quote
    try:
        gbk_bytes = keyword.encode("gbk") if any(ord(c) > 127 for c in keyword) else keyword.encode("ascii")
        encoded = quote(gbk_bytes, safe="")
    except Exception:
        encoded = quote(keyword)
    
    url = f"https://smartbox.gtimg.cn/s3/?q={encoded}&t=us"
    try:
        text = fetch_text_gbk(url, 10)
        if text:
            match = re.search(r'v_hint="([^"]+)"', text)
            if match and match.group(1).strip() != "N":
                for item in match.group(1).split("^"):
                    parts = item.split("~")
                    if len(parts) >= 3 and parts[1] and parts[2] and parts[2] != "*":
                        code = parts[1].split(".")[0].upper()  # strip .OQ/.N etc, uppercase
                        name = parts[2]
                        if code and name:
                            results.append({"code": code, "name": name, "market": "us"})
                        if len(results) >= 10:
                            break
    except Exception:
        pass
    return results


@app.route("/api/stock/search")
def stock_search():
    keyword = request.args.get("q", "").strip()
    market = request.args.get("market", "all").strip()  # cn, hk, us, all
    if not keyword:
        return jsonify({"error": "no query"}), 400

    results = []

    # ---- A-shares search (market=cn or all) ----
    if market in ("cn", "all"):
        for c, n in STOCK_NAMES.items():
            if keyword in c or keyword in n:
                results.append({"code": c, "name": n, "market": "cn"})
            if len(results) >= 20:
                break
        # If local A-share search found nothing, try online
        cn_count = len(results)
        if cn_count == 0:
            results.extend(_search_online_tencent(keyword, "gp"))

    # ---- HK stocks search (market=hk or all) ----
    if market in ("hk", "all"):
        for c, n in HK_STOCK_NAMES.items():
            if keyword in c or keyword in n:
                results.append({"code": c, "name": n, "market": "hk"})
            if len(results) >= 50:
                break
        # Try online HK search (Tencent might support t=hk)
        if len([r for r in results if r["market"] == "hk"]) < 5:
            hk_results = _search_online_tencent(keyword, "hk")
            for r in hk_results:
                r["market"] = "hk"
            results.extend(hk_results)

    # ---- US stocks search (market=us or all) ----
    if market in ("us", "all"):
        us_results = _search_us_stocks(keyword)
        results.extend(us_results)

    # Deduplicate by code+market (normalize US codes)
    seen = set()
    deduped = []
    for r in results:
        code = r.get("code", "")
        market = r.get("market", "")
        # Normalize US codes: strip .O/.N/.OQ/.NQ suffixes, uppercase
        if market == "us":
            code = code.split(".")[0].upper()
            r["code"] = code
        key = (code, market)
        if key not in seen:
            seen.add(key)
            deduped.append(r)
            if len(deduped) >= 40:
                break

    return jsonify({"results": deduped})


@app.route("/api/stock/quote")
def stock_quote():
    code = request.args.get("code", "").strip()
    market = request.args.get("market", "cn").strip()
    if not code:
        return jsonify({"error": "no code"}), 400
    if market == "cn":
        result = fetch_cn_quote(code)
    elif market == "hk":
        result = fetch_hk_quote(code)
    elif market == "us":
        result = fetch_us_quote(code)
    else:
        return jsonify({"error": "invalid market"}), 400
    if result is None:
        return jsonify({"error": "stock not found"}), 404
    if isinstance(result, dict) and "error" in result:
        return jsonify(result), 500
    return jsonify(result)


@app.route("/api/stock/kline")
def stock_kline():
    code = request.args.get("code", "").strip()
    market = request.args.get("market", "cn")
    limit = int(request.args.get("limit", 60))
    try:
        if market in ("cn", "hk"):
            prefix_map = {"cn": ("sh" if code.startswith(("6", "5", "1")) else "sz", code),
                          "hk": ("hk", code.zfill(5))}
            prefix, c = prefix_map.get(market, ("sh", code))
            url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{c},day,,,{limit},qfq"
            data = fetch_json(url, 15)
            if isinstance(data, dict) and "error" in data:
                return jsonify({"klines": []})
            klines_raw = data.get("data", {}).get(f"{prefix}{c}", {}).get("qfqday", [])
            klines = []
            for k in klines_raw:
                if len(k) >= 6:
                    klines.append({
                        "date": k[0], "open": float(k[1]), "close": float(k[2]),
                        "high": float(k[3]), "low": float(k[4]), "volume": int(float(k[5])) * 100
                    })
            return jsonify({"klines": klines})
        else:
            # US stocks - try yfinance
            try:
                import yfinance as yf
                df = yf.Ticker(code).history(period=f"{limit}d")
                klines = []
                for idx, r in df.iterrows():
                    klines.append({
                        "date": str(idx)[:10],
                        "open": float(r["Open"]), "close": float(r["Close"]),
                        "high": float(r["High"]), "low": float(r["Low"]),
                        "volume": int(r["Volume"])
                    })
                return jsonify({"klines": klines})
            except ImportError:
                return jsonify({"klines": [], "error": "yfinance not available for US klines"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stock/ai-analysis", methods=["POST"])
def stock_ai_analysis():
    data = request.json or {}
    code = data.get("code", "")
    name = data.get("name", "")
    market = data.get("market", "cn")
    aspect = data.get("aspect", "comprehensive")

    if not code:
        return jsonify({"error": "no stock code"}), 400

    try:
        quote = None
        klines = None
        if market == "cn":
            quote = fetch_cn_quote(code)
            if quote and "error" not in quote:
                name = quote.get("name", name)
            klines = fetch_cn_kline(code, 30)
        elif market == "hk":
            quote = fetch_hk_quote(code)
            if quote and "error" not in quote:
                name = quote.get("name", name)
            # Use same kline fetch (supports hk in /api/stock/kline)
            try:
                kline_resp = json.loads(requests.get(
                    f"http://127.0.0.1:5003/api/stock/kline?code={code}&market=hk&limit=30",
                    timeout=10
                ).text)
                klines = kline_resp.get("klines", [])
            except Exception:
                klines = []
        elif market == "us":
            quote = fetch_us_quote(code)
            if quote and "error" not in quote:
                name = quote.get("name", name)
            # Try yfinance for US klines
            try:
                import yfinance as yf
                df = yf.Ticker(code).history(period="30d")
                klines = []
                for idx, r in df.iterrows():
                    klines.append({
                        "date": str(idx)[:10],
                        "open": float(r["Open"]), "close": float(r["Close"]),
                        "high": float(r["High"]), "low": float(r["Low"]),
                        "volume": int(r["Volume"])
                    })
            except Exception:
                klines = []
        name = name or code

        aspect_prompts = {
            "comprehensive": f"Provide a comprehensive investment analysis for {name} ({code}). Include: 1) current valuation 2) recent price trend 3) key risks 4) short-term outlook. Be specific with numbers.",
            "technical": f"Provide a technical analysis for {name} ({code}). Analyze: 1) support/resistance levels 2) volume patterns 3) momentum indicators 4) entry/exit signals.",
            "fundamental": f"Provide a fundamental analysis for {name} ({code}). Analyze: 1) financial health 2) profitability trends 3) growth prospects 4) valuation comparison with peers.",
            "news": f"Analyze recent news and events affecting {name} ({code}). Focus on: 1) key catalysts 2) market sentiment 3) sector trends 4) potential impact on price.",
            "valuation": f"Provide a detailed valuation analysis for {name} ({code}). Include: 1) PE/PB/PS comparison with industry average 2) DCF or relative valuation assessment 3) PEG and EV/EBITDA analysis 4) Is the stock overvalued or undervalued? Give a fair value range.",
            "sector": f"Provide a sector/industry comparison analysis for {name} ({code}). Include: 1) Compare valuation metrics (PE/PB) with top 3 peers 2) Market share and competitive position 3) Sector trend and where this stock stands 4) Which peer is most attractive now?",
            "risk": f"Provide a risk assessment for {name} ({code}). Include: 1) Financial risk (debt ratio, liquidity, cash flow) 2) Market risk (volatility, beta, drawdown) 3) Industry/regulatory risk 4) Overall risk rating (Low/Medium/High) with explanation. Suggest risk management strategies."
        }

        ctx = []
        if quote and "error" not in quote:
            ctx.append(f"Current price: {quote['price']}, Change: {quote['change_pct']}%, PE: {quote.get('pe', 'N/A')}")
        if klines:
            recent = klines[-5:]
            klines_text = "\n".join([f"{k['date']}: O{k['open']} H{k['high']} L{k['low']} C{k['close']} V{k['volume']}" for k in recent])
            ctx.append(f"Recent 5 days K-line:\n{klines_text}")

        system_msg = "You are a professional Chinese financial analyst. Write in Chinese. Be concise and specific. Use numbers and data. Format with clear sections. Under 800 words."
        user_msg = aspect_prompts.get(aspect, aspect_prompts["comprehensive"])
        if ctx:
            user_msg += f"\n\nCurrent market data:\n" + "\n".join(ctx)

        analysis = deepseek_chat([
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg}
        ], max_tokens=2000)

        # 保存分析历史（如果已登录）
        uid = current_user_id()
        if uid:
            auth_db.save_analysis(uid, code, name, market, aspect, analysis)

        return jsonify({
            "code": code, "name": name, "aspect": aspect,
            "analysis": analysis,
            "quote": quote if quote and "error" not in quote else None,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/stock/generate-report", methods=["POST"])
def generate_report():
    data = request.json or {}
    code = data.get("code", "")
    name = data.get("name", "")
    analysis = data.get("analysis", "")
    if not code or not analysis:
        return jsonify({"error": "missing data"}), 400
    try:
        from fpdf import FPDF
    except ImportError:
        return jsonify({"error": "PDF generation requires fpdf2 package"}), 500
    try:
        pdf = FPDF()
        pdf.add_page()
        pdf.add_font("SimSun", "", "C:/Windows/Fonts/simsun.ttc", uni=True)
        pdf.add_font("SimHei", "", "C:/Windows/Fonts/simhei.ttf", uni=True)
        pdf.set_font("SimHei", "", 18)
        pdf.cell(0, 12, f"AI Stock Analysis Report", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("SimSun", "", 11)
        pdf.cell(0, 8, f"{name} ({code})  |  {datetime.now().strftime('%Y-%m-%d')}", align="C", new_x="LMARGIN", new_y="NEXT")
        pdf.line(3, pdf.get_y(), 207, pdf.get_y())
        pdf.ln(5)
        pdf.set_font("SimSun", "", 10)
        for line in analysis.split("\n"):
            line = line.strip()
            if not line:
                pdf.ln(2)
                continue
            if line.startswith("#"):
                pdf.set_font("SimHei", "", 12)
                pdf.cell(0, 8, line.lstrip("#").strip(), new_x="LMARGIN", new_y="NEXT")
                pdf.set_font("SimSun", "", 10)
            elif line.startswith("-") or line.startswith("*"):
                pdf.cell(0, 6, f"  {line}", new_x="LMARGIN", new_y="NEXT")
            else:
                pdf.multi_cell(0, 6, line)
        buf = BytesIO()
        pdf.output(buf)
        buf.seek(0)
        return send_file(buf, mimetype="application/pdf", as_attachment=True,
                           download_name=f"stock_report_{code}_{datetime.now().strftime('%Y%m%d')}.pdf")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================================

# =========================================================
# =========================================================
# 大盘指数 API
# =========================================================
@app.route("/api/market/indices")
def market_indices():
    """获取主要大盘指数实时数据"""
    # 指数代码：上证(sh000001)、深证成指(sz399001)、创业板(sz399006)
    #           恒生(hk800000)、标普500(us.INX)、纳斯达克(us.IXIC)、道琼斯(us.DJI)
    codes = "sh000001,sz399001,sz399006,hk800000,us.INX,us.IXIC,us.DJI"
    url = f"https://qt.gtimg.cn/q={codes}"
    try:
        text = _fetch_tencent_raw(url)
        if not text:
            return jsonify({"indices": []})
        results = []
        for m in re.finditer(r'v_([^=]+)="([^"]*)"', text):
            code = m.group(1)
            fields = m.group(2).split("~")
            if len(fields) < 35:
                continue
            try:
                price      = float(fields[3]) if fields[3] else 0.0
                prev_close = float(fields[4]) if fields[4] else price
                change     = price - prev_close
                change_pct = (change / prev_close * 100) if prev_close else 0.0
                name = fields[1] if len(fields) > 1 and fields[1] else code
                results.append({
                    "code":       code,
                    "name":       name,
                    "price":      round(price, 2),
                    "change":     round(change, 2),
                    "change_pct": round(change_pct, 2),
                })
            except (ValueError, IndexError):
                continue
        return jsonify({"indices": results})
    except Exception as e:
        return jsonify({"error": str(e), "indices": []}), 500


# ==========================================================
# 全球指数扩展 API (新增亚太/欧洲/商品/加密货币)
# ==========================================================
@app.route("/api/market/global-indices")
def global_indices():
    """获取扩展的全球大盘指数，含商品和加密货币"""
    results = {"asia": [], "europe": [], "commodities": [], "crypto": [], "us": []}

    # --- 亚太指数 ---
    asia_codes = "hkHIS,sh000688,jpN225,krKOSPI,inNIFTY"
    # 港股恒生、上证科创板50、日经225、韩国KOSPI、印度NIFTY
    url_asia = f"https://qt.gtimg.cn/q={asia_codes}"
    from urllib.parse import quote
    try:
        text = _fetch_tencent_raw(url_asia)
        if text:
            for m in re.finditer(r'v_([^=]+)="([^"]*)"', text):
                fields = m.group(2).split("~")
                if len(fields) < 35:
                    continue
                try:
                    price = float(fields[3]) if fields[3] else 0.0
                    prev_close = float(fields[4]) if fields[4] else price
                    change = price - prev_close
                    change_pct = (change / prev_close * 100) if prev_close else 0.0
                    name = fields[1] if fields[1] else m.group(1)
                    code = m.group(1)
                    # Map names
                    name_map = {
                        "hkHIS": "恒生指数", "sh000688": "科创50",
                        "jpN225": "日经225", "krKOSPI": "韩国KOSPI", "inNIFTY": "印度NIFTY 50"
                    }
                    results["asia"].append({
                        "code": code, "name": name_map.get(code, name),
                        "price": round(price, 2), "change": round(change, 2),
                        "change_pct": round(change_pct, 2),
                    })
                except (ValueError, IndexError):
                    continue
    except Exception:
        pass

    # --- 欧洲指数 (via yfinance or fallback) ---
    # FTSE100, DAX, CAC40 from Tencent
    eu_codes = "ukFTSE,deDAX,frCAC"
    try:
        text = _fetch_tencent_raw(f"https://qt.gtimg.cn/q={eu_codes}")
        if text:
            eu_names = {"ukFTSE": "英国富时100", "deDAX": "德国DAX", "frCAC": "法国CAC40"}
            for m in re.finditer(r'v_([^=]+)="([^"]*)"', text):
                fields = m.group(2).split("~")
                if len(fields) < 35:
                    continue
                try:
                    price = float(fields[3]) if fields[3] else 0.0
                    prev_close = float(fields[4]) if fields[4] else price
                    change = price - prev_close
                    change_pct = (change / prev_close * 100) if prev_close else 0.0
                    code = m.group(1)
                    results["europe"].append({
                        "code": code, "name": eu_names.get(code, fields[1]),
                        "price": round(price, 2), "change": round(change, 2),
                        "change_pct": round(change_pct, 2),
                    })
                except (ValueError, IndexError):
                    continue
    except Exception:
        pass

    # --- 商品 (黄金/原油/白银) ---
    # Using Tencent futures API or yfinance
    try:
        try:
            import yfinance as yf
            for sym, name in [("GC=F", "黄金期货"), ("CL=F", "WTI原油"), ("SI=F", "白银期货")]:
                try:
                    t = yf.Ticker(sym)
                    info = t.info
                    price = info.get("regularMarketPrice") or info.get("previousClose") or 0
                    prev = info.get("previousClose") or price
                    if price > 0:
                        chg_pct = ((price - prev) / prev * 100) if prev else 0
                        results["commodities"].append({
                            "code": sym, "name": name,
                            "price": round(price, 2), "change": round(price - prev, 2),
                            "change_pct": round(chg_pct, 2),
                        })
                except Exception:
                    pass
        except ImportError:
            pass
    except Exception:
        pass

    # --- 加密货币 (BTC/ETH) ---
    try:
        for sym, name in [("BTC-USD", "比特币"), ("ETH-USD", "以太坊")]:
            try:
                t = yf.Ticker(sym) if "yf" in dir() else None
                if t:
                    info = t.info
                    price = info.get("regularMarketPrice") or 0
                    prev = info.get("previousClose") or price
                    if price > 0:
                        chg_pct = ((price - prev) / prev * 100) if prev else 0
                        results["crypto"].append({
                            "code": sym, "name": name,
                            "price": round(price, 2), "change": round(price - prev, 2),
                            "change_pct": round(chg_pct, 2),
                        })
            except Exception:
                pass
    except Exception:
        pass

    return jsonify(results)


# ==========================================================
# 分时图数据 (Intraday)
# ==========================================================
@app.route("/api/stock/intraday")
def stock_intraday():
    """获取分时图数据"""
    code = request.args.get("code", "").strip()
    market = request.args.get("market", "cn").strip()
    if not code:
        return jsonify({"error": "no code"}), 400

    try:
        if market == "cn":
            prefix = "sh" if code.startswith(("6", "5", "1")) else "sz"
            url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data&code={prefix}{code}"
            text = _fetch_tencent_raw(url)
            if not text:
                return jsonify({"points": [], "error": "fetch failed"})

            # Parse minute data
            match = re.search(r'min_data="([^"]*)"', text)
            if not match:
                return jsonify({"points": []})

            raw = match.group(1)
            lines = raw.strip().split("\\n")
            points = []
            prev_close = None
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        t = parts[0]
                        price = float(parts[1])
                        vol = float(parts[3]) if len(parts) > 3 else 0
                        points.append({"time": t, "price": price, "volume": vol})
                    except (ValueError, IndexError):
                        continue
            return jsonify({"points": points})
        elif market == "hk":
            code_fill = code.zfill(5)
            url = f"https://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data&code=hk{code_fill}"
            text = _fetch_tencent_raw(url)
            if not text:
                return jsonify({"points": [], "error": "fetch failed"})
            match = re.search(r'min_data="([^"]*)"', text)
            if not match:
                return jsonify({"points": []})
            raw = match.group(1)
            lines = raw.strip().split("\\n")
            points = []
            for line in lines:
                parts = line.strip().split()
                if len(parts) >= 2:
                    try:
                        points.append({"time": parts[0], "price": float(parts[1])})
                    except (ValueError, IndexError):
                        continue
            return jsonify({"points": points})
        else:
            return jsonify({"points": [], "error": "US intraday not supported yet"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================================
# 技术指标计算
# ==========================================================
def calc_ema(data, period):
    """计算指数移动平均"""
    if len(data) < period:
        return [None] * len(data)
    k = 2 / (period + 1)
    ema = [sum(data[:period]) / period] * (period - 1)
    ema.append(sum(data[:period]) / period)
    for i in range(period, len(data)):
        ema.append(data[i] * k + ema[-1] * (1 - k))
    return [None] * (period - 1) + ema[period - 1:]


def calc_macd(closes):
    """计算 MACD (12, 26, 9)"""
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    dif = [a - b if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
    # DEA = 9-day EMA of DIF
    valid_dif = [x for x in dif if x is not None]
    if len(valid_dif) < 9:
        return {"dif": dif, "dea": [None] * len(closes), "histogram": [None] * len(closes)}
    dea_vals = calc_ema(valid_dif, 9)
    dea = [None] * (len(dif) - len(dea_vals)) + dea_vals
    histogram = [(d - e) * 2 if d is not None and e is not None else None for d, e in zip(dif, dea)]
    return {"dif": dif, "dea": dea, "histogram": histogram}


def calc_rsi(closes, period=14):
    """计算 RSI"""
    if len(closes) < period + 1:
        return [None] * len(closes)
    gains, losses = [], []
    for i in range(1, len(closes)):
        chg = closes[i] - closes[i - 1]
        gains.append(chg if chg > 0 else 0)
        losses.append(-chg if chg < 0 else 0)

    rsi = [None] * (period + 1)
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
    rsi.append(100 - 100 / (1 + rs) if avg_loss > 0 else 100)

    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = avg_gain / avg_loss if avg_loss > 0 else float("inf")
        rsi.append(100 - 100 / (1 + rs) if avg_loss > 0 else 100 if avg_gain > 0 else 50)
    return rsi


def calc_bollinger(closes, period=20, std_dev=2):
    """计算布林带"""
    if len(closes) < period:
        return {"upper": [None] * len(closes), "middle": [None] * len(closes), "lower": [None] * len(closes)}
    import statistics
    upper, middle, lower = [], [], []
    for i in range(len(closes)):
        if i < period - 1:
            upper.append(None)
            middle.append(None)
            lower.append(None)
        else:
            window = closes[i - period + 1 : i + 1]
            ma = sum(window) / period
            std = statistics.stdev(window) if len(window) > 1 else 0
            middle.append(ma)
            upper.append(ma + std_dev * std)
            lower.append(ma - std_dev * std)
    return {"upper": upper, "middle": middle, "lower": lower}


def calc_kdj(highs, lows, closes, period=9):
    """计算 KDJ"""
    n = len(closes)
    if n < period:
        return {"k": [None] * n, "d": [None] * n, "j": [None] * n}
    k_vals, d_vals, j_vals = [50] * (period - 1), [50] * (period - 1), [50] * (period - 1)
    prev_k, prev_d = 50, 50
    for i in range(period - 1, n):
        high_max = max(highs[i - period + 1 : i + 1])
        low_min = min(lows[i - period + 1 : i + 1])
        rsv = (closes[i] - low_min) / (high_max - low_min) * 100 if high_max != low_min else 50
        k = 2 / 3 * prev_k + 1 / 3 * rsv
        d = 2 / 3 * prev_d + 1 / 3 * k
        j = 3 * k - 2 * d
        k_vals.append(round(k, 2))
        d_vals.append(round(d, 2))
        j_vals.append(round(j, 2))
        prev_k, prev_d = k, d
    return {"k": k_vals, "d": d_vals, "j": j_vals}


@app.route("/api/stock/indicators")
def stock_indicators():
    """获取技术指标数据"""
    code = request.args.get("code", "").strip()
    market = request.args.get("market", "cn").strip()
    limit = int(request.args.get("limit", 120))

    if not code:
        return jsonify({"error": "no code"}), 400

    # Fetch kline data (reuse existing logic)
    klines = []
    try:
        if market in ("cn", "hk"):
            prefix_map = {"cn": ("sh" if code.startswith(("6", "5", "1")) else "sz", code),
                          "hk": ("hk", code.zfill(5))}
            prefix, c = prefix_map.get(market, ("sh", code))
            url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{c},day,,,{limit},qfq"
            data = fetch_json(url, 15)
            if not isinstance(data, dict) or "error" not in data:
                klines_raw = data.get("data", {}).get(f"{prefix}{c}", {}).get("qfqday", [])
                for k in klines_raw:
                    if len(k) >= 6:
                        klines.append({
                            "date": k[0], "open": float(k[1]), "close": float(k[2]),
                            "high": float(k[3]), "low": float(k[4]), "volume": int(float(k[5])) * 100
                        })
        else:
            try:
                import yfinance as yf
                df = yf.Ticker(code).history(period=f"{limit}d")
                for idx, r in df.iterrows():
                    klines.append({
                        "date": str(idx)[:10], "open": float(r["Open"]), "close": float(r["Close"]),
                        "high": float(r["High"]), "low": float(r["Low"]), "volume": int(r["Volume"])
                    })
            except Exception:
                pass
    except Exception:
        return jsonify({"error": "failed to fetch kline data"}), 500

    if not klines or len(klines) < 20:
        return jsonify({"error": "insufficient data", "indicators": {}})

    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    dates = [k["date"] for k in klines]
    volumes = [k["volume"] for k in klines]

    # Calculate all indicators
    ma5 = calc_ema(closes, 5)
    ma10 = calc_ema(closes, 10)
    ma20 = calc_ema(closes, 20)
    ma60 = calc_ema(closes, 60)
    macd_data = calc_macd(closes)
    rsi = calc_rsi(closes, 14)
    boll = calc_bollinger(closes, 20, 2)
    kdj = calc_kdj(highs, lows, closes, 9)

    return jsonify({
        "dates": dates,
        "klines": klines,
        "volumes": volumes,
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "macd": macd_data,
        "rsi": rsi,
        "bollinger": boll,
        "kdj": kdj,
    })


# ==========================================================
# 北向资金流向 (North-bound Capital Flow)
# ==========================================================
@app.route("/api/market/north-bound")
def north_bound_flow():
    """获取沪深港通北向资金流向"""
    try:
        # Eastmoney API for north-bound capital flow
        url = "https://push2.eastmoney.com/api/qt/kamt.kline/get?fields1=f1,f2,f3,f4&fields2=f51,f52,f53,f54&klt=101&lmt=30"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = resp.json()
        flows = []
        if data.get("data") and data["data"].get("klines"):
            for line in data["data"]["klines"]:
                parts = line.split(",")
                if len(parts) >= 4:
                    flows.append({
                        "date": parts[0],
                        "net_flow": float(parts[1]) if parts[1] != "-" else 0,
                    })
        return jsonify({"flows": flows, "updated": datetime.now().strftime("%H:%M:%S")})
    except Exception as e:
        return jsonify({"error": str(e), "flows": []})


# ==========================================================
# 板块热力图 (Sector Heatmap)
# ==========================================================
@app.route("/api/market/sectors")
def sector_heatmap():
    """获取行业板块涨跌数据"""
    try:
        # Eastmoney sector API
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=60&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:2&fields=f2,f3,f4,f12,f14"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = resp.json()
        sectors = []
        if data.get("data") and data["data"].get("diff"):
            for item in data["data"]["diff"]:
                sectors.append({
                    "code": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "price": item.get("f2", 0),
                    "change_pct": item.get("f3", 0),
                    "change": item.get("f4", 0),
                })
        return jsonify({"sectors": sectors})
    except Exception as e:
        return jsonify({"error": str(e), "sectors": []})


@app.route("/api/market/concepts")
def concept_heatmap():
    """获取概念板块涨跌数据"""
    try:
        url = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=60&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:3&fields=f2,f3,f4,f12,f14"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = resp.json()
        sectors = []
        if data.get("data") and data["data"].get("diff"):
            for item in data["data"]["diff"]:
                sectors.append({
                    "code": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "change_pct": item.get("f3", 0),
                })
        return jsonify({"sectors": sectors})
    except Exception as e:
        return jsonify({"error": str(e), "sectors": []})


# ==========================================================
# 龙虎榜 (Dragon-Tiger Board)
# ==========================================================
@app.route("/api/market/dragon-tiger")
def dragon_tiger():
    """获取每日龙虎榜数据"""
    try:
        today = datetime.now().strftime("%Y%m%d")
        url = f"https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=50&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:90+t:4&fields=f2,f3,f4,f12,f14,f62,f184,f66,f72,f75,f78,f81,f84,f87,f204,f205,f206"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        data = resp.json()
        stocks = []
        if data.get("data") and data["data"].get("diff"):
            for item in data["data"]["diff"]:
                stocks.append({
                    "code": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "change_pct": item.get("f3", 0),
                    "price": item.get("f2", 0),
                    "net_buy": item.get("f62", 0),  # 龙虎榜净买额
                })
        return jsonify({"stocks": stocks, "date": datetime.now().strftime("%Y-%m-%d")})
    except Exception as e:
        return jsonify({"error": str(e), "stocks": []})


# ==========================================================
# 个股财务数据 (Financial Data)
# ==========================================================
@app.route("/api/stock/financials")
def stock_financials():
    """获取个股财务数据"""
    code = request.args.get("code", "").strip()
    market = request.args.get("market", "cn").strip()
    if not code:
        return jsonify({"error": "no code"}), 400

    result = {"pe": None, "pb": None, "roe": None, "revenue": None, "net_profit": None,
              "total_mv": None, "eps": None, "bps": None, "debt_ratio": None}

    try:
        if market == "cn":
            # Eastmoney financial data
            prefix = "1" if code.startswith("6") else "0"
            secid = f"{prefix}.{code}"
            url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={secid}&fields=f9,f20,f23,f37,f38,f39,f40,f41,f43,f44,f45,f46,f55,f57,f58,f115,f162,f167,f170,f173"
            resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            data = resp.json()
            if data.get("data"):
                d = data["data"]
                result = {
                    "pe": d.get("f9"),           # 市盈率(动态)
                    "pb": d.get("f23"),          # 市净率
                    "roe": d.get("f173"),        # ROE
                    "revenue": d.get("f44"),     # 营业总收入
                    "net_profit": d.get("f46"),  # 净利润
                    "total_mv": d.get("f20"),    # 总市值
                    "eps": d.get("f43"),         # 每股收益
                    "bps": d.get("f41"),         # 每股净资产
                    "debt_ratio": d.get("f55"),  # 资产负债率
                    "gross_margin": d.get("f38"), # 毛利率
                    "net_margin": d.get("f39"),  # 净利率
                }
        elif market == "us":
            try:
                import yfinance as yf
                t = yf.Ticker(code)
                info = t.info
                result = {
                    "pe": info.get("trailingPE"),
                    "pb": info.get("priceToBook"),
                    "roe": info.get("returnOnEquity"),
                    "revenue": info.get("totalRevenue"),
                    "net_profit": info.get("netIncomeToCommon"),
                    "total_mv": info.get("marketCap"),
                    "eps": info.get("trailingEps"),
                    "bps": info.get("bookValue"),
                    "debt_ratio": info.get("debtToEquity"),
                    "gross_margin": info.get("grossMargins"),
                    "net_margin": info.get("profitMargins"),
                }
            except Exception:
                pass
    except Exception:
        pass

    return jsonify({"financials": result})


# ==========================================================
# 个股对比 (Stock Comparison)
# ==========================================================
@app.route("/api/stock/compare", methods=["POST"])
def stock_compare():
    """对比多只股票"""
    data = request.json or {}
    stocks = data.get("stocks", [])  # [{"code": "600519", "market": "cn"}, ...]
    if not stocks or len(stocks) < 2:
        return jsonify({"error": "至少需要2只股票进行对比"}), 400
    if len(stocks) > 5:
        return jsonify({"error": "最多对比5只股票"}), 400

    results = []
    for s in stocks:
        code = s.get("code", "")
        market = s.get("market", "cn")
        try:
            if market == "cn":
                q = fetch_cn_quote(code)
            elif market == "hk":
                q = fetch_hk_quote(code)
            elif market == "us":
                q = fetch_us_quote(code)
            else:
                continue
            if q and "error" not in q:
                results.append({
                    "code": code, "name": q.get("name", code), "market": market,
                    "price": q.get("price", 0), "change_pct": q.get("change_pct", 0),
                    "pe": q.get("pe"), "market_cap": q.get("market_cap"),
                    "volume": q.get("volume", 0),
                })
        except Exception:
            continue

    return jsonify({"comparison": results})


# ==========================================================
# 智能选股 (Stock Screener)
# ==========================================================
@app.route("/api/stock/screener", methods=["POST"])
def stock_screener():
    """多条件选股"""
    data = request.json or {}
    # 筛选条件: pe_max, pe_min, market_cap_min, change_pct_min, change_pct_max
    filters = {
        "pe_max": data.get("pe_max"),
        "pe_min": data.get("pe_min"),
        "market_cap_min": data.get("market_cap_min"),
        "change_pct_min": data.get("change_pct_min"),
        "change_pct_max": data.get("change_pct_max"),
        "roe_min": data.get("roe_min"),
    }

    try:
        # Eastmoney stock list with filters
        # 沪深A股, filtered by PE, market cap
        url = ("https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=30&po=1&np=1&fltt=2&invt=2&fid=f3"
               "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
               "&fields=f2,f3,f4,f9,f12,f14,f15,f16,f17,f18,f20,f21,f23,f173")
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        result = resp.json()
        stocks = []
        if result.get("data") and result["data"].get("diff"):
            for item in result["data"]["diff"]:
                pe = item.get("f9")
                price = item.get("f2", 0)
                change_pct = item.get("f3", 0)
                market_cap = item.get("f20", 0)

                # Apply filters
                if filters["pe_max"] and (pe is None or pe > filters["pe_max"]):
                    continue
                if filters["pe_min"] and (pe is None or pe < filters["pe_min"]):
                    continue
                if filters["market_cap_min"] and market_cap < filters["market_cap_min"] * 1e8:
                    continue
                if filters["change_pct_min"] is not None and change_pct < filters["change_pct_min"]:
                    continue
                if filters["change_pct_max"] is not None and change_pct > filters["change_pct_max"]:
                    continue

                stocks.append({
                    "code": item.get("f12", ""),
                    "name": item.get("f14", ""),
                    "price": price,
                    "change_pct": change_pct,
                    "pe": pe,
                    "market_cap": market_cap,
                })
        return jsonify({"stocks": stocks, "total": len(stocks)})
    except Exception as e:
        return jsonify({"error": str(e), "stocks": []})


# ==========================================================
# K线数据增强 (含成交量、完整OHLCV)
# ==========================================================
@app.route("/api/stock/kline-full")
def stock_kline_full():
    """获取完整K线数据 (OHLCV + 分时图点)"""
    code = request.args.get("code", "").strip()
    market = request.args.get("market", "cn")
    limit = int(request.args.get("limit", 120))

    if not code:
        return jsonify({"error": "no code"}), 400

    try:
        if market in ("cn", "hk"):
            prefix_map = {"cn": ("sh" if code.startswith(("6", "5", "1")) else "sz", code),
                          "hk": ("hk", code.zfill(5))}
            prefix, c = prefix_map.get(market, ("sh", code))
            url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?param={prefix}{c},day,,,{limit},qfq"
            data = fetch_json(url, 15)
            if isinstance(data, dict) and "error" in data:
                return jsonify({"klines": []})
            klines_raw = data.get("data", {}).get(f"{prefix}{c}", {}).get("qfqday", [])
            klines = []
            for k in klines_raw:
                if len(k) >= 6:
                    klines.append({
                        "date": k[0], "open": float(k[1]), "close": float(k[2]),
                        "high": float(k[3]), "low": float(k[4]), "volume": int(float(k[5])) * 100
                    })
            return jsonify({"klines": klines})
        else:
            try:
                import yfinance as yf
                df = yf.Ticker(code).history(period=f"{limit}d")
                klines = []
                for idx, r in df.iterrows():
                    klines.append({
                        "date": str(idx)[:10], "open": float(r["Open"]), "close": float(r["Close"]),
                        "high": float(r["High"]), "low": float(r["Low"]), "volume": int(r["Volume"])
                    })
                return jsonify({"klines": klines})
            except ImportError:
                return jsonify({"klines": [], "error": "yfinance not available"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ==========================================================
# 涨跌幅排行榜 (Top Movers)
# ==========================================================
@app.route("/api/market/movers")
def top_movers():
    """获取涨跌幅排行榜"""
    try:
        # A股涨幅榜
        url_up = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=15&po=1&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f2,f3,f4,f12,f14,f20,f9"
        url_down = "https://push2.eastmoney.com/api/qt/clist/get?pn=1&pz=15&po=0&np=1&fltt=2&invt=2&fid=f3&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23&fields=f2,f3,f4,f12,f14,f20,f9"
        h = {"User-Agent": "Mozilla/5.0"}
        up_data = requests.get(url_up, headers=h, timeout=10).json()
        down_data = requests.get(url_down, headers=h, timeout=10).json()

        def parse_mover(item):
            return {
                "code": item.get("f12", ""),
                "name": item.get("f14", ""),
                "price": item.get("f2", 0),
                "change_pct": item.get("f3", 0),
                "market_cap": item.get("f20", 0),
                "pe": item.get("f9"),
            }

        gainers = [parse_mover(i) for i in up_data.get("data", {}).get("diff", [])[:15]]
        losers = [parse_mover(i) for i in down_data.get("data", {}).get("diff", [])[:15]]
        return jsonify({"gainers": gainers, "losers": losers,
                        "updated": datetime.now().strftime("%H:%M:%S")})
    except Exception as e:
        return jsonify({"error": str(e), "gainers": [], "losers": []})


# ==========================================================
# 财经新闻 (Financial News)
# ==========================================================
@app.route("/api/news/finance")
def finance_news():
    """获取财经新闻"""
    try:
        # Eastmoney news headlines
        url = "https://push2.eastmoney.com/api/qt/ulist.np/get?fltt=2&secids=&fields=f3,f4,f12,f14,f17,f18&np=1&pz=15&ut=bd1d9ddb04089700cf9c27f6f7426281&cb=jQuery"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        # Simple approach: use a known news API
        news_url = "https://newsapi.org/v2/top-headlines?category=business&language=en&pageSize=20&apiKey=demo"
        try:
            nresp = requests.get(news_url, timeout=10)
            ndata = nresp.json()
            articles = []
            for a in ndata.get("articles", [])[:15]:
                articles.append({
                    "title": a.get("title", ""),
                    "source": a.get("source", {}).get("name", ""),
                    "url": a.get("url", ""),
                    "published": a.get("publishedAt", ""),
                    "description": a.get("description", "")[:150] if a.get("description") else "",
                })
            if articles:
                return jsonify({"news": articles, "updated": datetime.now().strftime("%H:%M")})
        except Exception:
            pass

        # Fallback: return curated financial news
        return jsonify({
            "news": [
                {"title": "Markets await Fed decision on interest rates", "source": "Reuters", "published": datetime.now().strftime("%Y-%m-%dT%H:%M:00Z")},
                {"title": "Tech stocks lead global rally amid AI optimism", "source": "Bloomberg", "published": datetime.now().strftime("%Y-%m-%dT%H:%M:00Z")},
                {"title": "Oil prices stabilize after recent volatility", "source": "CNBC", "published": datetime.now().strftime("%Y-%m-%dT%H:%M:00Z")},
            ],
            "updated": datetime.now().strftime("%H:%M"),
            "note": "Using demo/sample data. Configure NEWS_API_KEY for live news."
        })
    except Exception as e:
        return jsonify({"error": str(e), "news": []})


# ==========================================================
# 经济日历 (Economic Calendar)
# ==========================================================
@app.route("/api/market/calendar")
def economic_calendar():
    """经济事件日历"""
    today = datetime.now()
    events = []
    # Generate upcoming events for next 7 days
    for i in range(7):
        d = today + timedelta(days=i)
        day_events = []
        if d.weekday() == 0:  # Monday
            day_events = [
                {"time": "09:30", "event": "China Manufacturing PMI", "importance": "high", "country": "CN"},
                {"time": "10:00", "event": "Eurozone Industrial Production", "importance": "medium", "country": "EU"},
            ]
        elif d.weekday() == 2:  # Wednesday
            day_events = [
                {"time": "14:00", "event": "US Fed Interest Rate Decision", "importance": "high", "country": "US"},
                {"time": "16:30", "event": "US Crude Oil Inventories", "importance": "medium", "country": "US"},
            ]
        elif d.weekday() == 3:  # Thursday
            day_events = [
                {"time": "08:00", "event": "UK GDP (QoQ)", "importance": "high", "country": "UK"},
                {"time": "20:30", "event": "US Initial Jobless Claims", "importance": "medium", "country": "US"},
            ]
        elif d.weekday() == 4:  # Friday
            day_events = [
                {"time": "09:30", "event": "China CPI (YoY)", "importance": "high", "country": "CN"},
                {"time": "14:30", "event": "US Nonfarm Payrolls", "importance": "high", "country": "US"},
            ]
        else:
            day_events = [
                {"time": "10:00", "event": "Consumer Confidence Index", "importance": "low", "country": "EU"},
            ]
        events.append({
            "date": d.strftime("%Y-%m-%d"),
            "day": d.strftime("%A"),
            "events": day_events,
        })
    return jsonify({"calendar": events, "note": "Sample calendar. Live data requires premium API key."})


@app.route("/api/media/generate", methods=["POST"])
def media_generate():
    data = request.json or {}
    prompt = data.get("prompt", "")
    engine = data.get("engine", "deepseek")
    if not prompt:
        return jsonify({"error": "no prompt"}), 400
    try:
        if engine == "claude" and CLAUDE_API_KEY:
            resp = requests.post("https://api.anthropic.com/v1/messages",
                headers={"x-api-key": CLAUDE_API_KEY, "anthropic-version": "2023-06-01",
                           "Content-Type": "application/json"},
                json={"model": "claude-sonnet-4-20250514", "max_tokens": 2000,
                       "messages": [{"role": "user", "content": prompt}]},
                timeout=60)
            if resp.status_code == 200:
                return jsonify({"result": resp.json()["content"][0]["text"], "engine": "claude"})
        result = deepseek_chat([
            {"role": "system", "content": "You are a professional Chinese content creator. Write in Chinese."},
            {"role": "user", "content": prompt}
        ], max_tokens=2000)
        return jsonify({"result": result, "engine": "deepseek"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/media/hot-topics")
def hot_topics():
    topics = [
        {"tag": "AI工具", "hot": 98, "desc": "AI工具推荐与评测持续火爆"},
        {"tag": "副业赚钱", "hot": 95, "desc": "经济下行期副业内容需求大"},
        {"tag": "股票投资", "hot": 92, "desc": "震荡市中股民关注度高"},
        {"tag": "人工智能", "hot": 90, "desc": "AI技术科普类内容长盛不衰"},
        {"tag": "自媒体运营", "hot": 88, "desc": "新人入局需求持续增长"},
        {"tag": "职场技能", "hot": 85, "desc": "技能提升类内容稳定流量"},
        {"tag": "数码评测", "hot": 82, "desc": "新品发布带动评测热度"},
        {"tag": "个人成长", "hot": 80, "desc": "读书/学习/效率类内容长青"},
        {"tag": "财经解读", "hot": 78, "desc": "宏观政策解读类流量稳定"},
        {"tag": "创业经验", "hot": 75, "desc": "真实创业故事类内容稀缺"}
    ]
    return jsonify({"topics": topics})


# ==========================================================
# MODULE 3: SERVICES
# ==========================================================
@app.route("/api/services/inquiry", methods=["POST"])
def service_inquiry():
    data = request.json or {}
    service_type = data.get("type", "")
    description = data.get("description", "")
    contact = data.get("contact", "")
    inquiries_path = "output/inquiries.json"
    inquiries = []
    if os.path.exists(inquiries_path):
        inquiries = json.load(open(inquiries_path, encoding="utf-8"))
    inquiries.append({
        "id": len(inquiries) + 1,
        "type": service_type, "description": description, "contact": contact,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })
    json.dump(inquiries, open(inquiries_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return jsonify({"success": True, "message": "Inquiry received. We will contact you within 24 hours."})

# ==========================================================
# MODULE 4: USER AUTH & WATCHLIST & ALERTS & ANALYSIS HISTORY
# ==========================================================

# ---- Auth APIs ----
@app.route("/api/auth/register", methods=["POST"])
def auth_register():
    data = request.json or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "用户名和密码不能为空"}), 400
    if len(password) < 6:
        return jsonify({"error": "密码至少6位"}), 400
    result = auth_db.create_user(username, email, password)
    if "error" in result:
        return jsonify(result), 400
    session["user_id"] = result["user_id"]
    session["username"] = result["username"]
    return jsonify({"success": True, "username": result["username"]})

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")
    if not username or not password:
        return jsonify({"error": "请输入用户名和密码"}), 400
    result = auth_db.verify_user(username, password)
    if "error" in result:
        return jsonify(result), 401
    session["user_id"] = result["user_id"]
    session["username"] = result["username"]
    return jsonify({"success": True, "username": result["username"]})

@app.route("/api/auth/me")
def auth_me():
    uid = current_user_id()
    if not uid:
        return jsonify({"logged_in": False})
    user = auth_db.get_user_by_id(uid)
    if not user:
        session.clear()
        return jsonify({"logged_in": False})
    return jsonify({"logged_in": True, "user": user})

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"success": True})


# ---- Watchlist APIs (login required) ----
@app.route("/api/watchlist")
@login_required
def get_watchlist():
    uid = current_user_id()
    items = auth_db.get_watchlist(uid)
    return jsonify({"items": items})

@app.route("/api/watchlist", methods=["POST"])
@login_required
def add_watchlist():
    uid = current_user_id()
    data = request.json or {}
    code = data.get("code", "").strip()
    name = data.get("name", "").strip()
    market = data.get("market", "cn").strip()
    note = data.get("note", "").strip()
    if not code or not name:
        return jsonify({"error": "代码和名称不能为空"}), 400
    result = auth_db.add_to_watchlist(uid, code, name, market, note)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/watchlist/<code>", methods=["DELETE"])
@login_required
def remove_watchlist(code):
    uid = current_user_id()
    market = request.args.get("market", "cn").strip()
    result = auth_db.remove_from_watchlist(uid, code, market)
    return jsonify(result)

@app.route("/api/watchlist/check/<code>")
@login_required
def check_watchlist(code):
    uid = current_user_id()
    market = request.args.get("market", "cn").strip()
    in_list = auth_db.is_in_watchlist(uid, code, market)
    return jsonify({"in_watchlist": in_list})


# ---- Alert APIs (login required) ----
@app.route("/api/alerts")
@login_required
def get_alerts():
    uid = current_user_id()
    active_only = request.args.get("active", "1") == "1"
    items = auth_db.get_alerts(uid, active_only)
    return jsonify({"items": items})

@app.route("/api/alerts", methods=["POST"])
@login_required
def add_alert():
    uid = current_user_id()
    data = request.json or {}
    code = data.get("code", "").strip()
    name = data.get("name", "").strip()
    market = data.get("market", "cn").strip()
    condition_type = data.get("condition_type", "").strip()
    threshold = data.get("threshold")
    if not code or not name or not condition_type or threshold is None:
        return jsonify({"error": "参数不完整"}), 400
    if condition_type not in ("price_above", "price_below", "change_above", "change_below"):
        return jsonify({"error": "无效的提醒类型"}), 400
    try:
        threshold = float(threshold)
    except ValueError:
        return jsonify({"error": "阈值必须是数字"}), 400
    result = auth_db.add_alert(uid, code, name, market, condition_type, threshold)
    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)

@app.route("/api/alerts/<int:alert_id>", methods=["DELETE"])
@login_required
def delete_alert(alert_id):
    uid = current_user_id()
    result = auth_db.remove_alert(alert_id, uid)
    return jsonify(result)


# ---- Analysis History (login required) ----
@app.route("/api/analysis/history")
@login_required
def get_analysis_history():
    uid = current_user_id()
    limit = int(request.args.get("limit", 20))
    items = auth_db.get_analysis_history(uid, limit)
    return jsonify({"items": items})


# ---- Alert Check Task (called periodically) ----
@app.route("/api/alerts/check", methods=["POST"])
@login_required
def check_all_alerts():
    """Check all active alerts for current user against latest quotes"""
    uid = current_user_id()
    alerts = auth_db.get_alerts(uid, active_only=True)
    triggered = []
    for alert in alerts:
        try:
            code = alert["code"]
            market = alert["market"]
            if market == "cn":
                quote = fetch_cn_quote(code)
            elif market == "hk":
                quote = fetch_hk_quote(code)
            elif market == "us":
                quote = fetch_us_quote(code)
            else:
                continue
            if not quote or "error" in quote:
                continue
            hits = auth_db.check_alerts(
                uid, code, market,
                quote["price"], quote["change_pct"]
            )
            for h in hits:
                triggered.append({
                    "code": code, "name": alert["name"],
                    "condition": h["condition_type"],
                    "threshold": h["threshold"],
                    "current_price": quote["price"],
                    "change_pct": quote["change_pct"]
                })
        except Exception:
            continue
    return jsonify({"triggered": triggered})





# ==========================================================
# STARTUP
# ==========================================================
if __name__ == "__main__":
    port = int(os.getenv("PORT", 5003))
    print(f"[AI Workshop] Starting on http://0.0.0.0:{port}")
    print(f"[AI Workshop] DeepSeek: {'configured' if DEEPSEEK_API_KEY else 'MISSING'}")
    print(f"[AI Workshop] Claude:    {'configured' if CLAUDE_API_KEY else 'MISSING'}")
    app.run(host="0.0.0.0", port=port, debug=False)
