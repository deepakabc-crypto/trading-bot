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

| Variable | Description | Example |
|----------|-------------|---------|
| `API_KEY` | ICICI Breeze API Key | abc123... |
| `API_SECRET` | ICICI Breeze Secret | xyz789... |
| `API_SESSION` | Breeze Session Token (daily) | abc123xyz... |
| `TELEGRAM_BOT_TOKEN` | From @BotFather | 123456:ABC... |
| `TELEGRAM_CHAT_ID` | Your chat ID | 987654321 |
| `CAPITAL` | Trading capital | 500000 |
| `STRATEGY` | Default strategy | iron_condor |

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

### "Found 0 expiry dates"
This error is now fixed! The backtester calculates expiry dates programmatically without API calls.

### "ModuleNotFoundError: schedule"
Fixed in `requirements.txt` - includes `schedule>=1.2.0`

### "Can't open file 'bot_runner.py'"
Renamed entry point to `app.py` - matches Procfile

## ⚠️ Disclaimer

Trading involves risk. Use paper trading first. Not responsible for losses.

## 📞 Support

Create GitHub issue for help.
