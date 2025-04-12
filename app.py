import json
import os
from flask import Flask, render_template, jsonify
import yfinance as yf
from fredapi import Fred

app = Flask(__name__)

# Load the configuration file from the specified path
def load_config():
    with open(r'/home/ned/market_bot/market_monitor/bottom_sniffer_dashboard/config.json', 'r') as f:
        return json.load(f)

# Load config at startup
config = load_config()
print("Loaded config:", config)

# Initialize FRED API (make sure to set your FRED_API_KEY in your environment)
fred_api_key = os.environ.get('FRED_API_KEY', '<YOUR_FRED_API_KEY>')
fred = Fred(api_key=fred_api_key)

# Example function to fetch the latest price from Yahoo Finance
def get_yahoo_price(ticker_symbol):
    try:
        data = yf.download(ticker_symbol, period="1d", interval="1d")
        if not data.empty:
            # Get the last closing price
            return float(data['Close'].iloc[-1])
    except Exception as e:
        print(f"Error fetching {ticker_symbol} from Yahoo Finance: {e}")
    return None

# Example function to fetch the latest value from FRED
def get_fred_value(series_id):
    try:
        series = fred.get_series(series_id)
        if series is not None and len(series) > 0:
            return float(series.iloc[-1])
    except Exception as e:
        print(f"Error fetching {series_id} from FRED: {e}")
    return None

# Mapping of indicator names to data sources and corresponding ticker or series IDs
INDICATOR_SOURCES = {
    "VIX": ("yahoo", "^VIX"),
    "Skew Index": ("yahoo", "^SKEW"),
    "Gold Price": ("yahoo", "GC=F"),
    "Bitcoin Price": ("yahoo", "BTC-USD"),
    "Dollar Index (DXY)": ("yahoo", "DX-Y.NYB"),
    "UST 2s/10s Curve": ("fred_spread", ("DGS2", "DGS10"))
    # Add more mappings as needed...
}

@app.route('/api/indicator/<indicator_name>')
def get_indicator_data(indicator_name):
    """
    Fetch real-time data for a given indicator.
    Uses yfinance for Yahoo-based tickers and FRED for calculating spreads.
    """
    source_info = INDICATOR_SOURCES.get(indicator_name)
    if not source_info:
        return jsonify({"name": indicator_name, "error": "No data source mapped"}), 404

    source_type = source_info[0]
    if source_type == "yahoo":
        ticker_symbol = source_info[1]
        price = get_yahoo_price(ticker_symbol)
        return jsonify({"name": indicator_name, "value": price})
    elif source_type == "fred_spread":
        fred_ids = source_info[1]
        v2y = get_fred_value(fred_ids[0])
        v10y = get_fred_value(fred_ids[1])
        if v2y is not None and v10y is not None:
            spread = v10y - v2y
            return jsonify({"name": indicator_name, "value": spread})
    # Fallback if nothing matches
    return jsonify({"name": indicator_name, "value": None})

@app.route('/dashboard')
def dashboard():
    # Render the dashboard template, passing the full config to it
    return render_template('dashboard.html', config=config)

if __name__ == '__main__':
    app.run(host="127.0.0.1", port=5000)
