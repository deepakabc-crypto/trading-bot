# 🤖 Nifty Options Trading Bot v3.0

Automated trading bot for Nifty options with Iron Condor, Short Straddle, and **Daily Scalp** strategies.

## ✨ Features

- 🦅 **Iron Condor v2.0** - VIX filter, dynamic strikes, trailing SL, per-leg adjustments
- 📊 **Short Straddle** - Higher premium, 55-60% win rate
- ⚡ **Daily Scalp (NEW)** - Intraday ATM straddle sell with strict risk management
- 🖥️ **Web Dashboard** - Real-time P&L tracking
- 📱 **Telegram Alerts** - Trade notifications & remote control
- 🔬 **Backtesting Engine** - Test strategies on historical data
- 🧺 **Basket Orders** - Multi-leg order placement with margin check & auto-rollback
- 📜 **Trade History** - Persistent trade logs
- ☁️ **Railway Ready** - One-click deploy

## 📁 Files

| File | Description |
|------|-------------|
| `app.py` | Combined dashboard + trading bot + backtester |
| `Procfile` | Railway process config (gunicorn) |
| `requirements.txt` | Python dependencies |

## ⚡ Daily Scalp Strategy (NEW in v3.0)

The Daily Scalp is an **intraday ATM straddle sell** designed for consistent daily income with strict risk management.

### How It Works

| Step | Detail |
|------|--------|
| **Entry** | SELL ATM CE + PE at 9:45 AM (after opening range settles) |
| **Target** | 25% premium decay → ~₹7-10K/day (3 lots) |
| **Stop Loss 1** | Combined premium rises 40% |
| **Stop Loss 2** | Nifty moves ±150 points from entry |
| **Trailing SL** | After 15% profit, trail 10% behind peak |
| **Hard Exit** | 2:00 PM — **NEVER holds overnight** |
| **VIX Filter** | Only trades when India VIX is 10-20 |
| **Re-entry** | No re-entry same day after SL hit |

### Daily Scalp Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `STRATEGY` | `daily_scalp` | Set to activate |
| `SCALP_NUM_LOTS` | `3` | Number of lots (3 × 75 = 225 qty) |
| `SCALP_TARGET_PERCENT` | `25` | Target profit % of premium |
| `SCALP_STOP_LOSS_PERCENT` | `40` | Max premium rise before SL |
| `SCALP_ENTRY_TIME` | `09:45` | Entry time (IST) |
| `SCALP_EXIT_TIME` | `14:00` | Hard exit time (IST) |
| `SCALP_SPOT_SL_POINTS` | `150` | Nifty ±points SL |
| `SCALP_TRAIL_ENABLED` | `true` | Enable trailing stop |
| `SCALP_TRAIL_ACTIVATE_PCT` | `15` | Activate trail after this % profit |
| `SCALP_TRAIL_OFFSET_PCT` | `10` | Trail behind peak by this % |
| `SCALP_MIN_PREMIUM` | `100` | Min combined premium to enter |
| `SCALP_MAX_VIX` | `20` | Skip if VIX above this |
| `SCALP_MIN_VIX` | `10` | Skip if VIX below this |

### Expected Performance

| Metric | Value |
|--------|-------|
| Daily Profit Target | ₹7,000 - 10,000 |
| Daily Max Loss | ₹15,000 - 25,000 |
| Win Rate | ~65-70% |
| Weekly Potential | ₹28,000 - 40,000 (4 trading days) |
| Margin Required | ~₹4-5 Lakhs |

### Risk Warnings
- **Naked selling** = unlimited theoretical risk. SL + time exit caps practical risk.
- Bot monitors every CHECK_INTERVAL seconds. Set to 30-60s for scalp.
- Never override SCALP_EXIT_TIME to hold overnight.

## 🚀 Deploy to Railway (5 minutes)

### Step 1: Create GitHub Repository
1. Create new repo on GitHub
2. Upload all files (`app.py`, `Procfile`, `requirements.txt`)

### Step 2: Deploy on Railway
1. Go to [railway.app](https://railway.app)
2. Click **"New Project"** → **"Deploy from GitHub"**
3. Select your repository

### Step 3: Add Environment Variables

#### Required Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `API_KEY` | ICICI Breeze API Key | abc123... |
| `API_SECRET` | ICICI Breeze Secret | xyz789... |
| `API_SESSION` | Breeze Session Token (daily) | abc123xyz... |

#### Required for Daily Scalp
```
STRATEGY=daily_scalp
SCALP_NUM_LOTS=3
CHECK_INTERVAL=30
```

#### Optional - Telegram

| Variable | Description | Example |
|----------|-------------|---------|
| `TELEGRAM_BOT_TOKEN` | From @BotFather | 123456:ABC... |
| `TELEGRAM_CHAT_ID` | Your chat ID | 987654321 |

#### Optional - Trading Settings

| Variable | Description | Default |
|----------|-------------|---------|
| `CAPITAL` | Trading capital | 500000 |
| `LOT_SIZE` | Nifty lot size | 75 |
| `NUM_LOTS` | Number of lots (IC/Straddle) | 1 |
| `STRATEGY` | iron_condor / straddle / daily_scalp / both | iron_condor |
| `MIN_PREMIUM` | Minimum premium to enter (IC/Straddle) | 10 |
| `AUTO_START` | Auto-start bot on deploy | true |

> **STRATEGY=both** runs Iron Condor + Daily Scalp simultaneously.

> **Note:** Total quantity = LOT_SIZE × NUM_LOTS (e.g., 75 × 2 = 150)

#### Optional - Timing (IST)

| Variable | Description | Default |
|----------|-------------|---------|
| `ENTRY_TIME_START` | Start of IC/Straddle entry window | 09:20 |
| `ENTRY_TIME_END` | End of IC/Straddle entry window | 14:00 |
| `EXIT_TIME` | Force exit IC/Straddle positions | 15:15 |
| `CHECK_INTERVAL` | Seconds between bot checks | 60 |
| `CUSTOM_EXPIRY` | Override expiry date (for holidays) | *(empty)* |

> **For Daily Scalp:** Set `CHECK_INTERVAL=30` for faster monitoring.

#### Optional - Strategy Parameters

| Variable | Description | Default |
|----------|-------------|---------|
| `IC_CALL_SELL_DISTANCE` | IC: Call sell distance from ATM | 150 |
| `IC_CALL_BUY_DISTANCE` | IC: Call buy distance from ATM | 250 |
| `IC_PUT_SELL_DISTANCE` | IC: Put sell distance from ATM | 150 |
| `IC_PUT_BUY_DISTANCE` | IC: Put buy distance from ATM | 250 |
| `IC_TARGET_PERCENT` | IC: Target profit % | 50 |
| `IC_STOP_LOSS_PERCENT` | IC: Stop loss % | 100 |
| `STR_TARGET_PERCENT` | Straddle: Target profit % | 30 |
| `STR_STOP_LOSS_PERCENT` | Straddle: Stop loss % | 20 |

#### Optional - Iron Condor v2.0 Improvements

| Variable | Description | Default |
|----------|-------------|---------|
| `IC_VIX_MAX` | Skip entry if VIX > this | 16 |
| `IC_VIX_MIN` | Skip entry if VIX < this | 9 |
| `IC_STRIKE_MODE` | `fixed` or `dynamic` (OI-based) | fixed |
| `IC_MIN_CREDIT` | Minimum net credit to enter | 20 |
| `IC_TRAILING_SL` | Enable trailing stop loss | true |
| `IC_TRAILING_ACTIVATE_PCT` | Activate trailing SL after % profit | 30 |
| `IC_TRAILING_OFFSET_PCT` | Trail behind peak by % | 15 |
| `IC_LEG_SL_ENABLED` | Per-leg stop loss | true |
| `IC_LEG_SL_PERCENT` | Per-leg SL % | 150 |
| `IC_ADJUSTMENT_ENABLED` | Close losing spread, keep winning | true |
| `IC_AVOID_EXPIRY_DAY` | Don't open IC on expiry day | true |
| `IC_DAILY_LOSS_LIMIT` | Stop after daily loss exceeds (0=off) | 0 |

### Step 4: Generate Domain
1. Settings → Public Networking
2. Click **"Generate Domain"**
3. Open URL → Dashboard! 🎉

## 📱 Telegram Commands

| Command | Action |
|---------|--------|
| `/session TOKEN` | Update API session |
| `/status` | Check bot status |
| `/start` | Start trading |
| `/stop` | Stop trading |
| `/backtest` | Run backtest |
| `/help` | Show all commands |

## 🔬 Backtesting

The bot includes a full backtesting engine accessible via the dashboard. All three strategies (Iron Condor, Straddle, Daily Scalp) can be backtested.

```bash
POST /api/backtest
{
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "strategy": "daily_scalp",
  "capital": 500000
}
```

## 📅 Daily Workflow

| Time | Action |
|------|--------|
| 9:00 AM | Get session token from ICICI |
| 9:05 AM | Send `/session TOKEN` via Telegram |
| 9:45 AM | ⚡ Daily Scalp enters automatically |
| 2:00 PM | ⚡ Daily Scalp hard exit (no overnight) |
| 3:15 PM | IC/Straddle exit (if running) |

## 🔧 Troubleshooting

### "Application failed to respond" on Railway
1. Make sure `Procfile` is uploaded: `web: gunicorn app:app --bind 0.0.0.0:$PORT --timeout 120 --workers 1 --threads 4 --preload`
2. Check Railway deploy logs for errors
3. Ensure `requirements.txt` has all dependencies
4. The bot thread now starts automatically at module load (works with gunicorn)

### "Limit exceed: API call per minute"
Set `CHECK_INTERVAL=60` or higher to reduce API calls.

### Bot thread not starting
Fixed in v3.0! The bot thread now starts at module import time, not just in `__main__`. Works with both `python app.py` and `gunicorn app:app`.

## ⚠️ Disclaimer

Trading involves risk. Use paper trading first. Not responsible for losses.
