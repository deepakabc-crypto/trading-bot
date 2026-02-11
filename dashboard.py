"""
Flask Web Dashboard – Multi-Index v3.2
Start/Stop bot, Update session token, per-index config + emergency exit.
"""

import logging
from datetime import datetime
import pytz
from flask import Flask, render_template_string, jsonify, request

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

DASHBOARD_HTML = r"""
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Multi-Index Options Bot</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0f1117;color:#e1e4e8;padding:16px;max-width:960px;margin:0 auto}
.hdr{text-align:center;padding:18px;margin-bottom:16px;background:linear-gradient(135deg,#1a1f36,#252a40);border-radius:12px;border:1px solid #2d3348}
.hdr h1{font-size:1.5em;color:#58a6ff}
.hdr .sub{color:#8b949e;margin-top:4px;font-size:.88em}

/* ── Control bar ─────────────────────────── */
.ctrl-bar{display:flex;gap:10px;align-items:center;justify-content:center;flex-wrap:wrap;margin-bottom:16px;padding:14px;background:#161b22;border:1px solid #21262d;border-radius:10px}
.ctrl-bar .status-pill{padding:5px 14px;border-radius:20px;font-weight:700;font-size:.85em}
.pill-running{background:#0d3321;color:#3fb950}
.pill-stopped{background:#3d1214;color:#f85149}
.pill-disconnected{background:#2d2a0f;color:#d29922}
.ctrl-bar .info{font-size:.78em;color:#8b949e}
.btn{padding:9px 18px;border:none;border-radius:6px;cursor:pointer;font-weight:600;font-size:.85em;transition:all .15s}
.btn-start{background:#238636;color:#fff}.btn-start:hover{background:#2ea043}
.btn-stop{background:#da3633;color:#fff}.btn-stop:hover{background:#f85149}
.btn-b{background:#1f6feb;color:#fff}.btn-b:hover{background:#388bfd}
.btn-g{background:#238636;color:#fff}.btn-g:hover{background:#2ea043}
.btn-r{background:#da3633;color:#fff}.btn-r:hover{background:#f85149}
.btn-y{background:#9e6a03;color:#fff}.btn-y:hover{background:#bb8009}
.btn-sm{padding:6px 12px;font-size:.8em}
.btn:disabled{opacity:.4;cursor:not-allowed}

/* ── Token section ───────────────────────── */
.token-bar{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:16px;padding:14px;background:#161b22;border:1px solid #21262d;border-radius:10px}
.token-bar label{font-size:.8em;color:#8b949e;white-space:nowrap}
.token-bar input{flex:1;min-width:180px;background:#0d1117;border:1px solid #21262d;border-radius:6px;color:#e1e4e8;padding:7px 10px;font-size:.85em;font-family:monospace}
.token-bar input:focus{border-color:#58a6ff;outline:none}
.token-bar .meta{font-size:.72em;color:#484f58}

/* ── Combined P&L ────────────────────────── */
.cpnl{text-align:center;padding:14px;margin-bottom:16px;border-radius:10px;border:1px solid #21262d;background:#161b22}
.cpnl .lbl{font-size:.78em;color:#8b949e;text-transform:uppercase;letter-spacing:1px}
.cpnl .val{font-size:2.1em;font-weight:700;margin:4px 0}
.profit{color:#3fb950}.loss{color:#f85149}.neutral{color:#8b949e}

/* ── Index cards ─────────────────────────── */
.idx-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px;margin-bottom:16px}
.card{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:16px;transition:border-color .2s}
.card:hover{border-color:#388bfd}
.card h3{color:#58a6ff;margin-bottom:8px;font-size:.83em;text-transform:uppercase;letter-spacing:1px;display:flex;justify-content:space-between;align-items:center}
.badge{display:inline-block;padding:2px 10px;border-radius:14px;font-size:.72em;font-weight:600}
.b-active{background:#0d3321;color:#3fb950}.b-ready{background:#0c2d6b;color:#58a6ff}
.b-error{background:#3d1214;color:#f85149}.b-closed{background:#2d2a0f;color:#d29922}
.b-disabled{background:#1c1c1c;color:#555}.b-stopped{background:#2d1a1a;color:#f85149}
.stat{font-size:1.7em;font-weight:700;margin:5px 0}
.meta{font-size:.8em;color:#8b949e;line-height:1.7}
.meta strong{color:#c9d1d9}
.pos-list{font-family:'Courier New',monospace;font-size:.78em;line-height:1.6;margin-top:6px}
.pos-list div{padding:2px 5px;border-radius:4px;margin:2px 0;background:#0d1117}

/* ── Sections ────────────────────────────── */
.section{background:#161b22;border:1px solid #21262d;border-radius:10px;padding:16px;margin-bottom:14px}
.section h3{color:#58a6ff;margin-bottom:10px;font-size:.83em;text-transform:uppercase;letter-spacing:1px}
.cfg-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:8px}
.fg{display:flex;flex-direction:column}
.fg label{font-size:.72em;color:#8b949e;margin-bottom:2px}
.fg input,.fg select{background:#0d1117;border:1px solid #21262d;border-radius:6px;color:#e1e4e8;padding:6px;font-size:.83em}
.fg input:focus{border-color:#58a6ff;outline:none}
.btn-row{display:flex;gap:8px;margin-top:12px;flex-wrap:wrap}
.toggle{display:flex;align-items:center;gap:8px;font-size:.82em}
.toggle input{width:17px;height:17px}
.trades{max-height:160px;overflow-y:auto;font-family:monospace;font-size:.76em}
.trades div{padding:2px 5px;border-bottom:1px solid #21262d}
.footer{text-align:center;color:#484f58;font-size:.72em;margin-top:16px}
@media(max-width:600px){.idx-grid{grid-template-columns:1fr}.cfg-grid{grid-template-columns:1fr}.stat{font-size:1.2em}.ctrl-bar{flex-direction:column}}
</style>
</head>
<body>

<div class="hdr">
  <h1>🔱 Multi-Index Options Bot</h1>
  <div class="sub">Iron Condor | NIFTY (65/lot · NFO) + SENSEX (20/lot · BFO) | v3.2</div>
</div>

<!-- ═══ Bot Control Bar ═══ -->
<div class="ctrl-bar">
  <span class="status-pill pill-stopped" id="botPill">STOPPED</span>
  <button class="btn btn-start" id="btnStart" onclick="startBot()">▶️ Start Bot</button>
  <button class="btn btn-stop" id="btnStop" onclick="stopBot(false)" disabled>⏹️ Stop Bot</button>
  <button class="btn btn-y btn-sm" id="btnStopExit" onclick="stopBot(true)" disabled>⏹️ Stop & Exit All</button>
  <span class="info">Started: <span id="botStartTime">-</span> | IST: <span id="clock">-</span></span>
</div>

<!-- ═══ Token Update Bar ═══ -->
<div class="token-bar">
  <label>🔑 Session Token:</label>
  <input type="text" id="tokenInput" placeholder="Paste new Breeze session token here...">
  <button class="btn btn-b btn-sm" onclick="updateToken()">Update & Reconnect</button>
  <div style="width:100%">
    <span class="meta">Current: <span id="tokenPreview">-</span> | API: <span id="apiStatus">-</span> | Last update: <span id="lastTokenUpdate">-</span></span>
  </div>
</div>

<!-- ═══ Combined P&L ═══ -->
<div class="cpnl">
  <div class="lbl">Combined P&L</div>
  <div class="val neutral" id="combinedPnl">₹0.00</div>
</div>

<!-- ═══ Index Cards ═══ -->
<div class="idx-grid">
  <div class="card">
    <h3>NIFTY <span class="badge b-ready" id="niftyBadge">-</span></h3>
    <div class="stat neutral" id="niftyPnl">₹0.00</div>
    <div class="meta">
      Lot: <strong>65</strong> × <span id="niftyLots">1</span> | Exchange: <strong>NFO</strong><br>
      Entry: <span id="niftyEntry">⏳</span> | Exit: <span id="niftyExit">⏳</span> | Updated: <span id="niftyUpdate">-</span>
    </div>
    <div class="pos-list" id="niftyPos"><div style="color:#8b949e">No positions</div></div>
  </div>
  <div class="card">
    <h3>SENSEX <span class="badge b-ready" id="sensexBadge">-</span></h3>
    <div class="stat neutral" id="sensexPnl">₹0.00</div>
    <div class="meta">
      Lot: <strong>20</strong> × <span id="sensexLots">1</span> | Exchange: <strong>BFO</strong><br>
      Entry: <span id="sensexEntry">⏳</span> | Exit: <span id="sensexExit">⏳</span> | Updated: <span id="sensexUpdate">-</span>
    </div>
    <div class="pos-list" id="sensexPos"><div style="color:#8b949e">No positions</div></div>
  </div>
</div>

<!-- ═══ Global Config ═══ -->
<div class="section">
  <h3>⚙️ Global Settings</h3>
  <form id="globalForm" onsubmit="return saveGlobal(event)">
    <div class="cfg-grid">
      <div class="fg"><label>Entry Time (IST)</label><input type="time" id="gEntry" value="09:20"></div>
      <div class="fg"><label>Exit Time (IST)</label><input type="time" id="gExit" value="15:15"></div>
    </div>
    <div class="btn-row"><button type="submit" class="btn btn-g btn-sm">💾 Save</button></div>
  </form>
</div>

<!-- ═══ NIFTY Config ═══ -->
<div class="section">
  <h3>⚙️ NIFTY Configuration</h3>
  <form onsubmit="return saveIndex(event,'NIFTY')">
    <div class="toggle"><input type="checkbox" id="niftyEnabled" checked> Enabled</div>
    <div class="cfg-grid" style="margin-top:8px">
      <div class="fg"><label>Lots (1-10)</label><input type="number" id="niftyLotSize" min="1" max="10" value="1"></div>
      <div class="fg"><label>Min Premium ₹</label><input type="number" id="niftyMinPrem" step="1" value="20"></div>
      <div class="fg"><label>CE Sell Offset</label><input type="number" id="niftyCES" step="50" value="200"></div>
      <div class="fg"><label>CE Buy Offset</label><input type="number" id="niftyCEB" step="50" value="400"></div>
      <div class="fg"><label>PE Sell Offset</label><input type="number" id="niftyPES" step="50" value="200"></div>
      <div class="fg"><label>PE Buy Offset</label><input type="number" id="niftyPEB" step="50" value="400"></div>
      <div class="fg"><label>Max Loss ₹</label><input type="number" id="niftyML" step="500" value="5000"></div>
      <div class="fg"><label>Target ₹</label><input type="number" id="niftyTP" step="500" value="3000"></div>
    </div>
    <div class="btn-row">
      <button type="submit" class="btn btn-b btn-sm">💾 Save NIFTY</button>
      <button type="button" class="btn btn-r btn-sm" onclick="emergExit('NIFTY')">🚨 Exit NIFTY</button>
    </div>
  </form>
</div>

<!-- ═══ SENSEX Config ═══ -->
<div class="section">
  <h3>⚙️ SENSEX Configuration</h3>
  <form onsubmit="return saveIndex(event,'SENSEX')">
    <div class="toggle"><input type="checkbox" id="sensexEnabled" checked> Enabled</div>
    <div class="cfg-grid" style="margin-top:8px">
      <div class="fg"><label>Lots (1-10)</label><input type="number" id="sensexLotSize" min="1" max="10" value="1"></div>
      <div class="fg"><label>Min Premium ₹</label><input type="number" id="sensexMinPrem" step="1" value="20"></div>
      <div class="fg"><label>CE Sell Offset</label><input type="number" id="sensexCES" step="100" value="300"></div>
      <div class="fg"><label>CE Buy Offset</label><input type="number" id="sensexCEB" step="100" value="600"></div>
      <div class="fg"><label>PE Sell Offset</label><input type="number" id="sensexPES" step="100" value="300"></div>
      <div class="fg"><label>PE Buy Offset</label><input type="number" id="sensexPEB" step="100" value="600"></div>
      <div class="fg"><label>Max Loss ₹</label><input type="number" id="sensexML" step="500" value="5000"></div>
      <div class="fg"><label>Target ₹</label><input type="number" id="sensexTP" step="500" value="3000"></div>
    </div>
    <div class="btn-row">
      <button type="submit" class="btn btn-b btn-sm">💾 Save SENSEX</button>
      <button type="button" class="btn btn-r btn-sm" onclick="emergExit('SENSEX')">🚨 Exit SENSEX</button>
    </div>
  </form>
</div>

<!-- ═══ Emergency ═══ -->
<div class="section" style="text-align:center">
  <button class="btn btn-r" style="font-size:.95em;padding:12px 28px" onclick="emergExitAll()">
    🚨 EMERGENCY EXIT ALL POSITIONS
  </button>
</div>

<!-- ═══ Trades Log ═══ -->
<div class="section">
  <h3>📝 Today's Trades</h3>
  <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
    <div><strong style="color:#8b949e;font-size:.78em">NIFTY</strong><div class="trades" id="niftyTrades"><div style="color:#555">—</div></div></div>
    <div><strong style="color:#8b949e;font-size:.78em">SENSEX</strong><div class="trades" id="sensexTrades"><div style="color:#555">—</div></div></div>
  </div>
</div>

<div class="footer">Multi-Index Options Bot v3.2 | Iron Condor | ICICI Breeze | Railway.app</div>

<script>
/* ── Helpers ──────────────────────────────── */
function badgeClass(st){
  if(!st)return'b-ready';
  if(st.includes('ACTIVE'))return'b-active';
  if(st==='READY')return'b-ready';
  if(st.includes('CLOSED')||st.includes('STOPPED'))return'b-closed';
  if(st.includes('DISABLED'))return'b-disabled';
  if(st.includes('FAIL')||st.includes('ERROR'))return'b-error';
  return'b-ready';
}
function pnlClass(v){return v>0?'profit':v<0?'loss':'neutral'}
function fmt(v){return'\u20B9'+v.toFixed(2)}
function api(url,opts){return fetch(url,opts).then(function(r){return r.json()})}

/* ── Start / Stop ────────────────────────── */
function startBot(){
  if(!confirm('▶️ Start trading bot?'))return;
  api('/api/bot/start',{method:'POST'}).then(function(d){
    alert(d.message||JSON.stringify(d));refresh();
  });
}
function stopBot(exitPos){
  var msg=exitPos?'⏹️ Stop bot AND close all positions?':'⏹️ Stop bot? (positions stay open)';
  if(!confirm(msg))return;
  api('/api/bot/stop',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({exit_positions:exitPos})
  }).then(function(d){alert(d.message||JSON.stringify(d));refresh();});
}

/* ── Token Update ────────────────────────── */
function updateToken(){
  var tok=document.getElementById('tokenInput').value.trim();
  if(!tok){alert('Please paste the new session token');return;}
  if(!confirm('🔑 Update session token and reconnect to Breeze API?'))return;
  api('/api/token/update',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({token:tok})
  }).then(function(d){
    alert(d.message||JSON.stringify(d));
    document.getElementById('tokenInput').value='';
    refresh();
  });
}

/* ── Render per-index data ───────────────── */
function renderIdx(prefix,d,cfg){
  var b=document.getElementById(prefix+'Badge');
  b.textContent=d.status||'-';b.className='badge '+badgeClass(d.status);
  var p=document.getElementById(prefix+'Pnl');
  p.textContent=fmt(d.pnl);p.className='stat '+pnlClass(d.pnl);
  document.getElementById(prefix+'Entry').textContent=d.entry_done?'\u2705':'\u23F3';
  document.getElementById(prefix+'Exit').textContent=d.exit_done?'\u2705':'\u23F3';
  document.getElementById(prefix+'Update').textContent=d.last_update||'-';
  var pl=document.getElementById(prefix+'Pos');
  pl.innerHTML=d.positions&&d.positions.length?d.positions.map(function(x){return'<div>'+x+'</div>'}).join(''):'<div style="color:#8b949e">No positions</div>';
  if(cfg){
    document.getElementById(prefix+'LotSize').value=cfg.lot_size;
    document.getElementById(prefix+'MinPrem').value=cfg.min_premium;
    document.getElementById(prefix+'CES').value=cfg.ce_sell_offset;
    document.getElementById(prefix+'CEB').value=cfg.ce_buy_offset;
    document.getElementById(prefix+'PES').value=cfg.pe_sell_offset;
    document.getElementById(prefix+'PEB').value=cfg.pe_buy_offset;
    document.getElementById(prefix+'ML').value=cfg.max_loss;
    document.getElementById(prefix+'TP').value=cfg.target_profit;
    document.getElementById(prefix+'Enabled').checked=cfg.enabled;
    document.getElementById(prefix+'Lots').textContent=cfg.lot_size;
  }
  var tl=document.getElementById(prefix+'Trades');
  if(d.trades_today&&d.trades_today.length){
    tl.innerHTML=d.trades_today.map(function(t){return'<div>'+(t.leg||'')+' '+(t.strike||'')+' '+(t.action||'')+' '+(t.success?'\u2705':'\u274C')+'</div>'}).join('');
  }else{tl.innerHTML='<div style="color:#555">\u2014</div>';}
}

/* ── Main refresh ────────────────────────── */
function refresh(){
  api('/api/status').then(function(d){
    /* Bot control bar */
    var pill=document.getElementById('botPill');
    var running=d.is_running;
    var connected=d.is_connected;
    if(running){pill.textContent='RUNNING';pill.className='status-pill pill-running';}
    else if(!connected){pill.textContent='DISCONNECTED';pill.className='status-pill pill-disconnected';}
    else{pill.textContent='STOPPED';pill.className='status-pill pill-stopped';}

    document.getElementById('btnStart').disabled=running;
    document.getElementById('btnStop').disabled=!running;
    document.getElementById('btnStopExit').disabled=!running;
    document.getElementById('botStartTime').textContent=d.bot_start_time||'-';

    /* Token */
    document.getElementById('tokenPreview').textContent=d.token_preview||'-';
    document.getElementById('apiStatus').textContent=connected?'\u2705 Connected':'\u274C Disconnected';
    document.getElementById('lastTokenUpdate').textContent=d.last_token_update||'-';

    /* Combined P&L */
    var cp=document.getElementById('combinedPnl');
    cp.textContent=fmt(d.combined_pnl);cp.className='val '+pnlClass(d.combined_pnl);

    /* Global config */
    if(d.config){
      if(d.config.entry_time)document.getElementById('gEntry').value=d.config.entry_time;
      if(d.config.exit_time)document.getElementById('gExit').value=d.config.exit_time;
    }

    /* Per-index */
    var ci=d.config?d.config.indices:{};
    if(d.indices.NIFTY)renderIdx('nifty',d.indices.NIFTY,ci.NIFTY);
    if(d.indices.SENSEX)renderIdx('sensex',d.indices.SENSEX,ci.SENSEX);
  }).catch(function(e){console.error(e)});

  document.getElementById('clock').textContent=new Date().toLocaleString('en-IN',{timeZone:'Asia/Kolkata',hour12:false});
}

/* ── Config saves ────────────────────────── */
function saveGlobal(ev){
  ev.preventDefault();
  var et=document.getElementById('gEntry').value.split(':');
  var xt=document.getElementById('gExit').value.split(':');
  api('/api/config/global',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({entry_hour:et[0],entry_minute:et[1],exit_hour:xt[0],exit_minute:xt[1]})
  }).then(function(d){alert(d.success?'Saved!':'Error: '+d.error)});
  return false;
}
function saveIndex(ev,idx){
  ev.preventDefault();
  var p=idx.toLowerCase();
  var data={
    enabled:document.getElementById(p+'Enabled').checked,
    lot_size:document.getElementById(p+'LotSize').value,
    min_premium:document.getElementById(p+'MinPrem').value,
    ce_sell_offset:document.getElementById(p+'CES').value,
    ce_buy_offset:document.getElementById(p+'CEB').value,
    pe_sell_offset:document.getElementById(p+'PES').value,
    pe_buy_offset:document.getElementById(p+'PEB').value,
    max_loss:document.getElementById(p+'ML').value,
    target_profit:document.getElementById(p+'TP').value,
  };
  api('/api/config/'+idx,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)})
    .then(function(d){alert(d.success?idx+' saved!':'Error: '+d.error)});
  return false;
}

/* ── Emergency exits ─────────────────────── */
function emergExit(idx){
  if(confirm('\u26A0\uFE0F Close ALL '+idx+' positions?')){
    api('/api/emergency-exit/'+idx,{method:'POST'}).then(function(d){alert(d.message||JSON.stringify(d));refresh();});
  }
}
function emergExitAll(){
  if(confirm('\u26A0\uFE0F EMERGENCY: Close ALL positions on ALL indices?')){
    api('/api/emergency-exit-all',{method:'POST'}).then(function(d){alert(d.message||JSON.stringify(d));refresh();});
  }
}

refresh();setInterval(refresh,10000);
</script>
</body>
</html>
"""


def create_app(bot_state, start_bot_fn, stop_bot_fn, update_token_fn):
    """
    Create Flask app.
    Receives function references for start/stop/token from bot_runner.
    """
    app = Flask(__name__)
    app.secret_key = 'multi-idx-bot-v32'

    @app.route('/')
    def index():
        return render_template_string(DASHBOARD_HTML)

    @app.route('/health')
    def health():
        return jsonify({
            "status": "ok",
            "time": datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S IST'),
            "is_running": bot_state.is_running,
            "is_connected": bot_state.is_connected,
        })

    @app.route('/api/status')
    def api_status():
        return jsonify(bot_state.to_dict())

    # ── Bot Start / Stop ─────────────────────────────────

    @app.route('/api/bot/start', methods=['POST'])
    def api_start():
        try:
            success, msg = start_bot_fn()
            return jsonify({"success": success, "message": msg})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route('/api/bot/stop', methods=['POST'])
    def api_stop():
        try:
            data = request.get_json() or {}
            exit_positions = data.get('exit_positions', False)
            success, msg = stop_bot_fn(exit_positions=exit_positions)
            return jsonify({"success": success, "message": msg})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    # ── Token Update ─────────────────────────────────────

    @app.route('/api/token/update', methods=['POST'])
    def api_token_update():
        try:
            data = request.get_json() or {}
            new_token = data.get('token', '').strip()
            if not new_token:
                return jsonify({"success": False, "message": "No token provided"})
            success, msg = update_token_fn(new_token)
            return jsonify({"success": success, "message": msg})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    # ── Config ───────────────────────────────────────────

    @app.route('/api/config/global', methods=['POST'])
    def api_config_global():
        try:
            bot_state.config.update_global(request.get_json())
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    @app.route('/api/config/<index_name>', methods=['POST'])
    def api_config_index(index_name):
        try:
            idx = index_name.upper()
            if idx not in bot_state.config.indices:
                return jsonify({"success": False, "error": f"Unknown index: {idx}"})
            bot_state.config.indices[idx].update(request.get_json())
            logger.info(f"[{idx}] Config updated")
            return jsonify({"success": True})
        except Exception as e:
            return jsonify({"success": False, "error": str(e)})

    # ── Emergency Exit ───────────────────────────────────

    @app.route('/api/emergency-exit/<index_name>', methods=['POST'])
    def api_emergency_exit(index_name):
        idx = index_name.upper()
        try:
            st = bot_state.index_states.get(idx)
            if not st or not st.strategy or not st.entry_done or st.exit_done:
                return jsonify({"success": False, "message": f"No active {idx} positions"})
            result = st.strategy.exit_position()
            st.exit_done = True
            st.positions = []
            st.pnl = result.get('realized_pnl', 0)
            st.status = "EMERGENCY_EXIT"
            if bot_state.telegram and bot_state.telegram.enabled:
                bot_state.telegram.send(f"🚨 *{idx} EMERGENCY EXIT*\nP&L: ₹{st.pnl:.2f}")
            return jsonify({"success": True, "message": f"{idx} positions closed", "pnl": st.pnl})
        except Exception as e:
            return jsonify({"success": False, "message": str(e)})

    @app.route('/api/emergency-exit-all', methods=['POST'])
    def api_emergency_exit_all():
        results = {}
        for idx, st in bot_state.index_states.items():
            if st.strategy and st.entry_done and not st.exit_done:
                try:
                    r = st.strategy.exit_position()
                    st.exit_done = True
                    st.positions = []
                    st.pnl = r.get('realized_pnl', 0)
                    st.status = "EMERGENCY_EXIT"
                    results[idx] = {"success": True, "pnl": st.pnl}
                except Exception as e:
                    results[idx] = {"success": False, "error": str(e)}
            else:
                results[idx] = {"success": True, "message": "No active positions"}
        if bot_state.telegram and bot_state.telegram.enabled:
            total = sum(r.get('pnl', 0) for r in results.values() if r.get('success'))
            bot_state.telegram.send(f"🚨 *ALL EMERGENCY EXIT*\nCombined P&L: ₹{total:.2f}")
        return jsonify({"success": True, "message": "Emergency exit complete", "results": results})

    return app
