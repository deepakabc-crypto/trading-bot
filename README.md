# 🤖 Nifty Options Trading Bot v2.0

Automated trading bot for Nifty options with Iron Condor and Short Straddle strategies.

## ✨ Features

- 🦅 **Iron Condor** - Limited risk, 65-70% win rate
- 📊 **Short Straddle** - Higher premium, 55-60% win rate
- 🖥️ **Web Dashboard** - Real-time P&L tracking
- 📱 **Telegram Alerts** - Trade notifications & remote control
- 🔬 **Backtesting Engine** - Test strategies on historical data
- 📜 **Trade History** - Persistent trade logs
- ☁️ **Railway Ready** - One-click deploy

## 📁 Files

| File | Description |
|------|-------------|
| `app.py` | Combined dashboard + trading bot + backtester |
| `Procfile` | Railway process config |
| `requirements.txt` | Python dependencies |

## 🚀 Deploy to Railway (5 minutes)

### Step 1: Create GitHub Repository
1. Create new repo on GitHub
2. Upload all files

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
| `NUM_LOTS` | Number of lots to trade | 1 |
| `STRATEGY` | iron_condor / straddle / both | iron_condor |
| `MIN_PREMIUM` | Minimum premium to enter | 10 |
| `AUTO_START` | Auto-start bot on deploy | true |

> **Note:** Total quantity = LOT_SIZE × NUM_LOTS (e.g., 75 × 2 = 150)

#### Optional - Timing (IST)

| Variable | Description | Default |
|----------|-------------|---------|
| `ENTRY_TIME_START` | Start of entry window | 09:20 |
| `ENTRY_TIME_END` | End of entry window | 14:00 |
| `EXIT_TIME` | Force exit all positions | 15:15 |
| `CHECK_INTERVAL` | Seconds between bot checks | 60 |
| `CUSTOM_EXPIRY` | Override expiry date (for holidays) | *(empty)* |
| `USE_CURRENT_EXPIRY` | Use current week expiry on Thursday | false |
| `EXPIRY_DAY_CUTOFF` | Time after which to use next expiry on Thursday | 09:30 |

> **Holiday Expiry:** When expiry is shifted due to a holiday (e.g., Thursday is holiday, expiry moves to Monday/Tuesday), set `CUSTOM_EXPIRY=17-02-2026` to override.
>
> **Supported formats:** `17-02-2026`, `2026-02-17`, `17-Feb-2026`, `17/02/2026`

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

> **Note:** `API_SESSION` expires daily. You can update it via Telegram `/session TOKEN` or the dashboard.

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

The bot includes a full backtesting engine accessible via the dashboard:

1. Go to the **Backtesting** tab
2. Set start/end dates
3. Choose strategy
4. Click **Run Backtest**

## 🔬 Backtesting

The backtesting engine uses the **same entry/exit times** as the live trading bot:

### Features
- **Entry Window**: Configurable entry time start and end
- **Exit Time**: Force exit time for all positions
- **Intraday Simulation**: Simulates price movement throughout the day
- **Exit Breakdown**: Shows how many trades hit target, stop-loss, or time exit

### Backtest Results Show:
| Field | Description |
|-------|-------------|
| Total Trades | Number of trades executed |
| Win Rate | Percentage of profitable trades |
| Total P&L | Net profit/loss |
| Return % | Return on initial capital |
| Avg Exit Time | Average time of day for exits |
| Target Hits | Trades that hit target |
| Stop Loss | Trades that hit stop-loss |
| Time Exits | Trades exited at force exit time |

### Detailed Trade Log
Each trade shows:
- **Entry Date** - When the trade was entered
- **Entry Time** - Actual entry time (random within window)
- **Exit Time** - When the trade was closed
- **Premium** - Entry premium collected
- **P&L** - Profit/loss in ₹
- **Exit Reason** - TARGET, STOP_LOSS, or TIME_EXIT

### API Usage
```bash
POST /api/backtest
{
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "strategy": "iron_condor",
  "capital": 500000,
  "entry_time_start": "09:20",
  "entry_time_end": "14:00",
  "exit_time": "15:15"
}
```

---

## 📊 Dashboard Features

### Live Position Panel
- **Real-time P&L** - Updates every 5 seconds
- **Position Details** - Entry time, spot price, expiry, quantity
- **Leg-wise Breakdown** - See each option leg with entry/current prices
- **Progress Bar** - Visual indicator showing distance to target/stop-loss
- **Unrealized P&L** - Both absolute value and percentage

### Status Badges
- 🕐 Current IST time
- 📊 Market status (OPEN/CLOSED)
- ⏳ Entry window status
- 📅 Next expiry date

### API Endpoints for Backtesting

```bash
# Get expiry dates
GET /api/expiries?start=2025-01-01&end=2025-12-31

# Run backtest
POST /api/backtest
{
  "start_date": "2025-01-01",
  "end_date": "2025-12-31",
  "strategy": "iron_condor",
  "capital": 500000
}

# Get bot status (timing, settings)
GET /api/status

# Get current settings
GET /api/settings

# Get live positions
GET /api/position

# Get real-time P&L for positions
GET /api/live_pnl?strategy=iron_condor
GET /api/live_pnl?strategy=straddle
GET /api/live_pnl?strategy=all
```

### Example Status Response

```json
{
  "current_time_ist": "2026-02-12 10:30:00",
  "is_trading_time": true,
  "is_market_hours": true,
  "entry_time_start": "09:20",
  "entry_time_end": "14:00",
  "exit_time": "15:15"
}
```

### Expiry Date Format for Breeze API

The bot automatically handles date formatting:
- **Display format**: `13-Feb-2026`
- **Breeze API format**: `2026-02-13T07:00:00.000Z`

## 📅 Daily Workflow

| Time | Action |
|------|--------|
| 9:00 AM | Get session token from ICICI |
| 9:05 AM | Send `/session TOKEN` via Telegram |
| 9:20 AM | Bot starts trading automatically |
| 3:15 PM | Bot exits all positions |

## ⚙️ Strategy Settings

### Iron Condor
- Lot Size: **65**
- Sell: ATM ± 150
- Buy: ATM ± 250
- Target: 50%
- Stop Loss: 100%
- Min Premium: ₹20

### Short Straddle
- Lot Size: **65**
- Strike: ATM
- Target: 30%
- Stop Loss: 20%
- Min Premium: ₹20

## 📜 Trade History

Trade history is automatically preserved in `trade_history.json`:

```json
{
  "trades": [...],
  "backtest_results": [...]
}
```

Access via:
- Dashboard → Trade History tab
- API: `GET /api/history`

## 🔧 Troubleshooting

### "Limit exceed: API call per minute"
The Breeze API has a limit of ~60 calls per minute. The bot now includes:
- **Rate limiting** - Minimum 500ms between API calls
- **LTP caching** - 5-second cache to avoid repeated calls
- **Auto-wait** - Waits 60s when limit is detected
- **Check interval** - Default increased to 60 seconds

To reduce API calls further:
```
CHECK_INTERVAL=120  # Check every 2 minutes instead of 1
```

### "Found 0 expiry dates"
This error is now fixed! The backtester calculates expiry dates programmatically without API calls.

### "No Data Found" for option quotes
This usually means:
1. **Wrong expiry** - On Thursday, the bot now uses next week's expiry by default
2. **Strike doesn't exist** - The strike price might not have contracts. Check if the strike is valid.
3. **API issue** - Breeze API might be down. The bot will retry 3 times.

The bot now tries multiple expiry formats:
- `2026-02-19T07:00:00.000Z` (ISO format)
- `19-Feb-2026` (DD-Mon-YYYY)
- `2026-02-19` (YYYY-MM-DD)

### "Credit 0 < MIN_PREMIUM"
This means the option quotes returned 0 or failed. Check:
1. Session token is valid
2. Market is open
3. Expiry date is correct (check `/api/status` endpoint)

### "ModuleNotFoundError: schedule"
Fixed in `requirements.txt` - includes `schedule>=1.2.0`

### "Can't open file 'bot_runner.py'"
Renamed entry point to `app.py` - matches Procfile

## ⚠️ Disclaimer

Trading involves risk. Use paper trading first. Not responsible for losses.

## 📞 Support

Create GitHub issue for help.
