"""
ICICI Breeze API Client Wrapper
Handles connection, order placement, and data retrieval.
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
RETRY_DELAY = 2  # seconds


class BreezeClient:
    def __init__(self):
        self.api_key = os.environ.get('BREEZE_API_KEY', '')
        self.api_secret = os.environ.get('BREEZE_API_SECRET', '')
        self.session_token = os.environ.get('BREEZE_SESSION_TOKEN', '')
        self.breeze = None
        self.connected = False

    def connect(self):
        """Connect to Breeze API."""
        if not all([self.api_key, self.api_secret, self.session_token]):
            raise ValueError("Missing Breeze API credentials in environment variables")

        self.breeze = BreezeConnect(api_key=self.api_key)
        self.breeze.generate_session(
            api_secret=self.api_secret,
            session_token=self.session_token
        )
        self.connected = True
        logger.info("Breeze API session generated successfully")

    def _retry(self, func, *args, **kwargs):
        """Execute function with retry logic for rate limiting."""
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                result = func(*args, **kwargs)
                return result
            except Exception as e:
                error_str = str(e).lower()
                if 'rate' in error_str or 'limit' in error_str or 'throttl' in error_str:
                    wait = RETRY_DELAY * attempt
                    logger.warning(f"Rate limited, retry {attempt}/{MAX_RETRIES} in {wait}s")
                    time.sleep(wait)
                else:
                    raise
        raise Exception(f"Failed after {MAX_RETRIES} retries")

    @staticmethod
    def format_date(dt=None):
        """Format date as DD-Mon-YYYY for Breeze API."""
        if dt is None:
            dt = datetime.now(IST)
        return dt.strftime('%d-%b-%Y')  # e.g., 11-Feb-2026

    @staticmethod
    def get_nearest_expiry():
        """Get nearest weekly expiry (Thursday)."""
        now = datetime.now(IST)
        days_ahead = 3 - now.weekday()  # Thursday = 3
        if days_ahead < 0:
            days_ahead += 7
        if days_ahead == 0 and now.hour >= 15:
            days_ahead = 7
        expiry = now + timedelta(days=days_ahead)
        return expiry.strftime('%d-%b-%Y')

    @staticmethod
    def round_to_strike(price, step=50):
        """Round price to nearest strike price."""
        return round(price / step) * step

    def get_nifty_spot(self):
        """Get current Nifty spot price."""
        try:
            quotes = self._retry(
                self.breeze.get_quotes,
                stock_code="NIFTY",
                exchange_code="NSE",
                product_type="cash"
            )
            if quotes and 'Success' in quotes:
                data = quotes['Success']
                if isinstance(data, list) and len(data) > 0:
                    ltp = float(data[0].get('ltp', 0))
                    if ltp > 0:
                        return ltp

            # Fallback: try index quote
            quotes = self._retry(
                self.breeze.get_quotes,
                stock_code="NIFTY 50",
                exchange_code="NSE",
                product_type="cash"
            )
            if quotes and 'Success' in quotes:
                data = quotes['Success']
                if isinstance(data, list) and len(data) > 0:
                    return float(data[0].get('ltp', 0))

            raise ValueError("Could not fetch Nifty spot price")

        except Exception as e:
            logger.error(f"Error fetching Nifty spot: {e}")
            raise

    def get_option_ltp(self, strike, option_type, expiry=None):
        """
        Get LTP for a specific option.
        option_type: 'call' or 'put'
        """
        if expiry is None:
            expiry = self.get_nearest_expiry()

        right = "call" if option_type.lower() in ['call', 'ce'] else "put"

        try:
            quotes = self._retry(
                self.breeze.get_quotes,
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date=expiry,
                strike_price=str(strike),
                right=right
            )
            if quotes and 'Success' in quotes:
                data = quotes['Success']
                if isinstance(data, list) and len(data) > 0:
                    return float(data[0].get('ltp', 0))
            return 0
        except Exception as e:
            logger.error(f"Error fetching option LTP {strike} {right}: {e}")
            return 0

    def place_order(self, strike, option_type, action, quantity, expiry=None):
        """
        Place an option order.
        action: 'buy' or 'sell'
        """
        if expiry is None:
            expiry = self.get_nearest_expiry()

        right = "call" if option_type.lower() in ['call', 'ce'] else "put"
        transaction = "buy" if action.lower() == 'buy' else "sell"

        try:
            order = self._retry(
                self.breeze.place_order,
                stock_code="NIFTY",
                exchange_code="NFO",
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
                strike_price=str(strike)
            )

            if order and 'Success' in order:
                order_id = order['Success'].get('order_id', 'N/A')
                logger.info(f"Order placed: {action} {quantity} {strike}{right[0].upper()}E @ market | ID: {order_id}")
                return {
                    'success': True,
                    'order_id': order_id,
                    'strike': strike,
                    'type': right,
                    'action': transaction,
                    'quantity': quantity
                }
            else:
                error = order.get('Error', 'Unknown') if order else 'No response'
                logger.error(f"Order failed: {error}")
                return {'success': False, 'error': str(error)}

        except Exception as e:
            logger.error(f"Order exception: {e}")
            return {'success': False, 'error': str(e)}

    def get_positions(self):
        """Get current positions."""
        try:
            positions = self._retry(self.breeze.get_portfolio_positions)
            if positions and 'Success' in positions:
                return positions['Success'] if isinstance(positions['Success'], list) else []
            return []
        except Exception as e:
            logger.error(f"Error fetching positions: {e}")
            return []
