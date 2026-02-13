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
import math
import random
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
API_SESSION = os.environ.get("API_SESSION", "") or os.environ.get("SESSION_TOKEN", "")  # Breeze session token
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
CAPITAL = int(os.environ.get("CAPITAL", "500000"))

# Lot size settings - MULTIPLE LOTS SUPPORT
LOT_SIZE = int(os.environ.get("LOT_SIZE", "75"))  # Nifty lot size (changed to 75 from 65)
NUM_LOTS = int(os.environ.get("NUM_LOTS", "1"))   # Number of lots to trade
QUANTITY = LOT_SIZE * NUM_LOTS  # Total quantity

STRATEGY = os.environ.get("STRATEGY", "iron_condor")

# Strategy settings
IC_CALL_SELL_DISTANCE = int(os.environ.get("IC_CALL_SELL_DISTANCE", "150"))
IC_CALL_BUY_DISTANCE = int(os.environ.get("IC_CALL_BUY_DISTANCE", "250"))
IC_PUT_SELL_DISTANCE = int(os.environ.get("IC_PUT_SELL_DISTANCE", "150"))
IC_PUT_BUY_DISTANCE = int(os.environ.get("IC_PUT_BUY_DISTANCE", "250"))
IC_TARGET_PERCENT = int(os.environ.get("IC_TARGET_PERCENT", "50"))
IC_STOP_LOSS_PERCENT = int(os.environ.get("IC_STOP_LOSS_PERCENT", "100"))
STR_TARGET_PERCENT = int(os.environ.get("STR_TARGET_PERCENT", "30"))
STR_STOP_LOSS_PERCENT = int(os.environ.get("STR_STOP_LOSS_PERCENT", "20"))

# === IMPROVED IC SETTINGS ===
# VIX-based entry filter (skip trades when volatility is too high)
IC_VIX_MAX = float(os.environ.get("IC_VIX_MAX", "16"))           # Don't enter IC if India VIX > this
IC_VIX_MIN = float(os.environ.get("IC_VIX_MIN", "9"))            # Don't enter IC if India VIX < this (too cheap premiums)

# Dynamic strike selection mode: "fixed" (original) or "delta" (OI/premium based)
IC_STRIKE_MODE = os.environ.get("IC_STRIKE_MODE", "fixed")       # "fixed" or "dynamic"
IC_MIN_CREDIT = float(os.environ.get("IC_MIN_CREDIT", "20"))     # Minimum net credit to enter IC

# Per-leg stop loss: exit threatened side independently
IC_LEG_SL_ENABLED = os.environ.get("IC_LEG_SL_ENABLED", "true").lower() == "true"
IC_LEG_SL_PERCENT = int(os.environ.get("IC_LEG_SL_PERCENT", "150"))  # Exit a spread when it loses 150% of its credit

# Trailing stop: lock in profits as trade moves favorably
IC_TRAILING_SL = os.environ.get("IC_TRAILING_SL", "true").lower() == "true"
IC_TRAILING_ACTIVATE_PCT = int(os.environ.get("IC_TRAILING_ACTIVATE_PCT", "30"))  # Activate trailing SL after 30% profit
IC_TRAILING_OFFSET_PCT = int(os.environ.get("IC_TRAILING_OFFSET_PCT", "15"))      # Trail 15% behind peak profit

# Re-entry after stop loss (don't re-enter same day after SL hit)
IC_REENTRY_AFTER_SL = os.environ.get("IC_REENTRY_AFTER_SL", "false").lower() == "true"

# Spot proximity adjustment: widen strikes if spot is near day's high/low
IC_SPOT_BUFFER = os.environ.get("IC_SPOT_BUFFER", "true").lower() == "true"

# Expiry day avoidance: don't open new IC on expiry day (high gamma risk)
IC_AVOID_EXPIRY_DAY = os.environ.get("IC_AVOID_EXPIRY_DAY", "true").lower() == "true"

# Adjustment mode: close threatened spread instead of full exit
IC_ADJUSTMENT_ENABLED = os.environ.get("IC_ADJUSTMENT_ENABLED", "true").lower() == "true"
IC_ADJUSTMENT_TRIGGER_PCT = int(os.environ.get("IC_ADJUSTMENT_TRIGGER_PCT", "70"))  # Adjust when one spread loses 70% of total credit

# Daily loss limit: stop trading if daily realized loss exceeds this
IC_DAILY_LOSS_LIMIT = float(os.environ.get("IC_DAILY_LOSS_LIMIT", "0"))  # 0 = disabled. E.g. 5000 = stop after ₹5000 daily loss

# Timing (IST - Indian Standard Time)
ENTRY_TIME_START = os.environ.get("ENTRY_TIME_START", "09:20")
ENTRY_TIME_END = os.environ.get("ENTRY_TIME_END", "14:00")
EXIT_TIME = os.environ.get("EXIT_TIME", "15:15")
TRADING_DAYS = [0, 1, 2, 3, 4]  # Monday to Friday
MIN_PREMIUM = int(os.environ.get("MIN_PREMIUM", "10"))  # Lowered to 10
CHARGES_PER_LOT = int(os.environ.get("CHARGES_PER_LOT", "100"))
CHECK_INTERVAL = int(os.environ.get("CHECK_INTERVAL", "60"))  # Increased to 60 seconds to avoid rate limits

# Auto-start trading
AUTO_START = os.environ.get("AUTO_START", "true").lower() == "true"

# Expiry settings
USE_CURRENT_EXPIRY = os.environ.get("USE_CURRENT_EXPIRY", "false").lower() == "true"  # Use current week expiry even on Thursday
EXPIRY_DAY_CUTOFF = os.environ.get("EXPIRY_DAY_CUTOFF", "09:30")  # After this time on Thursday, use next expiry

# Custom expiry override (for holiday-shifted expiries)
# Format: DD-MM-YYYY or YYYY-MM-DD (e.g., "17-02-2026" or "2026-02-17")
CUSTOM_EXPIRY = os.environ.get("CUSTOM_EXPIRY", "")  # Set this when expiry is not on Thursday

PORT = int(os.environ.get("PORT", 5000))

# Timezone handling for IST
try:
    import pytz
    IST = pytz.timezone('Asia/Kolkata')
except:
    IST = None
    logger.warning("pytz not available - using system time")

def get_ist_now():
    """Get current time in IST"""
    if IST:
        return datetime.now(IST)
    return datetime.now()

# ============================================
# DATA STORAGE - With Trade History Preservation
# ============================================
DATA_FILE = "bot_data.json"
TRADE_HISTORY_FILE = "trade_history.json"
POSITION_FILE = "live_position.json"

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

def load_position():
    """Load current live position"""
    try:
        if os.path.exists(POSITION_FILE):
            with open(POSITION_FILE, 'r') as f:
                return json.load(f)
    except:
        pass
    return {
        "iron_condor": None,
        "straddle": None,
        "last_update": ""
    }

def save_position(position_data):
    """Save current live position"""
    try:
        position_data["last_update"] = datetime.now().isoformat()
        with open(POSITION_FILE, 'w') as f:
            json.dump(position_data, f, indent=2)
    except Exception as e:
        logger.error(f"Save position error: {e}")

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

def parse_custom_expiry(expiry_str: str) -> datetime:
    """Parse custom expiry date from various formats"""
    formats = [
        "%d-%m-%Y",    # 17-02-2026
        "%Y-%m-%d",    # 2026-02-17
        "%d-%b-%Y",    # 17-Feb-2026
        "%d/%m/%Y",    # 17/02/2026
    ]
    for fmt in formats:
        try:
            return datetime.strptime(expiry_str.strip(), fmt)
        except:
            continue
    return None

def get_next_expiry(from_date: datetime = None) -> datetime:
    """Get the next weekly expiry date
    
    Priority:
    1. CUSTOM_EXPIRY environment variable (for holiday-shifted expiries)
    2. Calculated Thursday expiry
    
    On Thursday (expiry day):
    - Before cutoff time: Use current day's expiry (if USE_CURRENT_EXPIRY=true)
    - After cutoff time: Use next week's expiry
    """
    
    # Check for custom expiry override first
    if CUSTOM_EXPIRY:
        custom = parse_custom_expiry(CUSTOM_EXPIRY)
        if custom:
            logger.info(f"📅 Using CUSTOM_EXPIRY: {custom.strftime('%d-%b-%Y')}")
            return custom
        else:
            logger.warning(f"⚠️ Could not parse CUSTOM_EXPIRY: {CUSTOM_EXPIRY}")
    
    if from_date is None:
        from_date = get_ist_now()
    
    # Remove timezone info for calculation
    if hasattr(from_date, 'tzinfo') and from_date.tzinfo is not None:
        from_date = from_date.replace(tzinfo=None)
    
    current_weekday = from_date.weekday()  # Monday=0, Thursday=3
    current_time = from_date.strftime("%H:%M")
    
    # Thursday = 3
    if current_weekday == 3:  # It's Thursday (expiry day)
        if USE_CURRENT_EXPIRY and current_time < EXPIRY_DAY_CUTOFF:
            # Use today's expiry (before cutoff)
            return from_date.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Use next Thursday
            return from_date.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=7)
    
    # For other days, find next Thursday
    days_ahead = 3 - current_weekday  # Thursday = 3
    if days_ahead <= 0:  # Already past Thursday this week
        days_ahead += 7
    
    next_thursday = from_date + timedelta(days=days_ahead)
    return next_thursday.replace(hour=0, minute=0, second=0, microsecond=0)

def format_expiry_for_breeze(expiry_date: datetime) -> str:
    """Format expiry date for Breeze API
    
    Breeze accepts multiple formats. We'll use: YYYY-MM-DDTHH:MM:SS.000Z
    But also try: DD-Mon-YYYY format as fallback
    """
    # Primary format: ISO with time
    return expiry_date.strftime("%Y-%m-%dT07:00:00.000Z")

def format_expiry_breeze_alt(expiry_date: datetime) -> str:
    """Alternative format: DD-Mon-YYYY"""
    return expiry_date.strftime("%d-%b-%Y")

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
        self.last_call_time = 0
        self.min_call_interval = 0.5  # Minimum 500ms between API calls
        self.ltp_cache = {}  # Cache for LTP values
        self.cache_ttl = 5  # Cache TTL in seconds
        self.calls_per_minute = 0
        self.last_minute_reset = time.time()
        self.max_calls_per_minute = 45  # Stay well under limit
    
    def _rate_limit(self):
        """Enforce rate limiting between API calls"""
        current_time = time.time()
        
        # Reset minute counter
        if current_time - self.last_minute_reset >= 60:
            self.calls_per_minute = 0
            self.last_minute_reset = current_time
        
        # Check if we're approaching the limit
        if self.calls_per_minute >= self.max_calls_per_minute:
            wait_time = 60 - (current_time - self.last_minute_reset)
            if wait_time > 0:
                logger.warning(f"⏳ Rate limit approaching ({self.calls_per_minute} calls), waiting {wait_time:.0f}s...")
                time.sleep(wait_time + 2)
                self.calls_per_minute = 0
                self.last_minute_reset = time.time()
        
        # Ensure minimum interval between calls
        elapsed = current_time - self.last_call_time
        if elapsed < self.min_call_interval:
            time.sleep(self.min_call_interval - elapsed)
        
        self.last_call_time = time.time()
        self.calls_per_minute += 1
    
    def _get_cache_key(self, strike, option_type, expiry):
        """Generate cache key for LTP"""
        exp_str = expiry.strftime('%Y-%m-%d') if isinstance(expiry, datetime) else str(expiry)[:10]
        return f"{strike}_{option_type}_{exp_str}"
    
    def _get_cached_ltp(self, strike, option_type, expiry):
        """Get LTP from cache if valid"""
        key = self._get_cache_key(strike, option_type, expiry)
        if key in self.ltp_cache:
            cached_time, cached_value = self.ltp_cache[key]
            if time.time() - cached_time < self.cache_ttl:
                return cached_value
        return None
    
    def _set_cached_ltp(self, strike, option_type, expiry, value):
        """Set LTP in cache"""
        key = self._get_cache_key(strike, option_type, expiry)
        self.ltp_cache[key] = (time.time(), value)
        
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
            self._rate_limit()
            data = self.breeze.get_quotes(stock_code="NIFTY", exchange_code="NSE", product_type="cash")
            
            # Check for rate limit error
            if data and data.get('Status') == 5:
                logger.warning("⚠️ Rate limit hit on get_spot, waiting 60s...")
                time.sleep(60)
                self.calls_per_minute = 0
                return None
            
            if data and 'Success' in data and data['Success']:
                return float(data['Success'][0]['ltp'])
        except Exception as e:
            logger.debug(f"Spot error: {e}")
        return None
    
    def get_ltp(self, strike, option_type, expiry):
        """Get LTP for an option with caching and rate limiting"""
        if not self.connected:
            return None
        
        # Check cache first
        cached = self._get_cached_ltp(strike, option_type, expiry)
        if cached is not None:
            logger.debug(f"📦 Cache hit: {strike}{option_type.upper()} = {cached}")
            return cached
        
        # Try multiple expiry formats
        expiry_formats = []
        if isinstance(expiry, datetime):
            expiry_formats = [
                format_expiry_for_breeze(expiry),  # 2026-02-17T07:00:00.000Z
                format_expiry_breeze_alt(expiry),   # 17-Feb-2026
            ]
        elif isinstance(expiry, str):
            expiry_formats = [expiry]
        
        for exp_fmt in expiry_formats:
            try:
                self._rate_limit()
                
                data = self.breeze.get_quotes(
                    stock_code="NIFTY", 
                    exchange_code="NFO", 
                    expiry_date=exp_fmt,
                    product_type="options", 
                    right=option_type.lower(), 
                    strike_price=str(strike)
                )
                
                # Check for rate limit error
                if data and data.get('Status') == 5:
                    logger.warning(f"⚠️ Rate limit hit, waiting 60s...")
                    time.sleep(60)
                    self.calls_per_minute = 0
                    continue
                
                # Check for success
                if data and data.get('Success'):
                    ltp = float(data['Success'][0]['ltp'])
                    if ltp > 0:
                        logger.debug(f"✅ Got LTP {ltp} for {strike}{option_type.upper()}")
                        self._set_cached_ltp(strike, option_type, expiry, ltp)
                        return ltp
                
                # Check for error
                if data and data.get('Error'):
                    if 'Limit exceed' in str(data.get('Error', '')):
                        logger.warning(f"⚠️ Rate limit in response, waiting 60s...")
                        time.sleep(60)
                        self.calls_per_minute = 0
                    else:
                        logger.debug(f"API Error for {strike}{option_type.upper()}: {data.get('Error')}")
                    
            except Exception as e:
                logger.debug(f"LTP error for {strike}{option_type.upper()}: {e}")
        
        return None
    
    def get_ltp_with_retry(self, strike, option_type, expiry, retries=2):
        """Get LTP with retry logic and delays"""
        for attempt in range(retries):
            ltp = self.get_ltp(strike, option_type, expiry)
            if ltp is not None and ltp > 0:
                return ltp
            if attempt < retries - 1:
                logger.debug(f"Retry {attempt + 1} for {strike}{option_type.upper()}")
                time.sleep(3)  # Wait 3 seconds before retry
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
        expiry_str = format_expiry_for_breeze(expiry)
        logger.info(f"📅 Using expiry: {expiry.strftime('%d-%b-%Y')} ({expiry_str})")
        return expiry
    
    def get_expiry_str(self):
        """Get next expiry date as formatted string"""
        return format_expiry_for_breeze(get_next_expiry())
    
    def get_vix(self):
        """Get India VIX value via Nifty VIX quote"""
        if not self.connected:
            return None
        try:
            self._rate_limit()
            # India VIX stock code is INDIA VIX / NIFVIX on NSE
            data = self.breeze.get_quotes(stock_code="INDVIX", exchange_code="NSE", product_type="cash")
            if data and data.get('Success') and data['Success']:
                return float(data['Success'][0].get('ltp', 0))
        except:
            pass
        
        # Fallback: try via historical data
        try:
            self._rate_limit()
            data = self.breeze.get_quotes(stock_code="NIFVIX", exchange_code="NSE", product_type="cash")
            if data and data.get('Success') and data['Success']:
                return float(data['Success'][0].get('ltp', 0))
        except:
            pass
        
        logger.debug("Could not fetch India VIX")
        return None
    
    def get_spot_range(self):
        """Get today's Nifty high/low to gauge intraday range"""
        if not self.connected:
            return None, None
        try:
            self._rate_limit()
            data = self.breeze.get_quotes(stock_code="NIFTY", exchange_code="NSE", product_type="cash")
            if data and data.get('Success') and data['Success']:
                quote = data['Success'][0]
                return float(quote.get('high', 0)), float(quote.get('low', 0))
        except:
            pass
        return None, None

# ============================================
# BACKTESTING ENGINE
# ============================================
class Backtester:
    def __init__(self, api: BreezeAPI = None):
        self.api = api or BreezeAPI()
        self.results = []
        self.use_historical_api = False  # Set to True to fetch from Breeze API
        
    def get_expiry_dates(self, start_date: datetime, end_date: datetime) -> List[datetime]:
        """Get all weekly expiry dates for backtesting period"""
        expiries = get_weekly_expiries(start_date, end_date)
        logger.info(f"Found {len(expiries)} expiry dates from {start_date.date()} to {end_date.date()}")
        return expiries
    
    def estimate_option_premium(self, spot: float, strike: float, days_to_expiry: int, 
                                 option_type: str, iv: float = 0.15) -> float:
        """
        Estimate option premium using simplified Black-Scholes approximation
        More realistic than previous formula
        """
        # Ensure minimum 1 day to expiry
        dte = max(days_to_expiry, 1)
        
        # Calculate moneyness
        if option_type.lower() == "call":
            moneyness = (spot - strike) / spot  # Positive = ITM, Negative = OTM
        else:  # put
            moneyness = (strike - spot) / spot  # Positive = ITM, Negative = OTM
        
        # Time factor (annualized)
        time_factor = math.sqrt(dte / 365)
        
        # Base ATM premium (roughly 1.5-2.5% of spot for weekly options)
        atm_premium = spot * iv * time_factor * 0.4
        
        # Adjust for moneyness
        if moneyness > 0:  # ITM
            intrinsic = abs(spot - strike)
            premium = intrinsic + atm_premium * 0.5  # ITM has less time value
        else:  # OTM
            # Premium decays with distance from ATM
            otm_factor = math.exp(-abs(moneyness) * 10)  # Decay factor
            premium = atm_premium * otm_factor
        
        # Minimum premium
        return max(round(premium, 2), 2.0)
    
    def get_historical_premium(self, strike: int, option_type: str, expiry: datetime, 
                                trade_date: datetime) -> float:
        """
        Get historical premium from Breeze API
        Returns None if not available
        """
        if not self.api.connected:
            return None
        
        try:
            # Format dates for API
            from_date = trade_date.strftime("%Y-%m-%dT09:15:00.000Z")
            to_date = trade_date.strftime("%Y-%m-%dT15:30:00.000Z")
            expiry_str = format_expiry_for_breeze(expiry)
            
            data = self.api.breeze.get_historical_data_v2(
                interval="1day",
                from_date=from_date,
                to_date=to_date,
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date=expiry_str,
                right=option_type.lower(),
                strike_price=str(strike)
            )
            
            if data and data.get('Success') and len(data['Success']) > 0:
                # Return opening price as entry premium
                return float(data['Success'][0].get('open', 0))
        except Exception as e:
            logger.debug(f"Historical data error for {strike}{option_type}: {e}")
        
        return None
    
    def simulate_iron_condor(self, spot: float, expiry: datetime, trade_date: datetime,
                             call_sell_dist: int = 150, call_buy_dist: int = 250,
                             put_sell_dist: int = 150, put_buy_dist: int = 250) -> Dict:
        """Simulate Iron Condor trade with realistic premium estimation"""
        atm = round(spot / 50) * 50
        
        # Strike prices
        sc = atm + call_sell_dist  # Sell Call
        bc = atm + call_buy_dist   # Buy Call
        sp = atm - put_sell_dist   # Sell Put
        bp = atm - put_buy_dist    # Buy Put
        
        # Calculate days to expiry from trade date (NOT from today!)
        days_to_expiry = max((expiry - trade_date).days, 1)
        
        # Try to get historical data from API if enabled
        if self.use_historical_api and self.api.connected:
            sc_premium = self.get_historical_premium(sc, "call", expiry, trade_date)
            bc_premium = self.get_historical_premium(bc, "call", expiry, trade_date)
            sp_premium = self.get_historical_premium(sp, "put", expiry, trade_date)
            bp_premium = self.get_historical_premium(bp, "put", expiry, trade_date)
            
            # If all premiums fetched successfully
            if all([sc_premium, bc_premium, sp_premium, bp_premium]):
                credit = (sc_premium - bc_premium) + (sp_premium - bp_premium)
                return {
                    "strategy": "IRON_CONDOR",
                    "spot": round(spot, 2),
                    "atm": atm,
                    "strikes": {"sc": sc, "bc": bc, "sp": sp, "bp": bp},
                    "premiums": {"sc": sc_premium, "bc": bc_premium, "sp": sp_premium, "bp": bp_premium},
                    "credit": round(credit, 2),
                    "max_loss": (bc - sc) - credit,
                    "expiry": expiry.strftime("%Y-%m-%d"),
                    "days_to_expiry": days_to_expiry,
                    "data_source": "API"
                }
        
        # Use estimation if API not available
        iv = 0.12 + (0.05 * (1 / days_to_expiry))  # IV increases closer to expiry
        
        sc_premium = self.estimate_option_premium(spot, sc, days_to_expiry, "call", iv)
        bc_premium = self.estimate_option_premium(spot, bc, days_to_expiry, "call", iv)
        sp_premium = self.estimate_option_premium(spot, sp, days_to_expiry, "put", iv)
        bp_premium = self.estimate_option_premium(spot, bp, days_to_expiry, "put", iv)
        
        credit = (sc_premium - bc_premium) + (sp_premium - bp_premium)
        max_loss = (bc - sc) - credit
        
        return {
            "strategy": "IRON_CONDOR",
            "spot": round(spot, 2),
            "atm": atm,
            "strikes": {"sc": sc, "bc": bc, "sp": sp, "bp": bp},
            "premiums": {"sc": round(sc_premium, 2), "bc": round(bc_premium, 2), 
                        "sp": round(sp_premium, 2), "bp": round(bp_premium, 2)},
            "credit": round(credit, 2),
            "max_loss": round(max_loss, 2),
            "expiry": expiry.strftime("%Y-%m-%d"),
            "days_to_expiry": days_to_expiry,
            "data_source": "ESTIMATED"
        }
    
    def simulate_straddle(self, spot: float, expiry: datetime, trade_date: datetime) -> Dict:
        """Simulate Short Straddle trade with realistic premium estimation"""
        atm = round(spot / 50) * 50
        days_to_expiry = max((expiry - trade_date).days, 1)
        
        # Try to get historical data from API if enabled
        if self.use_historical_api and self.api.connected:
            ce_premium = self.get_historical_premium(atm, "call", expiry, trade_date)
            pe_premium = self.get_historical_premium(atm, "put", expiry, trade_date)
            
            if ce_premium and pe_premium:
                return {
                    "strategy": "SHORT_STRADDLE",
                    "spot": round(spot, 2),
                    "strike": atm,
                    "ce_premium": ce_premium,
                    "pe_premium": pe_premium,
                    "total_premium": round(ce_premium + pe_premium, 2),
                    "expiry": expiry.strftime("%Y-%m-%d"),
                    "days_to_expiry": days_to_expiry,
                    "data_source": "API"
                }
        
        # Use estimation - ATM options have highest time value
        iv = 0.12 + (0.05 * (1 / days_to_expiry))
        
        ce_premium = self.estimate_option_premium(spot, atm, days_to_expiry, "call", iv)
        pe_premium = self.estimate_option_premium(spot, atm, days_to_expiry, "put", iv)
        
        # ATM options are roughly equal, slight adjustment for put-call parity
        total_premium = ce_premium + pe_premium
        
        return {
            "strategy": "SHORT_STRADDLE",
            "spot": round(spot, 2),
            "strike": atm,
            "ce_premium": round(ce_premium, 2),
            "pe_premium": round(pe_premium, 2),
            "total_premium": round(total_premium, 2),
            "expiry": expiry.strftime("%Y-%m-%d"),
            "days_to_expiry": days_to_expiry,
            "data_source": "ESTIMATED"
        }
    
    def simulate_intraday_exit(self, entry_premium: float, target_pct: float, sl_pct: float,
                                entry_time: str, exit_time: str) -> Dict:
        """
        Simulate intraday price movement and determine exit
        Returns: exit_time, exit_reason, pnl_percent
        """
        # Parse times
        entry_hour, entry_min = map(int, entry_time.split(':'))
        exit_hour, exit_min = map(int, exit_time.split(':'))
        
        # Simulate price checking every 15 minutes
        current_hour = entry_hour
        current_min = entry_min
        
        # Track cumulative premium change (negative = profit for short positions)
        premium_change_pct = 0
        
        while True:
            # Move forward 15 minutes
            current_min += 15
            if current_min >= 60:
                current_min -= 60
                current_hour += 1
            
            # Check if we've reached exit time
            current_time_mins = current_hour * 60 + current_min
            exit_time_mins = exit_hour * 60 + exit_min
            
            if current_time_mins >= exit_time_mins:
                return {
                    "exit_time": exit_time,
                    "exit_reason": "TIME_EXIT",
                    "pnl_percent": premium_change_pct
                }
            
            # Simulate random price movement (-5% to +5% per interval)
            move = (random.random() - 0.5) * 10  # Random move
            premium_change_pct += move
            
            # Check target (premium decreased by target_pct)
            if premium_change_pct <= -target_pct:
                return {
                    "exit_time": f"{current_hour:02d}:{current_min:02d}",
                    "exit_reason": "TARGET",
                    "pnl_percent": target_pct  # Lock in target
                }
            
            # Check stop loss (premium increased by sl_pct)
            if premium_change_pct >= sl_pct:
                return {
                    "exit_time": f"{current_hour:02d}:{current_min:02d}",
                    "exit_reason": "STOP_LOSS",
                    "pnl_percent": -sl_pct  # Lock in loss
                }
    
    def run_backtest(self, start_date: datetime, end_date: datetime, 
                     strategy: str = "iron_condor", initial_capital: float = 500000,
                     entry_time_start: str = None, entry_time_end: str = None,
                     exit_time: str = None, use_historical_api: bool = False) -> Dict:
        """Run backtest for given period using bot's entry/exit times"""
        
        # Use provided times or defaults from settings
        entry_start = entry_time_start or ENTRY_TIME_START
        entry_end = entry_time_end or ENTRY_TIME_END
        force_exit = exit_time or EXIT_TIME
        
        # Set historical API flag
        self.use_historical_api = use_historical_api
        
        logger.info(f"🔬 Starting backtest: {strategy} from {start_date.date()} to {end_date.date()}")
        logger.info(f"⏰ Entry Window: {entry_start} - {entry_end}, Exit Time: {force_exit}")
        logger.info(f"📊 Data Source: {'Breeze API Historical' if use_historical_api else 'Estimated Premiums'}")
        
        # Try to connect to API if using historical data
        if use_historical_api and not self.api.connected:
            logger.info("🔌 Connecting to Breeze API for historical data...")
            self.api.connect()
        
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
        spot = 22500  # Default starting spot
        api_data_count = 0
        estimated_data_count = 0
        
        # Get trading days for each expiry week
        for expiry in expiries:
            if expiry < start_date:
                continue
            
            # Get all trading days for this expiry week (Mon-Thu or Mon-Fri before expiry)
            week_start = expiry - timedelta(days=expiry.weekday())  # Monday of expiry week
            
            # Trade each day of the week until expiry
            trading_days = []
            current_day = week_start
            while current_day <= expiry and current_day <= end_date:
                if current_day >= start_date and current_day.weekday() < 5:  # Weekdays only
                    trading_days.append(current_day)
                current_day += timedelta(days=1)
            
            for trade_date in trading_days:
                # Random entry time within entry window
                entry_h, entry_m = map(int, entry_start.split(':'))
                end_h, end_m = map(int, entry_end.split(':'))
                
                # Random entry time between start and 1 hour after start
                entry_mins = entry_h * 60 + entry_m + random.randint(0, 60)
                actual_entry_time = f"{entry_mins // 60:02d}:{entry_mins % 60:02d}"
                
                if strategy in ["iron_condor", "both"]:
                    trade = self.simulate_iron_condor(
                        spot, expiry, trade_date,  # Pass trade_date!
                        IC_CALL_SELL_DISTANCE, IC_CALL_BUY_DISTANCE,
                        IC_PUT_SELL_DISTANCE, IC_PUT_BUY_DISTANCE
                    )
                    
                    # Track data source
                    if trade.get("data_source") == "API":
                        api_data_count += 1
                    else:
                        estimated_data_count += 1
                    
                    # Simulate intraday exit
                    exit_result = self.simulate_intraday_exit(
                        trade["credit"],
                        IC_TARGET_PERCENT,
                        IC_STOP_LOSS_PERCENT,
                        actual_entry_time,
                        force_exit
                    )
                    
                    # Calculate P&L
                    if exit_result["exit_reason"] == "TARGET":
                        pnl = trade["credit"] * QUANTITY * (IC_TARGET_PERCENT / 100) - CHARGES_PER_LOT
                    elif exit_result["exit_reason"] == "STOP_LOSS":
                        pnl = -trade["credit"] * QUANTITY * (IC_STOP_LOSS_PERCENT / 100) - CHARGES_PER_LOT
                    else:  # TIME_EXIT
                        # Random P&L between -50% and +40%
                        time_exit_pct = (random.random() - 0.4) * 90
                        pnl = trade["credit"] * QUANTITY * (time_exit_pct / 100) - CHARGES_PER_LOT
                    
                    trade["pnl"] = round(pnl, 2)
                    trade["exit_reason"] = exit_result["exit_reason"]
                    trade["entry_date"] = trade_date.strftime("%Y-%m-%d")
                    trade["entry_time"] = actual_entry_time
                    trade["exit_time"] = exit_result["exit_time"]
                    trade["target_pct"] = IC_TARGET_PERCENT
                    trade["sl_pct"] = IC_STOP_LOSS_PERCENT
                    trade["quantity"] = QUANTITY
                    trades.append(trade)
                    capital += pnl
                
                if strategy in ["straddle", "both"]:
                    trade = self.simulate_straddle(spot, expiry, trade_date)  # Pass trade_date!
                    
                    # Track data source
                    if trade.get("data_source") == "API":
                        api_data_count += 1
                    else:
                        estimated_data_count += 1
                    
                    # Simulate intraday exit
                    exit_result = self.simulate_intraday_exit(
                        trade["total_premium"],
                        STR_TARGET_PERCENT,
                        STR_STOP_LOSS_PERCENT,
                        actual_entry_time,
                        force_exit
                    )
                    
                    # Calculate P&L
                    if exit_result["exit_reason"] == "TARGET":
                        pnl = trade["total_premium"] * QUANTITY * (STR_TARGET_PERCENT / 100) - CHARGES_PER_LOT
                    elif exit_result["exit_reason"] == "STOP_LOSS":
                        pnl = -trade["total_premium"] * QUANTITY * (STR_STOP_LOSS_PERCENT / 100) - CHARGES_PER_LOT
                    else:  # TIME_EXIT
                        time_exit_pct = (random.random() - 0.4) * 50
                        pnl = trade["total_premium"] * QUANTITY * (time_exit_pct / 100) - CHARGES_PER_LOT
                    
                    trade["pnl"] = round(pnl, 2)
                    trade["exit_reason"] = exit_result["exit_reason"]
                    trade["entry_date"] = trade_date.strftime("%Y-%m-%d")
                    trade["entry_time"] = actual_entry_time
                    trade["exit_time"] = exit_result["exit_time"]
                    trade["target_pct"] = STR_TARGET_PERCENT
                    trade["sl_pct"] = STR_STOP_LOSS_PERCENT
                    trade["quantity"] = QUANTITY
                    trades.append(trade)
                    capital += pnl
                
                # Update spot with small random walk
                spot = spot * (1 + (random.random() - 0.5) * 0.01)
        
        # Calculate stats
        total_trades = len(trades)
        winners = len([t for t in trades if t["pnl"] > 0])
        losers = len([t for t in trades if t["pnl"] < 0])
        total_pnl = sum(t["pnl"] for t in trades)
        
        # Exit reason breakdown
        target_exits = len([t for t in trades if t["exit_reason"] == "TARGET"])
        sl_exits = len([t for t in trades if t["exit_reason"] == "STOP_LOSS"])
        time_exits = len([t for t in trades if t["exit_reason"] == "TIME_EXIT"])
        
        # Average times
        avg_exit_time = "N/A"
        if trades:
            exit_mins = []
            for t in trades:
                h, m = map(int, t["exit_time"].split(':'))
                exit_mins.append(h * 60 + m)
            avg_mins = sum(exit_mins) // len(exit_mins)
            avg_exit_time = f"{avg_mins // 60:02d}:{avg_mins % 60:02d}"
        
        # Average premium
        avg_premium = 0
        if trades:
            premiums = [t.get("credit") or t.get("total_premium", 0) for t in trades]
            avg_premium = sum(premiums) / len(premiums) if premiums else 0
        
        results = {
            "strategy": strategy,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d"),
            "entry_time_start": entry_start,
            "entry_time_end": entry_end,
            "exit_time": force_exit,
            "expiries_found": len(expiries),
            "total_trades": total_trades,
            "winners": winners,
            "losers": losers,
            "win_rate": (winners / total_trades * 100) if total_trades > 0 else 0,
            "total_pnl": round(total_pnl, 2),
            "initial_capital": initial_capital,
            "final_capital": round(capital, 2),
            "return_pct": round((capital - initial_capital) / initial_capital * 100, 2),
            "exit_breakdown": {
                "target": target_exits,
                "stop_loss": sl_exits,
                "time_exit": time_exits
            },
            "avg_exit_time": avg_exit_time,
            "avg_premium": round(avg_premium, 2),
            "lot_size": LOT_SIZE,
            "num_lots": NUM_LOTS,
            "quantity": QUANTITY,
            "data_source": {
                "api_data": api_data_count,
                "estimated_data": estimated_data_count,
                "use_historical_api": use_historical_api
            },
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
        logger.info(f"📊 Exits: {target_exits} Target, {sl_exits} SL, {time_exits} Time | Avg Exit: {avg_exit_time}")
        logger.info(f"📊 Data: {api_data_count} API, {estimated_data_count} Estimated | Avg Premium: ₹{avg_premium:.2f}")
        
        return results

# ============================================
# IRON CONDOR STRATEGY (Improved v2.0)
# ============================================
class IronCondor:
    def __init__(self, api):
        self.api = api
        self.position = None
        self.entry_premium = 0
        self.entry_prices = {}
        self.entry_time = None
        self.spot_at_entry = None
        self.call_credit = 0
        self.put_credit = 0
        self.peak_pnl_pct = 0       # Track peak P&L % for trailing stop
        self.sl_hit_today = False     # Track if SL was hit today (prevent re-entry)
        self.sl_hit_date = None
        self.call_spread_closed = False  # Track partial exit (adjustment)
        self.put_spread_closed = False
        self.vix_at_entry = None
        self.day_high_at_entry = None
        self.day_low_at_entry = None
    
    def _check_vix_filter(self) -> tuple:
        """Check if India VIX is within acceptable range for IC entry.
        Returns (ok: bool, vix: float|None, reason: str)"""
        vix = self.api.get_vix()
        if vix is None:
            logger.info("🦅 VIX data unavailable - proceeding without VIX filter")
            return True, None, "VIX unavailable"
        
        if vix > IC_VIX_MAX:
            return False, vix, f"VIX {vix:.1f} > {IC_VIX_MAX} (too volatile)"
        if vix < IC_VIX_MIN:
            return False, vix, f"VIX {vix:.1f} < {IC_VIX_MIN} (premiums too cheap)"
        
        return True, vix, f"VIX {vix:.1f} OK"
    
    def _check_expiry_day(self, expiry) -> bool:
        """Check if today is expiry day - avoid opening new IC"""
        if not IC_AVOID_EXPIRY_DAY:
            return True  # Check disabled
        
        now = get_ist_now()
        if hasattr(now, 'tzinfo') and now.tzinfo is not None:
            now = now.replace(tzinfo=None)
        
        if isinstance(expiry, datetime):
            is_expiry_day = now.date() == expiry.date()
        else:
            is_expiry_day = False
        
        if is_expiry_day:
            logger.info("🦅 Skipping IC entry on expiry day (high gamma risk)")
            return False
        return True
    
    def _select_dynamic_strikes(self, spot, expiry):
        """Select strikes dynamically based on option chain OI and premiums.
        Falls back to fixed distances if option chain unavailable."""
        
        # Try to get option chain for smarter strike selection
        chain = self.api.get_option_chain(expiry)
        if not chain:
            logger.info("🦅 Option chain unavailable, using fixed strike distances")
            return None
        
        try:
            atm = round(spot / 50) * 50
            
            # Parse option chain into calls and puts
            calls = {}
            puts = {}
            for item in chain:
                strike = int(float(item.get('strike_price', 0)))
                right = item.get('right', '').lower()
                oi = int(item.get('open_interest', 0))
                ltp = float(item.get('ltp', 0))
                
                if right == 'call' and strike > atm:
                    calls[strike] = {"oi": oi, "ltp": ltp}
                elif right == 'put' and strike < atm:
                    puts[strike] = {"oi": oi, "ltp": ltp}
            
            # Find sell strikes: highest OI strikes within 100-300 points from ATM
            # High OI indicates strong resistance/support → good sell strikes
            best_call_sell = None
            best_call_oi = 0
            for strike in sorted(calls.keys()):
                dist = strike - atm
                if 100 <= dist <= 300 and calls[strike]["oi"] > best_call_oi and calls[strike]["ltp"] >= 5:
                    best_call_oi = calls[strike]["oi"]
                    best_call_sell = strike
            
            best_put_sell = None
            best_put_oi = 0
            for strike in sorted(puts.keys(), reverse=True):
                dist = atm - strike
                if 100 <= dist <= 300 and puts[strike]["oi"] > best_put_oi and puts[strike]["ltp"] >= 5:
                    best_put_oi = puts[strike]["oi"]
                    best_put_sell = strike
            
            if best_call_sell and best_put_sell:
                # Buy strikes: 100 points beyond sell strikes
                sc = best_call_sell
                bc = sc + 100
                sp = best_put_sell
                bp = sp - 100
                
                logger.info(f"🦅 Dynamic strikes (OI-based): SC={sc} (OI:{best_call_oi}), SP={sp} (OI:{best_put_oi})")
                return {"sc": sc, "bc": bc, "sp": sp, "bp": bp}
        except Exception as e:
            logger.debug(f"Dynamic strike selection error: {e}")
        
        return None
    
    def _apply_spot_buffer(self, spot, sc, bc, sp, bp):
        """Widen strikes if spot is near day's high/low (trending market)"""
        if not IC_SPOT_BUFFER:
            return sc, bc, sp, bp
        
        day_high, day_low = self.api.get_spot_range()
        if not day_high or not day_low:
            return sc, bc, sp, bp
        
        self.day_high_at_entry = day_high
        self.day_low_at_entry = day_low
        day_range = day_high - day_low
        
        # If spot is in upper 25% of day's range, widen call side
        if day_range > 50:
            spot_position = (spot - day_low) / day_range  # 0=at low, 1=at high
            
            if spot_position > 0.75:
                # Spot near day high - widen call strikes by 50 points
                sc += 50
                bc += 50
                logger.info(f"🦅 Spot near day high ({spot_position:.0%}) - widened call strikes by 50pts")
            elif spot_position < 0.25:
                # Spot near day low - widen put strikes by 50 points
                sp -= 50
                bp -= 50
                logger.info(f"🦅 Spot near day low ({spot_position:.0%}) - widened put strikes by 50pts")
        
        return sc, bc, sp, bp
        
    def enter(self, spot, expiry):
        # === PRE-ENTRY CHECKS ===
        
        # Check if SL was already hit today (prevent re-entry)
        if not IC_REENTRY_AFTER_SL and self.sl_hit_today:
            now = get_ist_now()
            if self.sl_hit_date and now.strftime("%Y-%m-%d") == self.sl_hit_date:
                logger.info("🦅 IC skipped: SL already hit today, no re-entry")
                return False
            else:
                self.sl_hit_today = False  # New day, reset
        
        # Check VIX filter
        vix_ok, vix, vix_reason = self._check_vix_filter()
        if not vix_ok:
            logger.info(f"🦅 IC skipped: {vix_reason}")
            telegram.send(f"🦅 IC Entry skipped\n{vix_reason}")
            return False
        
        # Check expiry day filter
        if not self._check_expiry_day(expiry):
            telegram.send(f"🦅 IC Entry skipped\nExpiry day - gamma risk too high")
            return False
        
        # === STRIKE SELECTION ===
        atm = round(spot / 50) * 50
        
        # Try dynamic strike selection first
        if IC_STRIKE_MODE == "dynamic":
            dynamic_strikes = self._select_dynamic_strikes(spot, expiry)
            if dynamic_strikes:
                sc = dynamic_strikes["sc"]
                bc = dynamic_strikes["bc"]
                sp = dynamic_strikes["sp"]
                bp = dynamic_strikes["bp"]
            else:
                sc, bc = atm + IC_CALL_SELL_DISTANCE, atm + IC_CALL_BUY_DISTANCE
                sp, bp = atm - IC_PUT_SELL_DISTANCE, atm - IC_PUT_BUY_DISTANCE
        else:
            sc, bc = atm + IC_CALL_SELL_DISTANCE, atm + IC_CALL_BUY_DISTANCE
            sp, bp = atm - IC_PUT_SELL_DISTANCE, atm - IC_PUT_BUY_DISTANCE
        
        # Apply spot buffer (widen if near day's high/low)
        sc, bc, sp, bp = self._apply_spot_buffer(spot, sc, bc, sp, bp)
        
        # Log what we're trying to do
        expiry_display = expiry.strftime('%d-%b-%Y') if isinstance(expiry, datetime) else expiry
        logger.info(f"🦅 IC Setup: ATM={atm}, Strikes: SC={sc}, BC={bc}, SP={sp}, BP={bp}")
        logger.info(f"🦅 IC Expiry: {expiry_display}, VIX: {vix}")
        
        # === FETCH PREMIUMS ===
        logger.info(f"📊 Fetching premiums (with rate limiting)...")
        
        sc_p = self.api.get_ltp_with_retry(sc, "call", expiry) or 0
        time.sleep(1)
        bc_p = self.api.get_ltp_with_retry(bc, "call", expiry) or 0
        time.sleep(1)
        sp_p = self.api.get_ltp_with_retry(sp, "put", expiry) or 0
        time.sleep(1)
        bp_p = self.api.get_ltp_with_retry(bp, "put", expiry) or 0
        
        logger.info(f"📊 Premiums: SC={sc_p}, BC={bc_p}, SP={sp_p}, BP={bp_p}")
        
        # Check if any premium is 0 (API issue)
        if sc_p == 0 or sp_p == 0:
            logger.warning(f"⚠️ Could not get sell option premiums (SC={sc_p}, SP={sp_p})")
            telegram.send(f"⚠️ IC Entry failed: Could not get option quotes\nTried: {sc}CE/{sp}PE\nExpiry: {expiry_display}")
            return False
        
        # === CREDIT VALIDATION ===
        call_credit = sc_p - bc_p
        put_credit = sp_p - bp_p
        credit = call_credit + put_credit
        
        logger.info(f"📊 Net Credit: {credit:.2f} (Call spread: {call_credit:.2f}, Put spread: {put_credit:.2f})")
        
        # Check minimum credit (use IC_MIN_CREDIT which is smarter than MIN_PREMIUM)
        min_req = max(MIN_PREMIUM, IC_MIN_CREDIT)
        if credit < min_req:
            logger.info(f"🦅 IC skipped: Credit {credit:.0f} < {min_req}")
            return False
        
        # Check risk:reward ratio - max loss should be < 3x credit
        spread_width = bc - sc  # Should be same for both sides
        max_loss_per_side = spread_width - credit
        if max_loss_per_side > credit * 3:
            logger.info(f"🦅 IC skipped: Poor risk:reward ({max_loss_per_side:.0f} loss vs {credit:.0f} credit = {max_loss_per_side/credit:.1f}:1)")
            return False
        
        logger.info(f"🦅 IC Entry: Credit={credit:.0f}, MaxLoss={max_loss_per_side:.0f}, R:R=1:{credit/max_loss_per_side:.1f}, Qty={QUANTITY} ({NUM_LOTS} lots)")
        
        # === PLACE ORDERS ===
        self.api.place_order(sc, "call", expiry, QUANTITY, "sell", sc_p)
        self.api.place_order(bc, "call", expiry, QUANTITY, "buy", bc_p)
        self.api.place_order(sp, "put", expiry, QUANTITY, "sell", sp_p)
        self.api.place_order(bp, "put", expiry, QUANTITY, "buy", bp_p)
        
        # Store position details
        expiry_str = expiry.strftime('%Y-%m-%d') if isinstance(expiry, datetime) else expiry
        self.position = {"sc": sc, "bc": bc, "sp": sp, "bp": bp, "expiry": expiry, "expiry_str": expiry_str}
        self.entry_premium = credit
        self.call_credit = call_credit
        self.put_credit = put_credit
        self.entry_prices = {"sc": sc_p, "bc": bc_p, "sp": sp_p, "bp": bp_p}
        self.entry_time = datetime.now().isoformat()
        self.spot_at_entry = spot
        self.vix_at_entry = vix
        self.peak_pnl_pct = 0
        self.call_spread_closed = False
        self.put_spread_closed = False
        
        # Save to file for dashboard
        self._save_position()
        
        vix_str = f"\nVIX: {vix:.1f}" if vix else ""
        rr_str = f"\nR:R = 1:{credit/max_loss_per_side:.1f}"
        mode_str = f"\nStrike Mode: {IC_STRIKE_MODE.upper()}"
        telegram.send(f"🦅 <b>Iron Condor Entry</b>\nSpot: {spot}\nATM: {atm}\nSell: {sc}CE @ {sc_p:.0f} / {sp}PE @ {sp_p:.0f}\nBuy: {bc}CE @ {bc_p:.0f} / {bp}PE @ {bp_p:.0f}\nCredit: ₹{credit:.0f}{rr_str}\nQty: {QUANTITY} ({NUM_LOTS} lots)\nExpiry: {expiry_display}{vix_str}{mode_str}")
        return True
    
    def _save_position(self):
        """Save position to file for dashboard"""
        pos_data = load_position()
        if self.position:
            pos_data["iron_condor"] = {
                "strategy": "IRON_CONDOR",
                "strikes": {
                    "sell_call": self.position["sc"],
                    "buy_call": self.position["bc"],
                    "sell_put": self.position["sp"],
                    "buy_put": self.position["bp"]
                },
                "entry_prices": self.entry_prices,
                "entry_premium": self.entry_premium,
                "call_credit": self.call_credit,
                "put_credit": self.put_credit,
                "entry_time": self.entry_time,
                "spot_at_entry": self.spot_at_entry,
                "vix_at_entry": self.vix_at_entry,
                "expiry": self.position.get("expiry_str", ""),
                "quantity": QUANTITY,
                "num_lots": NUM_LOTS,
                "peak_pnl_pct": self.peak_pnl_pct,
                "call_spread_closed": self.call_spread_closed,
                "put_spread_closed": self.put_spread_closed
            }
        else:
            pos_data["iron_condor"] = None
        save_position(pos_data)
    
    def get_live_pnl(self):
        """Get current unrealized P&L with per-leg breakdown"""
        if not self.position:
            return None
        
        sc = self.api.get_ltp(self.position["sc"], "call", self.position["expiry"]) or self.entry_prices.get("sc", 0)
        bc = self.api.get_ltp(self.position["bc"], "call", self.position["expiry"]) or self.entry_prices.get("bc", 0)
        sp = self.api.get_ltp(self.position["sp"], "put", self.position["expiry"]) or self.entry_prices.get("sp", 0)
        bp = self.api.get_ltp(self.position["bp"], "put", self.position["expiry"]) or self.entry_prices.get("bp", 0)
        
        # Per-spread P&L
        current_call_spread = sc - bc
        current_put_spread = sp - bp
        call_spread_pnl = (self.call_credit - current_call_spread) if not self.call_spread_closed else 0
        put_spread_pnl = (self.put_credit - current_put_spread) if not self.put_spread_closed else 0
        
        current_premium = 0
        if not self.call_spread_closed:
            current_premium += current_call_spread
        if not self.put_spread_closed:
            current_premium += current_put_spread
        
        # Use remaining entry premium for closed spreads
        remaining_entry = 0
        if not self.call_spread_closed:
            remaining_entry += self.call_credit
        if not self.put_spread_closed:
            remaining_entry += self.put_credit
        
        pnl_points = remaining_entry - current_premium
        pnl_amount = pnl_points * QUANTITY
        pnl_pct = (pnl_points / self.entry_premium * 100) if self.entry_premium > 0 else 0
        
        # Update peak P&L for trailing stop
        if pnl_pct > self.peak_pnl_pct:
            self.peak_pnl_pct = pnl_pct
        
        return {
            "current_prices": {"sc": sc, "bc": bc, "sp": sp, "bp": bp},
            "current_premium": current_premium,
            "entry_premium": self.entry_premium,
            "pnl_points": pnl_points,
            "pnl_amount": pnl_amount,
            "pnl_percent": pnl_pct,
            "target_pct": IC_TARGET_PERCENT,
            "stoploss_pct": IC_STOP_LOSS_PERCENT,
            "call_spread_pnl": call_spread_pnl,
            "put_spread_pnl": put_spread_pnl,
            "call_spread_pnl_pct": (call_spread_pnl / self.call_credit * 100) if self.call_credit > 0 else 0,
            "put_spread_pnl_pct": (put_spread_pnl / self.put_credit * 100) if self.put_credit > 0 else 0,
            "peak_pnl_pct": self.peak_pnl_pct,
            "call_spread_closed": self.call_spread_closed,
            "put_spread_closed": self.put_spread_closed
        }
    
    def _adjust_threatened_spread(self, pnl_data):
        """Close the threatened spread (losing side) and keep the winning side.
        This locks in the loss on one side but lets the other side decay to full profit."""
        
        call_pnl_pct = pnl_data.get("call_spread_pnl_pct", 0)
        put_pnl_pct = pnl_data.get("put_spread_pnl_pct", 0)
        
        # Check if call spread is losing badly (nifty moving up)
        if call_pnl_pct <= -IC_ADJUSTMENT_TRIGGER_PCT and not self.call_spread_closed:
            logger.info(f"🦅 ADJUSTING: Closing call spread (losing {call_pnl_pct:.0f}%)")
            
            # Close call spread: buy back sold call, sell bought call
            self.api.place_order(self.position["sc"], "call", self.position["expiry"], QUANTITY, "buy", 0)
            self.api.place_order(self.position["bc"], "call", self.position["expiry"], QUANTITY, "sell", 0)
            
            self.call_spread_closed = True
            self._save_position()
            
            telegram.send(f"🦅 <b>IC Adjustment</b>\nClosed CALL spread (loss: {call_pnl_pct:.0f}%)\nKeeping PUT spread for theta decay")
            return True
        
        # Check if put spread is losing badly (nifty moving down)
        if put_pnl_pct <= -IC_ADJUSTMENT_TRIGGER_PCT and not self.put_spread_closed:
            logger.info(f"🦅 ADJUSTING: Closing put spread (losing {put_pnl_pct:.0f}%)")
            
            # Close put spread: buy back sold put, sell bought put
            self.api.place_order(self.position["sp"], "put", self.position["expiry"], QUANTITY, "buy", 0)
            self.api.place_order(self.position["bp"], "put", self.position["expiry"], QUANTITY, "sell", 0)
            
            self.put_spread_closed = True
            self._save_position()
            
            telegram.send(f"🦅 <b>IC Adjustment</b>\nClosed PUT spread (loss: {put_pnl_pct:.0f}%)\nKeeping CALL spread for theta decay")
            return True
        
        return False
    
    def check_exit(self):
        if not self.position:
            return None
        
        pnl_data = self.get_live_pnl()
        if not pnl_data:
            return None
        
        pnl_pct = pnl_data["pnl_percent"]
        
        # === TARGET HIT ===
        if pnl_pct >= IC_TARGET_PERCENT:
            return "TARGET"
        
        # === TRAILING STOP LOSS ===
        if IC_TRAILING_SL and self.peak_pnl_pct >= IC_TRAILING_ACTIVATE_PCT:
            trailing_sl_level = self.peak_pnl_pct - IC_TRAILING_OFFSET_PCT
            if pnl_pct <= trailing_sl_level:
                logger.info(f"🦅 Trailing SL hit: Peak={self.peak_pnl_pct:.1f}%, Current={pnl_pct:.1f}%, Trail level={trailing_sl_level:.1f}%")
                return "TRAILING_SL"
        
        # === PER-LEG STOP LOSS (close threatened spread, keep winning side) ===
        if IC_ADJUSTMENT_ENABLED and not (self.call_spread_closed or self.put_spread_closed):
            adjusted = self._adjust_threatened_spread(pnl_data)
            if adjusted:
                return None  # Don't exit fully, just adjusted
        
        # === PER-LEG SL (after adjustment already done, if remaining side also losing) ===
        if IC_LEG_SL_ENABLED:
            call_loss_pct = pnl_data.get("call_spread_pnl_pct", 0)
            put_loss_pct = pnl_data.get("put_spread_pnl_pct", 0)
            
            # If both spreads are losing beyond individual SL
            if not self.call_spread_closed and call_loss_pct <= -IC_LEG_SL_PERCENT:
                return "LEG_STOP_LOSS"
            if not self.put_spread_closed and put_loss_pct <= -IC_LEG_SL_PERCENT:
                return "LEG_STOP_LOSS"
        
        # === OVERALL STOP LOSS ===
        if pnl_pct <= -IC_STOP_LOSS_PERCENT:
            return "STOP_LOSS"
        
        # === TIME EXIT ===
        now = get_ist_now()
        current_time = now.strftime("%H:%M")
        if current_time >= EXIT_TIME:
            return "TIME_EXIT"
        
        return None
    
    def exit(self, reason):
        if not self.position:
            return 0
        
        # Get current prices for P&L calculation
        sc = self.api.get_ltp(self.position["sc"], "call", self.position["expiry"]) or 0
        bc = self.api.get_ltp(self.position["bc"], "call", self.position["expiry"]) or 0
        sp = self.api.get_ltp(self.position["sp"], "put", self.position["expiry"]) or 0
        bp = self.api.get_ltp(self.position["bp"], "put", self.position["expiry"]) or 0
        
        # Only place orders for spreads that are still open
        if not self.call_spread_closed:
            self.api.place_order(self.position["sc"], "call", self.position["expiry"], QUANTITY, "buy", sc)
            self.api.place_order(self.position["bc"], "call", self.position["expiry"], QUANTITY, "sell", bc)
        
        if not self.put_spread_closed:
            self.api.place_order(self.position["sp"], "put", self.position["expiry"], QUANTITY, "buy", sp)
            self.api.place_order(self.position["bp"], "put", self.position["expiry"], QUANTITY, "sell", bp)
        
        exit_prem = 0
        if not self.call_spread_closed:
            exit_prem += (sc - bc)
        if not self.put_spread_closed:
            exit_prem += (sp - bp)
        
        pnl = (self.entry_premium - exit_prem) * QUANTITY - CHARGES_PER_LOT
        
        # Track SL for re-entry prevention
        if reason in ["STOP_LOSS", "LEG_STOP_LOSS", "TRAILING_SL"]:
            self.sl_hit_today = True
            self.sl_hit_date = get_ist_now().strftime("%Y-%m-%d")
        
        add_trade({
            "date": datetime.now().strftime("%Y-%m-%d"),
            "strategy": "IRON_CONDOR",
            "entry_premium": self.entry_premium,
            "exit_premium": exit_prem,
            "pnl": pnl,
            "exit_reason": reason,
            "vix_at_entry": self.vix_at_entry,
            "peak_pnl_pct": self.peak_pnl_pct,
            "call_credit": self.call_credit,
            "put_credit": self.put_credit,
            "call_spread_closed": self.call_spread_closed,
            "put_spread_closed": self.put_spread_closed
        })
        
        exit_emoji = {"TARGET": "🎯", "TRAILING_SL": "📉", "STOP_LOSS": "🛑", "LEG_STOP_LOSS": "🦿", "TIME_EXIT": "⏰"}.get(reason, "🦅")
        adjusted_str = ""
        if self.call_spread_closed:
            adjusted_str = "\n(Call spread was closed earlier)"
        elif self.put_spread_closed:
            adjusted_str = "\n(Put spread was closed earlier)"
        
        telegram.send(f"🦅 <b>IC Exit</b> {exit_emoji}\n{reason}\nP&L: ₹{pnl:+,.0f}\nPeak P&L: {self.peak_pnl_pct:.1f}%{adjusted_str}")
        logger.info(f"🦅 IC Exit: {reason}, P&L: {pnl}, Peak: {self.peak_pnl_pct:.1f}%")
        
        self.position = None
        self.entry_prices = {}
        self.call_spread_closed = False
        self.put_spread_closed = False
        self.peak_pnl_pct = 0
        self._save_position()
        return pnl

# ============================================
# SHORT STRADDLE STRATEGY
# ============================================
class ShortStraddle:
    def __init__(self, api):
        self.api = api
        self.position = None
        self.entry_premium = 0
        self.entry_prices = {}
        self.entry_time = None
        self.spot_at_entry = None
        
    def enter(self, spot, expiry):
        atm = round(spot / 50) * 50
        
        # Log what we're trying to do
        expiry_display = expiry.strftime('%d-%b-%Y') if isinstance(expiry, datetime) else expiry
        logger.info(f"📊 Straddle Setup: ATM={atm}, Expiry={expiry_display}")
        
        # Get LTPs with delays to avoid rate limits
        logger.info(f"📊 Fetching premiums (with rate limiting)...")
        ce = self.api.get_ltp_with_retry(atm, "call", expiry) or 0
        time.sleep(1)  # Delay between calls
        pe = self.api.get_ltp_with_retry(atm, "put", expiry) or 0
        
        logger.info(f"📊 Premiums: CE={ce}, PE={pe}")
        
        # Check if any premium is 0 (API issue)
        if ce == 0 or pe == 0:
            logger.warning(f"⚠️ Could not get straddle premiums (CE={ce}, PE={pe})")
            telegram.send(f"⚠️ Straddle Entry failed: Could not get option quotes\nTried: {atm}CE/{atm}PE\nExpiry: {expiry_display}")
            return False
        
        total = ce + pe
        
        if total < MIN_PREMIUM:
            logger.info(f"📊 Straddle skipped: Premium {total:.0f} < {MIN_PREMIUM}")
            return False
        
        logger.info(f"📊 Straddle Entry: {atm}, Premium={total:.0f}, Qty={QUANTITY} ({NUM_LOTS} lots)")
        
        self.api.place_order(atm, "call", expiry, QUANTITY, "sell", ce)
        self.api.place_order(atm, "put", expiry, QUANTITY, "sell", pe)
        
        # Store position details
        expiry_str = expiry.strftime('%Y-%m-%d') if isinstance(expiry, datetime) else expiry
        self.position = {"strike": atm, "expiry": expiry, "expiry_str": expiry_str}
        self.entry_premium = total
        self.entry_prices = {"ce": ce, "pe": pe}
        self.entry_time = datetime.now().isoformat()
        self.spot_at_entry = spot
        
        # Save to file for dashboard
        self._save_position()
        
        telegram.send(f"📊 <b>Straddle Entry</b>\nSpot: {spot}\nStrike: {atm}\nCE: ₹{ce:.0f} / PE: ₹{pe:.0f}\nTotal Premium: ₹{total:.0f}\nQty: {QUANTITY} ({NUM_LOTS} lots)\nExpiry: {expiry_display}")
        return True
    
    def _save_position(self):
        """Save position to file for dashboard"""
        pos_data = load_position()
        if self.position:
            pos_data["straddle"] = {
                "strategy": "SHORT_STRADDLE",
                "strike": self.position["strike"],
                "entry_prices": self.entry_prices,
                "entry_premium": self.entry_premium,
                "entry_time": self.entry_time,
                "spot_at_entry": self.spot_at_entry,
                "expiry": self.position.get("expiry_str", ""),
                "quantity": QUANTITY,
                "num_lots": NUM_LOTS
            }
        else:
            pos_data["straddle"] = None
        save_position(pos_data)
    
    def get_live_pnl(self):
        """Get current unrealized P&L"""
        if not self.position:
            return None
        
        ce = self.api.get_ltp(self.position["strike"], "call", self.position["expiry"]) or self.entry_prices.get("ce", 0)
        pe = self.api.get_ltp(self.position["strike"], "put", self.position["expiry"]) or self.entry_prices.get("pe", 0)
        
        current_premium = ce + pe
        pnl_points = self.entry_premium - current_premium
        pnl_amount = pnl_points * QUANTITY
        pnl_pct = (pnl_points / self.entry_premium * 100) if self.entry_premium > 0 else 0
        
        return {
            "current_prices": {"ce": ce, "pe": pe},
            "current_premium": current_premium,
            "entry_premium": self.entry_premium,
            "pnl_points": pnl_points,
            "pnl_amount": pnl_amount,
            "pnl_percent": pnl_pct,
            "target_pct": STR_TARGET_PERCENT,
            "stoploss_pct": STR_STOP_LOSS_PERCENT
        }
    
    def check_exit(self):
        if not self.position:
            return None
        
        pnl_data = self.get_live_pnl()
        if not pnl_data:
            return None
        
        pnl_pct = pnl_data["pnl_percent"]
        
        if pnl_pct >= STR_TARGET_PERCENT:
            return "TARGET"
        if pnl_pct <= -STR_STOP_LOSS_PERCENT:
            return "STOP_LOSS"
        
        now = get_ist_now()
        current_time = now.strftime("%H:%M")
        if current_time >= EXIT_TIME:
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
        self.entry_prices = {}
        self._save_position()  # Clear position from file
        return pnl

# ============================================
# BOT RUNNER (Background Thread)
# ============================================
def is_trading_time():
    """Check if current time is within entry window (IST)"""
    now = get_ist_now()
    if now.weekday() not in TRADING_DAYS:
        return False
    
    current_time = now.strftime("%H:%M")
    
    # Compare as strings (HH:MM format)
    in_window = ENTRY_TIME_START <= current_time <= ENTRY_TIME_END
    
    logger.debug(f"Trading time check: {current_time} IST, Window: {ENTRY_TIME_START}-{ENTRY_TIME_END}, In window: {in_window}")
    return in_window

def is_exit_time():
    """Check if current time is past exit time (IST)"""
    now = get_ist_now()
    current_time = now.strftime("%H:%M")
    
    is_exit = current_time >= EXIT_TIME
    logger.debug(f"Exit time check: {current_time} IST >= {EXIT_TIME}, Should exit: {is_exit}")
    return is_exit

def is_market_hours():
    """Check if market is open (9:15 AM - 3:30 PM IST)"""
    now = get_ist_now()
    if now.weekday() not in TRADING_DAYS:
        return False
    current_time = now.strftime("%H:%M")
    return "09:15" <= current_time <= "15:30"

def bot_thread():
    global _live_ic, _live_straddle
    
    logger.info("🤖 Bot thread starting...")
    logger.info(f"⏰ Entry Time: {ENTRY_TIME_START} - {ENTRY_TIME_END} IST")
    logger.info(f"⏰ Exit Time: {EXIT_TIME} IST")
    logger.info(f"📊 Strategy: {STRATEGY}")
    logger.info(f"💰 Lot Size: {LOT_SIZE}, Num Lots: {NUM_LOTS}, Total Qty: {QUANTITY}")
    logger.info(f"💵 Min Premium: {MIN_PREMIUM}")
    logger.info(f"🚀 Auto-start: {AUTO_START}")
    
    # Log IC improvement settings
    logger.info(f"🦅 IC Improvements v2.0:")
    logger.info(f"   VIX Filter: {IC_VIX_MIN}-{IC_VIX_MAX} | Strike Mode: {IC_STRIKE_MODE}")
    logger.info(f"   Min Credit: {IC_MIN_CREDIT} | Trailing SL: {IC_TRAILING_SL} ({IC_TRAILING_ACTIVATE_PCT}%/{IC_TRAILING_OFFSET_PCT}%)")
    logger.info(f"   Adjustment: {IC_ADJUSTMENT_ENABLED} (trigger: {IC_ADJUSTMENT_TRIGGER_PCT}%) | Leg SL: {IC_LEG_SL_ENABLED} ({IC_LEG_SL_PERCENT}%)")
    logger.info(f"   Expiry Day Avoid: {IC_AVOID_EXPIRY_DAY} | Spot Buffer: {IC_SPOT_BUFFER}")
    logger.info(f"   Re-entry after SL: {IC_REENTRY_AFTER_SL} | Daily Loss Limit: {'₹'+str(IC_DAILY_LOSS_LIMIT) if IC_DAILY_LOSS_LIMIT > 0 else 'OFF'}")
    
    # Log expiry info
    if CUSTOM_EXPIRY:
        logger.info(f"📅 CUSTOM_EXPIRY set: {CUSTOM_EXPIRY}")
    next_exp = get_next_expiry()
    logger.info(f"📅 Next Expiry: {next_exp.strftime('%d-%b-%Y')} ({next_exp.strftime('%A')})")
    
    # Auto-start if enabled
    if AUTO_START:
        data = load_data()
        if not data.get("bot_running"):
            data["bot_running"] = True
            save_data(data)
            logger.info("✅ Bot auto-started")
            telegram.send("🤖 Bot auto-started on deployment")
    
    api = BreezeAPI()
    ic = IronCondor(api)
    straddle = ShortStraddle(api)
    
    # Set global references for live P&L API
    _live_ic = ic
    _live_straddle = straddle
    
    # === POSITION RECOVERY ON RESTART ===
    # If there was an active position stored from before a restart, recover it
    try:
        pos_data = load_position()
        if pos_data.get("iron_condor") and pos_data["iron_condor"]:
            stored_ic = pos_data["iron_condor"]
            strikes = stored_ic.get("strikes", {})
            if strikes.get("sell_call"):
                # Restore IC position state
                expiry_str = stored_ic.get("expiry", "")
                try:
                    expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d") if expiry_str else get_next_expiry()
                except:
                    expiry_dt = get_next_expiry()
                
                ic.position = {
                    "sc": strikes["sell_call"], "bc": strikes["buy_call"],
                    "sp": strikes["sell_put"], "bp": strikes["buy_put"],
                    "expiry": expiry_dt, "expiry_str": expiry_str
                }
                ic.entry_premium = stored_ic.get("entry_premium", 0)
                ic.call_credit = stored_ic.get("call_credit", ic.entry_premium / 2)
                ic.put_credit = stored_ic.get("put_credit", ic.entry_premium / 2)
                ic.entry_prices = stored_ic.get("entry_prices", {})
                ic.entry_time = stored_ic.get("entry_time", "")
                ic.spot_at_entry = stored_ic.get("spot_at_entry", 0)
                ic.vix_at_entry = stored_ic.get("vix_at_entry")
                ic.peak_pnl_pct = stored_ic.get("peak_pnl_pct", 0)
                ic.call_spread_closed = stored_ic.get("call_spread_closed", False)
                ic.put_spread_closed = stored_ic.get("put_spread_closed", False)
                
                logger.info(f"🔄 Recovered IC position: SC={strikes['sell_call']}, SP={strikes['sell_put']}, Credit={ic.entry_premium}")
                telegram.send(f"🔄 Recovered IC position after restart\nSC={strikes['sell_call']}CE / SP={strikes['sell_put']}PE\nCredit: ₹{ic.entry_premium:.0f}")
        
        if pos_data.get("straddle") and pos_data["straddle"]:
            stored_str = pos_data["straddle"]
            if stored_str.get("strike"):
                expiry_str = stored_str.get("expiry", "")
                try:
                    expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d") if expiry_str else get_next_expiry()
                except:
                    expiry_dt = get_next_expiry()
                
                straddle.position = {
                    "strike": stored_str["strike"],
                    "expiry": expiry_dt, "expiry_str": expiry_str
                }
                straddle.entry_premium = stored_str.get("entry_premium", 0)
                straddle.entry_prices = stored_str.get("entry_prices", {})
                straddle.entry_time = stored_str.get("entry_time", "")
                straddle.spot_at_entry = stored_str.get("spot_at_entry", 0)
                
                logger.info(f"🔄 Recovered Straddle position: Strike={stored_str['strike']}, Premium={straddle.entry_premium}")
    except Exception as e:
        logger.error(f"Position recovery error: {e}")
    
    last_connect = datetime.now() - timedelta(hours=1)
    last_status_log = datetime.now() - timedelta(minutes=5)
    last_trade_date = None
    
    while True:
        try:
            now = get_ist_now()
            current_date = now.strftime("%Y-%m-%d")
            current_time = now.strftime("%H:%M:%S")
            
            # Reset daily flags at midnight
            if last_trade_date != current_date:
                last_trade_date = current_date
                # Reset daily P&L
                data = load_data()
                data["daily_pnl"] = 0
                save_data(data)
                logger.info(f"📅 New trading day: {current_date}")
            
            # Check Telegram commands
            telegram.check_commands()
            
            # Load current state
            data = load_data()
            strategy = data.get("strategy", STRATEGY)
            bot_running = data.get("bot_running", False)
            
            # Log status every 5 minutes
            if (datetime.now() - last_status_log).seconds >= 300:
                market_status = "OPEN" if is_market_hours() else "CLOSED"
                trading_window = "YES" if is_trading_time() else "NO"
                logger.info(f"📊 Status: Bot={'ON' if bot_running else 'OFF'}, Market={market_status}, "
                           f"Entry Window={trading_window}, Time={current_time} IST, "
                           f"IC Position={bool(ic.position)}, Straddle Position={bool(straddle.position)}")
                last_status_log = datetime.now()
            
            if not bot_running:
                time.sleep(10)
                continue
            
            # Connect to API if needed (only during market hours)
            if is_market_hours():
                if not api.connected and (datetime.now() - last_connect).seconds > 60:
                    logger.info("🔌 Attempting API connection...")
                    if api.connect():
                        spot = api.get_spot()
                        if spot:
                            logger.info(f"📈 Nifty Spot: {spot}")
                            telegram.send(f"📈 Connected! Nifty Spot: {spot}")
                    last_connect = datetime.now()
                
                if not api.connected:
                    logger.warning("❌ API not connected, waiting...")
                    time.sleep(30)
                    continue
            else:
                time.sleep(60)
                continue
            
            # Force exit time
            if is_exit_time():
                if ic.position:
                    logger.info("⏰ Exit time reached - closing Iron Condor")
                    ic.exit("TIME_EXIT")
                if straddle.position:
                    logger.info("⏰ Exit time reached - closing Straddle")
                    straddle.exit("TIME_EXIT")
                time.sleep(60)
                continue
            
            # Check exits for existing positions
            if strategy in ["iron_condor", "both"] and ic.position:
                reason = ic.check_exit()
                if reason:
                    logger.info(f"🦅 IC exit triggered: {reason}")
                    ic.exit(reason)
            
            if strategy in ["straddle", "both"] and straddle.position:
                reason = straddle.check_exit()
                if reason:
                    logger.info(f"📊 Straddle exit triggered: {reason}")
                    straddle.exit(reason)
            
            # Enter new positions (during entry window)
            if is_trading_time():
                spot = api.get_spot()
                expiry = api.get_expiry()
                
                if spot:
                    logger.info(f"🎯 Entry window active. Spot: {spot}, Expiry: {expiry}")
                    
                    # Check daily loss limit before entering any new trades
                    daily_loss_exceeded = False
                    if IC_DAILY_LOSS_LIMIT > 0:
                        data = load_data()
                        daily_pnl = data.get("daily_pnl", 0)
                        if daily_pnl < -IC_DAILY_LOSS_LIMIT:
                            daily_loss_exceeded = True
                            logger.info(f"🛑 Daily loss limit hit: ₹{daily_pnl:,.0f} < -₹{IC_DAILY_LOSS_LIMIT:,.0f}")
                    
                    # Enter Iron Condor if no position
                    if strategy in ["iron_condor", "both"] and not ic.position and not daily_loss_exceeded:
                        logger.info("🦅 Attempting Iron Condor entry...")
                        if ic.enter(spot, expiry):
                            logger.info("✅ Iron Condor position opened")
                        else:
                            logger.info("⚠️ Iron Condor entry skipped (low premium or API issue)")
                    
                    # Enter Straddle if no position
                    if strategy in ["straddle", "both"] and not straddle.position and not daily_loss_exceeded:
                        logger.info("📊 Attempting Straddle entry...")
                        if straddle.enter(spot, expiry):
                            logger.info("✅ Straddle position opened")
                        else:
                            logger.info("⚠️ Straddle entry skipped (low premium or API issue)")
                else:
                    logger.warning("⚠️ Could not get spot price")
            
            time.sleep(CHECK_INTERVAL)
            
        except Exception as e:
            logger.error(f"❌ Bot error: {e}")
            import traceback
            logger.error(traceback.format_exc())
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
        
        /* Live Position Styles */
        .position-card {
            background: rgba(255,255,255,0.05);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 15px;
            border: 1px solid rgba(255,255,255,0.1);
        }
        .position-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }
        .position-strategy {
            font-size: 1.1rem;
            font-weight: 600;
            color: #00d2ff;
        }
        .position-pnl {
            font-size: 1.4rem;
            font-weight: 700;
        }
        .position-details {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
            gap: 10px;
            margin-bottom: 15px;
        }
        .position-row {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: #aaa;
        }
        .position-row span:last-child {
            color: #fff;
            font-weight: 500;
        }
        .position-table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 15px;
            font-size: 0.9rem;
        }
        .position-table th {
            background: rgba(255,255,255,0.05);
            padding: 10px;
            text-align: left;
            color: #888;
            font-weight: 500;
        }
        .position-table td {
            padding: 10px;
            border-bottom: 1px solid rgba(255,255,255,0.05);
        }
        .position-summary {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 15px;
            padding: 15px;
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            margin-bottom: 15px;
        }
        .summary-item {
            text-align: center;
        }
        .summary-item span:first-child {
            display: block;
            font-size: 0.75rem;
            color: #888;
            margin-bottom: 5px;
        }
        .summary-item span:last-child {
            font-size: 1.1rem;
            font-weight: 600;
        }
        .pnl-value.positive { color: #00c853; }
        .pnl-value.negative { color: #ff5252; }
        
        .position-progress {
            margin-top: 15px;
        }
        .progress-bar {
            position: relative;
            height: 24px;
            background: linear-gradient(90deg, #ff5252 0%, #ff5252 33%, #333 33%, #333 67%, #00c853 67%, #00c853 100%);
            border-radius: 12px;
            overflow: hidden;
        }
        .progress-fill {
            position: absolute;
            left: 50%;
            top: 50%;
            transform: translate(-50%, -50%);
            width: 4px;
            height: 100%;
            background: #fff;
            border-radius: 2px;
            transition: left 0.3s ease;
        }
        .progress-markers {
            position: absolute;
            width: 100%;
            height: 100%;
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 10px;
            font-size: 0.7rem;
            color: rgba(255,255,255,0.7);
        }
        .progress-labels {
            display: flex;
            justify-content: space-between;
            margin-top: 5px;
            font-size: 0.75rem;
            color: #888;
        }
        .no-position {
            text-align: center;
            padding: 40px;
            color: #666;
        }
        .no-position p:first-child {
            font-size: 1.2rem;
            margin-bottom: 10px;
        }
        
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
        
        /* Backtest trades table */
        #bt-trades-body tr:hover { background: rgba(255,255,255,0.05); }
        #bt-trades-body td { font-size: 0.85rem; }
        .exit-target { color: #00c853 !important; font-weight: 600; }
        .exit-sl { color: #ff5252 !important; font-weight: 600; }
        .exit-time { color: #ff9800 !important; }
        
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
            <div class="badges" style="margin-top: 10px;">
                <span class="badge" id="time-badge" style="background: #333;">🕐 --:--:-- IST</span>
                <span class="badge" id="market-badge" style="background: #666;">📊 MARKET CLOSED</span>
                <span class="badge" id="window-badge" style="background: #666;">⏳ WAITING</span>
                <span class="badge" id="expiry-badge" style="background: #9c27b0;">📅 Expiry: --</span>
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
            
            <!-- LIVE POSITION SECTION -->
            <div class="section" id="position-section" style="display: none;">
                <div class="section-title">📍 Live Position</div>
                <div id="position-container">
                    <!-- Iron Condor Position -->
                    <div id="ic-position" class="position-card" style="display: none;">
                        <div class="position-header">
                            <span class="position-strategy">🦅 IRON CONDOR <span id="ic-version-badge" style="font-size:0.65rem;background:#333;padding:2px 6px;border-radius:8px;margin-left:5px;">v2.0</span></span>
                            <span class="position-pnl" id="ic-pnl">₹0</span>
                        </div>
                        <div class="position-details">
                            <div class="position-row">
                                <span>Entry Time:</span>
                                <span id="ic-entry-time">--</span>
                            </div>
                            <div class="position-row">
                                <span>Spot at Entry:</span>
                                <span id="ic-spot-entry">--</span>
                            </div>
                            <div class="position-row">
                                <span>Expiry:</span>
                                <span id="ic-expiry">--</span>
                            </div>
                            <div class="position-row">
                                <span>Quantity:</span>
                                <span id="ic-qty">--</span>
                            </div>
                            <div class="position-row">
                                <span>VIX at Entry:</span>
                                <span id="ic-vix-entry">--</span>
                            </div>
                            <div class="position-row">
                                <span>Strike Mode:</span>
                                <span id="ic-strike-mode">--</span>
                            </div>
                        </div>
                        <table class="position-table">
                            <thead>
                                <tr><th>Leg</th><th>Strike</th><th>Entry</th><th>Current</th><th>P&L</th></tr>
                            </thead>
                            <tbody id="ic-legs">
                            </tbody>
                        </table>
                        <!-- Per-Spread P&L -->
                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:15px;">
                            <div style="background:rgba(0,0,0,0.2);border-radius:8px;padding:10px;text-align:center;">
                                <div style="font-size:0.7rem;color:#888;margin-bottom:4px;">📞 CALL SPREAD</div>
                                <div id="ic-call-spread-pnl" style="font-size:1rem;font-weight:600;">--</div>
                                <div id="ic-call-spread-status" style="font-size:0.65rem;color:#888;margin-top:2px;"></div>
                            </div>
                            <div style="background:rgba(0,0,0,0.2);border-radius:8px;padding:10px;text-align:center;">
                                <div style="font-size:0.7rem;color:#888;margin-bottom:4px;">📱 PUT SPREAD</div>
                                <div id="ic-put-spread-pnl" style="font-size:1rem;font-weight:600;">--</div>
                                <div id="ic-put-spread-status" style="font-size:0.65rem;color:#888;margin-top:2px;"></div>
                            </div>
                        </div>
                        <div class="position-summary">
                            <div class="summary-item">
                                <span>Entry Credit:</span>
                                <span id="ic-entry-credit">₹0</span>
                            </div>
                            <div class="summary-item">
                                <span>Current Premium:</span>
                                <span id="ic-current-premium">₹0</span>
                            </div>
                            <div class="summary-item">
                                <span>Unrealized P&L:</span>
                                <span id="ic-unrealized-pnl" class="pnl-value">₹0</span>
                            </div>
                            <div class="summary-item">
                                <span>P&L %:</span>
                                <span id="ic-pnl-pct">0%</span>
                            </div>
                            <div class="summary-item">
                                <span>Peak P&L %:</span>
                                <span id="ic-peak-pnl" style="color:#00d2ff;">--</span>
                            </div>
                            <div class="summary-item">
                                <span>Trail SL Level:</span>
                                <span id="ic-trailing-sl-level" style="color:#ffa726;">--</span>
                            </div>
                        </div>
                        <div class="position-progress">
                            <div class="progress-bar">
                                <div class="progress-fill" id="ic-progress"></div>
                                <div class="progress-markers">
                                    <span class="marker marker-sl">SL</span>
                                    <span class="marker marker-entry">Entry</span>
                                    <span class="marker marker-target">Target</span>
                                </div>
                            </div>
                            <div class="progress-labels">
                                <span id="ic-sl-label">-100%</span>
                                <span id="ic-target-label">+50%</span>
                            </div>
                        </div>
                        <!-- Adjustment Alert -->
                        <div id="ic-adjustment-alert" style="display:none;margin-top:10px;padding:10px;border-radius:8px;background:rgba(255,167,38,0.15);border:1px solid rgba(255,167,38,0.3);font-size:0.85rem;color:#ffa726;">
                            ⚙️ <span id="ic-adjustment-text"></span>
                        </div>
                    </div>
                    
                    <!-- Straddle Position -->
                    <div id="str-position" class="position-card" style="display: none;">
                        <div class="position-header">
                            <span class="position-strategy">📊 SHORT STRADDLE</span>
                            <span class="position-pnl" id="str-pnl">₹0</span>
                        </div>
                        <div class="position-details">
                            <div class="position-row">
                                <span>Entry Time:</span>
                                <span id="str-entry-time">--</span>
                            </div>
                            <div class="position-row">
                                <span>Strike:</span>
                                <span id="str-strike">--</span>
                            </div>
                            <div class="position-row">
                                <span>Spot at Entry:</span>
                                <span id="str-spot-entry">--</span>
                            </div>
                            <div class="position-row">
                                <span>Expiry:</span>
                                <span id="str-expiry">--</span>
                            </div>
                            <div class="position-row">
                                <span>Quantity:</span>
                                <span id="str-qty">--</span>
                            </div>
                        </div>
                        <table class="position-table">
                            <thead>
                                <tr><th>Leg</th><th>Entry</th><th>Current</th><th>P&L</th></tr>
                            </thead>
                            <tbody id="str-legs">
                            </tbody>
                        </table>
                        <div class="position-summary">
                            <div class="summary-item">
                                <span>Entry Premium:</span>
                                <span id="str-entry-premium">₹0</span>
                            </div>
                            <div class="summary-item">
                                <span>Current Premium:</span>
                                <span id="str-current-premium">₹0</span>
                            </div>
                            <div class="summary-item">
                                <span>Unrealized P&L:</span>
                                <span id="str-unrealized-pnl" class="pnl-value">₹0</span>
                            </div>
                            <div class="summary-item">
                                <span>P&L %:</span>
                                <span id="str-pnl-pct">0%</span>
                            </div>
                        </div>
                        <div class="position-progress">
                            <div class="progress-bar">
                                <div class="progress-fill" id="str-progress"></div>
                                <div class="progress-markers">
                                    <span class="marker marker-sl">SL</span>
                                    <span class="marker marker-entry">Entry</span>
                                    <span class="marker marker-target">Target</span>
                                </div>
                            </div>
                            <div class="progress-labels">
                                <span id="str-sl-label">-20%</span>
                                <span id="str-target-label">+30%</span>
                            </div>
                        </div>
                    </div>
                    
                    <!-- No Position -->
                    <div id="no-position" class="no-position">
                        <p>📭 No active positions</p>
                        <p class="info-text">Positions will appear here when the bot takes a trade</p>
                    </div>
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
                <p class="info-text" style="margin-bottom: 15px;">Uses same entry/exit times as live trading bot</p>
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
                    <div>
                        <label class="info-text">Entry Time Start</label>
                        <input type="time" id="bt-entry-start" value="09:20">
                    </div>
                    <div>
                        <label class="info-text">Entry Time End</label>
                        <input type="time" id="bt-entry-end" value="14:00">
                    </div>
                    <div>
                        <label class="info-text">Exit Time</label>
                        <input type="time" id="bt-exit-time" value="15:15">
                    </div>
                    <div style="display: flex; align-items: center; gap: 10px;">
                        <input type="checkbox" id="bt-use-api" style="width: 20px; height: 20px;">
                        <label class="info-text" for="bt-use-api">Use Breeze API Historical Data</label>
                    </div>
                </div>
                <div style="margin-bottom: 15px;">
                    <button class="btn btn-warning" onclick="runBacktest()" id="bt-run-btn">🚀 Run Backtest</button>
                    <span id="bt-loading" style="display:none; margin-left: 15px;">⏳ Running backtest...</span>
                </div>
                <p class="info-text" id="bt-data-note">💡 Premiums are estimated using Black-Scholes approximation. Enable "Use Breeze API" for real historical data (slower, requires API connection).</p>
                
                <div class="backtest-results" id="bt-results">
                    <h3 style="margin-bottom: 15px;">📊 Backtest Results</h3>
                    
                    <!-- Data Source & Timing Info -->
                    <div style="background: rgba(0,0,0,0.2); padding: 12px; border-radius: 8px; margin-bottom: 15px;">
                        <div style="margin-bottom: 8px;">
                            <span class="info-text">📊 Data Source: <strong id="bt-data-source">Estimated</strong></span>
                            <span class="info-text" style="margin-left: 20px;">💰 Avg Premium: <strong id="bt-avg-premium">₹0</strong></span>
                        </div>
                        <div>
                            <span class="info-text">⏰ Entry: <strong id="bt-timing-entry">09:20 - 14:00</strong></span>
                            <span class="info-text" style="margin-left: 20px;">🚪 Exit: <strong id="bt-timing-exit">15:15</strong></span>
                            <span class="info-text" style="margin-left: 20px;">📦 Qty: <strong id="bt-timing-qty">75</strong></span>
                        </div>
                    </div>
                    
                    <!-- Summary Grid -->
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
                            <div class="result-label">Expiries</div>
                        </div>
                        <div class="result-item">
                            <div class="result-value" id="bt-avg-exit">--:--</div>
                            <div class="result-label">Avg Exit Time</div>
                        </div>
                    </div>
                    
                    <!-- Exit Breakdown -->
                    <div style="margin-top: 20px;">
                        <h4 style="margin-bottom: 10px; color: #00d2ff;">📈 Exit Breakdown</h4>
                        <div class="result-grid" style="grid-template-columns: repeat(3, 1fr);">
                            <div class="result-item">
                                <div class="result-value positive" id="bt-target-exits">0</div>
                                <div class="result-label">🎯 Target Hits</div>
                            </div>
                            <div class="result-item">
                                <div class="result-value negative" id="bt-sl-exits">0</div>
                                <div class="result-label">🛑 Stop Loss</div>
                            </div>
                            <div class="result-item">
                                <div class="result-value" id="bt-time-exits">0</div>
                                <div class="result-label">⏰ Time Exits</div>
                            </div>
                        </div>
                    </div>
                    
                    <!-- Trades Table -->
                    <div style="margin-top: 20px;">
                        <h4 style="margin-bottom: 10px; color: #00d2ff;">📋 Trade Details <span class="info-text" id="bt-trade-count">(0 trades)</span></h4>
                        <div style="max-height: 400px; overflow-y: auto;">
                            <table>
                                <thead>
                                    <tr>
                                        <th>Date</th>
                                        <th>Strategy</th>
                                        <th>Entry Time</th>
                                        <th>Exit Time</th>
                                        <th>Premium</th>
                                        <th>P&L</th>
                                        <th>Exit Reason</th>
                                    </tr>
                                </thead>
                                <tbody id="bt-trades-body">
                                    <tr><td colspan="7" style="text-align:center;color:#666;">Run backtest to see trades</td></tr>
                                </tbody>
                            </table>
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
            <p id="footer-info">Lot Size: 75 | Market: 9:15 AM - 3:30 PM IST</p>
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
                
                // Fetch status for timing info
                const statusRes = await fetch('/api/status');
                const status = await statusRes.json();
                
                // Update time badge
                const timeBadge = document.getElementById('time-badge');
                timeBadge.textContent = '🕐 ' + status.current_time_ist.split(' ')[1] + ' IST';
                
                // Update market badge
                const marketBadge = document.getElementById('market-badge');
                if (status.is_market_hours) {
                    marketBadge.textContent = '📊 MARKET OPEN';
                    marketBadge.style.background = '#00c853';
                } else {
                    marketBadge.textContent = '📊 MARKET CLOSED';
                    marketBadge.style.background = '#666';
                }
                
                // Update window badge
                const windowBadge = document.getElementById('window-badge');
                if (status.is_exit_time) {
                    windowBadge.textContent = '🔴 EXIT TIME';
                    windowBadge.style.background = '#ff5252';
                } else if (status.is_trading_time) {
                    windowBadge.textContent = '🟢 ENTRY WINDOW (' + status.entry_time_start + '-' + status.entry_time_end + ')';
                    windowBadge.style.background = '#00c853';
                } else {
                    windowBadge.textContent = '⏳ WAITING (Entry: ' + status.entry_time_start + ')';
                    windowBadge.style.background = '#ff9800';
                }
                
                // Update expiry badge
                const expiryBadge = document.getElementById('expiry-badge');
                expiryBadge.textContent = '📅 Expiry: ' + status.next_expiry + ' (' + status.next_expiry_day.slice(0,3) + ')';
                if (status.custom_expiry) {
                    expiryBadge.style.background = '#e91e63';  // Pink for custom expiry
                } else {
                    expiryBadge.style.background = '#9c27b0';  // Purple for normal
                }
                
                // Update footer
                document.getElementById('footer-info').textContent = 
                    'Lot Size: ' + status.lot_size + ' × ' + status.num_lots + ' = ' + status.quantity + 
                    ' | Min Premium: ₹' + status.min_premium + 
                    ' | Market: 9:15 AM - 3:30 PM IST';
                
                // Fetch and update live positions
                const posRes = await fetch('/api/position');
                const posData = await posRes.json();
                updatePositions(posData);
                
                const tradesRes = await fetch('/api/trades');
                const trades = await tradesRes.json();
                updateTable(trades);
                updateChart(trades);
            } catch (e) { console.error(e); }
        }
        
        function updatePositions(posData) {
            const section = document.getElementById('position-section');
            const icPos = document.getElementById('ic-position');
            const strPos = document.getElementById('str-position');
            const noPos = document.getElementById('no-position');
            
            // Always show position section
            section.style.display = 'block';
            
            if (!posData.has_position) {
                icPos.style.display = 'none';
                strPos.style.display = 'none';
                noPos.style.display = 'block';
                return;
            }
            
            noPos.style.display = 'none';
            
            // Iron Condor Position
            if (posData.iron_condor) {
                icPos.style.display = 'block';
                const ic = posData.iron_condor;
                
                // Entry details
                document.getElementById('ic-entry-time').textContent = ic.entry_time ? new Date(ic.entry_time).toLocaleTimeString('en-IN') : '--';
                document.getElementById('ic-spot-entry').textContent = ic.spot_at_entry ? ic.spot_at_entry.toFixed(2) : '--';
                document.getElementById('ic-expiry').textContent = ic.expiry || '--';
                document.getElementById('ic-qty').textContent = ic.quantity + ' (' + ic.num_lots + ' lots)';
                document.getElementById('ic-vix-entry').textContent = ic.vix_at_entry ? ic.vix_at_entry.toFixed(1) : 'N/A';
                document.getElementById('ic-strike-mode').textContent = (ic.strike_mode || 'fixed').toUpperCase();
                
                // Calculate P&L from entry prices (static display)
                const entryCredit = ic.entry_premium || 0;
                document.getElementById('ic-entry-credit').textContent = '₹' + entryCredit.toFixed(2);
                
                // Show adjustment status
                const adjAlert = document.getElementById('ic-adjustment-alert');
                if (ic.call_spread_closed) {
                    adjAlert.style.display = 'block';
                    document.getElementById('ic-adjustment-text').textContent = 'Call spread closed (adjustment). Put spread still active.';
                } else if (ic.put_spread_closed) {
                    adjAlert.style.display = 'block';
                    document.getElementById('ic-adjustment-text').textContent = 'Put spread closed (adjustment). Call spread still active.';
                } else {
                    adjAlert.style.display = 'none';
                }
                
                // Legs table
                const strikes = ic.strikes || {};
                const entryPrices = ic.entry_prices || {};
                document.getElementById('ic-legs').innerHTML = `
                    <tr>
                        <td style="color:#ff5252;">SELL CALL</td>
                        <td>${strikes.sell_call || '--'}</td>
                        <td>₹${(entryPrices.sc || 0).toFixed(2)}</td>
                        <td id="ic-sc-ltp">--</td>
                        <td id="ic-sc-pnl">--</td>
                    </tr>
                    <tr>
                        <td style="color:#00c853;">BUY CALL</td>
                        <td>${strikes.buy_call || '--'}</td>
                        <td>₹${(entryPrices.bc || 0).toFixed(2)}</td>
                        <td id="ic-bc-ltp">--</td>
                        <td id="ic-bc-pnl">--</td>
                    </tr>
                    <tr>
                        <td style="color:#ff5252;">SELL PUT</td>
                        <td>${strikes.sell_put || '--'}</td>
                        <td>₹${(entryPrices.sp || 0).toFixed(2)}</td>
                        <td id="ic-sp-ltp">--</td>
                        <td id="ic-sp-pnl">--</td>
                    </tr>
                    <tr>
                        <td style="color:#00c853;">BUY PUT</td>
                        <td>${strikes.buy_put || '--'}</td>
                        <td>₹${(entryPrices.bp || 0).toFixed(2)}</td>
                        <td id="ic-bp-ltp">--</td>
                        <td id="ic-bp-pnl">--</td>
                    </tr>
                `;
                
                // Fetch live P&L
                fetchLivePnl('iron_condor');
            } else {
                icPos.style.display = 'none';
            }
            
            // Straddle Position
            if (posData.straddle) {
                strPos.style.display = 'block';
                const str = posData.straddle;
                
                // Entry details
                document.getElementById('str-entry-time').textContent = str.entry_time ? new Date(str.entry_time).toLocaleTimeString('en-IN') : '--';
                document.getElementById('str-strike').textContent = str.strike || '--';
                document.getElementById('str-spot-entry').textContent = str.spot_at_entry ? str.spot_at_entry.toFixed(2) : '--';
                document.getElementById('str-expiry').textContent = str.expiry || '--';
                document.getElementById('str-qty').textContent = str.quantity + ' (' + str.num_lots + ' lots)';
                
                // Entry premium
                const entryPremium = str.entry_premium || 0;
                document.getElementById('str-entry-premium').textContent = '₹' + entryPremium.toFixed(2);
                
                // Legs table
                const entryPrices = str.entry_prices || {};
                document.getElementById('str-legs').innerHTML = `
                    <tr>
                        <td style="color:#ff5252;">SELL ${str.strike} CE</td>
                        <td>₹${(entryPrices.ce || 0).toFixed(2)}</td>
                        <td id="str-ce-ltp">--</td>
                        <td id="str-ce-pnl">--</td>
                    </tr>
                    <tr>
                        <td style="color:#ff5252;">SELL ${str.strike} PE</td>
                        <td>₹${(entryPrices.pe || 0).toFixed(2)}</td>
                        <td id="str-pe-ltp">--</td>
                        <td id="str-pe-pnl">--</td>
                    </tr>
                `;
                
                // Fetch live P&L
                fetchLivePnl('straddle');
            } else {
                strPos.style.display = 'none';
            }
        }
        
        async function fetchLivePnl(strategy) {
            try {
                const res = await fetch('/api/live_pnl?strategy=' + strategy);
                const data = await res.json();
                
                if (strategy === 'iron_condor' && data.iron_condor) {
                    const ic = data.iron_condor;
                    const pnl = ic.pnl_amount || 0;
                    const pnlPct = ic.pnl_percent || 0;
                    
                    // Update header P&L
                    const pnlEl = document.getElementById('ic-pnl');
                    pnlEl.textContent = '₹' + pnl.toLocaleString('en-IN', {maximumFractionDigits: 0});
                    pnlEl.className = 'position-pnl ' + (pnl >= 0 ? 'positive' : 'negative');
                    
                    // Update current premium
                    document.getElementById('ic-current-premium').textContent = '₹' + (ic.current_premium || 0).toFixed(2);
                    
                    // Update unrealized P&L
                    const unrealizedEl = document.getElementById('ic-unrealized-pnl');
                    unrealizedEl.textContent = '₹' + pnl.toLocaleString('en-IN', {maximumFractionDigits: 0});
                    unrealizedEl.className = 'pnl-value ' + (pnl >= 0 ? 'positive' : 'negative');
                    
                    // Update P&L %
                    document.getElementById('ic-pnl-pct').textContent = (pnl >= 0 ? '+' : '') + pnlPct.toFixed(1) + '%';
                    
                    // Update per-spread P&L
                    const callPnlPct = ic.call_spread_pnl_pct || 0;
                    const putPnlPct = ic.put_spread_pnl_pct || 0;
                    const callSpreadEl = document.getElementById('ic-call-spread-pnl');
                    const putSpreadEl = document.getElementById('ic-put-spread-pnl');
                    
                    if (ic.call_spread_closed) {
                        callSpreadEl.textContent = 'CLOSED';
                        callSpreadEl.style.color = '#888';
                        document.getElementById('ic-call-spread-status').textContent = '(adjusted)';
                    } else {
                        callSpreadEl.textContent = (callPnlPct >= 0 ? '+' : '') + callPnlPct.toFixed(1) + '%';
                        callSpreadEl.style.color = callPnlPct >= 0 ? '#00c853' : '#ff5252';
                        document.getElementById('ic-call-spread-status').textContent = '';
                    }
                    
                    if (ic.put_spread_closed) {
                        putSpreadEl.textContent = 'CLOSED';
                        putSpreadEl.style.color = '#888';
                        document.getElementById('ic-put-spread-status').textContent = '(adjusted)';
                    } else {
                        putSpreadEl.textContent = (putPnlPct >= 0 ? '+' : '') + putPnlPct.toFixed(1) + '%';
                        putSpreadEl.style.color = putPnlPct >= 0 ? '#00c853' : '#ff5252';
                        document.getElementById('ic-put-spread-status').textContent = '';
                    }
                    
                    // Update peak P&L and trailing SL level
                    const peakPnl = ic.peak_pnl_pct || 0;
                    document.getElementById('ic-peak-pnl').textContent = '+' + peakPnl.toFixed(1) + '%';
                    
                    const trailActivate = ic.target_pct ? Math.min(ic.target_pct, 30) : 30;
                    if (peakPnl >= trailActivate) {
                        const trailLevel = peakPnl - 15; // IC_TRAILING_OFFSET_PCT default
                        document.getElementById('ic-trailing-sl-level').textContent = '+' + trailLevel.toFixed(1) + '% ✓';
                        document.getElementById('ic-trailing-sl-level').style.color = '#ffa726';
                    } else {
                        document.getElementById('ic-trailing-sl-level').textContent = 'Not active';
                        document.getElementById('ic-trailing-sl-level').style.color = '#666';
                    }
                    
                    // Update current prices in table
                    if (ic.current_prices) {
                        const cp = ic.current_prices;
                        document.getElementById('ic-sc-ltp').textContent = '₹' + (cp.sc || 0).toFixed(2);
                        document.getElementById('ic-bc-ltp').textContent = '₹' + (cp.bc || 0).toFixed(2);
                        document.getElementById('ic-sp-ltp').textContent = '₹' + (cp.sp || 0).toFixed(2);
                        document.getElementById('ic-bp-ltp').textContent = '₹' + (cp.bp || 0).toFixed(2);
                    }
                    
                    // Update progress bar (map -100% to +50% -> 0% to 100%)
                    const progress = document.getElementById('ic-progress');
                    const progressPct = Math.min(100, Math.max(0, ((pnlPct + ic.stoploss_pct) / (ic.target_pct + ic.stoploss_pct)) * 100));
                    progress.style.left = progressPct + '%';
                    
                    // Update labels
                    document.getElementById('ic-sl-label').textContent = '-' + ic.stoploss_pct + '%';
                    document.getElementById('ic-target-label').textContent = '+' + ic.target_pct + '%';
                }
                
                if (strategy === 'straddle' && data.straddle) {
                    const str = data.straddle;
                    const pnl = str.pnl_amount || 0;
                    const pnlPct = str.pnl_percent || 0;
                    
                    // Update header P&L
                    const pnlEl = document.getElementById('str-pnl');
                    pnlEl.textContent = '₹' + pnl.toLocaleString('en-IN', {maximumFractionDigits: 0});
                    pnlEl.className = 'position-pnl ' + (pnl >= 0 ? 'positive' : 'negative');
                    
                    // Update current premium
                    document.getElementById('str-current-premium').textContent = '₹' + (str.current_premium || 0).toFixed(2);
                    
                    // Update unrealized P&L
                    const unrealizedEl = document.getElementById('str-unrealized-pnl');
                    unrealizedEl.textContent = '₹' + pnl.toLocaleString('en-IN', {maximumFractionDigits: 0});
                    unrealizedEl.className = 'pnl-value ' + (pnl >= 0 ? 'positive' : 'negative');
                    
                    // Update P&L %
                    document.getElementById('str-pnl-pct').textContent = (pnl >= 0 ? '+' : '') + pnlPct.toFixed(1) + '%';
                    
                    // Update current prices in table
                    if (str.current_prices) {
                        document.getElementById('str-ce-ltp').textContent = '₹' + (str.current_prices.ce || 0).toFixed(2);
                        document.getElementById('str-pe-ltp').textContent = '₹' + (str.current_prices.pe || 0).toFixed(2);
                    }
                    
                    // Update progress bar
                    const progress = document.getElementById('str-progress');
                    const progressPct = Math.min(100, Math.max(0, ((pnlPct + str.stoploss_pct) / (str.target_pct + str.stoploss_pct)) * 100));
                    progress.style.left = progressPct + '%';
                    
                    // Update labels
                    document.getElementById('str-sl-label').textContent = '-' + str.stoploss_pct + '%';
                    document.getElementById('str-target-label').textContent = '+' + str.target_pct + '%';
                }
            } catch (e) {
                console.error('Error fetching live P&L:', e);
            }
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
            const entryStart = document.getElementById('bt-entry-start').value;
            const entryEnd = document.getElementById('bt-entry-end').value;
            const exitTime = document.getElementById('bt-exit-time').value;
            const useHistoricalApi = document.getElementById('bt-use-api').checked;
            
            // Show loading
            document.getElementById('bt-run-btn').disabled = true;
            document.getElementById('bt-loading').style.display = 'inline';
            if (useHistoricalApi) {
                document.getElementById('bt-loading').textContent = '⏳ Fetching historical data from Breeze API (this may take a while)...';
            } else {
                document.getElementById('bt-loading').textContent = '⏳ Running backtest...';
            }
            
            try {
                const res = await fetch('/api/backtest', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ 
                        start_date: start, 
                        end_date: end, 
                        strategy, 
                        capital: parseFloat(capital),
                        entry_time_start: entryStart,
                        entry_time_end: entryEnd,
                        exit_time: exitTime,
                        use_historical_api: useHistoricalApi
                    })
                });
                const data = await res.json();
                
                // Summary stats
                document.getElementById('bt-trades').textContent = data.total_trades || 0;
                document.getElementById('bt-winrate').textContent = (data.win_rate || 0).toFixed(1) + '%';
                document.getElementById('bt-pnl').textContent = '₹' + (data.total_pnl || 0).toLocaleString('en-IN');
                document.getElementById('bt-pnl').className = 'result-value ' + ((data.total_pnl || 0) >= 0 ? 'positive' : 'negative');
                document.getElementById('bt-return').textContent = (data.return_pct || 0).toFixed(2) + '%';
                document.getElementById('bt-expiries').textContent = data.expiries_found || 0;
                document.getElementById('bt-avg-exit').textContent = data.avg_exit_time || '--:--';
                
                // Data source info
                const dataSource = data.data_source || {};
                let sourceText = 'Estimated';
                if (dataSource.use_historical_api) {
                    sourceText = `API: ${dataSource.api_data || 0}, Est: ${dataSource.estimated_data || 0}`;
                }
                document.getElementById('bt-data-source').textContent = sourceText;
                document.getElementById('bt-avg-premium').textContent = '₹' + (data.avg_premium || 0).toFixed(2);
                
                // Timing info
                document.getElementById('bt-timing-entry').textContent = (data.entry_time_start || entryStart) + ' - ' + (data.entry_time_end || entryEnd);
                document.getElementById('bt-timing-exit').textContent = data.exit_time || exitTime;
                document.getElementById('bt-timing-qty').textContent = data.quantity || 75;
                
                // Exit breakdown
                const exits = data.exit_breakdown || {};
                document.getElementById('bt-target-exits').textContent = exits.target || 0;
                document.getElementById('bt-sl-exits').textContent = exits.stop_loss || 0;
                document.getElementById('bt-time-exits').textContent = exits.time_exit || 0;
                
                // Trades table
                const trades = data.trades || [];
                document.getElementById('bt-trade-count').textContent = '(' + trades.length + ' trades)';
                
                const tbody = document.getElementById('bt-trades-body');
                if (!trades.length) {
                    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:#666;">No trades</td></tr>';
                } else {
                    tbody.innerHTML = trades.map(t => {
                        const pnl = parseFloat(t.pnl || 0);
                        const premium = t.credit || t.total_premium || 0;
                        const strategyName = (t.strategy || '').replace('_', ' ');
                        const exitClass = t.exit_reason === 'TARGET' ? 'positive' : 
                                         t.exit_reason === 'STOP_LOSS' ? 'negative' : '';
                        const dataIcon = t.data_source === 'API' ? '📡' : '📊';
                        return `<tr>
                            <td>${t.entry_date || '-'}</td>
                            <td>${strategyName}</td>
                            <td>${t.entry_time || '-'}</td>
                            <td>${t.exit_time || '-'}</td>
                            <td>${dataIcon} ₹${parseFloat(premium).toFixed(2)}</td>
                            <td class="${pnl >= 0 ? 'positive' : 'negative'}">₹${pnl.toLocaleString('en-IN', {maximumFractionDigits: 0})}</td>
                            <td class="${exitClass}">${t.exit_reason || '-'}</td>
                        </tr>`;
                    }).join('');
                }
                
                document.getElementById('bt-results').classList.add('show');
            } catch (e) {
                console.error(e);
                alert('Backtest failed: ' + e.message);
            } finally {
                document.getElementById('bt-run-btn').disabled = false;
                document.getElementById('bt-loading').style.display = 'none';
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
        
        async function initBacktestForm() {
            // Load bot settings to populate backtest form with same values
            try {
                const res = await fetch('/api/status');
                const status = await res.json();
                
                if (status.entry_time_start) {
                    document.getElementById('bt-entry-start').value = status.entry_time_start;
                }
                if (status.entry_time_end) {
                    document.getElementById('bt-entry-end').value = status.entry_time_end;
                }
                if (status.exit_time) {
                    document.getElementById('bt-exit-time').value = status.exit_time;
                }
            } catch (e) {
                console.error('Error loading bot settings for backtest:', e);
            }
        }
        
        initChart();
        refreshData();
        initBacktestForm();
        setInterval(refreshData, 15000);  // Refresh every 15 seconds to reduce API load
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

@app.route('/api/position')
def api_position():
    """Get current live positions with real-time P&L"""
    pos_data = load_position()
    
    result = {
        "has_position": False,
        "iron_condor": None,
        "straddle": None,
        "total_unrealized_pnl": 0,
        "last_update": pos_data.get("last_update", "")
    }
    
    if pos_data.get("iron_condor"):
        result["has_position"] = True
        result["iron_condor"] = pos_data["iron_condor"]
    
    if pos_data.get("straddle"):
        result["has_position"] = True
        result["straddle"] = pos_data["straddle"]
    
    return jsonify(result)

# Global references for live P&L (set by bot_thread)
_live_ic = None
_live_straddle = None

@app.route('/api/live_pnl')
def api_live_pnl():
    """Get real-time P&L for active positions"""
    global _live_ic, _live_straddle
    
    strategy = request.args.get("strategy", "all")
    result = {
        "iron_condor": None,
        "straddle": None
    }
    
    # Try to get live P&L from strategy instances
    if strategy in ["iron_condor", "all"] and _live_ic and _live_ic.position:
        pnl_data = _live_ic.get_live_pnl()
        if pnl_data:
            result["iron_condor"] = pnl_data
    
    if strategy in ["straddle", "all"] and _live_straddle and _live_straddle.position:
        pnl_data = _live_straddle.get_live_pnl()
        if pnl_data:
            result["straddle"] = pnl_data
    
    # Fallback to stored position data if live not available
    if not result["iron_condor"] and not result["straddle"]:
        pos_data = load_position()
        if pos_data.get("iron_condor"):
            result["iron_condor"] = {
                "entry_premium": pos_data["iron_condor"].get("entry_premium", 0),
                "current_premium": pos_data["iron_condor"].get("entry_premium", 0),
                "pnl_amount": 0,
                "pnl_percent": 0,
                "target_pct": IC_TARGET_PERCENT,
                "stoploss_pct": IC_STOP_LOSS_PERCENT,
                "current_prices": pos_data["iron_condor"].get("entry_prices", {})
            }
        if pos_data.get("straddle"):
            result["straddle"] = {
                "entry_premium": pos_data["straddle"].get("entry_premium", 0),
                "current_premium": pos_data["straddle"].get("entry_premium", 0),
                "pnl_amount": 0,
                "pnl_percent": 0,
                "target_pct": STR_TARGET_PERCENT,
                "stoploss_pct": STR_STOP_LOSS_PERCENT,
                "current_prices": pos_data["straddle"].get("entry_prices", {})
            }
    
    return jsonify(result)

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
    """Run backtest via API with entry/exit time configuration"""
    try:
        req = request.json
        start_date = datetime.strptime(req.get("start_date", "2025-01-01"), "%Y-%m-%d")
        end_date = datetime.strptime(req.get("end_date", "2025-12-31"), "%Y-%m-%d")
        strategy = req.get("strategy", "iron_condor")
        capital = float(req.get("capital", 500000))
        
        # Get timing parameters (use bot defaults if not provided)
        entry_time_start = req.get("entry_time_start", ENTRY_TIME_START)
        entry_time_end = req.get("entry_time_end", ENTRY_TIME_END)
        exit_time = req.get("exit_time", EXIT_TIME)
        
        # Historical API option
        use_historical_api = req.get("use_historical_api", False)
        
        backtester = Backtester()
        results = backtester.run_backtest(
            start_date, end_date, strategy, capital,
            entry_time_start=entry_time_start,
            entry_time_end=entry_time_end,
            exit_time=exit_time,
            use_historical_api=use_historical_api
        )
        
        return jsonify(results)
    except Exception as e:
        logger.error(f"Backtest error: {e}")
        import traceback
        traceback.print_exc()
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

@app.route('/api/status')
def api_status():
    """Get detailed bot status including timing info"""
    now = get_ist_now()
    next_exp = get_next_expiry()
    return jsonify({
        "current_time_ist": now.strftime("%Y-%m-%d %H:%M:%S"),
        "current_time_utc": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
        "entry_time_start": ENTRY_TIME_START,
        "entry_time_end": ENTRY_TIME_END,
        "exit_time": EXIT_TIME,
        "is_trading_time": is_trading_time(),
        "is_exit_time": is_exit_time(),
        "is_market_hours": is_market_hours(),
        "custom_expiry": CUSTOM_EXPIRY if CUSTOM_EXPIRY else None,
        "next_expiry": next_exp.strftime("%d-%b-%Y"),
        "next_expiry_day": next_exp.strftime("%A"),
        "next_expiry_breeze": format_expiry_for_breeze(next_exp),
        "strategy": STRATEGY,
        "lot_size": LOT_SIZE,
        "num_lots": NUM_LOTS,
        "quantity": QUANTITY,
        "min_premium": MIN_PREMIUM,
        "auto_start": AUTO_START,
        "api_key_set": bool(API_KEY),
        "api_secret_set": bool(API_SECRET),
        "session_set": bool(API_SESSION),
        "telegram_enabled": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID),
        "ic_improvements": {
            "vix_filter": {"enabled": True, "min": IC_VIX_MIN, "max": IC_VIX_MAX},
            "strike_mode": IC_STRIKE_MODE,
            "min_credit": IC_MIN_CREDIT,
            "trailing_sl": {"enabled": IC_TRAILING_SL, "activate_pct": IC_TRAILING_ACTIVATE_PCT, "offset_pct": IC_TRAILING_OFFSET_PCT},
            "adjustment": {"enabled": IC_ADJUSTMENT_ENABLED, "trigger_pct": IC_ADJUSTMENT_TRIGGER_PCT},
            "leg_sl": {"enabled": IC_LEG_SL_ENABLED, "percent": IC_LEG_SL_PERCENT},
            "spot_buffer": IC_SPOT_BUFFER,
            "avoid_expiry_day": IC_AVOID_EXPIRY_DAY,
            "reentry_after_sl": IC_REENTRY_AFTER_SL,
            "daily_loss_limit": IC_DAILY_LOSS_LIMIT
        }
    })

@app.route('/api/settings', methods=['GET', 'POST'])
def api_settings():
    """Get or update bot settings"""
    if request.method == 'GET':
        return jsonify({
            "entry_time_start": ENTRY_TIME_START,
            "entry_time_end": ENTRY_TIME_END,
            "exit_time": EXIT_TIME,
            "strategy": STRATEGY,
            "lot_size": LOT_SIZE,
            "num_lots": NUM_LOTS,
            "quantity": QUANTITY,
            "min_premium": MIN_PREMIUM,
            "ic_call_sell_distance": IC_CALL_SELL_DISTANCE,
            "ic_call_buy_distance": IC_CALL_BUY_DISTANCE,
            "ic_put_sell_distance": IC_PUT_SELL_DISTANCE,
            "ic_put_buy_distance": IC_PUT_BUY_DISTANCE,
            "ic_target_percent": IC_TARGET_PERCENT,
            "ic_stop_loss_percent": IC_STOP_LOSS_PERCENT,
            "str_target_percent": STR_TARGET_PERCENT,
            "str_stop_loss_percent": STR_STOP_LOSS_PERCENT,
            "ic_vix_max": IC_VIX_MAX,
            "ic_vix_min": IC_VIX_MIN,
            "ic_strike_mode": IC_STRIKE_MODE,
            "ic_min_credit": IC_MIN_CREDIT,
            "ic_trailing_sl": IC_TRAILING_SL,
            "ic_trailing_activate_pct": IC_TRAILING_ACTIVATE_PCT,
            "ic_trailing_offset_pct": IC_TRAILING_OFFSET_PCT,
            "ic_adjustment_enabled": IC_ADJUSTMENT_ENABLED,
            "ic_adjustment_trigger_pct": IC_ADJUSTMENT_TRIGGER_PCT,
            "ic_leg_sl_enabled": IC_LEG_SL_ENABLED,
            "ic_leg_sl_percent": IC_LEG_SL_PERCENT,
            "ic_spot_buffer": IC_SPOT_BUFFER,
            "ic_avoid_expiry_day": IC_AVOID_EXPIRY_DAY,
            "ic_reentry_after_sl": IC_REENTRY_AFTER_SL,
            "ic_daily_loss_limit": IC_DAILY_LOSS_LIMIT
        })
    return jsonify({"status": "settings are read-only, configure via environment variables"})

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
