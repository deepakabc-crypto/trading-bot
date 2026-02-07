"""
================================================================================
BOT RUNNER - Railway.app Worker Process
================================================================================
Handles:
- Scheduled trading during market hours
- Auto-restart on failures
- Session token updates via Telegram
- Health monitoring

This runs as a worker process alongside the web dashboard.
================================================================================
"""

import os
import sys
import time
import logging
import threading
from datetime import datetime, timedelta
import schedule

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('bot_runner.log')
    ]
)
logger = logging.getLogger(__name__)

# Import config
from config import *

# Import telegram alerts
try:
    from telegram_alerts import TelegramAlert
    telegram = TelegramAlert(TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID) if TELEGRAM_ALERTS else None
except ImportError:
    telegram = None
    logger.warning("Telegram alerts not available")

# ============================================
# SESSION TOKEN MANAGEMENT
# ============================================
class SessionManager:
    """Manage API session token"""
    
    def __init__(self):
        self.session_token = API_SESSION
        self.last_updated = datetime.now()
    
    def update_token(self, new_token: str):
        """Update session token"""
        global API_SESSION
        self.session_token = new_token
        API_SESSION = new_token
        self.last_updated = datetime.now()
        logger.info(f"Session token updated at {self.last_updated}")
        
        # Save to environment (persists in Railway)
        os.environ["API_SESSION"] = new_token
        
        if telegram:
            telegram.custom_alert("Session Updated", 
                                 f"New session token applied.\nTime: {self.last_updated.strftime('%H:%M')}", 
                                 "🔑")
    
    def is_valid(self) -> bool:
        """Check if session is likely valid (updated today)"""
        today = datetime.now().date()
        return self.last_updated.date() == today and bool(self.session_token)

session_manager = SessionManager()

# ============================================
# TELEGRAM COMMAND HANDLER
# ============================================
class TelegramCommandHandler:
    """Handle commands sent via Telegram"""
    
    def __init__(self):
        self.last_update_id = 0
        self.running = True
    
    def check_messages(self):
        """Check for new Telegram messages"""
        if not TELEGRAM_BOT_TOKEN:
            return
        
        try:
            import requests
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
            params = {"offset": self.last_update_id + 1, "timeout": 5}
            
            response = requests.get(url, params=params, timeout=10)
            data = response.json()
            
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    self.last_update_id = update["update_id"]
                    self.process_message(update)
                    
        except Exception as e:
            logger.debug(f"Telegram check error: {e}")
    
    def process_message(self, update: dict):
        """Process incoming Telegram message"""
        try:
            message = update.get("message", {})
            text = message.get("text", "")
            chat_id = str(message.get("chat", {}).get("id", ""))
            
            # Only process from authorized chat
            if chat_id != TELEGRAM_CHAT_ID:
                return
            
            # Command: /session NEW_TOKEN
            if text.startswith("/session "):
                new_token = text.replace("/session ", "").strip()
                if new_token:
                    session_manager.update_token(new_token)
                    self.reply(chat_id, "✅ Session token updated!")
                else:
                    self.reply(chat_id, "❌ Please provide token: /session YOUR_TOKEN")
            
            # Command: /status
            elif text == "/status":
                status = self.get_status()
                self.reply(chat_id, status)
            
            # Command: /help
            elif text == "/help":
                help_text = """
🤖 *Trading Bot Commands*

/session TOKEN - Update API session
/status - Check bot status
/stop - Stop trading (manual exit)
/help - Show this help

📊 Bot runs automatically during market hours.
"""
                self.reply(chat_id, help_text)
            
            # Command: /stop
            elif text == "/stop":
                self.reply(chat_id, "⚠️ Stop command received. Please exit positions manually in ICICI Direct app.")
                
        except Exception as e:
            logger.error(f"Message processing error: {e}")
    
    def reply(self, chat_id: str, text: str):
        """Send reply to Telegram"""
        try:
            import requests
            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
            requests.post(url, json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})
        except:
            pass
    
    def get_status(self) -> str:
        """Get current bot status"""
        now = datetime.now()
        market_open = now.replace(hour=9, minute=15, second=0)
        market_close = now.replace(hour=15, minute=30, second=0)
        
        is_market_hours = market_open <= now <= market_close and now.weekday() < 5
        
        status = f"""
📊 *Bot Status*

⏰ Time: {now.strftime('%H:%M:%S')}
📅 Date: {now.strftime('%d-%b-%Y')}

🏪 Market: {'🟢 Open' if is_market_hours else '🔴 Closed'}
🔑 Session: {'✅ Valid' if session_manager.is_valid() else '❌ Needs update'}
📈 Strategy: {STRATEGY.upper()}
💰 Capital: ₹{CAPITAL:,}

☁️ Running on Railway
"""
        return status

telegram_handler = TelegramCommandHandler()

# ============================================
# MARKET HOURS CHECK
# ============================================
def is_market_open() -> bool:
    """Check if Indian market is open"""
    now = datetime.now()
    
    # Weekend check
    if now.weekday() >= 5:
        return False
    
    # IST market hours (Railway servers may be in different timezone)
    # Adjust if needed
    market_open = now.replace(hour=9, minute=15, second=0)
    market_close = now.replace(hour=15, minute=30, second=0)
    
    return market_open <= now <= market_close

def is_trading_day() -> bool:
    """Check if today is a trading day"""
    now = datetime.now()
    day_name = now.strftime("%A").upper()
    return day_name in TRADE_DAYS

# ============================================
# BOT RUNNER
# ============================================
class TradingBotRunner:
    """Main bot runner"""
    
    def __init__(self):
        self.running = False
        self.bot_thread = None
        self.today_traded = False
    
    def start_trading(self):
        """Start the trading bot"""
        if self.running:
            logger.info("Bot already running")
            return
        
        # Validate config
        errors = validate_config()
        if errors:
            logger.error(f"Config errors: {errors}")
            if telegram:
                telegram.error_alert("Config Error", "\n".join(errors))
            return
        
        # Check session
        if not session_manager.is_valid():
            logger.warning("Session token may be expired")
            if telegram:
                telegram.custom_alert("Session Warning", 
                                     "Session token may be expired.\nSend new token: /session YOUR_TOKEN", 
                                     "⚠️")
        
        self.running = True
        logger.info(f"Starting {STRATEGY} trading bot...")
        
        if telegram:
            telegram.bot_started(STRATEGY.upper(), CAPITAL)
        
        # Import and run appropriate strategy
        try:
            if STRATEGY == "iron_condor":
                from iron_condor_bot import run_bot
                run_bot()
            else:
                from straddle_bot import run_bot
                run_bot()
        except Exception as e:
            logger.error(f"Bot error: {e}")
            if telegram:
                telegram.error_alert("Bot Error", str(e))
        finally:
            self.running = False
            self.today_traded = True
    
    def should_trade_today(self) -> bool:
        """Check if we should trade today"""
        if not is_trading_day():
            return False
        
        if self.today_traded:
            return False
        
        return True
    
    def reset_daily(self):
        """Reset daily flags"""
        self.today_traded = False
        logger.info("Daily reset completed")

bot_runner = TradingBotRunner()

# ============================================
# SCHEDULED JOBS
# ============================================
def job_start_trading():
    """Scheduled job to start trading"""
    logger.info("Scheduled trading job triggered")
    
    if not bot_runner.should_trade_today():
        logger.info("Skipping: Already traded or not a trading day")
        return
    
    if not is_market_open():
        logger.info("Market not open yet")
        return
    
    # Start in separate thread
    thread = threading.Thread(target=bot_runner.start_trading)
    thread.start()

def job_check_telegram():
    """Check for Telegram commands"""
    telegram_handler.check_messages()

def job_daily_reset():
    """Reset daily flags at midnight"""
    bot_runner.reset_daily()

def job_health_check():
    """Log health status"""
    logger.info(f"Health check: Bot running={bot_runner.running}, Market open={is_market_open()}")

# ============================================
# MAIN LOOP
# ============================================
def main():
    """Main entry point"""
    logger.info("=" * 60)
    logger.info("🚂 RAILWAY BOT RUNNER STARTED")
    logger.info("=" * 60)
    
    print_config()
    
    # Schedule jobs (IST times)
    schedule.every().day.at("09:25").do(job_start_trading)  # Before market open
    schedule.every().day.at("09:35").do(job_start_trading)  # Backup trigger
    schedule.every().day.at("00:01").do(job_daily_reset)    # Daily reset
    schedule.every(30).seconds.do(job_check_telegram)       # Check Telegram
    schedule.every(5).minutes.do(job_health_check)          # Health check
    
    logger.info("Scheduled jobs:")
    logger.info("  - Trading: 09:25, 09:35 IST")
    logger.info("  - Telegram check: Every 30 seconds")
    logger.info("  - Health check: Every 5 minutes")
    logger.info("  - Daily reset: 00:01 IST")
    
    if telegram:
        telegram.custom_alert("Bot Runner Started", 
                             f"Trading bot is online and scheduled.\nStrategy: {STRATEGY}\nCapital: ₹{CAPITAL:,}",
                             "🚂")
    
    # Run scheduler
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()
