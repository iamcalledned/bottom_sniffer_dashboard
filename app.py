import json
from flask import Flask, render_template, jsonify

app = Flask(__name__)

def load_config():
    with open('config.json', 'r') as f:
        return json.load(f)

# Load configuration at startup
config = load_config()

@app.route('/')
def home():
    # Render a fun and inviting homepage using the configuration
    homepage_config = config.get("server_config", {}).get("homepage", {})
    return render_template("home.html", homepage=homepage_config)

@app.route('/dashboard')
def dashboard():
    # Pass dashboard config to the template for dynamic rendering
    dashboard_config = config.get("dashboard", {})
    return render_template("dashboard.html", dashboard=dashboard_config)

# Example: An API endpoint to update individual indicator data in real-time
@app.route('/api/indicator/<indicator_name>')
def get_indicator_data(indicator_name):
    # In a real implementation, you’d fetch data from your chosen data feeds.
    # This is a stub example returning a random value.
    import random
    data = {
        "name": indicator_name,
        "value": round(random.uniform(10, 100), 2),
        "alert": "green"  # You would apply your threshold logic here.
    }
    return jsonify(data)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5000)
