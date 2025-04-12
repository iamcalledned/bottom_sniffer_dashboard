import json
import os
from flask import Flask, render_template, jsonify
import yfinance as yf
from fredapi import Fred
from dotenv import load_dotenv
from urllib.parse import unquote
from threading import Thread
from time import sleep
from datetime import datetime, timedelta

fred_cache = {}
fred_cache_ttl_minutes = 5


app = Flask(__name__)

# Load environment variables from the .env file
load_dotenv()

# Function to load configuration from config.json
def load_config():
    with open(r'/home/ned/market_bot/market_monitor/bottom_sniffer_dashboard/config.json', 'r') as f:
        return json.load(f)

# Load the configuration at startup
config = load_config()
print("Loaded config:", config)

# Initialize FRED using the API key from the environment
fred_api_key = os.environ.get('FRED_API_KEY')
fred = Fred(api_key=fred_api_key)

def fetch_fred_series(series_ids):
    global fred_cache
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


# Function to fetch the latest price from Yahoo Finance
def get_yahoo_price(ticker_symbol):
    try:
        data = yf.download(ticker_symbol, period="1d", interval="1d")
        if not data.empty:
            return float(data['Close'].iloc[-1])
    except Exception as e:
        print(f"Error fetching {ticker_symbol} from Yahoo Finance: {e}")
    return None

# Function to fetch the latest value from a FRED series
def get_fred_value(series_id):
    try:
        series = fred.get_series(series_id)
        if series is not None and len(series) > 0:
            return float(series.iloc[-1])
    except Exception as e:
        print(f"Error fetching {series_id} from FRED: {e}")
    return None

# Mapping of indicator names to data sources
# For now, only some indicators are mapped. Expand as needed.
INDICATOR_SOURCES = {
    "2-Year Yield": ("fred", "DGS2"),
    "10-Year Yield": ("fred", "DGS10"),
    "UST 2s/10s Curve": ("fred_spread", ("DGS2", "DGS10")),
    "UST 3m/10y Curve": ("fred_spread", ("TB3MS", "DGS10")),
    "30Y Yield": ("fred", "DGS30"),
    "Fed Funds Rate": ("fred", "FEDFUNDS"),
    "Unemployment Rate": ("fred", "UNRATE"),
    "CPI (YoY)": ("fred", "CPIAUCSL"),
    "Retail Sales": ("fred", "RSAFS"),
    "Stress Composite Score": ("mock_composite", ["DGS2", "DGS10", "DGS30", "FEDFUNDS", "UNRATE"])
}


@app.route('/api/indicator/<path:indicator_name>')
def get_indicator_data(indicator_name):
    indicator_name = unquote(indicator_name)
    source_info = INDICATOR_SOURCES.get(indicator_name)
    if not source_info:
        return jsonify({"name": indicator_name, "value": None, "error": "No data source mapped"}), 200

    source_type = source_info[0]

    if source_type == "fred_spread":
        fred_ids = source_info[1]
        val1 = get_fred_value(fred_ids[0])
        val2 = get_fred_value(fred_ids[1])
        if val1 is not None and val2 is not None:
            spread = val2 - val1
            return jsonify({"name": indicator_name, "value": spread})
    
    elif source_type == "fred":
        series_id = source_info[1]
        value = get_fred_value(series_id)
        return jsonify({"name": indicator_name, "value": value})

    elif source_type == "mock_composite":
        ids = source_info[1]
        values = [get_fred_value(i) for i in ids]
        values = [v for v in values if v is not None]
        composite = sum(values) / len(values) if values else None
        return jsonify({"name": indicator_name, "value": composite})

    return jsonify({"name": indicator_name, "value": None, "error": "Unhandled source type"})


@app.route('/dashboard')
def dashboard():
    # Render the dashboard template, passing the full configuration
    return render_template('dashboard.html', config=config)
start_fred_prefetcher()
if __name__ == '__main__':
    app.run(host="127.0.0.1", port=5000)
