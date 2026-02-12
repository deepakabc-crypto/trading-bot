# 🤖 Nifty Options Trading Bot

Automated trading bot for Nifty options with Iron Condor and Short Straddle strategies.

## ✨ Features

- 🦅 **Iron Condor** - Limited risk, 65-70% win rate
- 📊 **Short Straddle** - Higher premium, 55-60% win rate
- 🖥️ **Web Dashboard** - Real-time P&L tracking
- 📱 **Telegram Alerts** - Trade notifications & remote control
- ☁️ **Railway Ready** - One-click deploy

## 📁 Files

| File | Description |
|------|-------------|
| `app.py` | Combined dashboard + trading bot |
| `Procfile` | Railway process config |
| `requirements.txt` | Python dependencies |
| `runtime.txt` | Python version |

## 🚀 Deploy to Railway (5 minutes)

### Step 1: Create GitHub Repository
1. Create new repo on GitHub
2. Upload all 4 files

### Step 2: Deploy on Railway
1. Go to [railway.app](https://railway.app)
2. Click **"New Project"** → **"Deploy from GitHub"**
3. Select your repository

### Step 3: Add Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `API_KEY` | ICICI Breeze API Key | abc123... |
| `API_SECRET` | ICICI Breeze Secret | xyz789... |
| `TELEGRAM_BOT_TOKEN` | From @BotFather | 123456:ABC... |
| `TELEGRAM_CHAT_ID` | Your chat ID | 987654321 |
| `CAPITAL` | Trading capital | 500000 |
| `STRATEGY` | Default strategy | iron_condor |

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

### Short Straddle
- Lot Size: **65**
- Strike: ATM
- Target: 30%
- Stop Loss: 20%

## ⚠️ Disclaimer

Trading involves risk. Use paper trading first. Not responsible for losses.

## 📞 Support

Create GitHub issue for help.
