from flask import Flask, render_template, jsonify
import os
from dotenv import load_dotenv
from fredapi import Fred
from urllib.parse import unquote
from threading import Thread
from time import sleep
from datetime import datetime
import json

app = Flask(__name__)

# Load .env with FRED_API_KEY
load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")
fred = Fred(api_key=FRED_API_KEY)

# Cache for FRED values
fred_cache = {}
fred_cache_ttl_minutes = 5

# Load dashboard config
with open("/home/ned/market_bot/market_monitor/bottom_sniffer_dashboard/config.json", "r") as f:
    config = json.load(f)

# Indicator mappings
INDICATOR_SOURCES = {
    "2-Year Yield": ("fred", "DGS2"),
    "10-Year Yield": ("fred", "DGS10"),
    "30Y Yield": ("fred", "DGS30"),
    "UST 2s/10s Curve": ("fred_spread", ("DGS2", "DGS10")),
    "UST 3m/10y Curve": ("fred_spread", ("TB3MS", "DGS10")),
    "Fed Funds Rate": ("fred", "FEDFUNDS"),
    "Unemployment Rate": ("fred", "UNRATE"),
    "CPI (YoY)": ("fred", "CPIAUCSL"),
    "Retail Sales": ("fred", "RSAFS"),
    "Stress Composite Score": ("mock_composite", ["DGS2", "DGS10", "DGS30", "FEDFUNDS", "UNRATE"])
}

def get_fred_value(series_id):
    entry = fred_cache.get(series_id)
    if entry:
        return entry["value"]
    return None

@app.route("/api/indicator/<path:indicator_name>")
def get_indicator_data(indicator_name):
    indicator_name = unquote(indicator_name)
    source_info = INDICATOR_SOURCES.get(indicator_name)

    if not source_info:
        return jsonify({"name": indicator_name, "value": None, "error": "No data source mapped"})

    source_type = source_info[0]

    if source_type == "fred":
        value = get_fred_value(source_info[1])
        return jsonify({"name": indicator_name, "value": value})

    elif source_type == "fred_spread":
        v1 = get_fred_value(source_info[1][0])
        v2 = get_fred_value(source_info[1][1])
        if v1 is not None and v2 is not None:
            return jsonify({"name": indicator_name, "value": round(v2 - v1, 4)})

    elif source_type == "mock_composite":
        values = [get_fred_value(sid) for sid in source_info[1]]
        values = [v for v in values if v is not None]
        composite = sum(values) / len(values) if values else None
        return jsonify({"name": indicator_name, "value": composite})

    return jsonify({"name": indicator_name, "value": None, "error": "Unhandled source type"})

@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", config=config)

def fetch_fred_series(series_ids):
    now = datetime.utcnow()
    for series_id in series_ids:
        try:
            series = fred.get_series(series_id)
            if series is not None and len(series) > 0:
                value = float(series.iloc[-1])
                fred_cache[series_id] = {
                    "value": value,
                    "timestamp": now
                }
                print(f"[FRED] Cached {series_id}: {value}")
        except Exception as e:
            print(f"[FRED] Error fetching {series_id}: {e}")

def start_fred_prefetcher():
    series_ids = [
        "DGS2", "DGS10", "DGS30", "TB3MS",
        "FEDFUNDS", "UNRATE", "CPIAUCSL", "RSAFS"
    ]
    def run_loop():
        while True:
            fetch_fred_series(series_ids)
            sleep(fred_cache_ttl_minutes * 60)

    thread = Thread(target=run_loop)
    thread.daemon = True
    thread.start()

# Start prefetcher
start_fred_prefetcher()

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=5000)
