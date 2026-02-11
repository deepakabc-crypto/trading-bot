"""
Flask Web Dashboard
Live monitoring, P&L tracking, and configuration for the trading bot.
"""

import logging
from datetime import datetime
import pytz
from flask import Flask, render_template_string, jsonify, request

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

DASHBOARD_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Nifty Bot - Iron Condor</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0f1117; color: #e1e4e8; padding: 20px;
        }
        .header {
            text-align: center; padding: 20px; margin-bottom: 20px;
            background: linear-gradient(135deg, #1a1f36, #252a40);
            border-radius: 12px; border: 1px solid #2d3348;
        }
        .header h1 { font-size: 1.6em; color: #58a6ff; }
        .header .subtitle { color: #8b949e; margin-top: 5px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; margin-bottom: 20px; }
        .card {
            background: #161b22; border: 1px solid #21262d; border-radius: 10px;
            padding: 20px; transition: border-color 0.2s;
        }
        .card:hover { border-color: #388bfd; }
        .card h3 { color: #58a6ff; margin-bottom: 12px; font-size: 0.9em; text-transform: uppercase; letter-spacing: 1px; }
        .stat { font-size: 2em; font-weight: bold; margin: 8px 0; }
        .stat.profit { color: #3fb950; }
        .stat.loss { color: #f85149; }
        .stat.neutral { color: #8b949e; }
        .status-badge {
            display: inline-block; padding: 4px 12px; border-radius: 20px;
            font-size: 0.85em; font-weight: 600;
        }
        .status-active { background: #0d3321; color: #3fb950; }
        .status-ready { background: #0c2d6b; color: #58a6ff; }
        .status-error { background: #3d1214; color: #f85149; }
        .status-closed { background: #2d2a0f; color: #d29922; }
        .positions-list { font-family: 'Courier New', monospace; font-size: 0.85em; line-height: 1.8; }
        .positions-list div { padding: 4px 8px; border-radius: 4px; margin: 2px 0; background: #0d1117; }
        .config-form { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
        .form-group { display: flex; flex-direction: column; }
        .form-group label { font-size: 0.8em; color: #8b949e; margin-bottom: 4px; }
        .form-group input, .form-group select {
            background: #0d1117; border: 1px solid #21262d; border-radius: 6px;
            color: #e1e4e8; padding: 8px; font-size: 0.9em;
        }
        .form-group input:focus { border-color: #58a6ff; outline: none; }
        .btn {
            padding: 10px 20px; border: none; border-radius: 6px; cursor: pointer;
            font-weight: 600; font-size: 0.9em; transition: all 0.2s;
        }
        .btn-primary { background: #238636; color: white; }
        .btn-primary:hover { background: #2ea043; }
        .btn-danger { background: #da3633; color: white; }
        .btn-danger:hover { background: #f85149; }
        .btn-group { display: flex; gap: 10px; margin-top: 15px; grid-column: 1 / -1; }
        .trades-log { max-height: 200px; overflow-y: auto; font-family: monospace; font-size: 0.8em; }
        .trades-log div { padding: 3px 6px; border-bottom: 1px solid #21262d; }
        .footer { text-align: center; color: #484f58; font-size: 0.8em; margin-top: 20px; }
        @media (max-width: 600px) {
            .grid { grid-template-columns: 1fr; }
            .config-form { grid-template-columns: 1fr; }
            .stat { font-size: 1.5em; }
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>🔱 Nifty Options Bot</h1>
        <div class="subtitle">Iron Condor Strategy | Auto-Trading</div>
    </div>

    <div class="grid">
        <!-- Status Card -->
        <div class="card">
            <h3>📊 Bot Status</h3>
            <div>
                <span class="status-badge" id="statusBadge">Loading...</span>
            </div>
            <div style="margin-top:12px; font-size:0.85em; color:#8b949e;">
                <div>Strategy: <strong style="color:#e1e4e8">Iron Condor</strong></div>
                <div>Last Update: <span id="lastUpdate">-</span></div>
                <div>Time (IST): <span id="currentTime">-</span></div>
            </div>
        </div>

        <!-- P&L Card -->
        <div class="card">
            <h3>💰 Live P&L</h3>
            <div class="stat neutral" id="pnlDisplay">₹0.00</div>
            <div style="font-size:0.85em; color:#8b949e;">
                <div>Entry: <span id="entryStatus">-</span></div>
                <div>Exit: <span id="exitStatus">-</span></div>
            </div>
        </div>

        <!-- Positions Card -->
        <div class="card" style="grid-column: 1 / -1;">
            <h3>📋 Active Positions</h3>
            <div class="positions-list" id="positionsList">
                <div style="color:#8b949e;">No active positions</div>
            </div>
        </div>

        <!-- Configuration Card -->
        <div class="card" style="grid-column: 1 / -1;">
            <h3>⚙️ Configuration</h3>
            <form class="config-form" id="configForm" onsubmit="return saveConfig(event)">
                <div class="form-group">
                    <label>Lot Size (1-10)</label>
                    <input type="number" name="lot_size" id="lotSize" min="1" max="10" value="1">
                </div>
                <div class="form-group">
                    <label>Min Premium (₹)</label>
                    <input type="number" name="min_premium" id="minPremium" step="1" value="20">
                </div>
                <div class="form-group">
                    <label>CE Sell Offset</label>
                    <input type="number" name="ce_sell_offset" id="ceSellOffset" step="50" value="200">
                </div>
                <div class="form-group">
                    <label>CE Buy Offset</label>
                    <input type="number" name="ce_buy_offset" id="ceBuyOffset" step="50" value="400">
                </div>
                <div class="form-group">
                    <label>PE Sell Offset</label>
                    <input type="number" name="pe_sell_offset" id="peSellOffset" step="50" value="200">
                </div>
                <div class="form-group">
                    <label>PE Buy Offset</label>
                    <input type="number" name="pe_buy_offset" id="peBuyOffset" step="50" value="400">
                </div>
                <div class="form-group">
                    <label>Entry Time (HH:MM IST)</label>
                    <input type="time" name="entry_time" id="entryTime" value="09:20">
                </div>
                <div class="form-group">
                    <label>Exit Time (HH:MM IST)</label>
                    <input type="time" name="exit_time" id="exitTime" value="15:15">
                </div>
                <div class="form-group">
                    <label>Max Loss (₹)</label>
                    <input type="number" name="max_loss" id="maxLoss" step="500" value="5000">
                </div>
                <div class="form-group">
                    <label>Target Profit (₹)</label>
                    <input type="number" name="target_profit" id="targetProfit" step="500" value="3000">
                </div>
                <div class="btn-group">
                    <button type="submit" class="btn btn-primary">💾 Save Config</button>
                    <button type="button" class="btn btn-danger" onclick="emergencyExit()">🚨 Emergency Exit</button>
                </div>
            </form>
        </div>

        <!-- Trades Log -->
        <div class="card" style="grid-column: 1 / -1;">
            <h3>📝 Today's Trades</h3>
            <div class="trades-log" id="tradesLog">
                <div style="color:#8b949e;">No trades today</div>
            </div>
        </div>
    </div>

    <div class="footer">
        Nifty Options Bot v2.0 | Iron Condor | ICICI Breeze API | Railway.app
    </div>

    <script>
        function updateDashboard() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    // Status badge
                    const badge = document.getElementById('statusBadge');
                    badge.textContent = data.status;
                    badge.className = 'status-badge ';
                    if (data.status.includes('ACTIVE')) badge.className += 'status-active';
                    else if (data.status === 'READY') badge.className += 'status-ready';
                    else if (data.status.includes('CLOSED') || data.status.includes('STOPPED')) badge.className += 'status-closed';
                    else if (data.status.includes('FAIL') || data.status.includes('ERROR')) badge.className += 'status-error';
                    else badge.className += 'status-ready';

                    // P&L
                    const pnl = document.getElementById('pnlDisplay');
                    pnl.textContent = '₹' + data.pnl.toFixed(2);
                    pnl.className = 'stat ' + (data.pnl > 0 ? 'profit' : data.pnl < 0 ? 'loss' : 'neutral');

                    // Entry/Exit status
                    document.getElementById('entryStatus').textContent = data.entry_done ? '✅ Done' : '⏳ Pending';
                    document.getElementById('exitStatus').textContent = data.exit_done ? '✅ Done' : '⏳ Pending';
                    document.getElementById('lastUpdate').textContent = data.last_update || '-';

                    // Positions
                    const posList = document.getElementById('positionsList');
                    if (data.positions && data.positions.length > 0) {
                        posList.innerHTML = data.positions.map(p => '<div>' + p + '</div>').join('');
                    } else {
                        posList.innerHTML = '<div style="color:#8b949e;">No active positions</div>';
                    }

                    // Config
                    if (data.config) {
                        document.getElementById('lotSize').value = data.config.lot_size;
                        document.getElementById('minPremium').value = data.config.min_premium;
                        document.getElementById('ceSellOffset').value = data.config.ce_sell_offset;
                        document.getElementById('ceBuyOffset').value = data.config.ce_buy_offset;
                        document.getElementById('peSellOffset').value = data.config.pe_sell_offset;
                        document.getElementById('peBuyOffset').value = data.config.pe_buy_offset;
                        document.getElementById('maxLoss').value = data.config.max_loss;
                        document.getElementById('targetProfit').value = data.config.target_profit;
                        if (data.config.entry_time) document.getElementById('entryTime').value = data.config.entry_time;
                        if (data.config.exit_time) document.getElementById('exitTime').value = data.config.exit_time;
                    }

                    // Trades
                    const tradesDiv = document.getElementById('tradesLog');
                    if (data.trades_today && data.trades_today.length > 0) {
                        tradesDiv.innerHTML = data.trades_today.map(t =>
                            '<div>' + (t.leg || '') + ' ' + (t.strike || '') + ' ' +
                            (t.action || '') + ' - ' + (t.success ? '✅' : '❌') + '</div>'
                        ).join('');
                    } else {
                        tradesDiv.innerHTML = '<div style="color:#8b949e;">No trades today</div>';
                    }
                })
                .catch(err => console.error('Update error:', err));

            // Update clock
            const now = new Date().toLocaleString('en-IN', { timeZone: 'Asia/Kolkata', hour12: false });
            document.getElementById('currentTime').textContent = now;
        }

        function saveConfig(event) {
            event.preventDefault();
            const form = document.getElementById('configForm');
            const entryTime = document.getElementById('entryTime').value.split(':');
            const exitTime = document.getElementById('exitTime').value.split(':');

            const data = {
                lot_size: document.getElementById('lotSize').value,
                min_premium: document.getElementById('minPremium').value,
                ce_sell_offset: document.getElementById('ceSellOffset').value,
                ce_buy_offset: document.getElementById('ceBuyOffset').value,
                pe_sell_offset: document.getElementById('peSellOffset').value,
                pe_buy_offset: document.getElementById('peBuyOffset').value,
                entry_hour: entryTime[0],
                entry_minute: entryTime[1],
                exit_hour: exitTime[0],
                exit_minute: exitTime[1],
                max_loss: document.getElementById('maxLoss').value,
                target_profit: document.getElementById('targetProfit').value
            };

            fetch('/api/config', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(data)
            })
            .then(r => r.json())
            .then(d => alert(d.success ? 'Config saved!' : 'Save failed: ' + d.error))
            .catch(err => alert('Error: ' + err));
            return false;
        }

        function emergencyExit() {
            if (confirm('⚠️ EMERGENCY EXIT: Close ALL positions immediately?')) {
                fetch('/api/emergency-exit', { method: 'POST' })
                    .then(r => r.json())
                    .then(d => alert(d.message || 'Exit triggered'))
                    .catch(err => alert('Error: ' + err));
            }
        }

        // Auto-refresh every 10 seconds
        updateDashboard();
        setInterval(updateDashboard, 10000);
    </script>
</body>
</html>
"""


def create_app(bot_state):
    """Create Flask application with dashboard routes."""
    app = Flask(__name__)
    app.secret_key = 'nifty-bot-secret-key'

    @app.route('/')
    def index():
        return render_template_string(DASHBOARD_HTML)

    @app.route('/health')
    def health():
        return jsonify({
            "status": "ok",
            "time": datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST'),
            "bot_status": bot_state.status
        })

    @app.route('/api/status')
    def api_status():
        return jsonify(bot_state.to_dict())

    @app.route('/api/config', methods=['POST'])
    def api_config():
        try:
            data = request.get_json()
            bot_state.config.update(data)
            logger.info(f"Config updated: {data}")
            return jsonify({"success": True})
        except Exception as e:
            logger.error(f"Config update error: {e}")
            return jsonify({"success": False, "error": str(e)})

    @app.route('/api/emergency-exit', methods=['POST'])
    def api_emergency_exit():
        try:
            if bot_state.strategy and bot_state.entry_done and not bot_state.exit_done:
                result = bot_state.strategy.exit_position()
                bot_state.exit_done = True
                bot_state.positions = []
                bot_state.pnl = result.get('realized_pnl', 0)
                bot_state.status = "EMERGENCY_EXIT"

                if bot_state.telegram and bot_state.telegram.enabled:
                    bot_state.telegram.send(
                        f"🚨 *EMERGENCY EXIT*\nAll positions closed\nP&L: ₹{bot_state.pnl:.2f}"
                    )
                return jsonify({"success": True, "message": "Emergency exit completed", "pnl": bot_state.pnl})
            else:
                return jsonify({"success": False, "message": "No active positions to exit"})
        except Exception as e:
            logger.error(f"Emergency exit error: {e}")
            return jsonify({"success": False, "message": str(e)})

    return app
