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
composite_score_cache = {"value": None, "timestamp": None}


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

def calculate_composite_score(data):
    weights = {
        "rates_and_curve": 0.15,  # Reduced weight
        "credit_and_volatility": 0.40,  # Increased weight
        "macro_indicators": 0.25,
        "flight_to_safety": 0.20,
    }
    rates_and_curve = normalize_rates_and_curve(data)
    credit_and_volatility = normalize_credit_and_volatility(data)
    macro_indicators = normalize_macro_indicators(data)
    flight_to_safety = normalize_flight_to_safety(data)

    composite_score = (
        weights["rates_and_curve"] * rates_and_curve +
        weights["credit_and_volatility"] * credit_and_volatility +
        weights["macro_indicators"] * macro_indicators +
        weights["flight_to_safety"] * flight_to_safety
    )

    # Log the components for debugging
    print(f"[Composite Score Calculation] Rates & Curve: {rates_and_curve}, "
          f"Credit & Volatility: {credit_and_volatility}, "
          f"Macro Indicators: {macro_indicators}, "
          f"Flight to Safety: {flight_to_safety}, "
          f"Composite Score: {composite_score}")

    return round(composite_score, 2)

def normalize_rates_and_curve(data):
    two_year = data.get("two_year_yield", 0)
    ten_year = data.get("ten_year_yield", 0)
    thirty_year = data.get("thirty_year_yield", 0)
    ust_2s10s = data.get("ust_2s10s_curve", 0)
    ust_3m10y = data.get("ust_3m10y_curve", 0)

    # Penalize near-zero or barely positive spreads
    curve_inversion_score = max(0, min(100, (0.5 - ust_2s10s) * 300))  # Increased sensitivity
    rates_score = max(0, min(100, (two_year + ten_year + thirty_year - 9) * 15))  # Penalize high yields more

    normalized_score = (curve_inversion_score + rates_score) / 2

    print(f"[Rates & Curve] Inputs: 2Y={two_year}, 10Y={ten_year}, 30Y={thirty_year}, "
          f"2s10s={ust_2s10s}, 3m10y={ust_3m10y} | Normalized Score: {normalized_score}")

    return normalized_score

def normalize_credit_and_volatility(data):
    vix = data.get("vix", 0)
    move_index = data.get("move_index", 0)
    vx_tlt = data.get("vx_tlt", 0)
    hy_credit_spread = data.get("hy_credit_spread", 0)

    # Adjust thresholds for VIX and HY spreads
    vix_score = max(0, min(100, (vix - 15) * 6))  # Increased sensitivity for VIX > 35
    move_score = max(0, min(100, (move_index - 100) * 2))  # MOVE > 150 = 100
    credit_spread_score = max(0, min(100, hy_credit_spread * 15))  # Increased sensitivity for HY spreads

    normalized_score = (vix_score + move_score + credit_spread_score + vx_tlt) / 4

    print(f"[Credit & Volatility] Inputs: VIX={vix}, MOVE={move_index}, VXTLT={vx_tlt}, "
          f"HY Spread={hy_credit_spread} | Normalized Score: {normalized_score}")

    return normalized_score

def normalize_macro_indicators(data):
    fed_funds_rate = data.get("fed_funds_rate", 0)
    cpi_yoy = data.get("cpi_yoy", 0)
    unemployment_rate = data.get("unemployment_rate", 0)
    retail_sales = data.get("retail_sales", 0)

    # Penalize elevated unemployment and flat retail sales
    unemployment_score = max(0, min(100, (unemployment_rate - 3) * 30))  # Increased sensitivity
    inflation_score = max(0, min(100, (cpi_yoy - 2) * 50))  # CPI > 2 = stress
    retail_sales_score = max(0, min(100, 100 - (retail_sales / 8000)))  # Penalize lower sales more

    normalized_score = (inflation_score + unemployment_score + retail_sales_score + fed_funds_rate) / 4

    print(f"[Macro Indicators] Inputs: Fed Funds={fed_funds_rate}, CPI YoY={cpi_yoy}, "
          f"Unemployment={unemployment_rate}, Retail Sales={retail_sales} | "
          f"Normalized Score: {normalized_score}")

    return normalized_score


def normalize_flight_to_safety(data):
    gold_price = data.get("gold_price", 0)
    bitcoin_price = data.get("bitcoin_price", 0)
    sofr_spread = data.get("sofr_spread", 0)

    # Penalize rising gold and falling Bitcoin more heavily
    gold_score = max(0, min(100, (gold_price - 1800) / 1.5))  # Increased sensitivity for gold > 2000
    bitcoin_score = max(0, min(100, (60000 - bitcoin_price) / 400))  # Penalize falling BTC more

    normalized_score = (gold_score + bitcoin_score) / 2

    print(f"[Flight to Safety] Inputs: Gold={gold_price}, Bitcoin={bitcoin_price}, "
          f"SOFR Spread={sofr_spread} | Normalized Score: {normalized_score}")

    return normalized_score

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

    def loop_composite_score():
        while True:
            update_composite_score()
            sleep(fred_cache_ttl_minutes * 60)  # Update composite score periodically

    # Preload data and calculate the composite score at startup
    fetch_fred_series(series_ids)
    prefetch_history()
    update_composite_score()  # Ensure the composite score is calculated at startup

    # Start background threads
    Thread(target=loop_fred, daemon=True).start()
    Thread(target=loop_history, daemon=True).start()
    Thread(target=loop_composite_score, daemon=True).start()

def update_composite_score():
    try:
        # Gather data from the cache
        data = {
            "two_year_yield": fred_cache.get("DGS2", {}).get("value"),
            "ten_year_yield": fred_cache.get("DGS10", {}).get("value"),
            "thirty_year_yield": fred_cache.get("DGS30", {}).get("value"),
            "ust_2s10s_curve": fred_cache.get("DGS10", {}).get("value") - fred_cache.get("DGS2", {}).get("value"),
            "ust_3m10y_curve": fred_cache.get("DGS10", {}).get("value") - fred_cache.get("TB3MS", {}).get("value"),
            "fed_funds_rate": fred_cache.get("FEDFUNDS", {}).get("value"),
            "unemployment_rate": fred_cache.get("UNRATE", {}).get("value"),
            "cpi_yoy": fred_cache.get("CPIAUCSL", {}).get("value"),
            "retail_sales": fred_cache.get("RSAFS", {}).get("value"),
            "vix": history_cache.get("VIX", [{}])[-1].get("value"),
            "move_index": history_cache.get("MOVE Index", [{}])[-1].get("value"),
            "vx_tlt": history_cache.get("VXTLT", [{}])[-1].get("value"),
            "sofr_spread": fred_cache.get("SOFR", {}).get("value") - fred_cache.get("EFFR", {}).get("value"),
            "hy_credit_spread": fred_cache.get("BAMLH0A0HYM2EY", {}).get("value"),
            "gold_price": history_cache.get("Gold", [{}])[-1].get("value"),
            "bitcoin_price": history_cache.get("Bitcoin", [{}])[-1].get("value"),
        }

        # Calculate the composite score
        rates_and_curve = normalize_rates_and_curve(data)
        credit_and_volatility = normalize_credit_and_volatility(data)
        macro_indicators = normalize_macro_indicators(data)
        flight_to_safety = normalize_flight_to_safety(data)

        score = calculate_composite_score(data)
        composite_score_cache.update({
            "value": score,
            "timestamp": datetime.utcnow(),
            "rates_and_curve": rates_and_curve,
            "credit_and_volatility": credit_and_volatility,
            "macro_indicators": macro_indicators,
            "flight_to_safety": flight_to_safety,
        })
        print(f"[DEBUG] Composite Score Updated: {composite_score_cache}")
    except Exception as e:
        print(f"[Composite Score] Error: {e}")

def classify_risk_level(score):
    """Classify the composite score into a risk level."""
    if score <= 20:
        return {
            "range": "0-20",
            "label": "Ultra Risk-On",
            "description": "Markets are in extreme risk appetite mode. Volatility is suppressed, yield curves are normal, credit spreads are tight, and macro indicators are strong. Conditions are historically bullish."
        }
    elif score <= 40:
        return {
            "range": "21-40",
            "label": "Risk-On",
            "description": "Risk appetite is evident. Most indicators suggest stability or optimism. Moderate caution is warranted but conditions favor constructive positioning."
        }
    elif score <= 60:
        return {
            "range": "41-60",
            "label": "Neutral / Caution",
            "description": "Mixed signals. Macro is uncertain, volatility is elevated, and curve signals may be flattening or inverting. This is a no-man’s-land environment; watch for regime shifts."
        }
    elif score <= 80:
        return {
            "range": "61-80",
            "label": "Risk-Off",
            "description": "Volatility and credit spreads are rising, macro indicators are weakening, and safety trades (e.g., gold, short duration) are gaining. Red flags are present across several categories."
        }
    else:
        return {
            "range": "81-100",
            "label": "Crisis / Extreme Risk-Off",
            "description": "Broad-based market stress is underway. Curve inversion, credit dysfunction, macro deterioration, and flight to safety are all flashing at once. This score historically aligns with systemic events or severe drawdowns."
        }

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

@app.route("/api/status")
def server_status():
    try:
        # Perform a lightweight check (e.g., return a success message)
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    

@app.route("/api/composite_score")
def get_composite_score():
    try:
        if composite_score_cache["value"] is None:
            update_composite_score()
        print(f"[DEBUG] Composite Score Cache: {composite_score_cache}")
        return jsonify({
            "composite_score": composite_score_cache["value"],
            "details": {
                "rates_and_curve": composite_score_cache.get("rates_and_curve"),
                "credit_and_volatility": composite_score_cache.get("credit_and_volatility"),
                "macro_indicators": composite_score_cache.get("macro_indicators"),
                "flight_to_safety": composite_score_cache.get("flight_to_safety"),
            },
            "risk_classification": classify_risk_level(composite_score_cache["value"])
        })
    except Exception as e:
        print(f"[Composite Score API] Error: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    start_background_updaters()
    app.run(host="127.0.0.1", port=5000)
