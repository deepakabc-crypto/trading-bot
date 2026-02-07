"""
================================================================================
CONFIGURATION - Railway.app Cloud Deployment
================================================================================
All sensitive values are loaded from Environment Variables.
Set these in Railway Dashboard → Variables tab.

Required Environment Variables:
- API_KEY
- API_SECRET
- API_SESSION
- TELEGRAM_BOT_TOKEN
- TELEGRAM_CHAT_ID
================================================================================
"""

import os

# ============================================
# ICICI Direct Breeze API Credentials
# ============================================
API_KEY = os.environ.get("API_KEY", "")
API_SECRET = os.environ.get("API_SECRET", "")
API_SESSION = os.environ.get("API_SESSION", "")

# ============================================
# CAPITAL & RISK MANAGEMENT
# ============================================
CAPITAL = int(os.environ.get("CAPITAL", "500000"))
MAX_RISK_PER_TRADE = float(os.environ.get("MAX_RISK_PER_TRADE", "0.02"))
MAX_POSITIONS = int(os.environ.get("MAX_POSITIONS", "3"))

# ============================================
# STRATEGY SELECTION
# ============================================
# Options: "iron_condor" or "straddle"
STRATEGY = os.environ.get("STRATEGY", "iron_condor")

# ============================================
# IRON CONDOR SETTINGS
# ============================================
CALL_SELL_DISTANCE = int(os.environ.get("CALL_SELL_DISTANCE", "200"))
CALL_BUY_DISTANCE = int(os.environ.get("CALL_BUY_DISTANCE", "300"))
PUT_SELL_DISTANCE = int(os.environ.get("PUT_SELL_DISTANCE", "200"))
PUT_BUY_DISTANCE = int(os.environ.get("PUT_BUY_DISTANCE", "300"))
SPREAD_WIDTH = CALL_BUY_DISTANCE - CALL_SELL_DISTANCE

# ============================================
# SHORT STRADDLE SETTINGS
# ============================================
STRADDLE_STOP_LOSS_PERCENT = int(os.environ.get("STRADDLE_STOP_LOSS_PERCENT", "25"))

# ============================================
# COMMON TRADING SETTINGS
# ============================================
QUANTITY = int(os.environ.get("QUANTITY", "25"))
MAX_LOTS = int(os.environ.get("MAX_LOTS", "2"))

# Entry & Exit
ENTRY_TIME = os.environ.get("ENTRY_TIME", "09:30")
ENTRY_END_TIME = os.environ.get("ENTRY_END_TIME", "14:00")
EXIT_TIME = os.environ.get("EXIT_TIME", "15:20")

# Targets
TARGET_PERCENT = int(os.environ.get("TARGET_PERCENT", "50"))
STOP_LOSS_PERCENT = int(os.environ.get("STOP_LOSS_PERCENT", "100"))

# ============================================
# INDEX SETTINGS
# ============================================
INDEX = "NIFTY"
EXCHANGE = "NFO"
STRIKE_INTERVAL = 50

# ============================================
# TRADING DAYS
# ============================================
TRADE_DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY"]
AVOID_EXPIRY_DAY = os.environ.get("AVOID_EXPIRY_DAY", "false").lower() == "true"

# ============================================
# VOLATILITY FILTERS
# ============================================
MIN_VIX = int(os.environ.get("MIN_VIX", "10"))
MAX_VIX = int(os.environ.get("MAX_VIX", "25"))
MIN_PREMIUM = int(os.environ.get("MIN_PREMIUM", "40"))

# ============================================
# TELEGRAM ALERTS
# ============================================
TELEGRAM_ALERTS = os.environ.get("TELEGRAM_ALERTS", "true").lower() == "true"
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# Alert Settings
SEND_ENTRY_ALERTS = True
SEND_EXIT_ALERTS = True
SEND_POSITION_UPDATES = True
POSITION_UPDATE_INTERVAL = 300
SEND_WARNING_ALERTS = True
WARNING_THRESHOLD = 70
SEND_DAILY_SUMMARY = True
SEND_ERROR_ALERTS = True

# ============================================
# LOGGING
# ============================================
LOG_FILE = "trading_bot.log"
SAVE_TRADES_CSV = True
TRADES_FILE = "trades_history.csv"

# ============================================
# CLOUD SETTINGS
# ============================================
IS_CLOUD = os.environ.get("RAILWAY_ENVIRONMENT", "") != ""
PORT = int(os.environ.get("PORT", "5000"))

# ============================================
# VALIDATION
# ============================================
def validate_config():
    """Check if all required config is set"""
    errors = []
    
    if not API_KEY:
        errors.append("API_KEY not set")
    if not API_SECRET:
        errors.append("API_SECRET not set")
    if not API_SESSION:
        errors.append("API_SESSION not set")
    
    if TELEGRAM_ALERTS:
        if not TELEGRAM_BOT_TOKEN:
            errors.append("TELEGRAM_BOT_TOKEN not set")
        if not TELEGRAM_CHAT_ID:
            errors.append("TELEGRAM_CHAT_ID not set")
    
    return errors

def print_config():
    """Print current configuration (hide sensitive values)"""
    print("=" * 50)
    print("CURRENT CONFIGURATION")
    print("=" * 50)
    print(f"Strategy: {STRATEGY}")
    print(f"Capital: ₹{CAPITAL:,}")
    print(f"Quantity: {QUANTITY}")
    print(f"API Key: {'✅ Set' if API_KEY else '❌ Not set'}")
    print(f"API Secret: {'✅ Set' if API_SECRET else '❌ Not set'}")
    print(f"API Session: {'✅ Set' if API_SESSION else '❌ Not set'}")
    print(f"Telegram: {'✅ Enabled' if TELEGRAM_ALERTS and TELEGRAM_BOT_TOKEN else '❌ Disabled'}")
    print(f"Cloud Mode: {'☁️ Railway' if IS_CLOUD else '💻 Local'}")
    print("=" * 50)
