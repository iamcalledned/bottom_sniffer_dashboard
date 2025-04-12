from flask import Flask, render_template, jsonify
import os
from dotenv import load_dotenv
from fredapi import Fred
import yfinance as yf
from urllib.parse import unquote
from threading import Thread
from time import sleep
from datetime import datetime
import json

app = Flask(__name__)

# Load env and FRED
load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")
fred = Fred(api_key=FRED_API_KEY)

# Load UI config
with open("/home/ned/market_bot/market_monitor/bottom_sniffer_dashboard/config.json", "r") as f:
    config = json.load(f)

# In-memory cache
fred_cache = {}
fred_cache_ttl_minutes = 5

# Map indicators
INDICATOR_SOURCES = {
    # FRED
    "2-Year Yield": ("fred", "DGS2"),
    "10-Year Yield": ("fred", "DGS10"),
    "30Y Yield": ("fred", "DGS30"),
    "UST 2s/10s Curve": ("fred_spread", ("DGS2", "DGS10")),
    "UST 3m/10y Curve": ("fred_spread", ("TB3MS", "DGS10")),
    "Fed Funds Rate": ("fred", "FEDFUNDS"),
    "Unemployment Rate": ("fred", "UNRATE"),
    "CPI (YoY)": ("fred_yoy", "CPIAUCSL"),
    "Retail Sales": ("fred", "RSAFS"),

    # Yahoo
    "VIX": ("yahoo", "^VIX"),
    "MOVE Index": ("yahoo", "^MOVE"),
    "VVIX": ("yahoo", "^VVIX"),
    "VXTLT": ("yahoo", "^VXTLT"),
    "HY Spreads": ("fred", "BAMLH0A0HYM2EY"),
    "Skew Index": ("yahoo", "^SKEW"),
    "SOFR Spread": ("fred_spread", ("SOFR", "EFFR")),

    "Gold": ("yahoo", "GC=F"),
    "Bitcoin": ("yahoo", "BTC-USD"),
    "USD Index": ("yahoo", "DX-Y.NYB"),
    "Treasury Demand (Bid/Cover)": ("mock", "bidcover"),

    # Composite
    "Stress Composite Score": ("mock_composite", ["DGS2", "DGS10", "DGS30", "FEDFUNDS", "UNRATE"])
}


def fetch_fred_series(series_ids):
    now = datetime.utcnow()
    for sid in series_ids:
        try:
            series = fred.get_series(sid)
            if sid == "CPIAUCSL" and len(series) >= 13:
                value = ((series.iloc[-1] - series.iloc[-13]) / series.iloc[-13]) * 100
            else:
                value = float(series.iloc[-1])

            fred_cache[sid] = {
                "value": round(value, 4),
                "timestamp": now
            }
            print(f"[FRED] Cached {sid}: {value}")

        except Exception as e:
            print(f"[FRED] Error fetching {sid}: {e}")


def start_fred_prefetcher():
    series_ids = set()
    for src in INDICATOR_SOURCES.values():
        if src[0] == "fred":
            series_ids.add(src[1])
        elif src[0] == "fred_spread":
            series_ids.update(src[1])
        elif src[0] == "fred_yoy":
            series_ids.add(src[1])
        elif src[0] == "mock_composite":
            series_ids.update(src[1])

    # First fetch immediately
    fetch_fred_series(series_ids)

    def loop():
        while True:
            fetch_fred_series(series_ids)
            sleep(fred_cache_ttl_minutes * 60)

    Thread(target=loop, daemon=True).start()


@app.route("/api/indicator/<path:indicator_name>")
def get_indicator_data(indicator_name):
    indicator_name = unquote(indicator_name)
    source_info = INDICATOR_SOURCES.get(indicator_name)

    if not source_info:
        return jsonify({"name": indicator_name, "value": None, "error": "No data source mapped"})

    source_type = source_info[0]

    try:
        if source_type == "fred":
            cached = fred_cache.get(source_info[1])
            if cached:
                return jsonify({"name": indicator_name, "value": cached["value"]})

        elif source_type == "fred_yoy":
            cached = fred_cache.get(source_info[1])
            if cached:
                return jsonify({"name": indicator_name, "value": cached["value"]})

        elif source_type == "fred_spread":
            s1, s2 = source_info[1]
            v1 = fred_cache.get(s1)
            v2 = fred_cache.get(s2)
            if v1 and v2:
                return jsonify({"name": indicator_name, "value": round(v2["value"] - v1["value"], 4)})

        elif source_type == "yahoo":
            ticker = yf.Ticker(source_info[1])
            data = ticker.history(period="2d")
            if not data.empty:
                latest = data['Close'].iloc[-1]
                return jsonify({"name": indicator_name, "value": round(float(latest), 2)})

        elif source_type == "mock_composite":
            values = [
                fred_cache.get(sid, {}).get("value") for sid in source_info[1]
            ]
            values = [v for v in values if v is not None]
            if values:
                composite = sum(values) / len(values)
                return jsonify({"name": indicator_name, "value": round(composite, 2)})

        elif source_type == "mock":
            return jsonify({"name": indicator_name, "value": 2.11})

    except Exception as e:
        return jsonify({"name": indicator_name, "value": None, "error": str(e)})

    return jsonify({"name": indicator_name, "value": None, "error": "Data unavailable"})


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", config=config)

@app.route("/api/history/<path:indicator_name>")
def get_indicator_history(indicator_name):
    indicator_name = unquote(indicator_name)
    source_info = INDICATOR_SOURCES.get(indicator_name)

    if not source_info:
        return jsonify({"name": indicator_name, "values": []})

    try:
        if source_info[0] == "yahoo":
            ticker = yf.Ticker(source_info[1])
            hist = ticker.history(period="7d", interval="1d")
            if not hist.empty:
                values = hist['Close'].dropna().tolist()
                return jsonify({"name": indicator_name, "values": [round(v, 2) for v in values]})

        elif source_info[0] in ["fred", "fred_yoy", "fred_spread"]:
            sid = source_info[1] if source_info[0] != "fred_spread" else source_info[1][1]
            series = fred.get_series(sid)
            if series is not None:
                values = series.dropna().tail(7).tolist()
                return jsonify({"name": indicator_name, "values": [round(v, 4) for v in values]})

    except Exception as e:
        return jsonify({"name": indicator_name, "values": [], "error": str(e)})

    return jsonify({"name": indicator_name, "values": []})



# Run setup
start_fred_prefetcher()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
