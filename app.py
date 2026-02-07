"""
================================================================================
🦅 NIFTY OPTIONS TRADING BOT - Full Dashboard
================================================================================
Features:
- Iron Condor & Short Straddle strategies
- Real-time P&L tracking
- Trade history
- Telegram session update
- Backtesting
================================================================================
"""

import os
import json
from datetime import datetime
from flask import Flask, render_template_string, jsonify, request

app = Flask(__name__)

# ============================================
# CONFIGURATION
# ============================================
CAPITAL = int(os.environ.get("CAPITAL", "500000"))
STRATEGY = os.environ.get("STRATEGY", "iron_condor")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
API_SESSION = os.environ.get("API_SESSION", "")

# ============================================
# DATA STORAGE
# ============================================
trades = []
session_token = API_SESSION

def load_trades():
    global trades
    try:
        if os.path.exists('trades.json'):
            with open('trades.json', 'r') as f:
                trades = json.load(f)
    except:
        trades = []

def save_trades():
    try:
        with open('trades.json', 'w') as f:
            json.dump(trades, f)
    except:
        pass

def get_summary():
    load_trades()
    total_trades = len(trades)
    winners = len([t for t in trades if float(t.get('net_pnl', 0)) > 0])
    total_pnl = sum(float(t.get('net_pnl', 0)) for t in trades)
    
    return {
        "total_trades": total_trades,
        "winners": winners,
        "losers": total_trades - winners,
        "win_rate": (winners / total_trades * 100) if total_trades > 0 else 0,
        "total_pnl": total_pnl,
        "capital": CAPITAL,
        "current_value": CAPITAL + total_pnl,
        "strategy": STRATEGY,
        "session_set": bool(session_token)
    }

# ============================================
# HTML TEMPLATE
# ============================================
DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🦅 Trading Bot Dashboard</title>
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
        .container { max-width: 1100px; margin: 0 auto; }
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
        .badge-session { background: #ff9800; color: #000; }
        .badge-session.active { background: #00c853; }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s;
        }
        .card:hover { transform: translateY(-3px); }
        .card-title {
            font-size: 0.8rem;
            color: #888;
            text-transform: uppercase;
            margin-bottom: 10px;
            letter-spacing: 1px;
        }
        .card-value {
            font-size: 2rem;
            font-weight: 700;
        }
        .card-subtitle {
            font-size: 0.8rem;
            color: #666;
            margin-top: 8px;
        }
        .positive { color: #00c853; }
        .negative { color: #f44336; }
        
        .info-box {
            background: rgba(58, 123, 213, 0.15);
            border: 1px solid rgba(58, 123, 213, 0.5);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
        }
        .info-box h3 { margin-bottom: 10px; color: #00d2ff; }
        .info-box code {
            background: rgba(0,0,0,0.4);
            padding: 6px 14px;
            border-radius: 6px;
            font-family: monospace;
            font-size: 1rem;
        }
        
        .chart-container {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 30px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .chart-title { font-size: 1.1rem; margin-bottom: 15px; }
        
        .table-container {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            overflow-x: auto;
            border: 1px solid rgba(255,255,255,0.1);
        }
        table { width: 100%; border-collapse: collapse; }
        th, td {
            padding: 12px 15px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        th {
            color: #888;
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        tr:hover { background: rgba(255,255,255,0.03); }
        
        .btn {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            border: none;
            color: #fff;
            padding: 12px 25px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
            font-size: 0.95rem;
            transition: opacity 0.3s;
        }
        .btn:hover { opacity: 0.85; }
        .btn-secondary {
            background: rgba(255,255,255,0.1);
            border: 1px solid rgba(255,255,255,0.2);
        }
        
        .actions { display: flex; gap: 10px; justify-content: center; margin: 30px 0; flex-wrap: wrap; }
        
        .footer {
            text-align: center;
            color: #555;
            margin-top: 40px;
            padding-top: 20px;
            border-top: 1px solid rgba(255,255,255,0.1);
        }
        
        .strategy-info {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .strategy-card {
            background: rgba(255,255,255,0.03);
            border-radius: 12px;
            padding: 20px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .strategy-card h4 { color: #00d2ff; margin-bottom: 10px; }
        .strategy-card ul { 
            list-style: none; 
            font-size: 0.9rem; 
            color: #aaa;
        }
        .strategy-card li { padding: 5px 0; }
        .strategy-card li::before { content: "✓ "; color: #00c853; }
        
        @media (max-width: 600px) {
            h1 { font-size: 1.4rem; }
            .card-value { font-size: 1.6rem; }
            .grid { grid-template-columns: repeat(2, 1fr); }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🦅 Trading Bot Dashboard</h1>
            <div class="badges">
                <span class="badge badge-strategy" id="strategy-badge">IRON CONDOR</span>
                <span class="badge badge-online">☁️ RAILWAY</span>
                <span class="badge badge-session" id="session-badge">🔑 NO SESSION</span>
            </div>
        </header>
        
        <div class="info-box">
            <h3>📱 Update Session Token via Telegram</h3>
            <p>Every morning, send this to your Telegram bot:</p>
            <p style="margin-top:10px;"><code>/session YOUR_ICICI_TOKEN</code></p>
        </div>
        
        <div class="grid">
            <div class="card">
                <div class="card-title">💰 Total P&L</div>
                <div class="card-value" id="total-pnl">₹0</div>
                <div class="card-subtitle" id="pnl-percent">0.00%</div>
            </div>
            <div class="card">
                <div class="card-title">📊 Win Rate</div>
                <div class="card-value" id="win-rate">0%</div>
                <div class="card-subtitle" id="win-loss">0W / 0L</div>
            </div>
            <div class="card">
                <div class="card-title">📈 Total Trades</div>
                <div class="card-value" id="total-trades">0</div>
                <div class="card-subtitle">Since deployment</div>
            </div>
            <div class="card">
                <div class="card-title">💼 Portfolio</div>
                <div class="card-value" id="portfolio">₹5,00,000</div>
                <div class="card-subtitle" id="capital">Capital: ₹5,00,000</div>
            </div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">📈 Cumulative P&L</div>
            <canvas id="pnlChart" height="100"></canvas>
        </div>
        
        <div class="strategy-info">
            <div class="strategy-card">
                <h4>🦅 Iron Condor Strategy</h4>
                <ul>
                    <li>Limited risk, defined max loss</li>
                    <li>65-70% win rate</li>
                    <li>Best for sideways markets</li>
                    <li>₹50-80K margin per lot</li>
                </ul>
            </div>
            <div class="strategy-card">
                <h4>📊 Short Straddle Strategy</h4>
                <ul>
                    <li>Higher premium collection</li>
                    <li>55-60% win rate</li>
                    <li>Unlimited risk (use stop loss!)</li>
                    <li>₹2.5L margin per lot</li>
                </ul>
            </div>
        </div>
        
        <div class="table-container">
            <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:20px; flex-wrap:wrap; gap:10px;">
                <h3>📋 Recent Trades</h3>
                <button class="btn" onclick="refreshData()">↻ Refresh</button>
            </div>
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
                    <tr><td colspan="6" style="text-align:center;color:#666;padding:30px;">No trades yet. Bot will trade during market hours (9:15 AM - 3:30 PM IST)</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="actions">
            <button class="btn" onclick="addSampleTrade()">+ Add Sample Trade (Test)</button>
            <button class="btn btn-secondary" onclick="clearTrades()">Clear All Trades</button>
        </div>
        
        <div class="footer">
            <p>Strategy: <strong id="footer-strategy">Iron Condor</strong> | 
            Capital: <strong>₹{{ capital }}</strong> | 
            Last updated: <span id="last-update">-</span></p>
            <p style="margin-top:10px;color:#444;">Market Hours: 9:15 AM - 3:30 PM IST (Mon-Fri)</p>
        </div>
    </div>
    
    <script>
        let pnlChart;
        
        function initChart() {
            const ctx = document.getElementById('pnlChart').getContext('2d');
            pnlChart = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Cumulative P&L',
                        data: [],
                        borderColor: '#00d2ff',
                        backgroundColor: 'rgba(0,210,255,0.1)',
                        fill: true,
                        tension: 0.4,
                        pointRadius: 4,
                        pointBackgroundColor: '#00d2ff'
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { 
                            grid: { color: 'rgba(255,255,255,0.1)' }, 
                            ticks: { color: '#888', callback: v => '₹' + v.toLocaleString() }
                        },
                        x: { 
                            grid: { color: 'rgba(255,255,255,0.05)' }, 
                            ticks: { color: '#888' }
                        }
                    }
                }
            });
        }
        
        async function refreshData() {
            try {
                const res = await fetch('/api/summary');
                const data = await res.json();
                
                // Update strategy badge
                document.getElementById('strategy-badge').textContent = (data.strategy || 'iron_condor').toUpperCase().replace('_', ' ');
                document.getElementById('footer-strategy').textContent = (data.strategy || 'iron_condor').replace('_', ' ');
                
                // Update session badge
                const sessionBadge = document.getElementById('session-badge');
                if (data.session_set) {
                    sessionBadge.textContent = '🔑 SESSION OK';
                    sessionBadge.classList.add('active');
                } else {
                    sessionBadge.textContent = '🔑 NO SESSION';
                    sessionBadge.classList.remove('active');
                }
                
                // Update cards
                const pnl = data.total_pnl || 0;
                document.getElementById('total-pnl').textContent = '₹' + pnl.toLocaleString('en-IN');
                document.getElementById('total-pnl').className = 'card-value ' + (pnl >= 0 ? 'positive' : 'negative');
                document.getElementById('pnl-percent').textContent = (pnl >= 0 ? '+' : '') + (pnl / data.capital * 100).toFixed(2) + '%';
                
                document.getElementById('win-rate').textContent = data.win_rate.toFixed(1) + '%';
                document.getElementById('win-loss').textContent = data.winners + 'W / ' + data.losers + 'L';
                document.getElementById('total-trades').textContent = data.total_trades;
                document.getElementById('portfolio').textContent = '₹' + data.current_value.toLocaleString('en-IN');
                document.getElementById('capital').textContent = 'Capital: ₹' + data.capital.toLocaleString('en-IN');
                
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
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666;padding:30px;">No trades yet. Bot will trade during market hours.</td></tr>';
                return;
            }
            
            tbody.innerHTML = trades.slice(-10).reverse().map(t => {
                const pnl = parseFloat(t.net_pnl || 0);
                return `<tr>
                    <td>${t.entry_date || t.date || '-'}</td>
                    <td>${(t.strategy || 'IRON_CONDOR').replace('_', ' ')}</td>
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
                pnlChart.update();
                return;
            }
            
            let cum = 0;
            const data = trades.map(t => { cum += parseFloat(t.net_pnl || 0); return cum; });
            pnlChart.data.labels = trades.map((t, i) => t.entry_date || `Trade ${i+1}`);
            pnlChart.data.datasets[0].data = data;
            pnlChart.update();
        }
        
        async function addSampleTrade() {
            const isProfit = Math.random() > 0.35; // 65% win rate
            const pnl = isProfit ? 
                Math.floor(Math.random() * 1500) + 500 : 
                -Math.floor(Math.random() * 2000) - 500;
            
            const trade = {
                entry_date: new Date().toISOString().split('T')[0],
                strategy: 'IRON_CONDOR',
                entry_premium: Math.floor(Math.random() * 50) + 40,
                exit_premium: Math.floor(Math.random() * 30) + 10,
                net_pnl: pnl,
                exit_reason: isProfit ? 'TARGET' : (Math.random() > 0.5 ? 'STOP_LOSS' : 'TIME_EXIT')
            };
            
            await fetch('/api/add_trade', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(trade)
            });
            
            refreshData();
        }
        
        async function clearTrades() {
            if (confirm('Clear all trades? This cannot be undone.')) {
                await fetch('/api/clear_trades', { method: 'POST' });
                refreshData();
            }
        }
        
        // Initialize
        initChart();
        refreshData();
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
""".replace('{{ capital }}', f'{CAPITAL:,}')

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
    load_trades()
    return jsonify(trades)

@app.route('/api/add_trade', methods=['POST'])
def api_add_trade():
    trade = request.json
    trade['timestamp'] = datetime.now().isoformat()
    trades.append(trade)
    save_trades()
    return jsonify({"status": "success"})

@app.route('/api/clear_trades', methods=['POST'])
def api_clear_trades():
    global trades
    trades = []
    save_trades()
    return jsonify({"status": "success"})

@app.route('/api/update_session', methods=['POST'])
def api_update_session():
    global session_token
    data = request.json
    session_token = data.get('token', '')
    return jsonify({"status": "success", "session_set": bool(session_token)})

@app.route('/health')
def health():
    return jsonify({
        "status": "ok", 
        "time": datetime.now().isoformat(),
        "strategy": STRATEGY,
        "capital": CAPITAL
    })

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print(f"🦅 Starting Trading Dashboard on port {port}...")
    app.run(host='0.0.0.0', port=port)
