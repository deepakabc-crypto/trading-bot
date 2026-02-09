"""
================================================================================
🤖 NIFTY TRADING BOT - Combined Dashboard + Bot
================================================================================
Single file that runs:
- Web Dashboard (Flask)
- Trading Bot (Background Thread)
================================================================================
"""

from flask import Flask, render_template_string, jsonify, request
import json
import os
import time
import threading
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

app = Flask(__name__)

# ============================================
# TIMEZONE - IST (UTC+5:30)
# ============================================
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """Get current time in IST"""
    return datetime.now(IST)

# ============================================
# LOGGING
# ============================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# SETTINGS (from environment variables)
# ============================================
API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")
API_SESSION = os.environ.get("API_SESSION", "")
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CAPITAL = int(os.environ.get("CAPITAL", "500000"))
QUANTITY = 65  # Nifty lot size
STRATEGY = os.environ.get("STRATEGY", "iron_condor")

# Strategy settings
IC_CALL_SELL_DISTANCE = 150
IC_CALL_BUY_DISTANCE = 250
IC_PUT_SELL_DISTANCE = 150
IC_PUT_BUY_DISTANCE = 250
IC_TARGET_PERCENT = 50
IC_STOP_LOSS_PERCENT = 100
STR_TARGET_PERCENT = 30
STR_STOP_LOSS_PERCENT = 20

# Timing (defaults - can be changed from dashboard)
DEFAULT_ENTRY_TIME_START = "09:20"
DEFAULT_ENTRY_TIME_END = "14:00"
DEFAULT_EXIT_TIME = "15:15"
TRADING_DAYS = [0, 1, 2, 3, 4]
MIN_PREMIUM = 30
CHARGES_PER_LOT = 100
CHECK_INTERVAL = 30

PORT = int(os.environ.get("PORT", 5000))

# ============================================
# GET CURRENT SETTINGS (from data file)
# ============================================
def get_entry_start():
    data = load_data()
    return data.get("entry_time_start", DEFAULT_ENTRY_TIME_START)

def get_entry_end():
    data = load_data()
    return data.get("entry_time_end", DEFAULT_ENTRY_TIME_END)

def get_exit_time():
    data = load_data()
    return data.get("exit_time", DEFAULT_EXIT_TIME)

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
        "session_token": API_SESSION,
        "daily_pnl": 0,
        "total_pnl": 0,
        "last_update": "",
        "entry_time_start": DEFAULT_ENTRY_TIME_START,
        "entry_time_end": DEFAULT_ENTRY_TIME_END,
        "exit_time": DEFAULT_EXIT_TIME
    }

def save_data(data):
    try:
        data["last_update"] = get_ist_now().isoformat()
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

def add_trade(trade):
    data = load_data()
    trade['timestamp'] = get_ist_now().isoformat()
    data["trades"].append(trade)
    data["daily_pnl"] = data.get("daily_pnl", 0) + float(trade.get("pnl", 0))
    data["total_pnl"] = sum(float(t.get('pnl', 0)) for t in data["trades"])
    save_data(data)

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
        "session_set": bool(data.get("session_token")),
        "last_update": data.get("last_update", ""),
        "entry_time_start": data.get("entry_time_start", DEFAULT_ENTRY_TIME_START),
        "entry_time_end": data.get("entry_time_end", DEFAULT_ENTRY_TIME_END),
        "exit_time": data.get("exit_time", DEFAULT_EXIT_TIME),
        "ist_time": get_ist_now().strftime("%H:%M:%S")
    }

# ============================================
# TELEGRAM
# ============================================
class Telegram:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(self.token and self.chat_id and self.token != "YOUR_BOT_TOKEN_HERE")
        self.last_update_id = 0
        
    def send(self, message):
        if not self.enabled:
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        except Exception as e:
            logger.error(f"Telegram error: {e}")
    
    def check_commands(self):
        if not self.enabled:
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            response = requests.get(url, params={"offset": self.last_update_id + 1, "timeout": 1}, timeout=5)
            updates = response.json().get("result", [])
            
            for update in updates:
                self.last_update_id = update["update_id"]
                text = update.get("message", {}).get("text", "")
                
                if text.startswith("/session "):
                    token = text.replace("/session ", "").strip()
                    if token:
                        data = load_data()
                        data["session_token"] = token
                        save_data(data)
                        self.send("✅ Session token updated!")
                        logger.info("Session updated via Telegram")
                
                elif text == "/status":
                    data = load_data()
                    status = "🟢 Running" if data.get("bot_running") else "⏸️ Stopped"
                    self.send(f"📊 Status: {status}\nStrategy: {data.get('strategy')}\nP&L: ₹{data.get('daily_pnl', 0):,.0f}")
                
                elif text == "/start":
                    data = load_data()
                    data["bot_running"] = True
                    save_data(data)
                    self.send("▶️ Bot started!")
                
                elif text == "/stop":
                    data = load_data()
                    data["bot_running"] = False
                    save_data(data)
                    self.send("⏹️ Bot stopped!")
                    
                elif text == "/help":
                    self.send("🤖 Commands:\n/session TOKEN\n/status\n/start\n/stop")
        except:
            pass

telegram = Telegram()

# ============================================
# BREEZE API
# ============================================
BREEZE_AVAILABLE = False
try:
    from breeze_connect import BreezeConnect
    BREEZE_AVAILABLE = True
except:
    logger.warning("breeze_connect not available")

class BreezeAPI:
    def __init__(self):
        self.breeze = None
        self.connected = False
        
    def connect(self):
        if not BREEZE_AVAILABLE:
            return False
        
        data = load_data()
        session = data.get("session_token") or API_SESSION
        
        if not session or not API_KEY:
            logger.warning("API credentials not set")
            return False
        
        try:
            logger.info("Connecting to Breeze API...")
            self.breeze = BreezeConnect(api_key=API_KEY)
            self.breeze.generate_session(api_secret=API_SECRET, session_token=session)
            self.connected = True
            logger.info("✅ Connected to Breeze API")
            telegram.send("✅ Connected to Breeze API")
            return True
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            telegram.send(f"❌ Connection failed: {str(e)[:50]}")
            return False
    
    def get_spot(self):
        if not self.connected:
            return None
        try:
            data = self.breeze.get_quotes(stock_code="NIFTY", exchange_code="NSE", product_type="cash")
            if data and 'Success' in data:
                return float(data['Success'][0]['ltp'])
        except:
            pass
        return None
    
    def get_ltp(self, strike, option_type, expiry):
        if not self.connected:
            return None
        try:
            logger.debug(f"Getting LTP: NIFTY {strike} {option_type} exp={expiry}")
            data = self.breeze.get_quotes(
                stock_code="NIFTY",
                exchange_code="NFO",
                expiry_date=expiry,
                product_type="options",
                right=option_type.lower(),  # "call" or "put"
                strike_price=str(strike)
            )
            logger.debug(f"LTP Response: {data}")
            if data and data.get('Success') and len(data['Success']) > 0:
                ltp = data['Success'][0].get('ltp')
                if ltp and float(ltp) > 0:
                    return float(ltp)
            logger.warning(f"No LTP for {strike} {option_type}: {data.get('Error', 'No data')}")
        except Exception as e:
            logger.error(f"LTP error for {strike} {option_type}: {e}")
        return None
    
    def place_order(self, strike, option_type, expiry, quantity, side, price):
        if not self.connected:
            return None
        try:
            order = self.breeze.place_order(
                stock_code="NIFTY", exchange_code="NFO", product="options",
                action=side.lower(), order_type="market", quantity=str(quantity),
                price="", validity="day", expiry_date=expiry,
                right=option_type.lower(), strike_price=str(strike),
                stoploss="", disclosed_quantity=""
            )
            if order and 'Success' in order:
                logger.info(f"Order: {side} {strike} {option_type}")
                return order['Success']['order_id']
        except Exception as e:
            logger.error(f"Order error: {e}")
        return None
    
    def get_expiry(self):
        """Get current week expiry date in Breeze API format: DD-Mon-YYYY"""
        today = get_ist_now()
        days = (3 - today.weekday()) % 7  # Days until Thursday
        if days == 0 and today.hour >= 15:
            days = 7  # If Thursday after 3PM, next week
        expiry_date = today + timedelta(days=days)
        # Breeze API format: DD-Mon-YYYY (e.g., "13-Feb-2026")
        return expiry_date.strftime("%d-%b-%Y")
    
    def get_expiry_display(self):
        """Get expiry date for display"""
        today = get_ist_now()
        days = (3 - today.weekday()) % 7
        if days == 0 and today.hour >= 15:
            days = 7
        expiry_date = today + timedelta(days=days)
        return expiry_date.strftime("%Y-%m-%d")

# ============================================
# IRON CONDOR STRATEGY
# ============================================
class IronCondor:
    def __init__(self, api):
        self.api = api
        self.position = None
        self.entry_premium = 0
        
    def enter(self, spot, expiry):
        atm = round(spot / 50) * 50
        sc, bc = atm + IC_CALL_SELL_DISTANCE, atm + IC_CALL_BUY_DISTANCE
        sp, bp = atm - IC_PUT_SELL_DISTANCE, atm - IC_PUT_BUY_DISTANCE
        
        logger.info(f"🦅 IC Attempting Entry: Spot={spot}, ATM={atm}")
        logger.info(f"   Strikes: SC={sc}, BC={bc}, SP={sp}, BP={bp}")
        logger.info(f"   Expiry: {expiry}")
        
        sc_p = self.api.get_ltp(sc, "call", expiry)
        bc_p = self.api.get_ltp(bc, "call", expiry)
        sp_p = self.api.get_ltp(sp, "put", expiry)
        bp_p = self.api.get_ltp(bp, "put", expiry)
        
        logger.info(f"   Premiums: SC={sc_p}, BC={bc_p}, SP={sp_p}, BP={bp_p}")
        
        # Check if all premiums are valid
        if not all([sc_p, bc_p, sp_p, bp_p]):
            logger.error(f"❌ IC Entry failed: Could not get all premiums")
            telegram.send(f"❌ IC Entry failed: Missing premiums\nSC={sc_p}, BC={bc_p}, SP={sp_p}, BP={bp_p}")
            return False
        
        credit = (sc_p - bc_p) + (sp_p - bp_p)
        
        if credit < MIN_PREMIUM:
            logger.warning(f"⚠️ IC: Premium too low ({credit:.0f} < {MIN_PREMIUM})")
            return False
        
        logger.info(f"🦅 IC Entry: Credit={credit:.0f}")
        
        self.api.place_order(sc, "call", expiry, QUANTITY, "sell", sc_p)
        self.api.place_order(bc, "call", expiry, QUANTITY, "buy", bc_p)
        self.api.place_order(sp, "put", expiry, QUANTITY, "sell", sp_p)
        self.api.place_order(bp, "put", expiry, QUANTITY, "buy", bp_p)
        
        self.position = {"sc": sc, "bc": bc, "sp": sp, "bp": bp, "expiry": expiry}
        self.entry_premium = credit
        
        telegram.send(f"🦅 <b>Iron Condor Entry</b>\nSpot: {spot}\nCredit: ₹{credit:.0f}\nSell: {sc}CE/{sp}PE\nBuy: {bc}CE/{bp}PE")
        return True
    
    def check_exit(self):
        if not self.position:
            return None
        
        sc = self.api.get_ltp(self.position["sc"], "call", self.position["expiry"]) or 0
        bc = self.api.get_ltp(self.position["bc"], "call", self.position["expiry"]) or 0
        sp = self.api.get_ltp(self.position["sp"], "put", self.position["expiry"]) or 0
        bp = self.api.get_ltp(self.position["bp"], "put", self.position["expiry"]) or 0
        
        current = (sc - bc) + (sp - bp)
        pnl_pct = (self.entry_premium - current) / self.entry_premium * 100 if self.entry_premium > 0 else 0
        
        if pnl_pct >= IC_TARGET_PERCENT:
            return "TARGET"
        if pnl_pct <= -IC_STOP_LOSS_PERCENT:
            return "STOP_LOSS"
        
        # Check exit time in IST
        now = get_ist_now()
        current_time = now.strftime("%H:%M")
        if current_time >= get_exit_time():
            return "TIME_EXIT"
        return None
    
    def exit(self, reason):
        if not self.position:
            return 0
        
        sc = self.api.get_ltp(self.position["sc"], "call", self.position["expiry"]) or 0
        bc = self.api.get_ltp(self.position["bc"], "call", self.position["expiry"]) or 0
        sp = self.api.get_ltp(self.position["sp"], "put", self.position["expiry"]) or 0
        bp = self.api.get_ltp(self.position["bp"], "put", self.position["expiry"]) or 0
        
        self.api.place_order(self.position["sc"], "call", self.position["expiry"], QUANTITY, "buy", sc)
        self.api.place_order(self.position["bc"], "call", self.position["expiry"], QUANTITY, "sell", bc)
        self.api.place_order(self.position["sp"], "put", self.position["expiry"], QUANTITY, "buy", sp)
        self.api.place_order(self.position["bp"], "put", self.position["expiry"], QUANTITY, "sell", bp)
        
        exit_prem = (sc - bc) + (sp - bp)
        pnl = (self.entry_premium - exit_prem) * QUANTITY - CHARGES_PER_LOT
        
        add_trade({
            "date": get_ist_now().strftime("%Y-%m-%d"),
            "strategy": "IRON_CONDOR",
            "entry_premium": self.entry_premium,
            "exit_premium": exit_prem,
            "pnl": pnl,
            "exit_reason": reason
        })
        
        telegram.send(f"🦅 <b>IC Exit</b>\n{reason}\nP&L: ₹{pnl:+,.0f}")
        logger.info(f"🦅 IC Exit: {reason}, P&L: {pnl}")
        
        self.position = None
        return pnl

# ============================================
# SHORT STRADDLE STRATEGY
# ============================================
class ShortStraddle:
    def __init__(self, api):
        self.api = api
        self.position = None
        self.entry_premium = 0
        
    def enter(self, spot, expiry):
        atm = round(spot / 50) * 50
        
        logger.info(f"📊 Straddle Attempting Entry: Spot={spot}, Strike={atm}")
        logger.info(f"   Expiry: {expiry}")
        
        ce = self.api.get_ltp(atm, "call", expiry)
        pe = self.api.get_ltp(atm, "put", expiry)
        
        logger.info(f"   Premiums: CE={ce}, PE={pe}")
        
        if not ce or not pe:
            logger.error(f"❌ Straddle Entry failed: Could not get premiums")
            telegram.send(f"❌ Straddle Entry failed: CE={ce}, PE={pe}")
            return False
        
        total = ce + pe
        
        if total < MIN_PREMIUM:
            logger.warning(f"⚠️ Straddle: Premium too low ({total:.0f} < {MIN_PREMIUM})")
            return False
        
        logger.info(f"📊 Straddle Entry: {atm}, Premium={total:.0f}")
        
        self.api.place_order(atm, "call", expiry, QUANTITY, "sell", ce)
        self.api.place_order(atm, "put", expiry, QUANTITY, "sell", pe)
        
        self.position = {"strike": atm, "expiry": expiry}
        self.entry_premium = total
        
        telegram.send(f"📊 <b>Straddle Entry</b>\nSpot: {spot}\nStrike: {atm}\nCE: ₹{ce:.0f}, PE: ₹{pe:.0f}\nTotal: ₹{total:.0f}")
        return True
    
    def check_exit(self):
        if not self.position:
            return None
        
        ce = self.api.get_ltp(self.position["strike"], "call", self.position["expiry"]) or 0
        pe = self.api.get_ltp(self.position["strike"], "put", self.position["expiry"]) or 0
        current = ce + pe
        
        pnl_pct = (self.entry_premium - current) / self.entry_premium * 100 if self.entry_premium > 0 else 0
        
        if pnl_pct >= STR_TARGET_PERCENT:
            return "TARGET"
        if pnl_pct <= -STR_STOP_LOSS_PERCENT:
            return "STOP_LOSS"
        
        # Check exit time in IST
        now = get_ist_now()
        current_time = now.strftime("%H:%M")
        if current_time >= get_exit_time():
            return "TIME_EXIT"
        return None
    
    def exit(self, reason):
        if not self.position:
            return 0
        
        ce = self.api.get_ltp(self.position["strike"], "call", self.position["expiry"]) or 0
        pe = self.api.get_ltp(self.position["strike"], "put", self.position["expiry"]) or 0
        
        self.api.place_order(self.position["strike"], "call", self.position["expiry"], QUANTITY, "buy", ce)
        self.api.place_order(self.position["strike"], "put", self.position["expiry"], QUANTITY, "buy", pe)
        
        exit_prem = ce + pe
        pnl = (self.entry_premium - exit_prem) * QUANTITY - CHARGES_PER_LOT
        
        add_trade({
            "date": get_ist_now().strftime("%Y-%m-%d"),
            "strategy": "SHORT_STRADDLE",
            "entry_premium": self.entry_premium,
            "exit_premium": exit_prem,
            "pnl": pnl,
            "exit_reason": reason
        })
        
        telegram.send(f"📊 <b>Straddle Exit</b>\n{reason}\nP&L: ₹{pnl:+,.0f}")
        logger.info(f"📊 Straddle Exit: {reason}, P&L: {pnl}")
        
        self.position = None
        return pnl

# ============================================
# BOT RUNNER (Background Thread)
# ============================================
def is_trading_time():
    now = get_ist_now()
    if now.weekday() not in TRADING_DAYS:
        return False
    
    # Create time objects for comparison
    current_time = now.strftime("%H:%M")
    
    # Compare as strings (HH:MM format)
    return get_entry_start() <= current_time <= get_entry_end()

def is_exit_time():
    now = get_ist_now()
    current_time = now.strftime("%H:%M")
    return current_time >= get_exit_time()

def bot_thread():
    logger.info("🤖 Bot thread starting...")
    
    api = BreezeAPI()
    ic = IronCondor(api)
    straddle = ShortStraddle(api)
    last_connect = datetime.now(IST) - timedelta(hours=1)
    last_status_log = datetime.now(IST) - timedelta(minutes=10)
    
    while True:
        try:
            # Check Telegram commands
            telegram.check_commands()
            
            # Load current state
            data = load_data()
            strategy = data.get("strategy", STRATEGY)
            bot_running = data.get("bot_running", False)
            
            # Log status every 5 minutes
            now_ist = get_ist_now()
            if (now_ist - last_status_log).seconds >= 300:
                logger.info(f"⏰ IST: {now_ist.strftime('%H:%M:%S')} | Bot: {'Running' if bot_running else 'Stopped'} | Entry: {get_entry_start()}-{get_entry_end()} | Trading: {is_trading_time()}")
                last_status_log = now_ist
            
            if not bot_running:
                time.sleep(10)
                continue
            
            # Connect to API if needed
            if not api.connected and (datetime.now(IST) - last_connect).seconds > 60:
                api.connect()
                last_connect = datetime.now(IST)
            
            if not api.connected:
                time.sleep(30)
                continue
            
            # Force exit time
            if is_exit_time():
                if ic.position:
                    ic.exit("TIME_EXIT")
                if straddle.position:
                    straddle.exit("TIME_EXIT")
                time.sleep(60)
                continue
            
            # Check exits
            if strategy in ["iron_condor", "both"] and ic.position:
                reason = ic.check_exit()
                if reason:
                    ic.exit(reason)
            
            if strategy in ["straddle", "both"] and straddle.position:
                reason = straddle.check_exit()
                if reason:
                    straddle.exit(reason)
            
            # Enter new positions
            if is_trading_time():
                spot = api.get_spot()
                expiry = api.get_expiry()
                
                if spot:
                    logger.info(f"📊 Spot: {spot}, Strategy: {strategy}, IC Position: {ic.position is not None}, Straddle Position: {straddle.position is not None}")
                    
                    if strategy in ["iron_condor", "both"] and not ic.position:
                        ic.enter(spot, expiry)
                    
                    if strategy in ["straddle", "both"] and not straddle.position:
                        straddle.enter(spot, expiry)
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(60)

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
        .strategy-btn h4 { margin-bottom: 8px; color: #fff; }
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
        }
        .btn:hover { opacity: 0.85; }
        .btn-danger { background: linear-gradient(90deg, #f44336, #d32f2f); }
        .btn-success { background: linear-gradient(90deg, #00c853, #00a844); }
        
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid rgba(255,255,255,0.1); }
        th { color: #888; font-size: 0.75rem; text-transform: uppercase; }
        
        .info-text { color: #888; font-size: 0.9rem; margin-top: 10px; }
        .chart-container { height: 200px; margin-top: 15px; }
        
        .time-input {
            width: 100%;
            padding: 12px;
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 8px;
            background: rgba(255,255,255,0.05);
            color: #fff;
            font-size: 1.2rem;
            text-align: center;
            margin-top: 10px;
        }
        .time-input::-webkit-calendar-picker-indicator {
            filter: invert(1);
        }
        
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
                <span class="badge badge-offline" id="bot-badge">⏸️ STOPPED</span>
                <span class="badge badge-session" id="session-badge">🔑 NO SESSION</span>
            </div>
        </header>
        
        <div class="section">
            <div class="grid">
                <div class="card">
                    <div class="card-title">💰 Total P&L</div>
                    <div class="card-value" id="total-pnl">₹0</div>
                </div>
                <div class="card">
                    <div class="card-title">📅 Today's P&L</div>
                    <div class="card-value" id="daily-pnl">₹0</div>
                </div>
                <div class="card">
                    <div class="card-title">📊 Win Rate</div>
                    <div class="card-value" id="win-rate">0%</div>
                </div>
                <div class="card">
                    <div class="card-title">💼 Portfolio</div>
                    <div class="card-value" id="portfolio">₹5,00,000</div>
                </div>
            </div>
        </div>
        
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
        
        <div class="section">
            <div class="section-title">🔑 Update Session Token</div>
            <p class="info-text">Get token from ICICI Direct, or send /session TOKEN via Telegram</p>
            <div class="session-input">
                <input type="text" id="session-token" placeholder="Paste session token here...">
                <button class="btn" onclick="updateSession()">Update</button>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">⏰ Trading Times (IST)</div>
            <p class="info-text">Current IST Time: <strong id="ist-clock">--:--:--</strong></p>
            <div class="grid" style="margin-top: 15px;">
                <div class="card">
                    <div class="card-title">Entry Start</div>
                    <input type="time" id="entry-start" class="time-input" value="09:20">
                </div>
                <div class="card">
                    <div class="card-title">Entry End</div>
                    <input type="time" id="entry-end" class="time-input" value="14:00">
                </div>
                <div class="card">
                    <div class="card-title">Exit Time</div>
                    <input type="time" id="exit-time" class="time-input" value="15:15">
                </div>
            </div>
            <button class="btn" style="margin-top: 15px;" onclick="updateTimes()">💾 Save Times</button>
        </div>
        
        <div class="section">
            <div class="section-title">🎮 Bot Controls</div>
            <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                <button class="btn btn-success" onclick="startBot()">▶️ Start Bot</button>
                <button class="btn btn-danger" onclick="stopBot()">⏹️ Stop Bot</button>
                <button class="btn" onclick="refreshData()">🔄 Refresh</button>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">📈 P&L History</div>
            <div class="chart-container">
                <canvas id="pnlChart"></canvas>
            </div>
        </div>
        
        <div class="section">
            <div class="section-title">📋 Recent Trades</div>
            <table>
                <thead>
                    <tr><th>Date</th><th>Strategy</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Reason</th></tr>
                </thead>
                <tbody id="trades-body">
                    <tr><td colspan="6" style="text-align:center;color:#666;">No trades yet</td></tr>
                </tbody>
            </table>
        </div>
        
        <div style="text-align:center; color:#555; margin-top:30px;">
            <p>Lot Size: 65 | Market: 9:15 AM - 3:30 PM IST</p>
        </div>
    </div>
    
    <script>
        let pnlChart;
        
        function initChart() {
            const ctx = document.getElementById('pnlChart').getContext('2d');
            pnlChart = new Chart(ctx, {
                type: 'line',
                data: { labels: [], datasets: [{ label: 'P&L', data: [], borderColor: '#00d2ff', fill: true, tension: 0.4 }] },
                options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } } }
            });
        }
        
        async function refreshData() {
            try {
                const res = await fetch('/api/summary');
                const data = await res.json();
                
                document.getElementById('strategy-badge').textContent = (data.strategy || 'iron_condor').toUpperCase().replace('_', ' ');
                
                const botBadge = document.getElementById('bot-badge');
                botBadge.textContent = data.bot_running ? '🟢 RUNNING' : '⏸️ STOPPED';
                botBadge.className = 'badge ' + (data.bot_running ? 'badge-online' : 'badge-offline');
                
                const sessionBadge = document.getElementById('session-badge');
                sessionBadge.textContent = data.session_set ? '🔑 SESSION OK' : '🔑 NO SESSION';
                sessionBadge.className = 'badge badge-session' + (data.session_set ? ' active' : '');
                
                const pnl = data.total_pnl || 0;
                document.getElementById('total-pnl').textContent = '₹' + pnl.toLocaleString('en-IN');
                document.getElementById('total-pnl').className = 'card-value ' + (pnl >= 0 ? 'positive' : 'negative');
                
                document.getElementById('daily-pnl').textContent = '₹' + (data.daily_pnl || 0).toLocaleString('en-IN');
                document.getElementById('win-rate').textContent = data.win_rate.toFixed(1) + '%';
                document.getElementById('portfolio').textContent = '₹' + data.current_value.toLocaleString('en-IN');
                
                document.querySelectorAll('.strategy-btn').forEach(btn => {
                    btn.classList.toggle('active', btn.dataset.strategy === data.strategy);
                });
                
                // Update time settings
                document.getElementById('entry-start').value = data.entry_time_start || '09:20';
                document.getElementById('entry-end').value = data.entry_time_end || '14:00';
                document.getElementById('exit-time').value = data.exit_time || '15:15';
                document.getElementById('ist-clock').textContent = data.ist_time || '--:--:--';
                
                const tradesRes = await fetch('/api/trades');
                const trades = await tradesRes.json();
                updateTable(trades);
                updateChart(trades);
            } catch (e) { console.error(e); }
        }
        
        async function updateTimes() {
            const entryStart = document.getElementById('entry-start').value;
            const entryEnd = document.getElementById('entry-end').value;
            const exitTime = document.getElementById('exit-time').value;
            
            if (!entryStart || !entryEnd || !exitTime) {
                alert('Please fill all time fields');
                return;
            }
            
            await fetch('/api/times', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    entry_time_start: entryStart,
                    entry_time_end: entryEnd,
                    exit_time: exitTime
                })
            });
            alert('Times updated! Entry: ' + entryStart + ' - ' + entryEnd + ', Exit: ' + exitTime);
            refreshData();
        }
        
        function updateTable(trades) {
            const tbody = document.getElementById('trades-body');
            if (!trades.length) {
                tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666;">No trades yet</td></tr>';
                return;
            }
            tbody.innerHTML = trades.slice(-10).reverse().map(t => {
                const pnl = parseFloat(t.pnl || 0);
                return `<tr>
                    <td>${t.date || '-'}</td>
                    <td>${(t.strategy || '-').replace('_', ' ')}</td>
                    <td>₹${parseFloat(t.entry_premium || 0).toFixed(0)}</td>
                    <td>₹${parseFloat(t.exit_premium || 0).toFixed(0)}</td>
                    <td class="${pnl >= 0 ? 'positive' : 'negative'}">₹${pnl.toLocaleString('en-IN')}</td>
                    <td>${t.exit_reason || '-'}</td>
                </tr>`;
            }).join('');
        }
        
        function updateChart(trades) {
            if (!trades.length) return;
            let cum = 0;
            pnlChart.data.labels = trades.map(t => t.date || '');
            pnlChart.data.datasets[0].data = trades.map(t => { cum += parseFloat(t.pnl || 0); return cum; });
            pnlChart.update();
        }
        
        async function selectStrategy(s) {
            await fetch('/api/strategy', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ strategy: s }) });
            refreshData();
        }
        
        async function updateSession() {
            const token = document.getElementById('session-token').value.trim();
            if (!token) return alert('Enter token');
            await fetch('/api/session', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ token }) });
            document.getElementById('session-token').value = '';
            refreshData();
            alert('Session updated!');
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
    return jsonify(load_data().get("trades", []))

@app.route('/api/strategy', methods=['POST'])
def api_strategy():
    data = load_data()
    data["strategy"] = request.json.get("strategy", "iron_condor")
    save_data(data)
    return jsonify({"status": "success"})

@app.route('/api/session', methods=['POST'])
def api_session():
    data = load_data()
    data["session_token"] = request.json.get("token", "")
    save_data(data)
    return jsonify({"status": "success"})

@app.route('/api/bot/start', methods=['POST'])
def api_bot_start():
    data = load_data()
    data["bot_running"] = True
    save_data(data)
    telegram.send("▶️ Bot started from dashboard")
    return jsonify({"status": "success"})

@app.route('/api/bot/stop', methods=['POST'])
def api_bot_stop():
    data = load_data()
    data["bot_running"] = False
    save_data(data)
    telegram.send("⏹️ Bot stopped from dashboard")
    return jsonify({"status": "success"})

@app.route('/api/times', methods=['POST'])
def api_times():
    data = load_data()
    req = request.json
    
    if "entry_time_start" in req:
        data["entry_time_start"] = req["entry_time_start"]
    if "entry_time_end" in req:
        data["entry_time_end"] = req["entry_time_end"]
    if "exit_time" in req:
        data["exit_time"] = req["exit_time"]
    
    save_data(data)
    telegram.send(f"⏰ Times updated:\nEntry: {data.get('entry_time_start')} - {data.get('entry_time_end')}\nExit: {data.get('exit_time')}")
    return jsonify({"status": "success"})

@app.route('/health')
def health():
    now_ist = get_ist_now()
    return jsonify({
        "status": "ok",
        "ist_time": now_ist.strftime("%Y-%m-%d %H:%M:%S"),
        "is_trading_time": is_trading_time(),
        "is_exit_time": is_exit_time(),
        "entry_window": f"{get_entry_start()} - {get_entry_end()}",
        "exit_time": get_exit_time()
    })

@app.route('/api/test_quotes')
def test_quotes():
    """Test endpoint to debug option quotes"""
    api = BreezeAPI()
    
    # Check if session exists
    data = load_data()
    session = data.get("session_token") or API_SESSION
    
    if not session:
        return jsonify({"error": "No session token set"})
    
    if not api.connect():
        return jsonify({"error": "Could not connect to Breeze API"})
    
    # Get spot price
    spot = api.get_spot()
    if not spot:
        return jsonify({"error": "Could not get spot price"})
    
    atm = round(spot / 50) * 50
    expiry = api.get_expiry()  # DD-Mon-YYYY format
    
    # Try to get option quote
    results = {
        "spot": spot,
        "atm": atm,
        "expiry": expiry,
        "ist_time": get_ist_now().strftime("%Y-%m-%d %H:%M:%S"),
        "call_quote": None,
        "put_quote": None
    }
    
    # Test Call
    try:
        ce_data = api.breeze.get_quotes(
            stock_code="NIFTY",
            exchange_code="NFO",
            expiry_date=expiry,
            product_type="options",
            right="call",
            strike_price=str(atm)
        )
        results["call_quote"] = ce_data
    except Exception as e:
        results["call_quote"] = {"error": str(e)}
    
    # Test Put
    try:
        pe_data = api.breeze.get_quotes(
            stock_code="NIFTY",
            exchange_code="NFO",
            expiry_date=expiry,
            product_type="options",
            right="put",
            strike_price=str(atm)
        )
        results["put_quote"] = pe_data
    except Exception as e:
        results["put_quote"] = {"error": str(e)}
    
    return jsonify(results)

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    # Start bot in background thread
    bot = threading.Thread(target=bot_thread, daemon=True)
    bot.start()
    logger.info("🤖 Bot thread started")
    
    # Start Flask app
    logger.info(f"🖥️ Dashboard starting on port {PORT}")
    app.run(host='0.0.0.0', port=PORT, debug=False, threaded=True)
