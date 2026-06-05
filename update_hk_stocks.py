"""
Update HK stock names database from Eastmoney API.
Fetches all HK stocks (Main Board, GEM, ETFs, etc.) and regenerates hk_stock_names.py
"""
import requests
import json
import os

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://data.eastmoney.com/",
}

def fetch_all_hk_stocks():
    """Fetch all HK stocks from Eastmoney"""
    stocks = {}
    page = 1
    page_size = 500

    while True:
        url = (
            f"https://push2.eastmoney.com/api/qt/clist/get"
            f"?pn={page}&pz={page_size}&po=1&np=1&fltt=2&invt=2"
            f"&fid=f12&fs=m:128+t:3,m:128+t:4,m:128+t:1,m:128+t:2"
            f"&fields=f2,f12,f14"
        )
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            data = resp.json()
            items = data.get("data", {}).get("diff", [])
            if not items:
                break

            for item in items:
                code = item.get("f12", "").strip()
                name = item.get("f14", "").strip()
                if code and name:
                    # Normalize code: ensure 5 digits with leading zeros
                    code_padded = code.zfill(5)
                    stocks[code_padded] = name

            total = data.get("data", {}).get("total", 0)
            print(f"  Page {page}: got {len(items)} stocks (total so far: {len(stocks)}, server total: {total})")

            if len(items) < page_size:
                break
            page += 1

        except Exception as e:
            print(f"  Error on page {page}: {e}")
            break

    return stocks


if __name__ == "__main__":
    print("Fetching HK stock list from Eastmoney...")
    stocks = fetch_all_hk_stocks()

    if not stocks:
        print("ERROR: No stocks fetched! Check network connection.")
        exit(1)

    # Sort by code
    sorted_stocks = dict(sorted(stocks.items()))

    # Generate Python file
    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hk_stock_names.py")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# Auto-generated HK stock database\n")
        f.write(f"# Generated: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Total stocks: {len(sorted_stocks)}\n")
        f.write("HK_STOCK_NAMES = {\n")
        for code, name in sorted_stocks.items():
            # Escape quotes in names
            safe_name = name.replace('"', '\\"').replace("'", "\\'")
            f.write(f'    "{code}": "{safe_name}",\n')
        f.write("}\n")

    print(f"\nDone! {len(sorted_stocks)} HK stocks written to {output_path}")
