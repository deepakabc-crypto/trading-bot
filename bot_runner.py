"""
================================================================================
🤖 BOT RUNNER - Background Trading Worker
================================================================================
Runs trading strategies and communicates with dashboard.
================================================================================
"""

import os
import sys
import time
import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ============================================
# IMPORT SETTINGS
# ============================================
try:
    from settings import *
except ImportError:
    API_KEY = os.environ.get("API_KEY", "")
    API_SECRET = os.environ.get("API_SECRET", "")
    API_SESSION = os.environ.get("API_SESSION", "")
    TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
    CAPITAL = int(os.environ.get("CAPITAL", "500000"))
    QUANTITY = 25
    STRATEGY = os.environ.get("STRATEGY", "iron_condor")
    IC_CALL_SELL_DISTANCE = 150
    IC_CALL_BUY_DISTANCE = 250
    IC_PUT_SELL_DISTANCE = 150
    IC_PUT_BUY_DISTANCE = 250
    IC_TARGET_PERCENT = 50
    IC_STOP_LOSS_PERCENT = 100
    STR_TARGET_PERCENT = 30
    STR_STOP_LOSS_PERCENT = 20
    ENTRY_TIME_START = "09:20"
    ENTRY_TIME_END = "14:00"
    EXIT_TIME = "15:15"
    TRADING_DAYS = [0, 1, 2, 3, 4]
    MIN_PREMIUM = 30
    CHARGES_PER_LOT = 100
    CHECK_INTERVAL = 30

# ============================================
# DATA FILE
# ============================================
DATA_FILE = "bot_data.json"

def load_data():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"trades": [], "bot_running": False, "strategy": STRATEGY, "session_token": "", "daily_pnl": 0}

def save_data(data):
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except:
        pass

def add_trade(trade):
    data = load_data()
    trade['timestamp'] = datetime.now().isoformat()
    data["trades"].append(trade)
    data["daily_pnl"] = data.get("daily_pnl", 0) + float(trade.get("pnl", 0))
    save_data(data)

# ============================================
# TELEGRAM
# ============================================
class Telegram:
    def __init__(self):
        self.token = TELEGRAM_BOT_TOKEN
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = self.token and self.token != "YOUR_BOT_TOKEN_HERE"
        self.last_update_id = 0
        
    def send(self, message):
        if not self.enabled:
            return
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            requests.post(url, json={"chat_id": self.chat_id, "text": message, "parse_mode": "HTML"}, timeout=10)
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
    
    def check_commands(self):
        if not self.enabled:
            return None
        try:
            import requests
            url = f"https://api.telegram.org/bot{self.token}/getUpdates"
            response = requests.get(url, params={"offset": self.last_update_id + 1, "timeout": 5}, timeout=10)
            updates = response.json().get("result", [])
            
            for update in updates:
                self.last_update_id = update["update_id"]
                message = update.get("message", {})
                text = message.get("text", "")
                
                if text.startswith("/session "):
                    token = text.replace("/session ", "").strip()
                    if token:
                        data = load_data()
                        data["session_token"] = token
                        save_data(data)
                        os.environ["API_SESSION"] = token
                        self.send("✅ Session token updated!")
                        logger.info("Session token updated via Telegram")
                        return ("session", token)
                
                elif text == "/status":
                    data = load_data()
                    status = "🟢 Running" if data.get("bot_running") else "⏸️ Stopped"
                    pnl = data.get("daily_pnl", 0)
                    self.send(f"📊 <b>Bot Status</b>\n\nStatus: {status}\nStrategy: {data.get('strategy', 'N/A')}\nToday's P&L: ₹{pnl:,.0f}")
                    return ("status", None)
                
                elif text == "/start":
                    data = load_data()
                    data["bot_running"] = True
                    save_data(data)
                    self.send("▶️ Bot started!")
                    return ("start", None)
                
                elif text == "/stop":
                    data = load_data()
                    data["bot_running"] = False
                    save_data(data)
                    self.send("⏹️ Bot stopped!")
                    return ("stop", None)
                
                elif text == "/help":
                    self.send("""
🤖 <b>Trading Bot Commands</b>

/session TOKEN - Update API session
/status - Check bot status
/start - Start trading
/stop - Stop trading
/help - Show this help
                    """)
        except Exception as e:
            logger.error(f"Telegram check error: {e}")
        return None

telegram = Telegram()

# ============================================
# BREEZE API
# ============================================
BREEZE_AVAILABLE = False
try:
    from breeze_connect import BreezeConnect
    BREEZE_AVAILABLE = True
except:
    pass

class BreezeAPI:
    def __init__(self):
        self.breeze = None
        self.connected = False
        
    def connect(self):
        if not BREEZE_AVAILABLE:
            logger.warning("breeze_connect not available")
            return False
        
        data = load_data()
        session = data.get("session_token") or os.environ.get("API_SESSION", "")
        
        if not session or not API_KEY or API_KEY == "YOUR_API_KEY_HERE":
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
            telegram.send(f"❌ Connection failed: {str(e)[:100]}")
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
            data = self.breeze.get_quotes(
                stock_code="NIFTY", exchange_code="NFO", expiry_date=expiry,
                product_type="options", right=option_type.lower(), strike_price=str(strike)
            )
            if data and 'Success' in data:
                return float(data['Success'][0]['ltp'])
        except:
            pass
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
                logger.info(f"Order placed: {side} {strike} {option_type}")
                return order['Success']['order_id']
        except Exception as e:
            logger.error(f"Order error: {e}")
        return None
    
    def get_expiry(self):
        today = datetime.now()
        days = (3 - today.weekday()) % 7
        if days == 0 and today.hour >= 15:
            days = 7
        return (today + timedelta(days=days)).strftime("%Y-%m-%d")

# ============================================
# TRADING STRATEGIES
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
        
        sc_p = self.api.get_ltp(sc, "call", expiry) or 0
        bc_p = self.api.get_ltp(bc, "call", expiry) or 0
        sp_p = self.api.get_ltp(sp, "put", expiry) or 0
        bp_p = self.api.get_ltp(bp, "put", expiry) or 0
        
        credit = (sc_p - bc_p) + (sp_p - bp_p)
        if credit < MIN_PREMIUM:
            return False
        
        logger.info(f"🦅 IC Entry: SC={sc}@{sc_p}, BC={bc}@{bc_p}, SP={sp}@{sp_p}, BP={bp}@{bp_p}, Credit={credit}")
        
        self.api.place_order(sc, "call", expiry, QUANTITY, "sell", sc_p)
        self.api.place_order(bc, "call", expiry, QUANTITY, "buy", bc_p)
        self.api.place_order(sp, "put", expiry, QUANTITY, "sell", sp_p)
        self.api.place_order(bp, "put", expiry, QUANTITY, "buy", bp_p)
        
        self.position = {"sc": sc, "bc": bc, "sp": sp, "bp": bp, "expiry": expiry}
        self.entry_premium = credit
        
        telegram.send(f"🦅 <b>Iron Condor Entry</b>\nSell: {sc}CE/{sp}PE\nBuy: {bc}CE/{bp}PE\nCredit: ₹{credit:.0f}")
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
        
        now = datetime.now()
        exit_t = datetime.strptime(EXIT_TIME, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
        if now >= exit_t:
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
            "date": datetime.now().strftime("%Y-%m-%d"),
            "strategy": "IRON_CONDOR",
            "entry_premium": self.entry_premium,
            "exit_premium": exit_prem,
            "pnl": pnl,
            "exit_reason": reason
        })
        
        telegram.send(f"🦅 <b>Iron Condor Exit</b>\nReason: {reason}\nP&L: ₹{pnl:+,.0f}")
        logger.info(f"🦅 IC Exit: {reason}, P&L: {pnl}")
        
        self.position = None
        return pnl

class ShortStraddle:
    def __init__(self, api):
        self.api = api
        self.position = None
        self.entry_premium = 0
        
    def enter(self, spot, expiry):
        atm = round(spot / 50) * 50
        
        ce = self.api.get_ltp(atm, "call", expiry) or 0
        pe = self.api.get_ltp(atm, "put", expiry) or 0
        total = ce + pe
        
        if total < MIN_PREMIUM:
            return False
        
        logger.info(f"📊 Straddle Entry: {atm} CE@{ce}, PE@{pe}, Total={total}")
        
        self.api.place_order(atm, "call", expiry, QUANTITY, "sell", ce)
        self.api.place_order(atm, "put", expiry, QUANTITY, "sell", pe)
        
        self.position = {"strike": atm, "expiry": expiry}
        self.entry_premium = total
        
        telegram.send(f"📊 <b>Straddle Entry</b>\nStrike: {atm}\nCE: ₹{ce:.0f}, PE: ₹{pe:.0f}\nTotal: ₹{total:.0f}")
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
        
        now = datetime.now()
        exit_t = datetime.strptime(EXIT_TIME, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
        if now >= exit_t:
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
            "date": datetime.now().strftime("%Y-%m-%d"),
            "strategy": "SHORT_STRADDLE",
            "entry_premium": self.entry_premium,
            "exit_premium": exit_prem,
            "pnl": pnl,
            "exit_reason": reason
        })
        
        telegram.send(f"📊 <b>Straddle Exit</b>\nReason: {reason}\nP&L: ₹{pnl:+,.0f}")
        logger.info(f"📊 Straddle Exit: {reason}, P&L: {pnl}")
        
        self.position = None
        return pnl

# ============================================
# MAIN RUNNER
# ============================================
def is_trading_time():
    now = datetime.now()
    if now.weekday() not in TRADING_DAYS:
        return False
    start = datetime.strptime(ENTRY_TIME_START, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
    end = datetime.strptime(ENTRY_TIME_END, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
    return start <= now <= end

def is_exit_time():
    now = datetime.now()
    exit_t = datetime.strptime(EXIT_TIME, "%H:%M").replace(year=now.year, month=now.month, day=now.day)
    return now >= exit_t

def run_bot():
    logger.info("🤖 Bot runner starting...")
    
    api = BreezeAPI()
    ic = IronCondor(api)
    straddle = ShortStraddle(api)
    daily_pnl = 0
    last_connect = datetime.now() - timedelta(hours=1)
    
    while True:
        try:
            # Check Telegram commands
            telegram.check_commands()
            
            # Load current state
            data = load_data()
            strategy = data.get("strategy", STRATEGY)
            bot_running = data.get("bot_running", False)
            
            if not bot_running:
                time.sleep(10)
                continue
            
            # Connect to API if needed
            if not api.connected and (datetime.now() - last_connect).seconds > 60:
                api.connect()
                last_connect = datetime.now()
            
            if not api.connected:
                time.sleep(30)
                continue
            
            # Force exit time
            if is_exit_time():
                if ic.position:
                    daily_pnl += ic.exit("TIME_EXIT")
                if straddle.position:
                    daily_pnl += straddle.exit("TIME_EXIT")
                
                data["daily_pnl"] = daily_pnl
                save_data(data)
                telegram.send(f"📊 <b>Day Ended</b>\nTotal P&L: ₹{daily_pnl:,.0f}")
                
                # Wait until next day
                time.sleep(3600)
                daily_pnl = 0
                continue
            
            # Check exits
            if strategy in ["iron_condor", "both"] and ic.position:
                reason = ic.check_exit()
                if reason:
                    daily_pnl += ic.exit(reason)
            
            if strategy in ["straddle", "both"] and straddle.position:
                reason = straddle.check_exit()
                if reason:
                    daily_pnl += straddle.exit(reason)
            
            # Enter new positions
            if is_trading_time():
                spot = api.get_spot()
                expiry = api.get_expiry()
                
                if spot:
                    if strategy in ["iron_condor", "both"] and not ic.position:
                        ic.enter(spot, expiry)
                    
                    if strategy in ["straddle", "both"] and not straddle.position:
                        straddle.enter(spot, expiry)
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Bot error: {e}")
            telegram.send(f"⚠️ Bot error: {str(e)[:100]}")
            time.sleep(60)

if __name__ == "__main__":
    run_bot()
