"""
================================================================================
🖥️ TRADING DASHBOARD - Flask Web App
================================================================================
Features:
- Strategy selection (Iron Condor / Straddle / Both)
- Real-time P&L tracking
- Trade history
- Session token update
- Bot status monitoring
================================================================================
"""

from flask import Flask, render_template_string, jsonify, request
import json
import os
from datetime import datetime

app = Flask(__name__)

# ============================================
# IMPORT SETTINGS
# ============================================
try:
    from settings import *
except ImportError:
    CAPITAL = 500000
    STRATEGY = "iron_condor"
    PORT = int(os.environ.get("PORT", 5000))

# ============================================
# DATA STORAGE
# ============================================
DATA_FILE = "bot_data.json"

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {
        "trades": [],
        "bot_running": False,
        "strategy": STRATEGY,
        "session_token": "",
        "daily_pnl": 0,
        "total_pnl": 0
    }

def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def get_summary():
    data = load_data()
    trades = data.get("trades", [])
    total_trades = len(trades)
    winners = len([t for t in trades if float(t.get('pnl', 0)) > 0])
    total_pnl = sum(float(t.get('pnl', 0)) for t in trades)
    
    return {
        "total_trades": total_trades,
        "winners": winners,
        "losers": total_trades - winners,
        "win_rate": (winners / total_trades * 100) if total_trades > 0 else 0,
        "total_pnl": total_pnl,
        "daily_pnl": data.get("daily_pnl", 0),
        "capital": CAPITAL,
        "current_value": CAPITAL + total_pnl,
        "strategy": data.get("strategy", STRATEGY),
        "bot_running": data.get("bot_running", False),
        "session_set": bool(data.get("session_token"))
    }

# ============================================
# HTML DASHBOARD
# ============================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 Nifty Trading Bot</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 50%, #16213e 100%);
            color: #fff;
            min-height: 100vh;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 20px 0;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            margin-bottom: 30px;
            flex-wrap: wrap;
            gap: 15px;
        }
        h1 {
            font-size: 1.8rem;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .badges { display: flex; gap: 10px; flex-wrap: wrap; }
        .badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .badge-strategy { background: #3a7bd5; }
        .badge-online { background: #00c853; color: #000; }
        .badge-offline { background: #f44336; }
        .badge-session { background: #ff9800; color: #000; }
        .badge-session.active { background: #00c853; }
        
        .section {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .section-title {
            font-size: 1.1rem;
            margin-bottom: 20px;
            color: #00d2ff;
        }
        
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; }
        .card {
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 20px;
            text-align: center;
        }
        .card-title { font-size: 0.75rem; color: #888; text-transform: uppercase; margin-bottom: 8px; }
        .card-value { font-size: 1.8rem; font-weight: 700; }
        .card-subtitle { font-size: 0.8rem; color: #666; margin-top: 5px; }
        .positive { color: #00c853; }
        .negative { color: #f44336; }
        
        .strategy-selector {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .strategy-btn {
            background: rgba(255,255,255,0.05);
            border: 2px solid rgba(255,255,255,0.1);
            border-radius: 12px;
            padding: 20px;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
        }
        .strategy-btn:hover { border-color: #3a7bd5; }
        .strategy-btn.active { border-color: #00c853; background: rgba(0,200,83,0.1); }
        .strategy-btn h4 { margin-bottom: 8px; }
        .strategy-btn p { font-size: 0.8rem; color: #888; }
        
        .session-input {
            display: flex;
            gap: 10px;
            margin-top: 15px;
        }
        .session-input input {
            flex: 1;
            padding: 12px 16px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            background: rgba(255,255,255,0.05);
            color: #fff;
            font-size: 1rem;
        }
        .btn {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            border: none;
            color: #fff;
            padding: 12px 24px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            transition: opacity 0.3s;
        }
        .btn:hover { opacity: 0.85; }
        .btn-danger { background: linear-gradient(90deg, #f44336, #d32f2f); }
        .btn-success { background: linear-gradient(90deg, #00c853, #00a844); }
        
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { color: #888; font-size: 0.75rem; text-transform: uppercase; }
        
        .info-text { color: #888; font-size: 0.9rem; margin-top: 10px; }
        .info-text code { background: rgba(0,0,0,0.3); padding: 2px 8px; border-radius: 4px; }
        
        .chart-container { height: 200px; margin-top: 15px; }
        
        @media (max-width: 600px) {
            h1 { font-size: 1.4rem; }
            .card-value { font-size: 1.4rem; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🤖 Nifty Trading Bot</h1>
            <div class="badges">
                <span class="badge badge-strategy" id="strategy-badge">IRON CONDOR</span>
                <span class="badge" id="bot-badge">⏸️ STOPPED</span>
                <span class="badge badge-session" id="session-badge">🔑 NO SESSION</span>
            </div>
        </header>
        
        <!-- P&L Cards -->
        <div class="section">
            <div class="grid">
                <div class="card">
                    <div class="card-title">💰 Total P&L</div>
                    <div class="card-value" id="total-pnl">₹0</div>
                    <div class="card-subtitle" id="pnl-percent">0.00%</div>
                </div>
                <div class="card">
                    <div class="card-title">📅 Today's P&L</div>
                    <div class="card-value" id="daily-pnl">₹0</div>
                </div>
                <div class="card">
                    <div class="card-title">📊 Win Rate</div>
                    <div class="card-value" id="win-rate">0%</div>
                    <div class="card-subtitle" id="win-loss">0W / 0L</div>
                </div>
                <div class="card">
                    <div class="card-title">💼 Portfolio</div>
                    <div class="card-value" id="portfolio">₹5,00,000</div>
                </div>
            </div>
        </div>
        
        <!-- Strategy Selection -->
        <div class="section">
            <div class="section-title">📊 Select Strategy</div>
            <div class="strategy-selector">
                <div class="strategy-btn" data-strategy="iron_condor" onclick="selectStrategy('iron_condor')">
                    <h4>🦅 Iron Condor</h4>
                    <p>Limited risk • 65-70% win rate</p>
                </div>
                <div class="strategy-btn" data-strategy="straddle" onclick="selectStrategy('straddle')">
                    <h4>📊 Short Straddle</h4>
                    <p>Higher premium • 55-60% win rate</p>
                </div>
                <div class="strategy-btn" data-strategy="both" onclick="selectStrategy('both')">
                    <h4>🔄 Both Strategies</h4>
                    <p>Diversified approach</p>
                </div>
            </div>
        </div>
        
        <!-- Session Token -->
        <div class="section">
            <div class="section-title">🔑 Update Session Token</div>
            <p class="info-text">Get token from ICICI Direct and paste below, or send <code>/session TOKEN</code> via Telegram</p>
            <div class="session-input">
                <input type="text" id="session-token" placeholder="Paste your session token here...">
                <button class="btn" onclick="updateSession()">Update Token</button>
            </div>
        </div>
        
        <!-- Bot Controls -->
        <div class="section">
            <div class="section-title">🎮 Bot Controls</div>
            <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                <button class="btn btn-success" id="start-btn" onclick="startBot()">▶️ Start Bot</button>
                <button class="btn btn-danger" id="stop-btn" onclick="stopBot()">⏹️ Stop Bot</button>
                <button class="btn" onclick="refreshData()">🔄 Refresh</button>
            </div>
        </div>
        
        <!-- P&L Chart -->
        <div class="section">
            <div class="section-title">📈 P&L History</div>
            <div class="chart-container">
                <canvas id="pnlChart"></canvas>
            </div>
        </div>
        
        <!-- Trade History -->
        <div class="section">
            <div class="section-title">📋 Recent Trades</div>
            <table>
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Strategy</th>
                        <th>Entry</th>
                        <th>Exit</th>
                        <th>P&L</th>
                        <th>Reason</th>
                    </tr>
                </thead>
                <tbody id="trades-body">
                    <tr><td colspan="6" style="text-align:center;color:#666;padding:30px;">No trades yet</td></tr>
                </tbody>
            </table>
        </div>
        
        <div style="text-align:center; color:#555; margin-top:30px;">
            <p>Market Hours: 9:15 AM - 3:30 PM IST (Mon-Fri)</p>
            <p style="margin-top:5px;">Last updated: <span id="last-update">-</span></p>
        </div>
    </div>
    
    <script>
        let pnlChart;
        
        function initChart() {
            const ctx = document.getElementById('pnlChart').getContext('2d');
            pnlChart = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'P&L', data: [], borderColor: '#00d2ff', backgroundColor: 'rgba(0,210,255,0.1)', fill: true, tension: 0.4 }] },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#888' } },
                        x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#888' } }
                    }
                }
            });
        }
        
        async function refreshData() {
            try {
                const res = await fetch('/api/summary');
                const data = await res.json();
                
                // Update badges
                document.getElementById('strategy-badge').textContent = (data.strategy || 'iron_condor').toUpperCase().replace('_', ' ');
                
                const botBadge = document.getElementById('bot-badge');
                if (data.bot_running) {
                    botBadge.textContent = '🟢 RUNNING';
                    botBadge.className = 'badge badge-online';
                } else {
                    botBadge.textContent = '⏸️ STOPPED';
                    botBadge.className = 'badge badge-offline';
                }
                
                const sessionBadge = document.getElementById('session-badge');
                if (data.session_set) {
                    sessionBadge.textContent = '🔑 SESSION OK';
                    sessionBadge.className = 'badge badge-session active';
                } else {
                    sessionBadge.textContent = '🔑 NO SESSION';
                    sessionBadge.className = 'badge badge-session';
                }
                
                // Update cards
                const pnl = data.total_pnl || 0;
                document.getElementById('total-pnl').textContent = '₹' + pnl.toLocaleString('en-IN');
                document.getElementById('total-pnl').className = 'card-value ' + (pnl >= 0 ? 'positive' : 'negative');
                document.getElementById('pnl-percent').textContent = (pnl >= 0 ? '+' : '') + (pnl / data.capital * 100).toFixed(2) + '%';
                
                const dailyPnl = data.daily_pnl || 0;
                document.getElementById('daily-pnl').textContent = '₹' + dailyPnl.toLocaleString('en-IN');
                document.getElementById('daily-pnl').className = 'card-value ' + (dailyPnl >= 0 ? 'positive' : 'negative');
                
                document.getElementById('win-rate').textContent = data.win_rate.toFixed(1) + '%';
                document.getElementById('win-loss').textContent = data.winners + 'W / ' + data.losers + 'L';
                document.getElementById('portfolio').textContent = '₹' + data.current_value.toLocaleString('en-IN');
                
                // Update strategy buttons
                document.querySelectorAll('.strategy-btn').forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.strategy === data.strategy);
                });
                
                document.getElementById('last-update').textContent = new Date().toLocaleString();
                
                // Load trades
                const tradesRes = await fetch('/api/trades');
                const trades = await tradesRes.json();
                updateTable(trades);
                updateChart(trades);
                
            } catch (e) {
                console.error('Error:', e);
            }
        }
        
        function updateTable(trades) {
            const tbody = document.getElementById('trades-body');
            if (!trades || trades.length === 0) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666;padding:30px;">No trades yet</td></tr>';
                return;
            }
            
            tbody.innerHTML = trades.slice(-10).reverse().map(t => {
                const pnl = parseFloat(t.pnl || 0);
                return `<tr>
                    <td>${t.date || '-'}</td>
                    <td>${(t.strategy || '-').replace('_', ' ')}</td>
                    <td>₹${parseFloat(t.entry_premium || 0).toFixed(0)}</td>
                    <td>₹${parseFloat(t.exit_premium || 0).toFixed(0)}</td>
                    <td class="${pnl >= 0 ? 'positive' : 'negative'}">${pnl >= 0 ? '+' : ''}₹${pnl.toLocaleString('en-IN')}</td>
                    <td>${t.exit_reason || '-'}</td>
                </tr>`;
            }).join('');
        }
        
        function updateChart(trades) {
            if (!trades || trades.length === 0) {
                pnlChart.data.labels = ['Start'];
                pnlChart.data.datasets[0].data = [0];
            } else {
                let cum = 0;
                pnlChart.data.labels = trades.map((t, i) => t.date || `#${i+1}`);
                pnlChart.data.datasets[0].data = trades.map(t => { cum += parseFloat(t.pnl || 0); return cum; });
            }
            pnlChart.update();
        }
        
        async function selectStrategy(strategy) {
            await fetch('/api/strategy', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ strategy })
            });
            refreshData();
        }
        
        async function updateSession() {
            const token = document.getElementById('session-token').value.trim();
            if (!token) { alert('Please enter a token'); return; }
            
            await fetch('/api/session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token })
            });
            document.getElementById('session-token').value = '';
            refreshData();
            alert('Session token updated!');
        }
        
        async function startBot() {
            await fetch('/api/bot/start', { method: 'POST' });
            refreshData();
        }
        
        async function stopBot() {
            await fetch('/api/bot/stop', { method: 'POST' });
            refreshData();
        }
        
        initChart();
        refreshData();
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
"""

# ============================================
# API ROUTES
# ============================================
@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/summary')
def api_summary():
    return jsonify(get_summary())

@app.route('/api/trades')
def api_trades():
    data = load_data()
    return jsonify(data.get("trades", []))

@app.route('/api/strategy', methods=['POST'])
def api_strategy():
    data = load_data()
    data["strategy"] = request.json.get("strategy", "iron_condor")
    save_data(data)
    return jsonify({"status": "success", "strategy": data["strategy"]})

@app.route('/api/session', methods=['POST'])
def api_session():
    data = load_data()
    data["session_token"] = request.json.get("token", "")
    save_data(data)
    # Also update environment variable for the bot
    os.environ["API_SESSION"] = data["session_token"]
    return jsonify({"status": "success"})

@app.route('/api/bot/start', methods=['POST'])
def api_bot_start():
    data = load_data()
    data["bot_running"] = True
    save_data(data)
    return jsonify({"status": "success"})

@app.route('/api/bot/stop', methods=['POST'])
def api_bot_stop():
    data = load_data()
    data["bot_running"] = False
    save_data(data)
    return jsonify({"status": "success"})

@app.route('/api/add_trade', methods=['POST'])
def api_add_trade():
    data = load_data()
    trade = request.json
    trade['timestamp'] = datetime.now().isoformat()
    data["trades"].append(trade)
    data["total_pnl"] = sum(float(t.get('pnl', 0)) for t in data["trades"])
    save_data(data)
    return jsonify({"status": "success"})

@app.route('/api/daily_reset', methods=['POST'])
def api_daily_reset():
    data = load_data()
    data["daily_pnl"] = 0
    save_data(data)
    return jsonify({"status": "success"})

@app.route('/health')
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🖥️ Dashboard starting on port {port}...")
    app.run(host='0.0.0.0', port=port, debug=False)
