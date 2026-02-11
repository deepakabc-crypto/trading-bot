#!/usr/bin/env python3
"""
Nifty Options Trading Bot - Iron Condor Strategy
Platform: Railway.app | API: ICICI Breeze
Version: 2.0 (Iron Condor Only)
"""

import os
import sys
import time
import json
import logging
import schedule
import pytz
from datetime import datetime, timedelta
from threading import Thread

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', mode='a')
    ]
)
logger = logging.getLogger(__name__)

IST = pytz.timezone('Asia/Kolkata')

# ── Import components ────────────────────────────────────────────
from breeze_client import BreezeClient
from iron_condor import IronCondorStrategy
from telegram_alerts import TelegramAlert
from dashboard import create_app
from config import Config

# ── Global State ─────────────────────────────────────────────────
class BotState:
    def __init__(self):
        self.is_running = False
        self.positions = []
        self.trades_today = []
        self.pnl = 0.0
        self.status = "INITIALIZED"
        self.last_update = None
        self.config = Config()
        self.breeze = None
        self.strategy = None
        self.telegram = None
        self.entry_done = False
        self.exit_done = False

    def to_dict(self):
        return {
            "is_running": self.is_running,
            "positions": self.positions,
            "trades_today": self.trades_today,
            "pnl": self.pnl,
            "status": self.status,
            "last_update": self.last_update,
            "strategy": "Iron Condor",
            "config": self.config.to_dict(),
            "entry_done": self.entry_done,
            "exit_done": self.exit_done
        }

bot_state = BotState()


# ── Initialize Components ────────────────────────────────────────
def initialize_bot():
    """Initialize Breeze API connection and strategy."""
    logger.info("=" * 60)
    logger.info("NIFTY OPTIONS TRADING BOT v2.0 - IRON CONDOR ONLY")
    logger.info("=" * 60)

    try:
        # Initialize Breeze client
        bot_state.breeze = BreezeClient()
        bot_state.breeze.connect()
        logger.info("✅ Breeze API connected successfully")

        # Initialize Iron Condor strategy
        bot_state.strategy = IronCondorStrategy(
            breeze=bot_state.breeze,
            config=bot_state.config
        )
        logger.info("✅ Iron Condor strategy initialized")

        # Initialize Telegram
        bot_state.telegram = TelegramAlert()
        if bot_state.telegram.enabled:
            logger.info("✅ Telegram alerts enabled")
            bot_state.telegram.send("🤖 *Bot Started*\nStrategy: Iron Condor\nStatus: Ready")
        else:
            logger.warning("⚠️ Telegram alerts disabled (no token)")

        bot_state.status = "READY"
        bot_state.is_running = True
        return True

    except Exception as e:
        logger.error(f"❌ Initialization failed: {e}")
        bot_state.status = f"INIT_FAILED: {e}"
        return False


# ── Trading Logic ────────────────────────────────────────────────
def check_market_hours():
    """Check if market is open."""
    now = datetime.now(IST)
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    weekday = now.weekday()

    if weekday >= 5:  # Saturday/Sunday
        return False
    return market_open <= now <= market_close


def reset_daily_flags():
    """Reset daily trading flags at start of day."""
    now = datetime.now(IST)
    if now.hour == 9 and now.minute == 0:
        bot_state.entry_done = False
        bot_state.exit_done = False
        bot_state.trades_today = []
        bot_state.pnl = 0.0
        logger.info("📅 Daily flags reset")
        if bot_state.telegram and bot_state.telegram.enabled:
            bot_state.telegram.send(f"📅 *New Trading Day*\nDate: {now.strftime('%d-%b-%Y')}\nStrategy: Iron Condor")


def execute_entry():
    """Execute Iron Condor entry at configured time."""
    if not bot_state.is_running or bot_state.entry_done:
        return

    now = datetime.now(IST)
    entry_hour = bot_state.config.entry_hour
    entry_minute = bot_state.config.entry_minute

    if now.hour == entry_hour and now.minute == entry_minute:
        if not check_market_hours():
            logger.info("Market closed, skipping entry")
            return

        logger.info("🚀 Executing Iron Condor entry...")
        bot_state.status = "ENTERING_POSITION"

        try:
            result = bot_state.strategy.enter_position()
            if result['success']:
                bot_state.positions = result['positions']
                bot_state.trades_today.extend(result['trades'])
                bot_state.entry_done = True
                bot_state.status = "POSITION_ACTIVE"

                msg = (
                    f"✅ *Iron Condor Entered*\n"
                    f"Nifty Spot: {result.get('spot_price', 'N/A')}\n"
                    f"CE Sell: {result.get('ce_sell_strike', 'N/A')}\n"
                    f"CE Buy: {result.get('ce_buy_strike', 'N/A')}\n"
                    f"PE Sell: {result.get('pe_sell_strike', 'N/A')}\n"
                    f"PE Buy: {result.get('pe_buy_strike', 'N/A')}\n"
                    f"Lots: {bot_state.config.lot_size}\n"
                    f"Premium Collected: ₹{result.get('total_premium', 0):.2f}"
                )
                logger.info(msg.replace('*', ''))
                if bot_state.telegram and bot_state.telegram.enabled:
                    bot_state.telegram.send(msg)
            else:
                bot_state.status = f"ENTRY_FAILED: {result.get('error', 'Unknown')}"
                logger.error(f"❌ Entry failed: {result.get('error')}")
                if bot_state.telegram and bot_state.telegram.enabled:
                    bot_state.telegram.send(f"❌ *Entry Failed*\n{result.get('error', 'Unknown error')}")

        except Exception as e:
            logger.error(f"❌ Entry exception: {e}")
            bot_state.status = f"ENTRY_ERROR: {e}"


def execute_exit():
    """Execute exit at configured time."""
    if not bot_state.is_running or bot_state.exit_done or not bot_state.entry_done:
        return

    now = datetime.now(IST)
    exit_hour = bot_state.config.exit_hour
    exit_minute = bot_state.config.exit_minute

    if now.hour == exit_hour and now.minute == exit_minute:
        logger.info("🛑 Executing Iron Condor exit...")
        bot_state.status = "EXITING_POSITION"

        try:
            result = bot_state.strategy.exit_position()
            if result['success']:
                bot_state.pnl = result.get('realized_pnl', 0)
                bot_state.positions = []
                bot_state.exit_done = True
                bot_state.status = "POSITION_CLOSED"

                msg = (
                    f"🛑 *Iron Condor Exited*\n"
                    f"Realized P&L: ₹{bot_state.pnl:.2f}\n"
                    f"Exit Reason: Scheduled Exit"
                )
                logger.info(msg.replace('*', ''))
                if bot_state.telegram and bot_state.telegram.enabled:
                    bot_state.telegram.send(msg)
            else:
                logger.error(f"❌ Exit failed: {result.get('error')}")

        except Exception as e:
            logger.error(f"❌ Exit exception: {e}")


def monitor_positions():
    """Monitor active positions and update P&L."""
    if not bot_state.is_running or not bot_state.entry_done or bot_state.exit_done:
        return

    if not check_market_hours():
        return

    try:
        result = bot_state.strategy.get_live_pnl()
        if result['success']:
            bot_state.pnl = result['pnl']
            bot_state.positions = result.get('positions', bot_state.positions)
            bot_state.last_update = datetime.now(IST).strftime('%H:%M:%S')
            bot_state.status = "POSITION_ACTIVE"

            # Check stop loss
            max_loss = bot_state.config.max_loss
            if bot_state.pnl < -max_loss:
                logger.warning(f"⚠️ Stop loss triggered! P&L: ₹{bot_state.pnl:.2f}")
                bot_state.status = "STOP_LOSS_TRIGGERED"
                execute_stop_loss()

    except Exception as e:
        logger.error(f"Monitor error: {e}")


def execute_stop_loss():
    """Emergency exit on stop loss."""
    try:
        result = bot_state.strategy.exit_position()
        if result['success']:
            bot_state.pnl = result.get('realized_pnl', bot_state.pnl)
            bot_state.positions = []
            bot_state.exit_done = True
            bot_state.status = "STOPPED_OUT"

            msg = (
                f"🚨 *STOP LOSS HIT*\n"
                f"Realized P&L: ₹{bot_state.pnl:.2f}\n"
                f"Max Loss Limit: ₹{bot_state.config.max_loss}"
            )
            logger.warning(msg.replace('*', ''))
            if bot_state.telegram and bot_state.telegram.enabled:
                bot_state.telegram.send(msg)

    except Exception as e:
        logger.error(f"❌ Stop loss exit failed: {e}")


# ── Scheduler ────────────────────────────────────────────────────
def run_scheduler():
    """Run the trading scheduler."""
    logger.info("📋 Scheduler started")

    # Run every minute
    schedule.every(1).minutes.do(reset_daily_flags)
    schedule.every(1).minutes.do(execute_entry)
    schedule.every(1).minutes.do(execute_exit)
    schedule.every(30).seconds.do(monitor_positions)

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(5)


# ── Main Entry Point ─────────────────────────────────────────────
def main():
    logger.info("Starting Nifty Options Trading Bot...")

    # Initialize bot
    if not initialize_bot():
        logger.error("Bot initialization failed. Starting dashboard only.")
        bot_state.status = "INIT_FAILED"

    # Start Flask dashboard in background thread
    app = create_app(bot_state)
    port = int(os.environ.get('PORT', 5000))

    flask_thread = Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True
    )
    flask_thread.start()
    logger.info(f"🌐 Dashboard running on port {port}")

    # Start scheduler on main thread
    run_scheduler()


if __name__ == '__main__':
    main()
