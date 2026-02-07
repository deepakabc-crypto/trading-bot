"""
Minimal Trading Dashboard for Railway.app
"""
import os
from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return '''
    <!DOCTYPE html>
    <html>
    <head>
        <title>Trading Bot Dashboard</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: Arial, sans-serif;
                background: linear-gradient(135deg, #1a1a2e, #16213e);
                color: white;
                min-height: 100vh;
                margin: 0;
                padding: 40px 20px;
                text-align: center;
            }
            h1 { color: #00d2ff; }
            .card {
                background: rgba(255,255,255,0.1);
                padding: 30px;
                border-radius: 16px;
                max-width: 500px;
                margin: 30px auto;
            }
            .status {
                background: #00c853;
                color: black;
                padding: 10px 20px;
                border-radius: 20px;
                display: inline-block;
                font-weight: bold;
            }
            code {
                background: rgba(0,0,0,0.3);
                padding: 5px 15px;
                border-radius: 5px;
            }
        </style>
    </head>
    <body>
        <h1>🦅 Trading Bot Dashboard</h1>
        <span class="status">✅ ONLINE</span>
        
        <div class="card">
            <h3>📱 Update Session Token</h3>
            <p>Send to your Telegram bot:</p>
            <code>/session YOUR_TOKEN</code>
        </div>
        
        <div class="card">
            <h3>📊 Status</h3>
            <p>Capital: ₹5,00,000</p>
            <p>Strategy: Iron Condor</p>
            <p>Market: Closed (opens 9:15 AM IST)</p>
        </div>
        
        <p style="color:#666; margin-top:40px;">
            Dashboard is live! Bot trades during market hours.
        </p>
    </body>
    </html>
    '''

@app.route('/health')
def health():
    return jsonify({"status": "ok"})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
