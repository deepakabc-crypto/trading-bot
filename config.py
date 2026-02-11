"""
Trading Bot Configuration
All configurable parameters for Iron Condor strategy.
"""

import os


class Config:
    def __init__(self):
        # ── Breeze API ───────────────────────────────────
        self.api_key = os.environ.get('BREEZE_API_KEY', '')
        self.api_secret = os.environ.get('BREEZE_API_SECRET', '')
        self.session_token = os.environ.get('BREEZE_SESSION_TOKEN', '')

        # ── Telegram ─────────────────────────────────────
        self.telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')

        # ── Trading Parameters ───────────────────────────
        self.lot_size = int(os.environ.get('LOT_SIZE', '1'))          # 1-10 lots
        self.nifty_lot_qty = 25                                        # Nifty lot quantity

        # ── Iron Condor Settings ─────────────────────────
        self.ce_sell_offset = int(os.environ.get('CE_SELL_OFFSET', '200'))    # Points above spot
        self.ce_buy_offset = int(os.environ.get('CE_BUY_OFFSET', '400'))      # Points above spot
        self.pe_sell_offset = int(os.environ.get('PE_SELL_OFFSET', '200'))     # Points below spot
        self.pe_buy_offset = int(os.environ.get('PE_BUY_OFFSET', '400'))      # Points below spot
        self.min_premium = float(os.environ.get('MIN_PREMIUM', '20'))          # Min premium ₹20

        # ── Entry/Exit Times (IST) ───────────────────────
        self.entry_hour = int(os.environ.get('ENTRY_HOUR', '9'))
        self.entry_minute = int(os.environ.get('ENTRY_MINUTE', '20'))
        self.exit_hour = int(os.environ.get('EXIT_HOUR', '15'))
        self.exit_minute = int(os.environ.get('EXIT_MINUTE', '15'))

        # ── Risk Management ──────────────────────────────
        self.max_loss = float(os.environ.get('MAX_LOSS', '5000'))             # Max loss in ₹
        self.target_profit = float(os.environ.get('TARGET_PROFIT', '3000'))   # Target profit ₹

        # ── Expiry ───────────────────────────────────────
        self.expiry_type = os.environ.get('EXPIRY_TYPE', 'weekly')            # weekly/monthly

    def to_dict(self):
        return {
            "lot_size": self.lot_size,
            "nifty_lot_qty": self.nifty_lot_qty,
            "ce_sell_offset": self.ce_sell_offset,
            "ce_buy_offset": self.ce_buy_offset,
            "pe_sell_offset": self.pe_sell_offset,
            "pe_buy_offset": self.pe_buy_offset,
            "min_premium": self.min_premium,
            "entry_time": f"{self.entry_hour:02d}:{self.entry_minute:02d}",
            "exit_time": f"{self.exit_hour:02d}:{self.exit_minute:02d}",
            "max_loss": self.max_loss,
            "target_profit": self.target_profit,
            "expiry_type": self.expiry_type
        }

    def update(self, params: dict):
        """Update config from dashboard form."""
        if 'lot_size' in params:
            self.lot_size = max(1, min(10, int(params['lot_size'])))
        if 'ce_sell_offset' in params:
            self.ce_sell_offset = int(params['ce_sell_offset'])
        if 'ce_buy_offset' in params:
            self.ce_buy_offset = int(params['ce_buy_offset'])
        if 'pe_sell_offset' in params:
            self.pe_sell_offset = int(params['pe_sell_offset'])
        if 'pe_buy_offset' in params:
            self.pe_buy_offset = int(params['pe_buy_offset'])
        if 'min_premium' in params:
            self.min_premium = float(params['min_premium'])
        if 'entry_hour' in params:
            self.entry_hour = int(params['entry_hour'])
        if 'entry_minute' in params:
            self.entry_minute = int(params['entry_minute'])
        if 'exit_hour' in params:
            self.exit_hour = int(params['exit_hour'])
        if 'exit_minute' in params:
            self.exit_minute = int(params['exit_minute'])
        if 'max_loss' in params:
            self.max_loss = float(params['max_loss'])
        if 'target_profit' in params:
            self.target_profit = float(params['target_profit'])
