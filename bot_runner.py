#!/usr/bin/env python3
"""
Nifty + Sensex Options Trading Bot – Iron Condor
Platform  : Railway.app
API       : ICICI Breeze
Indices   : NIFTY (65/lot, NFO) + SENSEX (20/lot, BFO)
Version   : 3.2

Features:
  - Start / Stop bot from dashboard
  - Update Breeze session token without redeploy
  - Per-index enable/disable, config, emergency exit
"""

import os
import sys
import time
import logging
import schedule
import pytz
from datetime import datetime
from threading import Thread

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('bot.log', mode='a'),
    ],
)
logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

from breeze_client import BreezeClient
from iron_condor import IronCondorStrategy
from telegram_alerts import TelegramAlert
from dashboard import create_app
from bot_config import Config


# ── Per-index runtime state ──────────────────────────────────────
class IndexState:
    def __init__(self, name):
        self.name = name
        self.strategy = None
        self.positions = []
        self.trades_today = []
        self.pnl = 0.0
        self.status = "INITIALIZED"
        self.last_update = None
        self.entry_done = False
        self.exit_done = False

    def to_dict(self):
        return {
            "name": self.name,
            "positions": self.positions,
            "trades_today": self.trades_today,
            "pnl": self.pnl,
            "status": self.status,
            "last_update": self.last_update,
            "entry_done": self.entry_done,
            "exit_done": self.exit_done,
        }


# ── Global bot state ────────────────────────────────────────────
class BotState:
    def __init__(self):
        self.is_running = False           # ← controls whether scheduler trades
        self.is_connected = False         # ← Breeze API connected
        self.config = Config()
        self.breeze = None
        self.telegram = None
        self.index_states = {}
        self.bot_start_time = None
        self.last_token_update = None

        for name in self.config.indices:
            self.index_states[name] = IndexState(name)

    @property
    def combined_pnl(self):
        return sum(s.pnl for s in self.index_states.values())

    def to_dict(self):
        return {
            "is_running": self.is_running,
            "is_connected": self.is_connected,
            "combined_pnl": self.combined_pnl,
            "config": self.config.to_dict(),
            "indices": {k: v.to_dict() for k, v in self.index_states.items()},
            "bot_start_time": self.bot_start_time,
            "last_token_update": self.last_token_update,
            "token_preview": self._token_preview(),
        }

    def _token_preview(self):
        """Show first/last 4 chars of token for verification."""
        t = self.config.session_token
        if len(t) > 10:
            return f"{t[:4]}...{t[-4:]}"
        return "(not set)" if not t else "****"


bot_state = BotState()


# ── Initialize / Connect ────────────────────────────────────────
def connect_breeze():
    """Connect to Breeze API (or reconnect with new token)."""
    try:
        if bot_state.breeze is None:
            bot_state.breeze = BreezeClient()

        # Sync token from config
        bot_state.breeze.api_key = bot_state.config.api_key
        bot_state.breeze.api_secret = bot_state.config.api_secret
        bot_state.breeze.session_token = bot_state.config.session_token

        bot_state.breeze.connect()
        bot_state.is_connected = True
        logger.info("✅ Breeze API connected")
        return True
    except Exception as e:
        bot_state.is_connected = False
        logger.error(f"❌ Breeze connection failed: {e}")
        return False


def init_strategies():
    """Initialize strategies for enabled indices."""
    for name, idx_cfg in bot_state.config.indices.items():
        st = bot_state.index_states[name]
        if idx_cfg.enabled:
            st.strategy = IronCondorStrategy(breeze=bot_state.breeze, index_cfg=idx_cfg)
            st.status = "READY"
            logger.info(f"✅ {name} IC initialized (lot={idx_cfg.lot_qty})")
        else:
            st.strategy = None
            st.status = "DISABLED"
            logger.info(f"⏸️  {name} disabled")


def start_bot():
    """Start the trading bot."""
    logger.info("=" * 60)
    logger.info("  MULTI-INDEX OPTIONS BOT v3.2 – STARTING")
    logger.info("  NIFTY (65/lot · NFO) + SENSEX (20/lot · BFO)")
    logger.info("=" * 60)

    if not connect_breeze():
        return False, "Breeze API connection failed – check token and credentials"

    init_strategies()

    # Telegram
    if bot_state.telegram is None:
        bot_state.telegram = TelegramAlert()

    bot_state.is_running = True
    bot_state.bot_start_time = datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S')

    if bot_state.telegram.enabled:
        enabled = [n for n, c in bot_state.config.indices.items() if c.enabled]
        bot_state.telegram.send(
            f"▶️ *Bot Started*\n"
            f"Indices: {', '.join(enabled)}\n"
            f"Strategy: Iron Condor\n"
            f"NIFTY lot: 65 | SENSEX lot: 20"
        )

    logger.info("▶️ Bot is RUNNING")
    return True, "Bot started successfully"


def stop_bot(exit_positions=False):
    """
    Stop the trading bot.
    If exit_positions=True, close all open positions first.
    """
    logger.info("⏹️ Stopping bot...")

    if exit_positions:
        for name, st in bot_state.index_states.items():
            if st.strategy and st.entry_done and not st.exit_done:
                try:
                    result = st.strategy.exit_position()
                    st.exit_done = True
                    st.positions = []
                    st.pnl = result.get('realized_pnl', st.pnl)
                    st.status = "STOPPED_EXITED"
                    logger.info(f"[{name}] Positions closed on stop – P&L: ₹{st.pnl:.2f}")
                except Exception as e:
                    logger.error(f"[{name}] Exit on stop failed: {e}")

    bot_state.is_running = False

    for st in bot_state.index_states.values():
        if st.status not in ("STOPPED_EXITED", "DISABLED"):
            st.status = "STOPPED"

    if bot_state.telegram and bot_state.telegram.enabled:
        total = bot_state.combined_pnl
        bot_state.telegram.send(
            f"⏹️ *Bot Stopped*\n"
            f"Positions {'closed' if exit_positions else 'kept open'}\n"
            f"Combined P&L: ₹{total:.2f}"
        )

    logger.info("⏹️ Bot is STOPPED")
    return True, "Bot stopped"


def update_session_token(new_token):
    """Update Breeze session token and reconnect."""
    if not new_token or len(new_token) < 5:
        return False, "Invalid token"

    old_running = bot_state.is_running

    try:
        # Update config
        bot_state.config.session_token = new_token

        # Reconnect
        if bot_state.breeze is None:
            bot_state.breeze = BreezeClient()

        bot_state.breeze.update_token(new_token)
        bot_state.is_connected = True
        bot_state.last_token_update = datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S')

        # Re-init strategies with new connection
        init_strategies()

        if bot_state.telegram and bot_state.telegram.enabled:
            bot_state.telegram.send(
                f"🔑 *Session Token Updated*\n"
                f"Connected: ✅\n"
                f"Time: {bot_state.last_token_update}"
            )

        logger.info(f"✅ Token updated and reconnected at {bot_state.last_token_update}")
        return True, "Token updated – API reconnected"

    except Exception as e:
        bot_state.is_connected = False
        logger.error(f"❌ Token update failed: {e}")
        return False, f"Token update failed: {e}"


# ── Market hours ─────────────────────────────────────────────────
def check_market_hours():
    now = datetime.now(IST)
    if now.weekday() >= 5:
        return False
    mkt_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    mkt_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return mkt_open <= now <= mkt_close


# ── Daily reset ──────────────────────────────────────────────────
def reset_daily_flags():
    if not bot_state.is_running:
        return
    now = datetime.now(IST)
    if now.hour == 9 and now.minute == 0:
        for st in bot_state.index_states.values():
            st.entry_done = False
            st.exit_done = False
            st.trades_today = []
            st.pnl = 0.0
            if st.strategy:
                st.status = "READY"
        logger.info("📅 Daily flags reset")
        if bot_state.telegram and bot_state.telegram.enabled:
            bot_state.telegram.send(
                f"📅 *New Trading Day*\nDate: {now.strftime('%d-%b-%Y')}\nIndices: NIFTY + SENSEX"
            )


# ── Entry ────────────────────────────────────────────────────────
def _enter_index(name):
    st = bot_state.index_states[name]
    cfg = bot_state.config.indices[name]

    if not cfg.enabled or st.entry_done or not st.strategy:
        return

    st.status = "ENTERING_POSITION"
    logger.info(f"🚀 [{name}] Entering Iron Condor...")

    try:
        result = st.strategy.enter_position()
        if result['success']:
            st.positions = result['positions']
            st.trades_today.extend(result['trades'])
            st.entry_done = True
            st.status = "POSITION_ACTIVE"
            msg = (
                f"✅ *{name} Iron Condor Entered*\n"
                f"Spot: {result.get('spot_price', 'N/A')}\n"
                f"CE Sell: {result.get('ce_sell_strike')} | CE Buy: {result.get('ce_buy_strike')}\n"
                f"PE Sell: {result.get('pe_sell_strike')} | PE Buy: {result.get('pe_buy_strike')}\n"
                f"Lots: {cfg.lot_size} × {cfg.lot_qty} = {cfg.lot_size * cfg.lot_qty}\n"
                f"Premium: ₹{result.get('total_premium', 0):.2f}"
            )
            logger.info(msg.replace('*', ''))
            if bot_state.telegram and bot_state.telegram.enabled:
                bot_state.telegram.send(msg)
        else:
            st.status = f"ENTRY_FAILED: {result.get('error', 'Unknown')}"
            logger.error(f"[{name}] Entry failed: {result.get('error')}")
            if bot_state.telegram and bot_state.telegram.enabled:
                bot_state.telegram.send(f"❌ *{name} Entry Failed*\n{result.get('error')}")
    except Exception as e:
        st.status = f"ENTRY_ERROR: {e}"
        logger.error(f"[{name}] Entry exception: {e}")


def execute_entries():
    if not bot_state.is_running or not bot_state.is_connected or not check_market_hours():
        return
    now = datetime.now(IST)
    if now.hour == bot_state.config.entry_hour and now.minute == bot_state.config.entry_minute:
        for name in bot_state.index_states:
            _enter_index(name)


# ── Exit ─────────────────────────────────────────────────────────
def _exit_index(name):
    st = bot_state.index_states[name]
    cfg = bot_state.config.indices[name]

    if not cfg.enabled or st.exit_done or not st.entry_done or not st.strategy:
        return

    st.status = "EXITING_POSITION"
    logger.info(f"🛑 [{name}] Exiting Iron Condor...")

    try:
        result = st.strategy.exit_position()
        if result['success']:
            st.pnl = result.get('realized_pnl', 0)
            st.positions = []
            st.exit_done = True
            st.status = "POSITION_CLOSED"
            msg = (
                f"🛑 *{name} Iron Condor Exited*\n"
                f"Realized P&L: ₹{st.pnl:.2f}\nExit: Scheduled"
            )
            logger.info(msg.replace('*', ''))
            if bot_state.telegram and bot_state.telegram.enabled:
                bot_state.telegram.send(msg)
        else:
            logger.error(f"[{name}] Exit failed: {result.get('error')}")
    except Exception as e:
        logger.error(f"[{name}] Exit exception: {e}")


def execute_exits():
    if not bot_state.is_running or not bot_state.is_connected:
        return
    now = datetime.now(IST)
    if now.hour == bot_state.config.exit_hour and now.minute == bot_state.config.exit_minute:
        for name in bot_state.index_states:
            _exit_index(name)


# ── Stop loss ────────────────────────────────────────────────────
def _stop_loss_index(name):
    st = bot_state.index_states[name]
    cfg = bot_state.config.indices[name]
    try:
        result = st.strategy.exit_position()
        if result['success']:
            st.pnl = result.get('realized_pnl', st.pnl)
            st.positions = []
            st.exit_done = True
            st.status = "STOPPED_OUT"
            msg = f"🚨 *{name} STOP LOSS HIT*\nP&L: ₹{st.pnl:.2f}\nLimit: ₹{cfg.max_loss}"
            logger.warning(msg.replace('*', ''))
            if bot_state.telegram and bot_state.telegram.enabled:
                bot_state.telegram.send(msg)
    except Exception as e:
        logger.error(f"[{name}] Stop loss exit failed: {e}")


# ── Monitor ──────────────────────────────────────────────────────
def monitor_positions():
    if not bot_state.is_running or not bot_state.is_connected or not check_market_hours():
        return

    for name, st in bot_state.index_states.items():
        cfg = bot_state.config.indices[name]
        if not cfg.enabled or not st.entry_done or st.exit_done or not st.strategy:
            continue
        try:
            result = st.strategy.get_live_pnl()
            if result['success']:
                st.pnl = result['pnl']
                st.positions = result.get('positions', st.positions)
                st.last_update = datetime.now(IST).strftime('%H:%M:%S')
                st.status = "POSITION_ACTIVE"
                if st.pnl < -cfg.max_loss:
                    logger.warning(f"[{name}] SL triggered! P&L: ₹{st.pnl:.2f}")
                    _stop_loss_index(name)
        except Exception as e:
            logger.error(f"[{name}] Monitor error: {e}")


# ── EOD summary ──────────────────────────────────────────────────
def send_eod_summary():
    if not bot_state.is_running:
        return
    now = datetime.now(IST)
    if now.hour == 15 and now.minute == 35 and now.weekday() < 5:
        lines = ["📊 *End-of-Day Summary*\n"]
        total = 0.0
        for name, st in bot_state.index_states.items():
            emoji = "🟢" if st.pnl >= 0 else "🔴"
            lines.append(f"{emoji} {name}: ₹{st.pnl:,.2f}")
            total += st.pnl
        emoji_t = "🟢" if total >= 0 else "🔴"
        lines.append(f"\n{emoji_t} *Combined: ₹{total:,.2f}*")
        if bot_state.telegram and bot_state.telegram.enabled:
            bot_state.telegram.send('\n'.join(lines))
        logger.info(f"EOD Summary – Combined P&L: ₹{total:.2f}")


# ── Scheduler ────────────────────────────────────────────────────
def run_scheduler():
    logger.info("📋 Scheduler started (trading controlled by Start/Stop)")
    schedule.every(1).minutes.do(reset_daily_flags)
    schedule.every(1).minutes.do(execute_entries)
    schedule.every(1).minutes.do(execute_exits)
    schedule.every(1).minutes.do(send_eod_summary)
    schedule.every(30).seconds.do(monitor_positions)

    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(5)


# ── Main ─────────────────────────────────────────────────────────
def main():
    logger.info("Starting Multi-Index Options Trading Bot...")

    # Initialize Telegram early so dashboard can send alerts
    bot_state.telegram = TelegramAlert()

    # Try initial connection (bot remains STOPPED until user clicks Start)
    if bot_state.config.session_token:
        try:
            connect_breeze()
            init_strategies()
            logger.info("✅ Pre-connected to Breeze (bot is STOPPED – click Start on dashboard)")
        except Exception as e:
            logger.warning(f"⚠️ Pre-connection failed: {e} – update token from dashboard")
    else:
        logger.info("⚠️ No session token – set token from dashboard")

    # Flask dashboard
    app = create_app(bot_state, start_bot, stop_bot, update_session_token)
    port = int(os.environ.get('PORT', 5000))
    flask_thread = Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()
    logger.info(f"🌐 Dashboard on port {port}")

    # Scheduler (always runs, but trading only when is_running=True)
    run_scheduler()


if __name__ == '__main__':
    main()
