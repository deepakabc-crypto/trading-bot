"""
🧪 Nifty Options Backtesting Engine
====================================
Backtest Iron Condor & Short Straddle strategies using ICICI Breeze historical data.

Setup:
    1. Edit settings.py with your API credentials & strategy parameters
    2. pip install breeze-connect pandas

Usage:
    python backtest.py --strategy iron_condor --days 180
    python backtest.py --strategy short_straddle --days 90
    python backtest.py --strategy both --days 365
    python backtest.py --simulate --days 60  # No API credentials needed

Configuration:
    All settings are in settings.py — API keys, strategy params, capital, costs.
"""

import json
import csv
import argparse
import logging
from datetime import datetime, timedelta, time as dtime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Tuple
from pathlib import Path

import settings

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("backtest")

# ---------------------------------------------------------------------------
# Try importing Breeze SDK
# ---------------------------------------------------------------------------
try:
    from breeze_connect import BreezeConnect
    BREEZE_AVAILABLE = True
except ImportError:
    BREEZE_AVAILABLE = False
    log.warning("breeze_connect not installed. Install via: pip install breeze-connect")

try:
    import pandas as pd
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    log.warning("pandas not installed. Install via: pip install pandas")


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class OptionLeg:
    """Single option leg in a strategy."""
    strike: float
    option_type: str          # "CE" or "PE"
    action: str               # "sell" or "buy"
    premium_entry: float = 0.0
    premium_exit: float = 0.0
    lots: int = 1
    lot_size: int = 65

    @property
    def quantity(self) -> int:
        return self.lots * self.lot_size

    @property
    def pnl(self) -> float:
        multiplier = 1 if self.action == "sell" else -1
        return multiplier * (self.premium_entry - self.premium_exit) * self.quantity


@dataclass
class Trade:
    """A complete trade with all legs."""
    trade_id: int
    strategy: str
    entry_date: str
    exit_date: str
    expiry: str
    nifty_spot: float
    legs: List[dict]
    gross_pnl: float
    slippage_cost: float
    brokerage: float
    net_pnl: float
    exit_reason: str          # "target" | "stoploss" | "expiry" | "eod"
    capital: float
    return_pct: float


@dataclass
class BacktestResult:
    """Aggregated backtest results."""
    strategy: str
    period: str
    initial_capital: float
    final_capital: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_pnl: float
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: float
    avg_profit: float
    avg_loss: float
    profit_factor: float
    best_trade: float
    worst_trade: float
    avg_trade_pnl: float
    total_return_pct: float


# ============================================================================
# BREEZE DATA FETCHER
# ============================================================================

class BreezeDataFetcher:
    """Fetch historical option chain data from ICICI Breeze API."""

    def __init__(self, api_key: str, api_secret: str, session_token: str):
        if not BREEZE_AVAILABLE:
            raise ImportError("breeze_connect is required. pip install breeze-connect")
        self.breeze = BreezeConnect(api_key=api_key)
        self.breeze.generate_session(api_secret=api_secret, session_token=session_token)
        log.info("✅ Connected to ICICI Breeze API")

    def get_historical_data(
        self,
        strike: float,
        option_type: str,
        expiry_date: str,
        from_date: str,
        to_date: str,
        interval: str = "1minute",
    ) -> list:
        """
        Fetch historical OHLCV data for a specific option contract using v1 API.
        """
        try:
            data = self.breeze.get_historical_data(
                interval=interval,
                from_date=f"{from_date}T07:00:00.000Z",
                to_date=f"{to_date}T16:00:00.000Z",
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date=f"{expiry_date}T07:00:00.000Z",
                right=option_type,
                strike_price=str(int(strike)),
            )
            if data and data.get("Success") and len(data["Success"]) > 0:
                return data["Success"]
            log.debug(f"No data for NIFTY {strike}{option_type} exp={expiry_date}")
            return []
        except Exception as e:
            log.error(f"Breeze API error for {strike}{option_type}: {e}")
            return []

    def get_spot_price(self, date: str) -> Optional[float]:
        """Fetch Nifty spot closing price using v1 API."""
        for days_back in range(0, 4):
            check_date = (datetime.strptime(date, "%Y-%m-%d") - timedelta(days=days_back)).strftime("%Y-%m-%d")
            try:
                data = self.breeze.get_historical_data(
                    interval="1day",
                    from_date=f"{check_date}T07:00:00.000Z",
                    to_date=f"{check_date}T16:00:00.000Z",
                    stock_code="NIFTY",
                    exchange_code="NSE",
                )
                if data and data.get("Success") and len(data["Success"]) > 0:
                    spot = float(data["Success"][0]["close"])
                    log.debug(f"Spot {date} = {spot} (from {check_date})")
                    return spot
            except Exception as e:
                log.debug(f"Spot fetch failed for {check_date}: {e}")
                continue

        log.warning(f"Could not fetch spot data for {date}")
        return None

    def get_expiry_dates(self, from_date: str, to_date: str) -> list:
        """Get list of weekly/monthly expiry dates in the range."""
        try:
            data = self.breeze.get_option_chain_quotes(
                stock_code="NIFTY",
                exchange_code="NFO",
                product_type="options",
                expiry_date=from_date,
            )
            # Fallback: generate Thursdays as approximate expiry dates
        except Exception:
            pass
        return self._generate_expiry_thursdays(from_date, to_date)

    @staticmethod
    def _generate_expiry_thursdays(from_date: str, to_date: str) -> List[str]:
        """Generate Thursday expiry dates (standard NSE weekly expiry)."""
        start = datetime.strptime(from_date, "%Y-%m-%d")
        end = datetime.strptime(to_date, "%Y-%m-%d")
        expiries = []
        current = start
        while current <= end:
            # Thursday = weekday 3
            days_until_thu = (3 - current.weekday()) % 7
            thursday = current + timedelta(days=days_until_thu)
            if start <= thursday <= end:
                expiries.append(thursday.strftime("%Y-%m-%d"))
            current = thursday + timedelta(days=1)
        return sorted(set(expiries))


# ============================================================================
# SIMULATED DATA FETCHER (for testing without Breeze credentials)
# ============================================================================

class SimulatedDataFetcher:
    """
    Generate realistic simulated option data for backtesting
    when Breeze API credentials are not available.
    """

    def __init__(self):
        import random
        self.rng = random.Random(42)
        self._spot_cache: Dict[str, float] = {}
        log.info("📊 Using simulated data (no Breeze credentials)")

    def get_spot_price(self, date: str) -> float:
        if date in self._spot_cache:
            return self._spot_cache[date]
        # Random walk around 22000
        if self._spot_cache:
            last = list(self._spot_cache.values())[-1]
            change = self.rng.gauss(0, 80)
            spot = round(last + change, 2)
        else:
            spot = round(self.rng.gauss(22000, 500), 2)
        self._spot_cache[date] = spot
        return spot

    def simulate_option_premium(
        self,
        spot: float,
        strike: float,
        option_type: str,
        dte: int,
    ) -> float:
        """Estimate option premium using simplified Black-Scholes-like model."""
        import math
        intrinsic = max(0, spot - strike) if option_type == "CE" else max(0, strike - spot)
        distance = abs(spot - strike)
        iv = 0.13 + self.rng.uniform(-0.02, 0.02)
        time_value = spot * iv * math.sqrt(max(dte, 0.5) / 365) * math.exp(-distance / (spot * 0.1))
        premium = intrinsic + time_value
        return round(max(premium, 1.0), 2)

    def simulate_intraday_movement(
        self,
        entry_premium: float,
        spot: float,
        strike: float,
        option_type: str,
    ) -> List[float]:
        """Simulate minute-by-minute premium path for the trading day."""
        prices = [entry_premium]
        current = entry_premium
        for _ in range(375):  # ~6.25 hours of trading
            change_pct = self.rng.gauss(0, 0.003)
            current = max(0.5, current * (1 + change_pct))
            prices.append(round(current, 2))
        return prices

    def get_expiry_dates(self, from_date: str, to_date: str) -> List[str]:
        return BreezeDataFetcher._generate_expiry_thursdays(from_date, to_date)


# ============================================================================
# STRATEGY ENGINE
# ============================================================================

class StrategyEngine:
    """Core strategy logic for Iron Condor and Short Straddle."""

    # Settings loaded from settings.py
    IC_CONFIG = {
        "lot_size": settings.IC_LOT_SIZE,
        "lots": settings.IC_LOTS,
        "sell_offset": settings.IC_SELL_OFFSET,
        "buy_offset": settings.IC_BUY_OFFSET,
        "target_pct": settings.IC_TARGET_PCT,
        "stoploss_pct": settings.IC_STOPLOSS_PCT,
    }

    SS_CONFIG = {
        "lot_size": settings.SS_LOT_SIZE,
        "lots": settings.SS_LOTS,
        "target_pct": settings.SS_TARGET_PCT,
        "stoploss_pct": settings.SS_STOPLOSS_PCT,
    }

    SLIPPAGE_PER_LOT = settings.SLIPPAGE_PER_LOT
    BROKERAGE_PER_ORDER = settings.BROKERAGE_PER_ORDER

    @staticmethod
    def round_strike(spot: float, base: int = 50) -> float:
        """Round spot to nearest strike price."""
        return round(spot / base) * base

    @classmethod
    def build_iron_condor(cls, spot: float, fetcher, expiry: str, dte: int) -> List[OptionLeg]:
        """Build Iron Condor legs around ATM."""
        cfg = cls.IC_CONFIG
        atm = cls.round_strike(spot)

        legs = [
            OptionLeg(atm + cfg["sell_offset"], "CE", "sell", lots=cfg["lots"], lot_size=cfg["lot_size"]),
            OptionLeg(atm + cfg["buy_offset"], "CE", "buy",  lots=cfg["lots"], lot_size=cfg["lot_size"]),
            OptionLeg(atm - cfg["sell_offset"], "PE", "sell", lots=cfg["lots"], lot_size=cfg["lot_size"]),
            OptionLeg(atm - cfg["buy_offset"], "PE", "buy",  lots=cfg["lots"], lot_size=cfg["lot_size"]),
        ]

        for leg in legs:
            if isinstance(fetcher, SimulatedDataFetcher):
                leg.premium_entry = fetcher.simulate_option_premium(spot, leg.strike, leg.option_type, dte)
            else:
                data = fetcher.get_historical_data(
                    leg.strike, "call" if leg.option_type == "CE" else "put",
                    expiry, expiry, expiry, interval="1minute",
                )
                if data:
                    leg.premium_entry = float(data[0].get("open", 0))
        return legs

    @classmethod
    def build_short_straddle(cls, spot: float, fetcher, expiry: str, dte: int) -> List[OptionLeg]:
        """Build Short Straddle at ATM."""
        cfg = cls.SS_CONFIG
        atm = cls.round_strike(spot)

        legs = [
            OptionLeg(atm, "CE", "sell", lots=cfg["lots"], lot_size=cfg["lot_size"]),
            OptionLeg(atm, "PE", "sell", lots=cfg["lots"], lot_size=cfg["lot_size"]),
        ]

        for leg in legs:
            if isinstance(fetcher, SimulatedDataFetcher):
                leg.premium_entry = fetcher.simulate_option_premium(spot, leg.strike, leg.option_type, dte)
            else:
                data = fetcher.get_historical_data(
                    leg.strike, "call" if leg.option_type == "CE" else "put",
                    expiry, expiry, expiry, interval="1minute",
                )
                if data:
                    leg.premium_entry = float(data[0].get("open", 0))
        return legs

    @classmethod
    def simulate_trade(
        cls,
        strategy: str,
        legs: List[OptionLeg],
        fetcher,
        spot: float,
        expiry: str,
    ) -> Tuple[str, List[OptionLeg]]:
        """
        Simulate intraday P&L and determine exit based on target/stoploss.
        Returns (exit_reason, updated_legs).
        """
        cfg = cls.IC_CONFIG if strategy == "iron_condor" else cls.SS_CONFIG
        target_pct = cfg["target_pct"]
        stoploss_pct = cfg["stoploss_pct"]

        total_credit = sum(
            leg.premium_entry * leg.quantity for leg in legs if leg.action == "sell"
        )
        total_debit = sum(
            leg.premium_entry * leg.quantity for leg in legs if leg.action == "buy"
        )
        net_credit = total_credit - total_debit

        if isinstance(fetcher, SimulatedDataFetcher):
            # Simulate minute-by-minute
            paths = {}
            for leg in legs:
                paths[id(leg)] = fetcher.simulate_intraday_movement(
                    leg.premium_entry, spot, leg.strike, leg.option_type
                )

            for minute in range(375):
                current_credit = 0
                current_debit = 0
                for leg in legs:
                    price = paths[id(leg)][minute]
                    if leg.action == "sell":
                        current_credit += price * leg.quantity
                    else:
                        current_debit += price * leg.quantity

                current_value = current_credit - current_debit
                unrealised_pnl = net_credit - current_value

                # Check target
                if unrealised_pnl >= net_credit * target_pct:
                    for leg in legs:
                        leg.premium_exit = paths[id(leg)][minute]
                    return "target", legs

                # Check stoploss
                if unrealised_pnl <= -net_credit * stoploss_pct:
                    for leg in legs:
                        leg.premium_exit = paths[id(leg)][minute]
                    return "stoploss", legs

            # EOD exit at last price
            for leg in legs:
                leg.premium_exit = paths[id(leg)][-1]
            return "eod", legs

        else:
            # Use real Breeze data
            for leg in legs:
                data = fetcher.get_historical_data(
                    leg.strike, "call" if leg.option_type == "CE" else "put",
                    expiry, expiry, expiry, interval="1minute",
                )
                if data:
                    leg.premium_exit = float(data[-1].get("close", leg.premium_entry))
                else:
                    leg.premium_exit = leg.premium_entry
            return "eod", legs


# ============================================================================
# BACKTESTER
# ============================================================================

class Backtester:
    """Main backtesting engine."""

    def __init__(
        self,
        fetcher,
        strategy: str,
        capital: float = 500_000,
        from_date: str = "2024-01-01",
        to_date: str = "2024-12-31",
    ):
        self.fetcher = fetcher
        self.strategy = strategy
        self.capital = capital
        self.initial_capital = capital
        self.from_date = from_date
        self.to_date = to_date
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = [capital]

    def run(self) -> BacktestResult:
        """Execute the backtest over the date range."""
        log.info(f"{'='*60}")
        log.info(f"🚀 Backtesting: {self.strategy.upper()}")
        log.info(f"📅 Period: {self.from_date} → {self.to_date}")
        log.info(f"💰 Capital: ₹{self.capital:,.0f}")
        log.info(f"{'='*60}")

        expiries = self.fetcher.get_expiry_dates(self.from_date, self.to_date)
        log.info(f"📆 Found {len(expiries)} expiry dates")

        trade_id = 0
        skipped = 0
        for i, expiry in enumerate(expiries):
            expiry_dt = datetime.strptime(expiry, "%Y-%m-%d")

            # Entry: 1 day before expiry or same day for weeklies
            entry_date = expiry  # Same-day entry for simplicity
            spot = self.fetcher.get_spot_price(entry_date)
            if spot is None:
                skipped += 1
                log.warning(f"  ⚠️ Skipping {entry_date} — could not fetch spot price")
                continue

            dte = max((expiry_dt - datetime.strptime(entry_date, "%Y-%m-%d")).days, 0)

            # Build legs
            if self.strategy == "iron_condor":
                legs = StrategyEngine.build_iron_condor(spot, self.fetcher, expiry, dte)
            else:
                legs = StrategyEngine.build_short_straddle(spot, self.fetcher, expiry, dte)

            if not legs or all(l.premium_entry == 0 for l in legs):
                log.warning(f"  ⚠️ Skipping {expiry} — no premium data")
                continue

            # Simulate trade
            exit_reason, legs = StrategyEngine.simulate_trade(
                self.strategy, legs, self.fetcher, spot, expiry
            )

            # Calculate P&L
            gross_pnl = sum(leg.pnl for leg in legs)
            num_orders = len(legs) * 2  # entry + exit
            slippage = StrategyEngine.SLIPPAGE_PER_LOT * legs[0].lot_size * len(legs)
            brokerage = StrategyEngine.BROKERAGE_PER_ORDER * num_orders
            net_pnl = gross_pnl - slippage - brokerage

            self.capital += net_pnl
            self.equity_curve.append(self.capital)

            trade_id += 1
            trade = Trade(
                trade_id=trade_id,
                strategy=self.strategy,
                entry_date=entry_date,
                exit_date=expiry,
                expiry=expiry,
                nifty_spot=spot,
                legs=[
                    {
                        "strike": l.strike,
                        "type": l.option_type,
                        "action": l.action,
                        "entry": l.premium_entry,
                        "exit": l.premium_exit,
                        "pnl": round(l.pnl, 2),
                    }
                    for l in legs
                ],
                gross_pnl=round(gross_pnl, 2),
                slippage_cost=round(slippage, 2),
                brokerage=round(brokerage, 2),
                net_pnl=round(net_pnl, 2),
                exit_reason=exit_reason,
                capital=round(self.capital, 2),
                return_pct=round((net_pnl / self.initial_capital) * 100, 4),
            )
            self.trades.append(trade)

            icon = "✅" if net_pnl > 0 else "❌"
            log.info(
                f"  {icon} #{trade_id:>3} | {entry_date} | Spot: {spot:>8.1f} | "
                f"P&L: ₹{net_pnl:>+10,.2f} | Exit: {exit_reason:<8} | "
                f"Capital: ₹{self.capital:>12,.2f}"
            )

        if skipped > 0:
            log.warning(f"⚠️ Skipped {skipped}/{len(expiries)} expiries due to missing data")
        if trade_id == 0:
            log.error("❌ No trades executed. Check your API connection or use --simulate for simulated data.")

        return self._compute_results()

    def _compute_results(self) -> BacktestResult:
        """Compute aggregate performance metrics."""
        if not self.trades:
            return BacktestResult(
                strategy=self.strategy, period=f"{self.from_date} to {self.to_date}",
                initial_capital=self.initial_capital, final_capital=self.capital,
                total_trades=0, winning_trades=0, losing_trades=0, win_rate=0,
                total_pnl=0, max_drawdown=0, max_drawdown_pct=0, sharpe_ratio=0,
                avg_profit=0, avg_loss=0, profit_factor=0, best_trade=0,
                worst_trade=0, avg_trade_pnl=0, total_return_pct=0,
            )

        pnls = [t.net_pnl for t in self.trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        # Max drawdown
        peak = self.equity_curve[0]
        max_dd = 0
        for equity in self.equity_curve:
            peak = max(peak, equity)
            dd = peak - equity
            max_dd = max(max_dd, dd)

        # Sharpe ratio (annualized, assuming weekly trades)
        import statistics
        avg_ret = statistics.mean(pnls) if pnls else 0
        std_ret = statistics.stdev(pnls) if len(pnls) > 1 else 1
        sharpe = (avg_ret / std_ret) * (52 ** 0.5) if std_ret > 0 else 0

        total_profit = sum(wins)
        total_loss = abs(sum(losses))
        profit_factor = total_profit / total_loss if total_loss > 0 else float("inf")

        return BacktestResult(
            strategy=self.strategy,
            period=f"{self.from_date} to {self.to_date}",
            initial_capital=self.initial_capital,
            final_capital=round(self.capital, 2),
            total_trades=len(pnls),
            winning_trades=len(wins),
            losing_trades=len(losses),
            win_rate=round(len(wins) / len(pnls) * 100, 2),
            total_pnl=round(sum(pnls), 2),
            max_drawdown=round(max_dd, 2),
            max_drawdown_pct=round((max_dd / self.initial_capital) * 100, 2),
            sharpe_ratio=round(sharpe, 2),
            avg_profit=round(statistics.mean(wins), 2) if wins else 0,
            avg_loss=round(statistics.mean(losses), 2) if losses else 0,
            profit_factor=round(profit_factor, 2),
            best_trade=round(max(pnls), 2),
            worst_trade=round(min(pnls), 2),
            avg_trade_pnl=round(avg_ret, 2),
            total_return_pct=round(((self.capital - self.initial_capital) / self.initial_capital) * 100, 2),
        )


# ============================================================================
# TRADE HISTORY LOGGER
# ============================================================================

class TradeHistoryLogger:
    """Persist trade history to CSV and JSON files."""

    OUTPUT_DIR = Path("trade_history")

    def __init__(self, strategy: str):
        self.strategy = strategy
        self.OUTPUT_DIR.mkdir(exist_ok=True)

    def save_trades_csv(self, trades: List[Trade]) -> str:
        """Save trade log to CSV."""
        filename = self.OUTPUT_DIR / f"trades_{self.strategy}_{datetime.now():%Y%m%d_%H%M%S}.csv"
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "Trade#", "Strategy", "Entry Date", "Exit Date", "Expiry",
                "Spot", "Gross P&L", "Slippage", "Brokerage", "Net P&L",
                "Exit Reason", "Capital", "Return%", "Legs",
            ])
            for t in trades:
                writer.writerow([
                    t.trade_id, t.strategy, t.entry_date, t.exit_date, t.expiry,
                    t.nifty_spot, t.gross_pnl, t.slippage_cost, t.brokerage,
                    t.net_pnl, t.exit_reason, t.capital, t.return_pct,
                    json.dumps(t.legs),
                ])
        log.info(f"💾 Trades saved to {filename}")
        return str(filename)

    def save_trades_json(self, trades: List[Trade]) -> str:
        """Save full trade history to JSON."""
        filename = self.OUTPUT_DIR / f"trades_{self.strategy}_{datetime.now():%Y%m%d_%H%M%S}.json"
        records = []
        for t in trades:
            records.append({
                "trade_id": t.trade_id,
                "strategy": t.strategy,
                "entry_date": t.entry_date,
                "exit_date": t.exit_date,
                "expiry": t.expiry,
                "nifty_spot": t.nifty_spot,
                "legs": t.legs,
                "gross_pnl": t.gross_pnl,
                "slippage_cost": t.slippage_cost,
                "brokerage": t.brokerage,
                "net_pnl": t.net_pnl,
                "exit_reason": t.exit_reason,
                "capital": t.capital,
                "return_pct": t.return_pct,
            })
        with open(filename, "w") as f:
            json.dump(records, f, indent=2)
        log.info(f"💾 Trade history saved to {filename}")
        return str(filename)

    def save_equity_curve(self, equity_curve: List[float]) -> str:
        """Save equity curve data."""
        filename = self.OUTPUT_DIR / f"equity_{self.strategy}_{datetime.now():%Y%m%d_%H%M%S}.csv"
        with open(filename, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Index", "Capital"])
            for i, val in enumerate(equity_curve):
                writer.writerow([i, round(val, 2)])
        log.info(f"📈 Equity curve saved to {filename}")
        return str(filename)


# ============================================================================
# REPORT PRINTER
# ============================================================================

def print_report(result: BacktestResult):
    """Print a formatted backtest report to console."""
    print(f"\n{'='*60}")
    print(f"  📊 BACKTEST REPORT — {result.strategy.upper()}")
    print(f"{'='*60}")
    print(f"  Period            : {result.period}")
    print(f"  Initial Capital   : ₹{result.initial_capital:>12,.2f}")
    print(f"  Final Capital     : ₹{result.final_capital:>12,.2f}")
    print(f"  Total Return      : {result.total_return_pct:>+.2f}%")
    print(f"  Total P&L         : ₹{result.total_pnl:>+12,.2f}")
    print(f"{'─'*60}")
    print(f"  Total Trades      : {result.total_trades}")
    print(f"  Winners           : {result.winning_trades}  ({result.win_rate}%)")
    print(f"  Losers            : {result.losing_trades}")
    print(f"{'─'*60}")
    print(f"  Avg Profit/Trade  : ₹{result.avg_profit:>+12,.2f}")
    print(f"  Avg Loss/Trade    : ₹{result.avg_loss:>+12,.2f}")
    print(f"  Best Trade        : ₹{result.best_trade:>+12,.2f}")
    print(f"  Worst Trade       : ₹{result.worst_trade:>+12,.2f}")
    print(f"  Avg Trade P&L     : ₹{result.avg_trade_pnl:>+12,.2f}")
    print(f"{'─'*60}")
    print(f"  Profit Factor     : {result.profit_factor}")
    print(f"  Sharpe Ratio      : {result.sharpe_ratio}")
    print(f"  Max Drawdown      : ₹{result.max_drawdown:>12,.2f}  ({result.max_drawdown_pct}%)")
    print(f"{'='*60}\n")


# ============================================================================
# MAIN
# ============================================================================

def main():
    parser = argparse.ArgumentParser(description="Nifty Options Backtester")
    parser.add_argument("--strategy", choices=["iron_condor", "short_straddle", "both"],
                        default=settings.STRATEGY, help="Strategy to backtest")
    parser.add_argument("--days", type=int, default=90, help="Number of days to backtest (from today backwards)")
    parser.add_argument("--capital", type=float, default=settings.CAPITAL,
                        help="Initial capital (₹)")
    parser.add_argument("--simulate", action="store_true", help="Use simulated data (no API needed)")
    args = parser.parse_args()

    to_date = datetime.now().strftime("%Y-%m-%d")
    from_date = (datetime.now() - timedelta(days=args.days)).strftime("%Y-%m-%d")

    # Initialize data fetcher
    api_key = settings.API_KEY
    api_secret = settings.API_SECRET
    session_token = settings.SESSION_TOKEN

    has_credentials = (
        api_key and api_key != "your_api_key_here"
        and api_secret and api_secret != "your_api_secret_here"
        and session_token and session_token != "your_session_token_here"
    )

    if not args.simulate and has_credentials:
        try:
            fetcher = BreezeDataFetcher(api_key, api_secret, session_token)
            log.info("🔗 Data source: ICICI Breeze API (live)")
        except Exception as e:
            log.warning(f"⚠️ Breeze connection failed: {e}. Falling back to simulation.")
            fetcher = SimulatedDataFetcher()
    else:
        if not args.simulate:
            log.info("ℹ️  No API credentials found. Use --simulate or update settings.py")
        fetcher = SimulatedDataFetcher()
        log.info("🔗 Data source: Simulated")

    strategies = (
        ["iron_condor", "short_straddle"] if args.strategy == "both"
        else [args.strategy]
    )

    for strat in strategies:
        bt = Backtester(
            fetcher=fetcher,
            strategy=strat,
            capital=args.capital,
            from_date=from_date,
            to_date=to_date,
        )
        result = bt.run()
        print_report(result)

        # Save trade history
        logger = TradeHistoryLogger(strat)
        logger.save_trades_csv(bt.trades)
        logger.save_trades_json(bt.trades)
        logger.save_equity_curve(bt.equity_curve)


if __name__ == "__main__":
    main()
