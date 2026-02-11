"""
ICICI Breeze API Client Wrapper
Multi-index: NIFTY (NFO) + SENSEX (BFO)
Supports session token refresh without restart.
"""

import os
import time
import logging
import pytz
from datetime import datetime, timedelta
from breeze_connect import BreezeConnect

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')

MAX_RETRIES = 3
RETRY_DELAY = 2


class BreezeClient:
    def __init__(self):
        self.api_key = os.environ.get('BREEZE_API_KEY', '')
        self.api_secret = os.environ.get('BREEZE_API_SECRET', '')
        self.session_token = os.environ.get('BREEZE_SESSION_TOKEN', '')
        self.breeze = None
        self.connected = False
        self.last_connected = None

    def connect(self):
        if not all([self.api_key, self.api_secret, self.session_token]):
            raise ValueError("Missing Breeze API credentials in environment variables")
        self.breeze = BreezeConnect(api_key=self.api_key)
        self.breeze.generate_session(
            api_secret=self.api_secret,
            session_token=self.session_token,
        )
        self.connected = True
        self.last_connected = datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S')
        logger.info("Breeze API session generated successfully")

    def update_token(self, new_token):
        """
        Update session token and reconnect.
        Used when daily token expires – callable from dashboard.
        """
        old_token = self.session_token[:8] + "..." if self.session_token else "(empty)"
        self.session_token = new_token
        os.environ['BREEZE_SESSION_TOKEN'] = new_token
        logger.info(f"Session token updated (was {old_token})")

        # Reconnect with new token
        self.connected = False
        self.breeze = BreezeConnect(api_key=self.api_key)
        self.breeze.generate_session(
            api_secret=self.api_secret,
            session_token=self.session_token,
        )
        self.connected = True
        self.last_connected = datetime.now(IST).strftime('%d-%b-%Y %H:%M:%S')
        logger.info("✅ Breeze API reconnected with new token")

    def disconnect(self):
        """Disconnect from Breeze API."""
        self.connected = False
        self.breeze = None
        logger.info("Breeze API disconnected")

    def _retry(self, func, *args, **kwargs):
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                err = str(e).lower()
                if any(w in err for w in ('rate', 'limit', 'throttl', 'too many')):
                    wait = RETRY_DELAY * attempt
                    logger.warning(f"Rate limited – retry {attempt}/{MAX_RETRIES} in {wait}s")
                    time.sleep(wait)
                else:
                    raise
        raise Exception(f"Failed after {MAX_RETRIES} retries")

    @staticmethod
    def format_date(dt=None):
        if dt is None:
            dt = datetime.now(IST)
        return dt.strftime('%d-%b-%Y')

    @staticmethod
    def get_nearest_expiry(index_name='NIFTY'):
        now = datetime.now(IST)
        expiry_day = 3 if index_name == 'NIFTY' else 4
        days_ahead = expiry_day - now.weekday()
        if days_ahead < 0:
            days_ahead += 7
        if days_ahead == 0 and now.hour >= 15:
            days_ahead = 7
        expiry = now + timedelta(days=days_ahead)
        return expiry.strftime('%d-%b-%Y')

    @staticmethod
    def round_to_strike(price, step=50):
        return round(price / step) * step

    def get_spot_price(self, index_cfg):
        try:
            quotes = self._retry(
                self.breeze.get_quotes,
                stock_code=index_cfg.cash_code,
                exchange_code=index_cfg.cash_exchange,
                product_type="cash",
            )
            if quotes and 'Success' in quotes:
                data = quotes['Success']
                if isinstance(data, list) and len(data) > 0:
                    ltp = float(data[0].get('ltp', 0))
                    if ltp > 0:
                        return ltp

            alt_names = {
                'NIFTY': ['NIFTY 50', 'NIFTY'],
                'SENSEX': ['SENSEX', 'BSE SENSEX', 'SENSEX 30'],
            }
            for alt in alt_names.get(index_cfg.name, []):
                try:
                    quotes = self._retry(
                        self.breeze.get_quotes,
                        stock_code=alt,
                        exchange_code=index_cfg.cash_exchange,
                        product_type="cash",
                    )
                    if quotes and 'Success' in quotes:
                        data = quotes['Success']
                        if isinstance(data, list) and len(data) > 0:
                            ltp = float(data[0].get('ltp', 0))
                            if ltp > 0:
                                return ltp
                except Exception:
                    continue

            raise ValueError(f"Could not fetch {index_cfg.name} spot price")
        except Exception as e:
            logger.error(f"Error fetching {index_cfg.name} spot: {e}")
            raise

    def get_option_ltp(self, index_cfg, strike, option_type, expiry=None):
        if expiry is None:
            expiry = self.get_nearest_expiry(index_cfg.name)
        right = "call" if option_type.lower() in ('call', 'ce') else "put"
        try:
            quotes = self._retry(
                self.breeze.get_quotes,
                stock_code=index_cfg.stock_code,
                exchange_code=index_cfg.exchange,
                product_type="options",
                expiry_date=expiry,
                strike_price=str(strike),
                right=right,
            )
            if quotes and 'Success' in quotes:
                data = quotes['Success']
                if isinstance(data, list) and len(data) > 0:
                    return float(data[0].get('ltp', 0))
            return 0.0
        except Exception as e:
            logger.error(f"Option LTP error {index_cfg.name} {strike}{right[0].upper()}E: {e}")
            return 0.0

    def place_order(self, index_cfg, strike, option_type, action, quantity, expiry=None):
        if expiry is None:
            expiry = self.get_nearest_expiry(index_cfg.name)
        right = "call" if option_type.lower() in ('call', 'ce') else "put"
        transaction = "buy" if action.lower() == 'buy' else "sell"
        try:
            order = self._retry(
                self.breeze.place_order,
                stock_code=index_cfg.stock_code,
                exchange_code=index_cfg.exchange,
                product="options",
                action=transaction,
                order_type="market",
                stoploss="",
                quantity=str(quantity),
                price="",
                validity="day",
                validity_date=self.format_date(),
                disclosed_quantity="0",
                expiry_date=expiry,
                right=right,
                strike_price=str(strike),
            )
            if order and 'Success' in order:
                oid = order['Success'].get('order_id', 'N/A')
                tag = f"{index_cfg.name} {action.upper()} {quantity} {strike}{right[0].upper()}E"
                logger.info(f"✅ Order placed: {tag} | ID: {oid}")
                return {
                    'success': True, 'order_id': oid, 'strike': strike,
                    'type': right, 'action': transaction, 'quantity': quantity,
                    'index': index_cfg.name,
                }
            else:
                error = order.get('Error', 'Unknown') if order else 'No response'
                logger.error(f"Order failed: {error}")
                return {'success': False, 'error': str(error)}
        except Exception as e:
            logger.error(f"Order exception: {e}")
            return {'success': False, 'error': str(e)}

    def get_positions(self):
        try:
            positions = self._retry(self.breeze.get_portfolio_positions)
            if positions and 'Success' in positions:
                return positions['Success'] if isinstance(positions['Success'], list) else []
            return []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
