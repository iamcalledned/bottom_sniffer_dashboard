import json
from flask import Flask, render_template, jsonify

app = Flask(__name__)

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

# Load configuration from the JSON file at startup
config = load_config()

@app.route('/dashboard')
def dashboard():
    # Render the dashboard template with your configuration data
    dashboard_config = config.get("dashboard", {})
    return render_template("dashboard.html", dashboard=dashboard_config)

@app.route('/api/indicator/<indicator_name>')
def get_indicator_data(indicator_name):
    # Replace with real API/data feed integration; this is a dummy implementation.
    import random
    data = {
        "name": indicator_name,
        "value": round(random.uniform(10, 100), 2),
        "alert": "green"
    }
    return jsonify(data)

if __name__ == '__main__':
    # Run the Flask app on port 5000 and bind it to localhost only.
    app.run(host="127.0.0.1", port=5000)
