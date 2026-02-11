"""
Iron Condor Strategy – Generic Multi-Index
Works with any IndexConfig (NIFTY / SENSEX).

Structure (for each index):
  Sell CE at Spot + ce_sell_offset
  Buy  CE at Spot + ce_buy_offset   (protection)
  Sell PE at Spot - pe_sell_offset
  Buy  PE at Spot - pe_buy_offset   (protection)
"""

import logging
import time
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')


class IronCondorStrategy:
    def __init__(self, breeze, index_cfg):
        """
        breeze    : BreezeClient instance
        index_cfg : IndexConfig for the specific index
        """
        self.breeze = breeze
        self.cfg = index_cfg
        self.active_legs = []
        self.entry_premiums = {}
        self.total_premium_collected = 0.0
        self.spot_at_entry = 0.0

    @property
    def label(self):
        return f"{self.cfg.name} IC"

    # ── Entry ────────────────────────────────────────────

    def enter_position(self):
        try:
            spot = self.breeze.get_spot_price(self.cfg)
            self.spot_at_entry = spot
            logger.info(f"[{self.cfg.name}] Spot: {spot}")

            expiry = self.breeze.get_nearest_expiry(self.cfg.name)
            qty = self.cfg.lot_size * self.cfg.lot_qty
            step = self.cfg.strike_step

            logger.info(
                f"[{self.cfg.name}] Expiry: {expiry} | "
                f"Lots: {self.cfg.lot_size} | Qty: {qty} | "
                f"Lot size: {self.cfg.lot_qty}"
            )

            # Calculate strikes
            ce_sell = self.breeze.round_to_strike(spot + self.cfg.ce_sell_offset, step)
            ce_buy = self.breeze.round_to_strike(spot + self.cfg.ce_buy_offset, step)
            pe_sell = self.breeze.round_to_strike(spot - self.cfg.pe_sell_offset, step)
            pe_buy = self.breeze.round_to_strike(spot - self.cfg.pe_buy_offset, step)

            logger.info(f"[{self.cfg.name}] CE Sell:{ce_sell} CE Buy:{ce_buy} PE Sell:{pe_sell} PE Buy:{pe_buy}")

            # Check premiums
            ce_sell_prem = self.breeze.get_option_ltp(self.cfg, ce_sell, 'call', expiry)
            pe_sell_prem = self.breeze.get_option_ltp(self.cfg, pe_sell, 'put', expiry)

            logger.info(f"[{self.cfg.name}] CE Sell Prem: ₹{ce_sell_prem} | PE Sell Prem: ₹{pe_sell_prem}")

            min_p = self.cfg.min_premium
            if ce_sell_prem < min_p:
                return {'success': False, 'error': f"{self.cfg.name} CE premium ₹{ce_sell_prem} < min ₹{min_p}"}
            if pe_sell_prem < min_p:
                return {'success': False, 'error': f"{self.cfg.name} PE premium ₹{pe_sell_prem} < min ₹{min_p}"}

            # ── Place 4 legs ────────────────────────────
            trades = []
            all_ok = True
            order_delay = 1  # seconds between orders

            legs_to_place = [
                ('CE_SELL', ce_sell, 'call', 'sell'),
                ('CE_BUY',  ce_buy,  'call', 'buy'),
                ('PE_SELL', pe_sell, 'put',  'sell'),
                ('PE_BUY',  pe_buy,  'put',  'buy'),
            ]

            for leg_name, strike, opt_type, action in legs_to_place:
                logger.info(f"[{self.cfg.name}] Leg {leg_name}: {action.upper()} {strike} {opt_type.upper()}")
                r = self.breeze.place_order(self.cfg, strike, opt_type, action, qty, expiry)
                time.sleep(order_delay)
                trades.append({**r, 'leg': leg_name, 'strike': strike})
                if not r.get('success'):
                    all_ok = False

            # Get buy premiums for net calculation
            ce_buy_prem = self.breeze.get_option_ltp(self.cfg, ce_buy, 'call', expiry)
            pe_buy_prem = self.breeze.get_option_ltp(self.cfg, pe_buy, 'put', expiry)

            net_prem = ce_sell_prem + pe_sell_prem - ce_buy_prem - pe_buy_prem
            self.total_premium_collected = net_prem * qty

            self.active_legs = [
                {'strike': ce_sell, 'type': 'call', 'action': 'sell', 'premium': ce_sell_prem},
                {'strike': ce_buy,  'type': 'call', 'action': 'buy',  'premium': ce_buy_prem},
                {'strike': pe_sell, 'type': 'put',  'action': 'sell', 'premium': pe_sell_prem},
                {'strike': pe_buy,  'type': 'put',  'action': 'buy',  'premium': pe_buy_prem},
            ]

            self.entry_premiums = {
                'ce_sell': ce_sell_prem, 'ce_buy': ce_buy_prem,
                'pe_sell': pe_sell_prem, 'pe_buy': pe_buy_prem,
                'net': net_prem,
            }

            if not all_ok:
                failed = [t for t in trades if not t.get('success')]
                logger.warning(f"[{self.cfg.name}] ⚠️ {len(failed)} leg(s) failed – manual check needed")

            positions = [
                f"SELL {ce_sell}CE @₹{ce_sell_prem}",
                f"BUY  {ce_buy}CE @₹{ce_buy_prem}",
                f"SELL {pe_sell}PE @₹{pe_sell_prem}",
                f"BUY  {pe_buy}PE @₹{pe_buy_prem}",
            ]

            return {
                'success': all_ok,
                'positions': positions,
                'trades': trades,
                'spot_price': spot,
                'ce_sell_strike': ce_sell,
                'ce_buy_strike': ce_buy,
                'pe_sell_strike': pe_sell,
                'pe_buy_strike': pe_buy,
                'total_premium': self.total_premium_collected,
                'net_premium_per_unit': net_prem,
            }

        except Exception as e:
            logger.error(f"[{self.cfg.name}] IC entry error: {e}")
            return {'success': False, 'error': str(e)}

    # ── Exit ─────────────────────────────────────────────

    def exit_position(self):
        try:
            if not self.active_legs:
                return {'success': True, 'realized_pnl': 0, 'message': 'No active legs'}

            expiry = self.breeze.get_nearest_expiry(self.cfg.name)
            qty = self.cfg.lot_size * self.cfg.lot_qty
            trades = []
            exit_cost = 0.0

            for leg in self.active_legs:
                exit_action = 'buy' if leg['action'] == 'sell' else 'sell'
                current = self.breeze.get_option_ltp(self.cfg, leg['strike'], leg['type'], expiry)

                logger.info(
                    f"[{self.cfg.name}] Exit: {exit_action.upper()} "
                    f"{leg['strike']}{leg['type'][0].upper()}E @₹{current}"
                )
                result = self.breeze.place_order(
                    self.cfg, leg['strike'], leg['type'], exit_action, qty, expiry
                )
                time.sleep(1)
                trades.append({**result, 'leg': f"{leg['type'].upper()}_{exit_action.upper()}",
                               'strike': leg['strike'], 'premium': current})

                if leg['action'] == 'sell':
                    exit_cost += current * qty
                else:
                    exit_cost -= current * qty

            realized_pnl = self.total_premium_collected - exit_cost
            self.active_legs = []
            return {'success': True, 'realized_pnl': realized_pnl, 'trades': trades}

        except Exception as e:
            logger.error(f"[{self.cfg.name}] IC exit error: {e}")
            return {'success': False, 'error': str(e)}

    # ── Live P&L ─────────────────────────────────────────

    def get_live_pnl(self):
        try:
            if not self.active_legs:
                return {'success': True, 'pnl': 0.0, 'positions': []}

            expiry = self.breeze.get_nearest_expiry(self.cfg.name)
            qty = self.cfg.lot_size * self.cfg.lot_qty
            total_pnl = 0.0
            positions = []

            for leg in self.active_legs:
                ltp = self.breeze.get_option_ltp(self.cfg, leg['strike'], leg['type'], expiry)
                entry = leg['premium']
                if leg['action'] == 'sell':
                    leg_pnl = (entry - ltp) * qty
                else:
                    leg_pnl = (ltp - entry) * qty

                positions.append(
                    f"{'SELL' if leg['action'] == 'sell' else 'BUY '} "
                    f"{leg['strike']}{leg['type'][0].upper()}E "
                    f"Entry:₹{entry:.1f} LTP:₹{ltp:.1f} P&L:₹{leg_pnl:.0f}"
                )
                total_pnl += leg_pnl

            return {'success': True, 'pnl': total_pnl, 'positions': positions}

        except Exception as e:
            logger.error(f"[{self.cfg.name}] Live P&L error: {e}")
            return {'success': False, 'pnl': 0.0, 'error': str(e)}
