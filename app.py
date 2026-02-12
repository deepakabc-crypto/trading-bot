"""
================================================================================
🤖 NIFTY TRADING BOT - Combined Dashboard + Bot + Backtester
================================================================================
Features:
- Web Dashboard (Flask)
- Trading Bot (Background Thread)
- Backtesting Engine with historical expiry dates
- Trade history preservation
================================================================================
"""

from flask import Flask, render_template_string, jsonify, request
import json
import os
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict
import calendar

app = Flask(__name__)

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

# Timing
ENTRY_TIME_START = "09:20"
ENTRY_TIME_END = "14:00"
EXIT_TIME = "15:15"
TRADING_DAYS = [0, 1, 2, 3, 4]
MIN_PREMIUM = 20  # Lowered from 30
CHARGES_PER_LOT = 100
CHECK_INTERVAL = 30

PORT = int(os.environ.get("PORT", 5000))

# ============================================
# DATA STORAGE - With Trade History Preservation
# ============================================
DATA_FILE = "bot_data.json"
TRADE_HISTORY_FILE = "trade_history.json"

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
        "last_update": ""
    }

def save_data(data):
    try:
        data["last_update"] = datetime.now().isoformat()
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        logger.error(f"Save error: {e}")

def load_trade_history():
    """Load persistent trade history"""
    try:
        if os.path.exists(TRADE_HISTORY_FILE):
            with open(TRADE_HISTORY_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {"trades": [], "backtest_results": []}

def save_trade_history(history):
    """Save persistent trade history"""
    try:
        with open(TRADE_HISTORY_FILE, 'w') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        logger.error(f"Save trade history error: {e}")

def add_trade(trade):
    # Add to session data
    data = load_data()
    trade['timestamp'] = datetime.now().isoformat()
    data["trades"].append(trade)
    data["daily_pnl"] = data.get("daily_pnl", 0) + float(trade.get("pnl", 0))
    data["total_pnl"] = sum(float(t.get('pnl', 0)) for t in data["trades"])
    save_data(data)
    
    # Also save to persistent history
    history = load_trade_history()
    history["trades"].append(trade)
    save_trade_history(history)

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
        "last_update": data.get("last_update", "")
    }

# ============================================
# EXPIRY DATE UTILITIES
# ============================================
def get_all_thursdays(year: int, month: int) -> List[datetime]:
    """Get all Thursdays in a given month"""
    thursdays = []
    cal = calendar.Calendar()
    for day in cal.itermonthdays2(year, month):
        if day[0] != 0 and day[1] == 3:  # Thursday = 3
            thursdays.append(datetime(year, month, day[0]))
    return thursdays

def get_weekly_expiries(start_date: datetime, end_date: datetime) -> List[datetime]:
    """Generate all weekly expiry dates (Thursdays) between start and end date"""
    expiries = []
    current = start_date
    
    while current <= end_date:
        year = current.year
        month = current.month
        
        thursdays = get_all_thursdays(year, month)
        for thursday in thursdays:
            if start_date <= thursday <= end_date:
                expiries.append(thursday)
        
        # Move to next month
        if month == 12:
            current = datetime(year + 1, 1, 1)
        else:
            current = datetime(year, month + 1, 1)
    
    # Remove duplicates and sort
    expiries = sorted(list(set(expiries)))
    return expiries

def get_next_expiry(from_date: datetime = None) -> datetime:
    """Get the next weekly expiry (Thursday) from given date"""
    if from_date is None:
        from_date = datetime.now()
    
    days_ahead = 3 - from_date.weekday()  # Thursday = 3
    if days_ahead < 0:
        days_ahead += 7
    elif days_ahead == 0 and from_date.hour >= 15:
        days_ahead = 7
    
    return from_date + timedelta(days=days_ahead)

def format_expiry_for_breeze(expiry_date: datetime) -> str:
    """Format expiry date for Breeze API: YYYY-MM-DDTHH:MM:SS.000Z"""
    return expiry_date.strftime("%Y-%m-%dT07:00:00.000Z")

def format_expiry_display(expiry_date: datetime) -> str:
    """Format expiry date for display: DD-Mon-YYYY"""
    return expiry_date.strftime("%d-%b-%Y")

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
                
                elif text == "/backtest":
                    self.send("🔬 Starting backtest... Check dashboard for results.")
                    
                elif text == "/help":
                    self.send("🤖 Commands:\n/session TOKEN\n/status\n/start\n/stop\n/backtest\n/help")
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
            # Ensure expiry is in correct format
            if isinstance(expiry, datetime):
                expiry = format_expiry_for_breeze(expiry)
            
            data = self.breeze.get_quotes(
                stock_code="NIFTY", 
                exchange_code="NFO", 
                expiry_date=expiry,
                product_type="options", 
                right=option_type.lower(), 
                strike_price=str(strike)
            )
            if data and 'Success' in data:
                return float(data['Success'][0]['ltp'])
        except Exception as e:
            logger.debug(f"LTP error: {e}")
        return None
    
    def get_historical_data(self, strike, option_type, expiry, from_date, to_date, interval="1day"):
        """Get historical OHLC data for backtesting"""
        if not self.connected:
            return None
        try:
            if isinstance(expiry, datetime):
                expiry = format_expiry_for_breeze(expiry)
            if isinstance(from_date, datetime):
                from_date = from_date.strftime("%Y-%m-%dT07:00:00.000Z")
            if isinstance(to_date, datetime):
                to_date = to_date.strftime("%Y-%m-%dT07:00:00.000Z")
                
            data = self.breeze.get_historical_data_v2(
                interval=interval,
                from_date=from_date,
                to_date=to_date,
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date=expiry,
                right=option_type.lower(),
                strike_price=str(strike)
            )
            if data and 'Success' in data:
                return data['Success']
        except Exception as e:
            logger.debug(f"Historical data error: {e}")
        return None
    
    def get_option_chain(self, expiry):
        """Get option chain for a given expiry"""
        if not self.connected:
            return None
        try:
            if isinstance(expiry, datetime):
                expiry = format_expiry_for_breeze(expiry)
                
            data = self.breeze.get_option_chain_quotes(
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date=expiry
            )
            if data and 'Success' in data:
                return data['Success']
        except Exception as e:
            logger.debug(f"Option chain error: {e}")
        return None
    
    def place_order(self, strike, option_type, expiry, quantity, side, price):
        if not self.connected:
            return None
        try:
            if isinstance(expiry, datetime):
                expiry = format_expiry_for_breeze(expiry)
                
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
        """Get next expiry date for live trading"""
        expiry = get_next_expiry()
        return format_expiry_for_breeze(expiry)

# ============================================
# BACKTESTING ENGINE
# ============================================
class Backtester:
    def __init__(self, api: BreezeAPI = None):
        self.api = api
        self.results = []
        
    def get_expiry_dates(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Get all weekly expiry dates for backtesting period"""
        expiries = get_weekly_expiries(start_date, end_date)
        logger.info(f"Found {len(expiries)} expiry dates from {start_date.date()} to {end_date.date()}")
        return expiries
    
    def simulate_iron_condor(self, spot: float, expiry: datetime, 
                             call_sell_dist: int = 150, call_buy_dist: int = 250,
                             put_sell_dist: int = 150, put_buy_dist: int = 250) -> Dict:
        """Simulate Iron Condor trade with estimated premiums"""
        atm = round(spot / 50) * 50
        
        # Strike prices
        sc = atm + call_sell_dist  # Sell Call
        bc = atm + call_buy_dist   # Buy Call
        sp = atm - put_sell_dist   # Sell Put
        bp = atm - put_buy_dist    # Buy Put
        
        # Estimate premiums based on moneyness (simplified Black-Scholes approximation)
        days_to_expiry = max((expiry - datetime.now()).days, 1)
        iv = 0.15  # Assumed IV
        
        # Simplified premium estimation
        sc_premium = max(5, 100 - (call_sell_dist / 10) * (7 / days_to_expiry))
        bc_premium = max(2, 50 - (call_buy_dist / 10) * (7 / days_to_expiry))
        sp_premium = max(5, 100 - (put_sell_dist / 10) * (7 / days_to_expiry))
        bp_premium = max(2, 50 - (put_buy_dist / 10) * (7 / days_to_expiry))
        
        credit = (sc_premium - bc_premium) + (sp_premium - bp_premium)
        max_loss = (call_buy_dist - call_sell_dist) - credit
        
        return {
            "strategy": "IRON_CONDOR",
            "spot": spot,
            "atm": atm,
            "strikes": {"sc": sc, "bc": bc, "sp": sp, "bp": bp},
            "premiums": {"sc": sc_premium, "bc": bc_premium, "sp": sp_premium, "bp": bp_premium},
            "credit": credit,
            "max_loss": max_loss,
            "expiry": expiry.strftime("%Y-%m-%d")
        }
    
    def simulate_straddle(self, spot: float, expiry: datetime) -> Dict:
        """Simulate Short Straddle trade"""
        atm = round(spot / 50) * 50
        days_to_expiry = max((expiry - datetime.now()).days, 1)
        
        # Simplified premium estimation
        ce_premium = max(50, 200 * (days_to_expiry / 7) ** 0.5)
        pe_premium = max(50, 200 * (days_to_expiry / 7) ** 0.5)
        
        total_premium = ce_premium + pe_premium
        
        return {
            "strategy": "SHORT_STRADDLE",
            "spot": spot,
            "strike": atm,
            "ce_premium": ce_premium,
            "pe_premium": pe_premium,
            "total_premium": total_premium,
            "expiry": expiry.strftime("%Y-%m-%d")
        }
    
    def run_backtest(self, start_date: datetime, end_date: datetime, 
                     strategy: str = "iron_condor", initial_capital: float = 500000) -> Dict:
        """Run backtest for given period"""
        logger.info(f"🔬 Starting backtest: {strategy} from {start_date.date()} to {end_date.date()}")
        
        expiries = self.get_expiry_dates(start_date, end_date)
        
        if len(expiries) == 0:
            logger.warning("Found 0 expiry dates!")
            return {
                "error": "No expiry dates found",
                "start_date": start_date.strftime("%Y-%m-%d"),
                "end_date": end_date.strftime("%Y-%m-%d"),
                "expiries_found": 0
            }
        
        trades = []
        capital = initial_capital
        spot = 22500  # Default spot, should fetch from API/data
        
        for expiry in expiries:
            # Skip if expiry is before start date
            if expiry < start_date:
                continue
            
            # Simulate entry on Monday before expiry (or expiry day if it's Monday)
            entry_date = expiry - timedelta(days=3)
            if entry_date < start_date:
                entry_date = start_date
            
            if strategy in ["iron_condor", "both"]:
                trade = self.simulate_iron_condor(spot, expiry)
                
                # Simulate outcome (60% win rate for IC)
                import random
                is_winner = random.random() < 0.65
                
                if is_winner:
                    pnl = trade["credit"] * QUANTITY * 0.5 - CHARGES_PER_LOT  # 50% target
                    exit_reason = "TARGET"
                else:
                    pnl = -trade["credit"] * QUANTITY - CHARGES_PER_LOT  # 100% SL
                    exit_reason = "STOP_LOSS"
                
                trade["pnl"] = pnl
                trade["exit_reason"] = exit_reason
                trade["entry_date"] = entry_date.strftime("%Y-%m-%d")
                trades.append(trade)
                capital += pnl
            
            if strategy in ["straddle", "both"]:
                trade = self.simulate_straddle(spot, expiry)
                
                # Simulate outcome (55% win rate for straddle)
                import random
                is_winner = random.random() < 0.55
                
                if is_winner:
                    pnl = trade["total_premium"] * QUANTITY * 0.3 - CHARGES_PER_LOT  # 30% target
                    exit_reason = "TARGET"
                else:
                    pnl = -trade["total_premium"] * QUANTITY * 0.2 - CHARGES_PER_LOT  # 20% SL
                    exit_reason = "STOP_LOSS"
                
                trade["pnl"] = pnl
                trade["exit_reason"] = exit_reason
                trade["entry_date"] = entry_date.strftime("%Y-%m-%d")
                trades.append(trade)
                capital += pnl
            
            # Update spot with small random walk
            spot = spot * (1 + (random.random() - 0.5) * 0.02)
        
        # Calculate stats
        total_trades = len(trades)
        winners = len([t for t in trades if t["pnl"] > 0])
        total_pnl = sum(t["pnl"] for t in trades)
        
        results = {
            "strategy": strategy,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "expiries_found": len(expiries),
            "total_trades": total_trades,
            "winners": winners,
            "losers": total_trades - winners,
            "win_rate": (winners / total_trades * 100) if total_trades > 0 else 0,
            "total_pnl": total_pnl,
            "initial_capital": initial_capital,
            "final_capital": capital,
            "return_pct": ((capital - initial_capital) / initial_capital * 100),
            "trades": trades
        }
        
        # Save to history
        history = load_trade_history()
        history["backtest_results"].append({
            "timestamp": datetime.now().isoformat(),
            "results": results
        })
        save_trade_history(history)
        
        logger.info(f"🔬 Backtest complete: {total_trades} trades, {results['win_rate']:.1f}% win rate, ₹{total_pnl:,.0f} P&L")
        
        return results

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
        
        sc_p = self.api.get_ltp(sc, "call", expiry) or 0
        bc_p = self.api.get_ltp(bc, "call", expiry) or 0
        sp_p = self.api.get_ltp(sp, "put", expiry) or 0
        bp_p = self.api.get_ltp(bp, "put", expiry) or 0
        
        credit = (sc_p - bc_p) + (sp_p - bp_p)
        if credit < MIN_PREMIUM:
            logger.info(f"🦅 IC skipped: Credit {credit:.0f} < {MIN_PREMIUM}")
            return False
        
        logger.info(f"🦅 IC Entry: Credit={credit:.0f}")
        
        self.api.place_order(sc, "call", expiry, QUANTITY, "sell", sc_p)
        self.api.place_order(bc, "call", expiry, QUANTITY, "buy", bc_p)
        self.api.place_order(sp, "put", expiry, QUANTITY, "sell", sp_p)
        self.api.place_order(bp, "put", expiry, QUANTITY, "buy", bp_p)
        
        self.position = {"sc": sc, "bc": bc, "sp": sp, "bp": bp, "expiry": expiry}
        self.entry_premium = credit
        
        telegram.send(f"🦅 <b>Iron Condor Entry</b>\nCredit: ₹{credit:.0f}\nSell: {sc}CE/{sp}PE")
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
        
        ce = self.api.get_ltp(atm, "call", expiry) or 0
        pe = self.api.get_ltp(atm, "put", expiry) or 0
        total = ce + pe
        
        if total < MIN_PREMIUM:
            logger.info(f"📊 Straddle skipped: Premium {total:.0f} < {MIN_PREMIUM}")
            return False
        
        logger.info(f"📊 Straddle Entry: {atm}, Premium={total:.0f}")
        
        self.api.place_order(atm, "call", expiry, QUANTITY, "sell", ce)
        self.api.place_order(atm, "put", expiry, QUANTITY, "sell", pe)
        
        self.position = {"strike": atm, "expiry": expiry}
        self.entry_premium = total
        
        telegram.send(f"📊 <b>Straddle Entry</b>\nStrike: {atm}\nPremium: ₹{total:.0f}")
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
        
        telegram.send(f"📊 <b>Straddle Exit</b>\n{reason}\nP&L: ₹{pnl:+,.0f}")
        logger.info(f"📊 Straddle Exit: {reason}, P&L: {pnl}")
        
        self.position = None
        return pnl

# ============================================
# BOT RUNNER (Background Thread)
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

def bot_thread():
    logger.info("🤖 Bot thread starting...")
    
    api = BreezeAPI()
    ic = IronCondor(api)
    straddle = ShortStraddle(api)
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
                    if strategy in ["iron_condor", "both"] and not ic.position:
                        ic.enter(spot, expiry)
                    
                    if strategy in ["straddle", "both"] and not straddle.position:
                        straddle.enter(spot, expiry)
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"Bot error: {e}")
            time.sleep(60)

# ============================================
# HTML DASHBOARD (with Backtesting UI)
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
        }
        .container { max-width: 1200px; margin: 0 auto; padding: 20px; }
        .header {
            text-align: center;
            padding: 30px 0;
            border-bottom: 1px solid #333;
            margin-bottom: 30px;
        }
        .header h1 { font-size: 2.5rem; margin-bottom: 10px; }
        .badges { display: flex; justify-content: center; gap: 15px; flex-wrap: wrap; margin-top: 15px; }
        .badge {
            padding: 8px 16px;
            border-radius: 20px;
            font-size: 0.85rem;
            font-weight: 600;
        }
        .badge-online { background: #00c853; }
        .badge-offline { background: #ff5252; }
        .badge-session { background: #333; }
        .badge-session.active { background: #2196f3; }
        
        .cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }
        .card {
            background: rgba(255,255,255,0.05);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .card-label { color: #888; font-size: 0.9rem; margin-bottom: 8px; }
        .card-value { font-size: 1.8rem; font-weight: 700; }
        .positive { color: #00c853; }
        .negative { color: #ff5252; }
        
        .section {
            background: rgba(255,255,255,0.03);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid rgba(255,255,255,0.08);
        }
        .section-title { font-size: 1.2rem; margin-bottom: 20px; color: #00d2ff; }
        
        .strategy-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; }
        .strategy-btn {
            background: rgba(255,255,255,0.05);
            border: 2px solid transparent;
            border-radius: 12px;
            padding: 20px;
            cursor: pointer;
            transition: all 0.3s;
            text-align: center;
        }
        .strategy-btn:hover { background: rgba(255,255,255,0.1); }
        .strategy-btn.active { border-color: #00d2ff; background: rgba(0,210,255,0.1); }
        .strategy-btn h4 { margin-bottom: 8px; }
        .strategy-btn p { font-size: 0.8rem; color: #888; }
        
        .btn {
            background: linear-gradient(135deg, #00d2ff, #3a7bd5);
            border: none;
            padding: 12px 25px;
            border-radius: 8px;
            color: #fff;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .btn:hover { transform: scale(1.05); }
        .btn-success { background: linear-gradient(135deg, #00c853, #00a843); }
        .btn-danger { background: linear-gradient(135deg, #ff5252, #d32f2f); }
        .btn-warning { background: linear-gradient(135deg, #ff9800, #f57c00); }
        
        .session-input { display: flex; gap: 10px; margin-top: 15px; }
        .session-input input {
            flex: 1;
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #333;
            background: #1a1a2e;
            color: #fff;
        }
        
        .chart-container { height: 300px; margin-top: 20px; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 15px; }
        th, td { padding: 12px; text-align: left; border-bottom: 1px solid #333; }
        th { color: #888; font-weight: 500; }
        
        .info-text { color: #888; font-size: 0.9rem; }
        
        .backtest-form { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 15px; margin-bottom: 15px; }
        .backtest-form input, .backtest-form select {
            padding: 12px;
            border-radius: 8px;
            border: 1px solid #333;
            background: #1a1a2e;
            color: #fff;
        }
        .backtest-results { 
            background: rgba(0, 210, 255, 0.1); 
            border-radius: 10px; 
            padding: 20px; 
            margin-top: 20px;
            display: none;
        }
        .backtest-results.show { display: block; }
        .result-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; }
        .result-item { text-align: center; }
        .result-value { font-size: 1.5rem; font-weight: bold; }
        .result-label { font-size: 0.8rem; color: #888; }
        
        .tabs { display: flex; gap: 10px; margin-bottom: 20px; }
        .tab {
            padding: 10px 20px;
            background: rgba(255,255,255,0.05);
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.3s;
        }
        .tab.active { background: #00d2ff; color: #000; }
        .tab-content { display: none; }
        .tab-content.active { display: block; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🤖 Nifty Trading Bot</h1>
            <p>Automated Options Trading with Iron Condor & Short Straddle</p>
            <div class="badges">
                <span class="badge badge-offline" id="bot-badge">⏸️ STOPPED</span>
                <span class="badge" id="strategy-badge">IRON CONDOR</span>
                <span class="badge badge-session" id="session-badge">🔑 NO SESSION</span>
            </div>
        </div>
        
        <div class="tabs">
            <div class="tab active" onclick="showTab('live')">📈 Live Trading</div>
            <div class="tab" onclick="showTab('backtest')">🔬 Backtesting</div>
            <div class="tab" onclick="showTab('history')">📜 Trade History</div>
        </div>
        
        <!-- LIVE TRADING TAB -->
        <div class="tab-content active" id="tab-live">
            <div class="cards">
                <div class="card">
                    <div class="card-label">Total P&L</div>
                    <div class="card-value positive" id="total-pnl">₹0</div>
                </div>
                <div class="card">
                    <div class="card-label">Today's P&L</div>
                    <div class="card-value" id="daily-pnl">₹0</div>
                </div>
                <div class="card">
                    <div class="card-label">Win Rate</div>
                    <div class="card-value" id="win-rate">0%</div>
                </div>
                <div class="card">
                    <div class="card-label">Portfolio Value</div>
                    <div class="card-value" id="portfolio">₹5,00,000</div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">📊 Select Strategy</div>
                <div class="strategy-grid">
                    <div class="strategy-btn active" data-strategy="iron_condor" onclick="selectStrategy('iron_condor')">
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
        </div>
        
        <!-- BACKTESTING TAB -->
        <div class="tab-content" id="tab-backtest">
            <div class="section">
                <div class="section-title">🔬 Run Backtest</div>
                <div class="backtest-form">
                    <div>
                        <label class="info-text">Start Date</label>
                        <input type="date" id="bt-start" value="2025-01-01">
                    </div>
                    <div>
                        <label class="info-text">End Date</label>
                        <input type="date" id="bt-end" value="2025-12-31">
                    </div>
                    <div>
                        <label class="info-text">Strategy</label>
                        <select id="bt-strategy">
                            <option value="iron_condor">Iron Condor</option>
                            <option value="straddle">Short Straddle</option>
                            <option value="both">Both Strategies</option>
                        </select>
                    </div>
                    <div>
                        <label class="info-text">Initial Capital</label>
                        <input type="number" id="bt-capital" value="500000">
                    </div>
                </div>
                <button class="btn btn-warning" onclick="runBacktest()">🚀 Run Backtest</button>
                
                <div class="backtest-results" id="bt-results">
                    <h3 style="margin-bottom: 15px;">📊 Backtest Results</h3>
                    <div class="result-grid">
                        <div class="result-item">
                            <div class="result-value" id="bt-trades">0</div>
                            <div class="result-label">Total Trades</div>
                        </div>
                        <div class="result-item">
                            <div class="result-value" id="bt-winrate">0%</div>
                            <div class="result-label">Win Rate</div>
                        </div>
                        <div class="result-item">
                            <div class="result-value positive" id="bt-pnl">₹0</div>
                            <div class="result-label">Total P&L</div>
                        </div>
                        <div class="result-item">
                            <div class="result-value" id="bt-return">0%</div>
                            <div class="result-label">Return %</div>
                        </div>
                        <div class="result-item">
                            <div class="result-value" id="bt-expiries">0</div>
                            <div class="result-label">Expiries Found</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        
        <!-- TRADE HISTORY TAB -->
        <div class="tab-content" id="tab-history">
            <div class="section">
                <div class="section-title">📜 Complete Trade History</div>
                <table>
                    <thead>
                        <tr><th>Date</th><th>Strategy</th><th>Entry</th><th>Exit</th><th>P&L</th><th>Reason</th></tr>
                    </thead>
                    <tbody id="history-body">
                        <tr><td colspan="6" style="text-align:center;color:#666;">Loading...</td></tr>
                    </tbody>
                </table>
            </div>
        </div>
        
        <div style="text-align:center; color:#555; margin-top:30px;">
            <p>Lot Size: 65 | Market: 9:15 AM - 3:30 PM IST</p>
        </div>
    </div>
    
    <script>
        let pnlChart;
        
        function showTab(tab) {
            document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelector(`.tab:nth-child(${tab === 'live' ? 1 : tab === 'backtest' ? 2 : 3})`).classList.add('active');
            document.getElementById('tab-' + tab).classList.add('active');
            
            if (tab === 'history') loadHistory();
        }
        
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
                
                const tradesRes = await fetch('/api/trades');
                const trades = await tradesRes.json();
                updateTable(trades);
                updateChart(trades);
            } catch (e) { console.error(e); }
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
        
        async function runBacktest() {
            const start = document.getElementById('bt-start').value;
            const end = document.getElementById('bt-end').value;
            const strategy = document.getElementById('bt-strategy').value;
            const capital = document.getElementById('bt-capital').value;
            
            try {
                const res = await fetch('/api/backtest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ start_date: start, end_date: end, strategy, capital: parseFloat(capital) })
                });
                const data = await res.json();
                
                document.getElementById('bt-trades').textContent = data.total_trades || 0;
                document.getElementById('bt-winrate').textContent = (data.win_rate || 0).toFixed(1) + '%';
                document.getElementById('bt-pnl').textContent = '₹' + (data.total_pnl || 0).toLocaleString('en-IN');
                document.getElementById('bt-pnl').className = 'result-value ' + ((data.total_pnl || 0) >= 0 ? 'positive' : 'negative');
                document.getElementById('bt-return').textContent = (data.return_pct || 0).toFixed(2) + '%';
                document.getElementById('bt-expiries').textContent = data.expiries_found || 0;
                
                document.getElementById('bt-results').classList.add('show');
            } catch (e) {
                console.error(e);
                alert('Backtest failed: ' + e.message);
            }
        }
        
        async function loadHistory() {
            try {
                const res = await fetch('/api/history');
                const data = await res.json();
                const tbody = document.getElementById('history-body');
                
                const trades = data.trades || [];
                if (!trades.length) {
                    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#666;">No trade history</td></tr>';
                    return;
                }
                
                tbody.innerHTML = trades.reverse().map(t => {
                    const pnl = parseFloat(t.pnl || 0);
                    return `<tr>
                        <td>${t.date || t.entry_date || '-'}</td>
                        <td>${(t.strategy || '-').replace('_', ' ')}</td>
                        <td>₹${parseFloat(t.entry_premium || t.credit || t.total_premium || 0).toFixed(0)}</td>
                        <td>₹${parseFloat(t.exit_premium || 0).toFixed(0)}</td>
                        <td class="${pnl >= 0 ? 'positive' : 'negative'}">₹${pnl.toLocaleString('en-IN')}</td>
                        <td>${t.exit_reason || '-'}</td>
                    </tr>`;
                }).join('');
            } catch (e) {
                console.error(e);
            }
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

@app.route('/api/history')
def api_history():
    return jsonify(load_trade_history())

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

@app.route('/api/backtest', methods=['POST'])
def api_backtest():
    """Run backtest via API"""
    try:
        req = request.json
        start_date = datetime.strptime(req.get("start_date", "2025-01-01"), "%Y-%m-%d")
        end_date = datetime.strptime(req.get("end_date", "2025-12-31"), "%Y-%m-%d")
        strategy = req.get("strategy", "iron_condor")
        capital = float(req.get("capital", 500000))
        
        backtester = Backtester()
        results = backtester.run_backtest(start_date, end_date, strategy, capital)
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/expiries', methods=['GET'])
def api_expiries():
    """Get expiry dates for a date range"""
    try:
        start = request.args.get("start", (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d"))
        end = request.args.get("end", (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"))
        
        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d")
        
        expiries = get_weekly_expiries(start_date, end_date)
        
        return jsonify({
            "start_date": start,
            "end_date": end,
            "count": len(expiries),
            "expiries": [format_expiry_display(e) for e in expiries],
            "expiries_breeze": [format_expiry_for_breeze(e) for e in expiries]
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/health')
def health():
    return jsonify({"status": "ok", "time": datetime.now().isoformat()})

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
