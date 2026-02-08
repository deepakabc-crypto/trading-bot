"""
================================================================================
⚙️ TRADING BOT SETTINGS
================================================================================
All settings in one place. Edit this file to configure your bot.

IMPORTANT: 
- This file must be named 'settings.py' (NOT config.py)
- For Railway: Set these as Environment Variables instead
================================================================================
"""
import os

# ============================================
# 🔑 API CREDENTIALS (ICICI Breeze)
# ============================================
API_KEY = os.environ.get("API_KEY", "YOUR_API_KEY_HERE")
API_SECRET = os.environ.get("API_SECRET", "YOUR_API_SECRET_HERE")
API_SESSION = os.environ.get("API_SESSION", "")  # Update daily via Telegram!

# ============================================
# 📱 TELEGRAM ALERTS
# ============================================
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "YOUR_CHAT_ID_HERE")

# ============================================
# 💰 CAPITAL & POSITION SIZING
# ============================================
CAPITAL = int(os.environ.get("CAPITAL", "500000"))
QUANTITY = 25             # Nifty lot size

# ============================================
# 📊 STRATEGY SELECTION
# Options: "iron_condor", "straddle", "both"
# ============================================
STRATEGY = os.environ.get("STRATEGY", "iron_condor")

# ============================================
# 🦅 IRON CONDOR SETTINGS
# ============================================
IC_CALL_SELL_DISTANCE = 150    # Sell Call at ATM + 150
IC_CALL_BUY_DISTANCE = 250     # Buy Call at ATM + 250
IC_PUT_SELL_DISTANCE = 150     # Sell Put at ATM - 150
IC_PUT_BUY_DISTANCE = 250      # Buy Put at ATM - 250
IC_TARGET_PERCENT = 50         # Exit at 50% profit
IC_STOP_LOSS_PERCENT = 100     # Exit at 100% loss

# ============================================
# 📊 SHORT STRADDLE SETTINGS
# ============================================
STR_TARGET_PERCENT = 30        # Exit at 30% profit
STR_STOP_LOSS_PERCENT = 20     # Exit at 20% loss

# ============================================
# ⏰ TRADING HOURS (IST)
# ============================================
ENTRY_TIME_START = "09:20"
ENTRY_TIME_END = "14:00"
EXIT_TIME = "15:15"

# ============================================
# 📅 TRADING DAYS (0=Mon, 4=Fri)
# ============================================
TRADING_DAYS = [0, 1, 2, 3, 4]

# ============================================
# 🛡️ RISK & CHARGES
# ============================================
MIN_PREMIUM = 30
CHARGES_PER_LOT = 100
CHECK_INTERVAL = 30

# ============================================
# 🌐 CLOUD SETTINGS
# ============================================
PORT = int(os.environ.get("PORT", "5000"))
IS_CLOUD = os.environ.get("RAILWAY_ENVIRONMENT") is not None
