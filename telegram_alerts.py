"""
Telegram Alert System
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
        if not self.enabled:
            return False
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True,
            }
            resp = requests.post(url, json=payload, timeout=10)
            if resp.status_code == 200:
                return True
            if 'parse' in resp.text.lower():
                payload['parse_mode'] = None
                retry = requests.post(url, json=payload, timeout=10)
                return retry.status_code == 200
            logger.warning(f"Telegram send failed: {resp.status_code}")
            return False
        except requests.exceptions.Timeout:
            logger.warning("Telegram send timed out")
            return False
        except Exception as e:
            logger.error(f"Telegram error: {e}")
            return False

    def send_pnl_update(self, index_name, pnl, status, positions=None):
        emoji = "🟢" if pnl >= 0 else "🔴"
        msg = f"{emoji} *{index_name} P&L Update*\nP&L: ₹{pnl:,.2f}\nStatus: {status}"
        if positions:
            msg += "\n\n*Positions:*\n"
            for pos in positions:
                msg += f"`{pos}`\n"
        return self.send(msg)

    def send_error(self, error_msg):
        return self.send(f"🚨 *ERROR*\n```\n{error_msg}\n```")
