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
        self.entry_prices = {}
        self.entry_time = None
        self.spot_at_entry = None
        
    def enter(self, spot, expiry):
        atm = round(spot / 50) * 50
        sc, bc = atm + IC_CALL_SELL_DISTANCE, atm + IC_CALL_BUY_DISTANCE
        sp, bp = atm - IC_PUT_SELL_DISTANCE, atm - IC_PUT_BUY_DISTANCE
        
        # Log what we're trying to do
        expiry_display = expiry.strftime('%d-%b-%Y') if isinstance(expiry, datetime) else expiry
        logger.info(f"🦅 IC Setup: ATM={atm}, Strikes: SC={sc}, BC={bc}, SP={sp}, BP={bp}")
        logger.info(f"🦅 IC Expiry: {expiry_display}")
        
        # Get all LTPs with delays between calls to avoid rate limits
        logger.info(f"📊 Fetching premiums (with rate limiting)...")
        
        sc_p = self.api.get_ltp_with_retry(sc, "call", expiry) or 0
        time.sleep(1)  # Delay between calls
        
        bc_p = self.api.get_ltp_with_retry(bc, "call", expiry) or 0
        time.sleep(1)
        
        sp_p = self.api.get_ltp_with_retry(sp, "put", expiry) or 0
        time.sleep(1)
        
        bp_p = self.api.get_ltp_with_retry(bp, "put", expiry) or 0
        
        # Log premiums
        logger.info(f"📊 Premiums: SC={sc_p}, BC={bc_p}, SP={sp_p}, BP={bp_p}")
        
        # Check if any premium is 0 (API issue)
        if sc_p == 0 or sp_p == 0:
            logger.warning(f"⚠️ Could not get sell option premiums (SC={sc_p}, SP={sp_p})")
            telegram.send(f"⚠️ IC Entry failed: Could not get option quotes\nTried: {sc}CE/{sp}PE\nExpiry: {expiry_display}")
            return False
        
        credit = (sc_p - bc_p) + (sp_p - bp_p)
        logger.info(f"📊 Net Credit: {credit:.2f} (Call spread: {sc_p - bc_p:.2f}, Put spread: {sp_p - bp_p:.2f})")
        
        if credit < MIN_PREMIUM:
            logger.info(f"🦅 IC skipped: Credit {credit:.0f} < {MIN_PREMIUM}")
            return False
        
        logger.info(f"🦅 IC Entry: Credit={credit:.0f}, Qty={QUANTITY} ({NUM_LOTS} lots)")
        
        # Place orders
        self.api.place_order(sc, "call", expiry, QUANTITY, "sell", sc_p)
        self.api.place_order(bc, "call", expiry, QUANTITY, "buy", bc_p)
        self.api.place_order(sp, "put", expiry, QUANTITY, "sell", sp_p)
        self.api.place_order(bp, "put", expiry, QUANTITY, "buy", bp_p)
        
        # Store position details
        expiry_str = expiry.strftime('%Y-%m-%d') if isinstance(expiry, datetime) else expiry
        self.position = {"sc": sc, "bc": bc, "sp": sp, "bp": bp, "expiry": expiry, "expiry_str": expiry_str}
        self.entry_premium = credit
        self.entry_prices = {"sc": sc_p, "bc": bc_p, "sp": sp_p, "bp": bp_p}
        self.entry_time = datetime.now().isoformat()
        self.spot_at_entry = spot
        
        # Save to file for dashboard
        self._save_position()
        
        telegram.send(f"🦅 <b>Iron Condor Entry</b>\nSpot: {spot}\nATM: {atm}\nSell: {sc}CE @ {sc_p:.0f} / {sp}PE @ {sp_p:.0f}\nBuy: {bc}CE @ {bc_p:.0f} / {bp}PE @ {bp_p:.0f}\nCredit: ₹{credit:.0f}\nQty: {QUANTITY} ({NUM_LOTS} lots)\nExpiry: {expiry_display}")
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
                "entry_time": self.entry_time,
                "spot_at_entry": self.spot_at_entry,
                "expiry": self.position.get("expiry_str", ""),
                "quantity": QUANTITY,
                "num_lots": NUM_LOTS
            }
        else:
            pos_data["iron_condor"] = None
        save_position(pos_data)
    
    def get_live_pnl(self):
        """Get current unrealized P&L"""
        if not self.position:
            return None
        
        sc = self.api.get_ltp(self.position["sc"], "call", self.position["expiry"]) or self.entry_prices.get("sc", 0)
        bc = self.api.get_ltp(self.position["bc"], "call", self.position["expiry"]) or self.entry_prices.get("bc", 0)
        sp = self.api.get_ltp(self.position["sp"], "put", self.position["expiry"]) or self.entry_prices.get("sp", 0)
        bp = self.api.get_ltp(self.position["bp"], "put", self.position["expiry"]) or self.entry_prices.get("bp", 0)
        
        current_premium = (sc - bc) + (sp - bp)
        pnl_points = self.entry_premium - current_premium
        pnl_amount = pnl_points * QUANTITY
        pnl_pct = (pnl_points / self.entry_premium * 100) if self.entry_premium > 0 else 0
        
        return {
            "current_prices": {"sc": sc, "bc": bc, "sp": sp, "bp": bp},
            "current_premium": current_premium,
            "entry_premium": self.entry_premium,
            "pnl_points": pnl_points,
            "pnl_amount": pnl_amount,
            "pnl_percent": pnl_pct,
            "target_pct": IC_TARGET_PERCENT,
            "stoploss_pct": IC_STOP_LOSS_PERCENT
        }
    
    def check_exit(self):
        if not self.position:
            return None
        
        pnl_data = self.get_live_pnl()
        if not pnl_data:
            return None
        
        pnl_pct = pnl_data["pnl_percent"]
        
        if pnl_pct >= IC_TARGET_PERCENT:
            return "TARGET"
        if pnl_pct <= -IC_STOP_LOSS_PERCENT:
            return "STOP_LOSS"
        
        now = get_ist_now()
        current_time = now.strftime("%H:%M")
        if current_time >= EXIT_TIME:
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
        self.entry_prices = {}
        self._save_position()  # Clear position from file
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
                    
                    # Enter Iron Condor if no position
                    if strategy in ["iron_condor", "both"] and not ic.position:
                        logger.info("🦅 Attempting Iron Condor entry...")
                        if ic.enter(spot, expiry):
                            logger.info("✅ Iron Condor position opened")
                        else:
                            logger.info("⚠️ Iron Condor entry skipped (low premium or API issue)")
                    
                    # Enter Straddle if no position
                    if strategy in ["straddle", "both"] and not straddle.position:
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
                            <span class="position-strategy">🦅 IRON CONDOR</span>
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
                        </div>
                        <table class="position-table">
                            <thead>
                                <tr><th>Leg</th><th>Strike</th><th>Entry</th><th>Current</th><th>P&L</th></tr>
                            </thead>
                            <tbody id="ic-legs">
                            </tbody>
                        </table>
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
                
                // Calculate P&L from entry prices (static display)
                const entryCredit = ic.entry_premium || 0;
                document.getElementById('ic-entry-credit').textContent = '₹' + entryCredit.toFixed(2);
                
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
        "telegram_enabled": bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
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
            "str_stop_loss_percent": STR_STOP_LOSS_PERCENT
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
