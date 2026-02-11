"""
Trading Bot Configuration
Multi-Index Iron Condor: SENSEX (20/lot) + NIFTY (65/lot)

IMPORTANT: This file is named bot_config.py (NOT config.py)
to avoid collision with breeze_connect's internal config module.
"""

import os


class IndexConfig:
    """Configuration for a single index."""

    def __init__(self, name, stock_code, exchange, lot_qty, strike_step,
                 cash_code=None, defaults=None):
        self.name = name
        self.stock_code = stock_code
        self.cash_code = cash_code or stock_code
        self.exchange = exchange            # NFO for Nifty, BFO for Sensex
        self.cash_exchange = 'NSE' if exchange == 'NFO' else 'BSE'
        self.lot_qty = lot_qty
        self.strike_step = strike_step
        self.enabled = True

        d = defaults or {}
        self.lot_size = int(d.get('lot_size', 1))
        self.ce_sell_offset = int(d.get('ce_sell_offset', 200 if name == 'NIFTY' else 300))
        self.ce_buy_offset = int(d.get('ce_buy_offset', 400 if name == 'NIFTY' else 600))
        self.pe_sell_offset = int(d.get('pe_sell_offset', 200 if name == 'NIFTY' else 300))
        self.pe_buy_offset = int(d.get('pe_buy_offset', 400 if name == 'NIFTY' else 600))
        self.min_premium = float(d.get('min_premium', 20))
        self.max_loss = float(d.get('max_loss', 5000))
        self.target_profit = float(d.get('target_profit', 3000))

    def to_dict(self):
        return {
            "name": self.name,
            "stock_code": self.stock_code,
            "exchange": self.exchange,
            "lot_qty": self.lot_qty,
            "strike_step": self.strike_step,
            "enabled": self.enabled,
            "lot_size": self.lot_size,
            "ce_sell_offset": self.ce_sell_offset,
            "ce_buy_offset": self.ce_buy_offset,
            "pe_sell_offset": self.pe_sell_offset,
            "pe_buy_offset": self.pe_buy_offset,
            "min_premium": self.min_premium,
            "max_loss": self.max_loss,
            "target_profit": self.target_profit,
        }

    def update(self, params: dict):
        field_map = {
            'lot_size': ('lot_size', lambda v: max(1, min(10, int(v)))),
            'ce_sell_offset': ('ce_sell_offset', int),
            'ce_buy_offset': ('ce_buy_offset', int),
            'pe_sell_offset': ('pe_sell_offset', int),
            'pe_buy_offset': ('pe_buy_offset', int),
            'min_premium': ('min_premium', float),
            'max_loss': ('max_loss', float),
            'target_profit': ('target_profit', float),
            'enabled': ('enabled', lambda v: v in [True, 'true', '1', 'on']),
        }
        for key, (attr, converter) in field_map.items():
            if key in params:
                setattr(self, attr, converter(params[key]))


class Config:
    def __init__(self):
        # ── Breeze API ───────────────────────────────────
        self.api_key = os.environ.get('BREEZE_API_KEY', '')
        self.api_secret = os.environ.get('BREEZE_API_SECRET', '')
        self.session_token = os.environ.get('BREEZE_SESSION_TOKEN', '')

        # ── Telegram ─────────────────────────────────────
        self.telegram_token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')

        # ── Entry/Exit Times (IST) ───────────────────────
        self.entry_hour = int(os.environ.get('ENTRY_HOUR', '9'))
        self.entry_minute = int(os.environ.get('ENTRY_MINUTE', '20'))
        self.exit_hour = int(os.environ.get('EXIT_HOUR', '15'))
        self.exit_minute = int(os.environ.get('EXIT_MINUTE', '15'))

        # ── Expiry ───────────────────────────────────────
        self.expiry_type = os.environ.get('EXPIRY_TYPE', 'weekly')

        # ── Index Configurations ─────────────────────────

        # NIFTY: 65 per lot, 50-pt strikes, NFO exchange
        nifty_defaults = {
            'lot_size': int(os.environ.get('NIFTY_LOT_SIZE', '1')),
            'ce_sell_offset': int(os.environ.get('NIFTY_CE_SELL_OFFSET', '200')),
            'ce_buy_offset': int(os.environ.get('NIFTY_CE_BUY_OFFSET', '400')),
            'pe_sell_offset': int(os.environ.get('NIFTY_PE_SELL_OFFSET', '200')),
            'pe_buy_offset': int(os.environ.get('NIFTY_PE_BUY_OFFSET', '400')),
            'min_premium': float(os.environ.get('NIFTY_MIN_PREMIUM', '20')),
            'max_loss': float(os.environ.get('NIFTY_MAX_LOSS', '5000')),
            'target_profit': float(os.environ.get('NIFTY_TARGET_PROFIT', '3000')),
        }
        self.indices = {}
        self.indices['NIFTY'] = IndexConfig(
            name='NIFTY',
            stock_code='NIFTY',
            exchange='NFO',
            lot_qty=65,
            strike_step=50,
            cash_code='NIFTY',
            defaults=nifty_defaults,
        )
        self.indices['NIFTY'].enabled = os.environ.get(
            'NIFTY_ENABLED', 'true').lower() == 'true'

        # SENSEX: 20 per lot, 100-pt strikes, BFO exchange
        sensex_defaults = {
            'lot_size': int(os.environ.get('SENSEX_LOT_SIZE', '1')),
            'ce_sell_offset': int(os.environ.get('SENSEX_CE_SELL_OFFSET', '300')),
            'ce_buy_offset': int(os.environ.get('SENSEX_CE_BUY_OFFSET', '600')),
            'pe_sell_offset': int(os.environ.get('SENSEX_PE_SELL_OFFSET', '300')),
            'pe_buy_offset': int(os.environ.get('SENSEX_PE_BUY_OFFSET', '600')),
            'min_premium': float(os.environ.get('SENSEX_MIN_PREMIUM', '20')),
            'max_loss': float(os.environ.get('SENSEX_MAX_LOSS', '5000')),
            'target_profit': float(os.environ.get('SENSEX_TARGET_PROFIT', '3000')),
        }
        self.indices['SENSEX'] = IndexConfig(
            name='SENSEX',
            stock_code='SENSEX',
            exchange='BFO',
            lot_qty=20,
            strike_step=100,
            cash_code='SENSEX',
            defaults=sensex_defaults,
        )
        self.indices['SENSEX'].enabled = os.environ.get(
            'SENSEX_ENABLED', 'true').lower() == 'true'

    def to_dict(self):
        return {
            "entry_time": f"{self.entry_hour:02d}:{self.entry_minute:02d}",
            "exit_time": f"{self.exit_hour:02d}:{self.exit_minute:02d}",
            "expiry_type": self.expiry_type,
            "indices": {k: v.to_dict() for k, v in self.indices.items()},
        }

    def update_global(self, params: dict):
        if 'entry_hour' in params:
            self.entry_hour = int(params['entry_hour'])
        if 'entry_minute' in params:
            self.entry_minute = int(params['entry_minute'])
        if 'exit_hour' in params:
            self.exit_hour = int(params['exit_hour'])
        if 'exit_minute' in params:
            self.exit_minute = int(params['exit_minute'])
