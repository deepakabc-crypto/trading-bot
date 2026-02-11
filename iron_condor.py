"""
Iron Condor Strategy for Nifty Options
Sells OTM Call + OTM Put, Buys further OTM Call + Put for protection.

Structure:
  - Sell CE at (Spot + ce_sell_offset)
  - Buy CE at (Spot + ce_buy_offset)     ← protection
  - Sell PE at (Spot - pe_sell_offset)
  - Buy PE at (Spot - pe_buy_offset)      ← protection

Max Profit = Net premium collected
Max Loss = Width of spread - Net premium
"""

import logging
import time
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)
IST = pytz.timezone('Asia/Kolkata')


class IronCondorStrategy:
    def __init__(self, breeze, config):
        self.breeze = breeze
        self.config = config
        self.active_legs = []
        self.entry_premiums = {}
        self.total_premium_collected = 0
        self.spot_at_entry = 0

    def enter_position(self):
        """Enter Iron Condor position."""
        try:
            # Get current Nifty spot
            spot = self.breeze.get_nifty_spot()
            self.spot_at_entry = spot
            logger.info(f"Nifty Spot: {spot}")

            expiry = self.breeze.get_nearest_expiry()
            qty = self.config.lot_size * self.config.nifty_lot_qty
            logger.info(f"Expiry: {expiry} | Lots: {self.config.lot_size} | Qty: {qty}")

            # Calculate strikes (rounded to nearest 50)
            ce_sell_strike = self.breeze.round_to_strike(spot + self.config.ce_sell_offset)
            ce_buy_strike = self.breeze.round_to_strike(spot + self.config.ce_buy_offset)
            pe_sell_strike = self.breeze.round_to_strike(spot - self.config.pe_sell_offset)
            pe_buy_strike = self.breeze.round_to_strike(spot - self.config.pe_buy_offset)

            logger.info(f"CE Sell: {ce_sell_strike} | CE Buy: {ce_buy_strike}")
            logger.info(f"PE Sell: {pe_sell_strike} | PE Buy: {pe_buy_strike}")

            # Check premiums before entry
            ce_sell_premium = self.breeze.get_option_ltp(ce_sell_strike, 'call', expiry)
            pe_sell_premium = self.breeze.get_option_ltp(pe_sell_strike, 'put', expiry)

            logger.info(f"CE Sell Premium: ₹{ce_sell_premium} | PE Sell Premium: ₹{pe_sell_premium}")

            if ce_sell_premium < self.config.min_premium:
                return {
                    'success': False,
                    'error': f"CE premium ₹{ce_sell_premium} below min ₹{self.config.min_premium}"
                }
            if pe_sell_premium < self.config.min_premium:
                return {
                    'success': False,
                    'error': f"PE premium ₹{pe_sell_premium} below min ₹{self.config.min_premium}"
                }

            # ── Place all 4 legs ──────────────────────────
            trades = []
            all_success = True

            # Leg 1: Sell OTM Call
            logger.info(f"Placing Leg 1: SELL {ce_sell_strike} CE")
            r1 = self.breeze.place_order(ce_sell_strike, 'call', 'sell', qty, expiry)
            time.sleep(1)
            trades.append({**r1, 'leg': 'CE_SELL', 'strike': ce_sell_strike})
            if not r1['success']:
                all_success = False

            # Leg 2: Buy OTM Call (protection)
            logger.info(f"Placing Leg 2: BUY {ce_buy_strike} CE")
            r2 = self.breeze.place_order(ce_buy_strike, 'call', 'buy', qty, expiry)
            time.sleep(1)
            trades.append({**r2, 'leg': 'CE_BUY', 'strike': ce_buy_strike})
            if not r2['success']:
                all_success = False

            # Leg 3: Sell OTM Put
            logger.info(f"Placing Leg 3: SELL {pe_sell_strike} PE")
            r3 = self.breeze.place_order(pe_sell_strike, 'put', 'sell', qty, expiry)
            time.sleep(1)
            trades.append({**r3, 'leg': 'PE_SELL', 'strike': pe_sell_strike})
            if not r3['success']:
                all_success = False

            # Leg 4: Buy OTM Put (protection)
            logger.info(f"Placing Leg 4: BUY {pe_buy_strike} PE")
            r4 = self.breeze.place_order(pe_buy_strike, 'put', 'buy', qty, expiry)
            time.sleep(1)
            trades.append({**r4, 'leg': 'PE_BUY', 'strike': pe_buy_strike})
            if not r4['success']:
                all_success = False

            # Get buy premiums for net calculation
            ce_buy_premium = self.breeze.get_option_ltp(ce_buy_strike, 'call', expiry)
            pe_buy_premium = self.breeze.get_option_ltp(pe_buy_strike, 'put', expiry)

            net_premium = (ce_sell_premium + pe_sell_premium - ce_buy_premium - pe_buy_premium)
            self.total_premium_collected = net_premium * qty

            # Store active legs
            self.active_legs = [
                {'strike': ce_sell_strike, 'type': 'call', 'action': 'sell', 'premium': ce_sell_premium},
                {'strike': ce_buy_strike, 'type': 'call', 'action': 'buy', 'premium': ce_buy_premium},
                {'strike': pe_sell_strike, 'type': 'put', 'action': 'sell', 'premium': pe_sell_premium},
                {'strike': pe_buy_strike, 'type': 'put', 'action': 'buy', 'premium': pe_buy_premium},
            ]

            self.entry_premiums = {
                'ce_sell': ce_sell_premium,
                'ce_buy': ce_buy_premium,
                'pe_sell': pe_sell_premium,
                'pe_buy': pe_buy_premium,
                'net': net_premium
            }

            if not all_success:
                failed = [t for t in trades if not t.get('success')]
                logger.warning(f"⚠️ {len(failed)} leg(s) failed. Manual check needed.")

            positions = [
                f"SELL {ce_sell_strike}CE @₹{ce_sell_premium}",
                f"BUY  {ce_buy_strike}CE @₹{ce_buy_premium}",
                f"SELL {pe_sell_strike}PE @₹{pe_sell_premium}",
                f"BUY  {pe_buy_strike}PE @₹{pe_buy_premium}",
            ]

            return {
                'success': all_success,
                'positions': positions,
                'trades': trades,
                'spot_price': spot,
                'ce_sell_strike': ce_sell_strike,
                'ce_buy_strike': ce_buy_strike,
                'pe_sell_strike': pe_sell_strike,
                'pe_buy_strike': pe_buy_strike,
                'total_premium': self.total_premium_collected,
                'net_premium_per_unit': net_premium
            }

        except Exception as e:
            logger.error(f"Iron Condor entry error: {e}")
            return {'success': False, 'error': str(e)}

    def exit_position(self):
        """Exit all Iron Condor legs."""
        try:
            if not self.active_legs:
                return {'success': True, 'realized_pnl': 0, 'message': 'No active legs'}

            expiry = self.breeze.get_nearest_expiry()
            qty = self.config.lot_size * self.config.nifty_lot_qty
            trades = []
            total_exit_cost = 0

            for leg in self.active_legs:
                # Reverse the action
                exit_action = 'buy' if leg['action'] == 'sell' else 'sell'
                current_premium = self.breeze.get_option_ltp(leg['strike'], leg['type'], expiry)

                logger.info(f"Exiting: {exit_action.upper()} {leg['strike']}{leg['type'][0].upper()}E @₹{current_premium}")

                result = self.breeze.place_order(
                    leg['strike'], leg['type'], exit_action, qty, expiry
                )
                time.sleep(1)

                trades.append({
                    **result,
                    'leg': f"{leg['type'].upper()}_{exit_action.upper()}",
                    'strike': leg['strike'],
                    'premium': current_premium
                })

                # Calculate P&L contribution
                if leg['action'] == 'sell':
                    # Sold at entry, buying back now
                    total_exit_cost += current_premium * qty
                else:
                    # Bought at entry, selling now
                    total_exit_cost -= current_premium * qty

            realized_pnl = self.total_premium_collected - total_exit_cost
            self.active_legs = []

            return {
                'success': True,
                'realized_pnl': realized_pnl,
                'trades': trades
            }

        except Exception as e:
            logger.error(f"Iron Condor exit error: {e}")
            return {'success': False, 'error': str(e)}

    def get_live_pnl(self):
        """Calculate live P&L for active position."""
        try:
            if not self.active_legs:
                return {'success': True, 'pnl': 0, 'positions': []}

            expiry = self.breeze.get_nearest_expiry()
            qty = self.config.lot_size * self.config.nifty_lot_qty
            current_cost = 0
            positions = []

            for leg in self.active_legs:
                current_ltp = self.breeze.get_option_ltp(leg['strike'], leg['type'], expiry)
                entry_premium = leg['premium']

                if leg['action'] == 'sell':
                    leg_pnl = (entry_premium - current_ltp) * qty
                else:
                    leg_pnl = (current_ltp - entry_premium) * qty

                positions.append(
                    f"{'SELL' if leg['action'] == 'sell' else 'BUY '} "
                    f"{leg['strike']}{leg['type'][0].upper()}E "
                    f"Entry:₹{entry_premium:.1f} "
                    f"LTP:₹{current_ltp:.1f} "
                    f"P&L:₹{leg_pnl:.0f}"
                )
                current_cost += leg_pnl

            return {
                'success': True,
                'pnl': current_cost,
                'positions': positions
            }

        except Exception as e:
            logger.error(f"Live P&L error: {e}")
            return {'success': False, 'pnl': 0, 'error': str(e)}
