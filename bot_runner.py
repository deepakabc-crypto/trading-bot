#!/usr/bin/env python3
"""
Nifty + Sensex Options Trading Bot – Iron Condor
Platform  : Railway.app
API       : ICICI Breeze
Indices   : NIFTY (65/lot, NFO) + SENSEX (20/lot, BFO)
Strategy  : Iron Condor on both indices
Version   : 3.0
"""

import os
import sys
import time
import logging
import schedule
import pytz
from datetime import datetime
from threading import Thread

# ── Logging ──────────────────────────────────────────────────────
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

# ── Imports ──────────────────────────────────────────────────────
from breeze_client import BreezeClient
from iron_condor import IronCondorStrategy
from telegram_alerts import TelegramAlert
from dashboard import create_app
from config import Config


# ── Per-index state ──────────────────────────────────────────────
class IndexState:
    """Runtime state for one index."""

    def __init__(self, name):
        self.name = name
        self.strategy = None       # IronCondorStrategy
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
        self.is_running = False
        self.config = Config()
        self.breeze = None
        self.telegram = None
        self.index_states = {}        # name -> IndexState

        for name in self.config.indices:
            self.index_states[name] = IndexState(name)

    @property
    def combined_pnl(self):
        return sum(s.pnl for s in self.index_states.values())

    def to_dict(self):
        return {
            "is_running": self.is_running,
            "combined_pnl": self.combined_pnl,
            "config": self.config.to_dict(),
            "indices": {k: v.to_dict() for k, v in self.index_states.items()},
        }


bot_state = BotState()


# ── Initialize ───────────────────────────────────────────────────
def initialize_bot():
    logger.info("=" * 60)
    logger.info("  MULTI-INDEX OPTIONS BOT v3.0 – IRON CONDOR")
    logger.info("  NIFTY (65/lot · NFO) + SENSEX (20/lot · BFO)")
    logger.info("=" * 60)

    try:
        # Breeze
        bot_state.breeze = BreezeClient()
        bot_state.breeze.connect()
        logger.info("✅ Breeze API connected")

        # Strategies
        for name, idx_cfg in bot_state.config.indices.items():
            if idx_cfg.enabled:
                strat = IronCondorStrategy(breeze=bot_state.breeze, index_cfg=idx_cfg)
                bot_state.index_states[name].strategy = strat
                bot_state.index_states[name].status = "READY"
                logger.info(f"✅ {name} Iron Condor initialized  (lot qty={idx_cfg.lot_qty})")
            else:
                bot_state.index_states[name].status = "DISABLED"
                logger.info(f"⏸️  {name} is disabled")

        # Telegram
        bot_state.telegram = TelegramAlert()
        if bot_state.telegram.enabled:
            enabled = [n for n, c in bot_state.config.indices.items() if c.enabled]
            bot_state.telegram.send(
                f"🤖 *Bot Started*\n"
                f"Indices: {', '.join(enabled)}\n"
                f"Strategy: Iron Condor\n"
                f"NIFTY lot: 65 | SENSEX lot: 20"
            )
            logger.info("✅ Telegram alerts enabled")
        else:
            logger.warning("⚠️ Telegram disabled (no token)")

        bot_state.is_running = True
        return True

    except Exception as e:
        logger.error(f"❌ Init failed: {e}")
        return False


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
    now = datetime.now(IST)
    if now.hour == 9 and now.minute == 0:
        for st in bot_state.index_states.values():
            st.entry_done = False
            st.exit_done = False
            st.trades_today = []
            st.pnl = 0.0
            if st.strategy:
                st.status = "READY"
        logger.info("📅 Daily flags reset – all indices")
        if bot_state.telegram and bot_state.telegram.enabled:
            bot_state.telegram.send(
                f"📅 *New Trading Day*\n"
                f"Date: {now.strftime('%d-%b-%Y')}\n"
                f"Indices: NIFTY + SENSEX"
            )


# ── Entry logic (per index) ─────────────────────────────────────
def _enter_index(name):
    """Execute Iron Condor entry for one index."""
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
    if not bot_state.is_running or not check_market_hours():
        return
    now = datetime.now(IST)
    if now.hour == bot_state.config.entry_hour and now.minute == bot_state.config.entry_minute:
        for name in bot_state.index_states:
            _enter_index(name)


# ── Exit logic (per index) ──────────────────────────────────────
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
                f"Realized P&L: ₹{st.pnl:.2f}\n"
                f"Exit: Scheduled"
            )
            logger.info(msg.replace('*', ''))
            if bot_state.telegram and bot_state.telegram.enabled:
                bot_state.telegram.send(msg)
        else:
            logger.error(f"[{name}] Exit failed: {result.get('error')}")

    except Exception as e:
        logger.error(f"[{name}] Exit exception: {e}")


def execute_exits():
    if not bot_state.is_running:
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
            msg = (
                f"🚨 *{name} STOP LOSS HIT*\n"
                f"P&L: ₹{st.pnl:.2f}\n"
                f"Limit: ₹{cfg.max_loss}"
            )
            logger.warning(msg.replace('*', ''))
            if bot_state.telegram and bot_state.telegram.enabled:
                bot_state.telegram.send(msg)
    except Exception as e:
        logger.error(f"[{name}] Stop loss exit failed: {e}")


# ── Monitor ──────────────────────────────────────────────────────
def monitor_positions():
    if not bot_state.is_running or not check_market_hours():
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

                # Per-index stop loss
                if st.pnl < -cfg.max_loss:
                    logger.warning(f"[{name}] SL triggered! P&L: ₹{st.pnl:.2f}")
                    _stop_loss_index(name)

        except Exception as e:
            logger.error(f"[{name}] Monitor error: {e}")


# ── End-of-day summary ──────────────────────────────────────────
def send_eod_summary():
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
    logger.info("📋 Scheduler started")
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

    if not initialize_bot():
        logger.error("Initialization failed – starting dashboard only")

    # Flask in background
    app = create_app(bot_state)
    port = int(os.environ.get('PORT', 5000))
    flask_thread = Thread(
        target=lambda: app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    flask_thread.start()
    logger.info(f"🌐 Dashboard on port {port}")

    # Scheduler on main thread
    run_scheduler()


if __name__ == '__main__':
    main()
