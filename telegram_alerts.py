"""
Telegram Alert System
Sends trade notifications and status updates via Telegram bot.
"""

import os
import logging
import requests

logger = logging.getLogger(__name__)


class TelegramAlert:
    def __init__(self):
        self.token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID', '')
        self.enabled = bool(self.token and self.chat_id)
        self.base_url = f"https://api.telegram.org/bot{self.token}" if self.token else ""

    def send(self, message, parse_mode='Markdown'):
        """Send a message via Telegram."""
        if not self.enabled:
            logger.debug("Telegram disabled, skipping message")
            return False

        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }
            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                return True
            else:
                logger.warning(f"Telegram send failed: {response.status_code} {response.text}")
                # Retry without markdown if parse error
                if 'parse' in response.text.lower():
                    payload['parse_mode'] = None
                    retry = requests.post(url, json=payload, timeout=10)
                    return retry.status_code == 200
                return False

        except requests.exceptions.Timeout:
            logger.warning("Telegram send timed out")
            return False
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    def send_pnl_update(self, pnl, status, positions=None):
        """Send formatted P&L update."""
        emoji = "🟢" if pnl >= 0 else "🔴"
        msg = (
            f"{emoji} *P&L Update*\n"
            f"P&L: ₹{pnl:,.2f}\n"
            f"Status: {status}"
        )
        if positions:
            msg += "\n\n*Positions:*\n"
            for pos in positions:
                msg += f"`{pos}`\n"

        return self.send(msg)

    def send_error(self, error_msg):
        """Send error alert."""
        return self.send(f"🚨 *ERROR*\n```\n{error_msg}\n```")
        
