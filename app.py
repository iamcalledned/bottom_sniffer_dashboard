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

# Load .env for FRED key
load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")
fred = Fred(api_key=FRED_API_KEY)

# Load dashboard config
with open("config.json", "r") as f:
    config = json.load(f)

fred_cache = {}
history_cache = {}
fred_cache_ttl_minutes = 5
history_cache_ttl_hours = 6

INDICATOR_SOURCES = {
    "2-Year Yield": ("fred", "DGS2"),
    "10-Year Yield": ("fred", "DGS10"),
    "30Y Yield": ("fred", "DGS30"),
    "UST 2s/10s Curve": ("fred_spread", ("DGS2", "DGS10")),
    "UST 3m/10y Curve": ("fred_spread", ("TB3MS", "DGS10")),
    "Fed Funds Rate": ("fred", "FEDFUNDS"),
    "Unemployment Rate": ("fred", "UNRATE"),
    "CPI (YoY)": ("fred_yoy", "CPIAUCSL"),
    "Retail Sales": ("fred", "RSAFS"),
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
            fred_cache[sid] = {"value": round(value, 4), "timestamp": now}
            print(f"[FRED] Cached {sid}: {value}")
        except Exception as e:
            print(f"[FRED] Error: {sid} - {e}")


def prefetch_history():
    for name, source in INDICATOR_SOURCES.items():
        try:
            if source[0] == "yahoo":
                ticker = yf.Ticker(source[1])
                hist = ticker.history(period="7d", interval="1d")
                if not hist.empty:
                    history_cache[name] = [
                        {"date": str(idx.date()), "value": round(val, 2)}
                        for idx, val in hist["Close"].dropna().items()
                    ]
            elif source[0] in ["fred", "fred_yoy", "fred_spread"]:
                sid = source[1] if source[0] != "fred_spread" else source[1][1]
                series = fred.get_series(sid).dropna().tail(7)
                history_cache[name] = [
                    {"date": str(date.date()), "value": round(val, 4)}
                    for date, val in series.items()
                ]
        except Exception as e:
            print(f"[History] Error for {name}: {e}")


def start_background_updaters():
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

    def loop_fred():
        while True:
            fetch_fred_series(series_ids)
            sleep(fred_cache_ttl_minutes * 60)

    def loop_history():
        while True:
            prefetch_history()
            sleep(history_cache_ttl_hours * 3600)

    fetch_fred_series(series_ids)
    prefetch_history()
    Thread(target=loop_fred, daemon=True).start()
    Thread(target=loop_history, daemon=True).start()


@app.route("/api/indicator/<path:indicator_name>")
def get_indicator_data(indicator_name):
    indicator_name = unquote(indicator_name)
    source_info = INDICATOR_SOURCES.get(indicator_name)

    if not source_info:
        return jsonify({"name": indicator_name, "value": None, "error": "No source"})

    try:
        if source_info[0] == "fred":
            return jsonify({"name": indicator_name, "value": fred_cache.get(source_info[1], {}).get("value")})
        elif source_info[0] == "fred_yoy":
            return jsonify({"name": indicator_name, "value": fred_cache.get(source_info[1], {}).get("value")})
        elif source_info[0] == "fred_spread":
            s1, s2 = source_info[1]
            v1 = fred_cache.get(s1, {}).get("value")
            v2 = fred_cache.get(s2, {}).get("value")
            return jsonify({"name": indicator_name, "value": round(v2 - v1, 4)}) if v1 and v2 else jsonify({"value": None})
        elif source_info[0] == "yahoo":
            data = yf.Ticker(source_info[1]).history(period="2d")
            if not data.empty:
                return jsonify({"name": indicator_name, "value": round(data['Close'].iloc[-1], 2)})
        elif source_info[0] == "mock_composite":
            values = [fred_cache.get(sid, {}).get("value") for sid in source_info[1]]
            values = [v for v in values if v is not None]
            avg = sum(values) / len(values) if values else None
            return jsonify({"name": indicator_name, "value": round(avg, 2) if avg else None})
        elif source_info[0] == "mock":
            return jsonify({"name": indicator_name, "value": 1.23})
    except Exception as e:
        return jsonify({"name": indicator_name, "value": None, "error": str(e)})

    return jsonify({"name": indicator_name, "value": None})


@app.route("/api/history/<path:indicator_name>")
def get_indicator_history(indicator_name):
    indicator_name = unquote(indicator_name)
    return jsonify({
        "name": indicator_name,
        "values": history_cache.get(indicator_name, [])
    })


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", config=config)


@app.route("/")
def home():
    return render_template("home.html")


if __name__ == "__main__":
    start_background_updaters()
    app.run(host="127.0.0.1", port=5000)
