"""
================================================================================
TRADING DASHBOARD - Railway.app Cloud Version
================================================================================
Access your trading dashboard from anywhere.
Deployed on Railway with Gunicorn.

Features:
- Real-time P&L
- Trade history
- Performance charts
- Mobile responsive
================================================================================
"""

from flask import Flask, render_template_string, jsonify, request
import json
import os
from datetime import datetime
from config import *

app = Flask(__name__)

# ============================================
# DATA STORAGE
# ============================================
class DashboardData:
    def __init__(self):
        self.trades = []
        self.load_trades()
    
    def load_trades(self):
        """Load trades from file"""
        try:
            if os.path.exists('dashboard_trades.json'):
                with open('dashboard_trades.json', 'r') as f:
                    self.trades = json.load(f)
        except:
            self.trades = []
    
    def save_trades(self):
        """Save trades to file"""
        try:
            with open('dashboard_trades.json', 'w') as f:
                json.dump(self.trades, f)
        except:
            pass
    
    def add_trade(self, trade: dict):
        trade['timestamp'] = datetime.now().isoformat()
        self.trades.append(trade)
        self.save_trades()
    
    def get_summary(self) -> dict:
        total_trades = len(self.trades)
        winners = len([t for t in self.trades if float(t.get('net_pnl', 0)) > 0])
        total_pnl = sum(float(t.get('net_pnl', 0)) for t in self.trades)
        
        return {
            "total_trades": total_trades,
            "winners": winners,
            "losers": total_trades - winners,
            "win_rate": (winners / total_trades * 100) if total_trades > 0 else 0,
            "total_pnl": total_pnl,
            "capital": CAPITAL,
            "current_value": CAPITAL + total_pnl,
            "strategy": STRATEGY
        }

dashboard_data = DashboardData()

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
            font-size: 1.6rem;
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        
        .badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        
        .badge-strategy { background: #3a7bd5; }
        .badge-cloud { background: #00c853; color: #000; }
        
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s;
        }
        
        .card:hover { transform: translateY(-3px); }
        
        .card-title {
            font-size: 0.85rem;
            color: #888;
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        
        .card-value {
            font-size: 1.8rem;
            font-weight: 700;
        }
        
        .positive { color: #00c853; }
        .negative { color: #f44336; }
        
        .card-subtitle {
            font-size: 0.8rem;
            color: #666;
            margin-top: 5px;
        }
        
        .chart-container {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 30px;
        }
        
        .chart-title { font-size: 1.1rem; margin-bottom: 15px; }
        
        .table-container {
            background: rgba(255,255,255,0.05);
            border-radius: 16px;
            padding: 24px;
            overflow-x: auto;
        }
        
        table { width: 100%; border-collapse: collapse; }
        
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        
        th {
            color: #888;
            font-size: 0.75rem;
            text-transform: uppercase;
        }
        
        .btn {
            background: linear-gradient(90deg, #00d2ff, #3a7bd5);
            border: none;
            color: #fff;
            padding: 10px 20px;
            border-radius: 8px;
            cursor: pointer;
            font-weight: 600;
        }
        
        .btn:hover { opacity: 0.9; }
        
        .info-box {
            background: rgba(58, 123, 213, 0.2);
            border: 1px solid #3a7bd5;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 30px;
        }
        
        .info-box h3 { margin-bottom: 10px; }
        .info-box code {
            background: rgba(0,0,0,0.3);
            padding: 2px 8px;
            border-radius: 4px;
            font-family: monospace;
        }
        
        .last-update {
            text-align: center;
            color: #666;
            font-size: 0.8rem;
            margin-top: 30px;
        }
        
        @media (max-width: 600px) {
            h1 { font-size: 1.3rem; }
            .card-value { font-size: 1.5rem; }
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🦅 Trading Bot Dashboard</h1>
            <div>
                <span class="badge badge-strategy" id="strategy-badge">LOADING...</span>
                <span class="badge badge-cloud">☁️ RAILWAY</span>
            </div>
        </header>
        
        <div class="info-box">
            <h3>📱 Update Session Token via Telegram</h3>
            <p>Send this command to your bot: <code>/session YOUR_NEW_TOKEN</code></p>
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
                <div class="card-value" id="portfolio-value">₹5,00,000</div>
                <div class="card-subtitle" id="capital">Capital: ₹5,00,000</div>
            </div>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">📈 Cumulative P&L</div>
            <canvas id="pnlChart" height="100"></canvas>
        </div>
        
        <div class="table-container">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
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
                    <tr><td colspan="6" style="text-align:center;color:#666;">No trades yet</td></tr>
                </tbody>
            </table>
        </div>
        
        <div class="last-update">
            Last updated: <span id="last-update">-</span>
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
                        label: 'P&L',
                        data: [],
                        borderColor: '#00d2ff',
                        backgroundColor: 'rgba(0,210,255,0.1)',
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    plugins: { legend: { display: false } },
                    scales: {
                        y: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#888' } },
                        x: { grid: { color: 'rgba(255,255,255,0.1)' }, ticks: { color: '#888' } }
                    }
                }
            });
        }
        
        async function refreshData() {
            try {
                const res = await fetch('/api/summary');
                const data = await res.json();
                
                document.getElementById('strategy-badge').textContent = data.strategy?.toUpperCase() || 'BOT';
                
                const pnl = data.total_pnl || 0;
                document.getElementById('total-pnl').textContent = '₹' + pnl.toLocaleString('en-IN');
                document.getElementById('total-pnl').className = 'card-value ' + (pnl >= 0 ? 'positive' : 'negative');
                document.getElementById('pnl-percent').textContent = (pnl >= 0 ? '+' : '') + (pnl / data.capital * 100).toFixed(2) + '%';
                
                document.getElementById('win-rate').textContent = data.win_rate.toFixed(1) + '%';
                document.getElementById('win-loss').textContent = data.winners + 'W / ' + data.losers + 'L';
                document.getElementById('total-trades').textContent = data.total_trades;
                document.getElementById('portfolio-value').textContent = '₹' + data.current_value.toLocaleString('en-IN');
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
            if (!trades.length) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666;">No trades yet</td></tr>';
                return;
            }
            
            tbody.innerHTML = trades.slice(-10).reverse().map(t => {
                const pnl = parseFloat(t.net_pnl || 0);
                return `<tr>
                    <td>${t.entry_date || '-'}</td>
                    <td>${t.strategy || '-'}</td>
                    <td>₹${parseFloat(t.entry_premium || 0).toFixed(2)}</td>
                    <td>₹${parseFloat(t.exit_premium || 0).toFixed(2)}</td>
                    <td class="${pnl >= 0 ? 'positive' : 'negative'}">${pnl >= 0 ? '+' : ''}₹${pnl.toLocaleString('en-IN')}</td>
                    <td>${t.exit_reason || '-'}</td>
                </tr>`;
            }).join('');
        }
        
        function updateChart(trades) {
            if (!trades.length) return;
            let cum = 0;
            const data = trades.map(t => { cum += parseFloat(t.net_pnl || 0); return cum; });
            pnlChart.data.labels = trades.map(t => t.entry_date || '');
            pnlChart.data.datasets[0].data = data;
            pnlChart.update();
        }
        
        initChart();
        refreshData();
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
"""

# ============================================
# ROUTES
# ============================================
@app.route('/')
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route('/api/summary')
def get_summary():
    dashboard_data.load_trades()
    return jsonify(dashboard_data.get_summary())

@app.route('/api/trades')
def get_trades():
    dashboard_data.load_trades()
    return jsonify(dashboard_data.trades)

@app.route('/api/add_trade', methods=['POST'])
def add_trade():
    trade = request.json
    dashboard_data.add_trade(trade)
    return jsonify({"status": "success"})

@app.route('/health')
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
