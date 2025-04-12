import json
from flask import Flask, render_template, jsonify

app = Flask(__name__)

def load_config():
    with open(r'/home/ned/market_bot/market_monitor/bottom_sniffer_dashboard/config.json', 'r') as f:
        return json.load(f)

# Load configuration from the JSON file at startup
config = load_config()
print("Loaded config:", config)


@app.route('/dashboard')
def dashboard():
    # Pass the entire config to the template
    return render_template("dashboard.html", config=config)


if __name__ == '__main__':
    # Run the Flask app on port 5000 and bind it to localhost only.
    app.run(host="127.0.0.1", port=5000)
