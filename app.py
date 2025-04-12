from flask import Flask, render_template, jsonify
import os
from dotenv import load_dotenv
from fredapi import Fred
import yfinance as yf
from urllib.parse import unquote
import json

app = Flask(__name__)

# Load environment variables
load_dotenv()
FRED_API_KEY = os.getenv("FRED_API_KEY")
fred = Fred(api_key=FRED_API_KEY)

# Load dashboard config
with open("/home/ned/market_bot/market_monitor/bottom_sniffer_dashboard/config.json", "r") as f:
    config = json.load(f)

# Indicator mapping
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

    # Yahoo Finance
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

    # Composite score
    "Stress Composite Score": ("mock_composite", ["DGS2", "DGS10", "DGS30", "FEDFUNDS", "UNRATE"])
}


@app.route("/api/indicator/<path:indicator_name>")
def get_indicator_data(indicator_name):
    indicator_name = unquote(indicator_name)
    source_info = INDICATOR_SOURCES.get(indicator_name)

    if not source_info:
        return jsonify({"name": indicator_name, "value": None, "error": "No data source mapped"})

    source_type = source_info[0]

    try:
        if source_type == "fred":
            series = fred.get_series(source_info[1])
            value = float(series.iloc[-1])
            return jsonify({"name": indicator_name, "value": round(value, 4)})

        elif source_type == "fred_yoy":
            series = fred.get_series(source_info[1])
            if len(series) >= 13:
                value = ((series.iloc[-1] - series.iloc[-13]) / series.iloc[-13]) * 100
                return jsonify({"name": indicator_name, "value": round(value, 2)})

        elif source_type == "fred_spread":
            s1, s2 = source_info[1]
            v1 = fred.get_series(s1).iloc[-1]
            v2 = fred.get_series(s2).iloc[-1]
            return jsonify({"name": indicator_name, "value": round(v2 - v1, 4)})

        elif source_type == "yahoo":
            ticker = yf.Ticker(source_info[1])
            data = ticker.history(period="2d")
            if not data.empty:
                latest = data['Close'].iloc[-1]
                return jsonify({"name": indicator_name, "value": round(float(latest), 2)})

        elif source_type == "mock_composite":
            values = []
            for sid in source_info[1]:
                try:
                    val = float(fred.get_series(sid).iloc[-1])
                    values.append(val)
                except:
                    continue
            composite = sum(values) / len(values) if values else None
            return jsonify({"name": indicator_name, "value": round(composite, 2) if composite else None})

        elif source_type == "mock":
            return jsonify({"name": indicator_name, "value": 2.11})

    except Exception as e:
        return jsonify({"name": indicator_name, "value": None, "error": str(e)})

    return jsonify({"name": indicator_name, "value": None, "error": "Unknown source type"})


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html", config=config)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000)
