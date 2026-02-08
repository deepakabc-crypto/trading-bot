# 🤖 Nifty Options Trading Bot

Automated trading bot for Nifty options using Iron Condor and Short Straddle strategies.

## ✨ Features

- **🦅 Iron Condor Strategy** - Limited risk, 65-70% win rate
- **📊 Short Straddle Strategy** - Higher premium, 55-60% win rate
- **🖥️ Web Dashboard** - Real-time P&L tracking
- **📱 Telegram Alerts** - Trade notifications & remote control
- **☁️ Cloud Ready** - Deploy on Railway.app

## 📁 Files

| File | Description |
|------|-------------|
| `app.py` | Dashboard web app |
| `bot_runner.py` | Trading bot worker |
| `settings.py` | Configuration |
| `Procfile` | Railway process config |
| `requirements.txt` | Python dependencies |

## 🚀 Quick Deploy to Railway

### Step 1: Create GitHub Repository

1. Create new repo on GitHub (private recommended)
2. Upload all files

### Step 2: Deploy on Railway

1. Go to [railway.app](https://railway.app)
2. Click **"New Project"**
3. Select **"Deploy from GitHub repo"**
4. Choose your repository

### Step 3: Add Environment Variables

In Railway dashboard, add these variables:

| Variable | Description |
|----------|-------------|
| `API_KEY` | ICICI Breeze API Key |
| `API_SECRET` | ICICI Breeze API Secret |
| `API_SESSION` | Session token (update daily) |
| `TELEGRAM_BOT_TOKEN` | Telegram bot token |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID |
| `CAPITAL` | Trading capital (e.g., 500000) |
| `STRATEGY` | iron_condor / straddle / both |

### Step 4: Generate Domain

1. Click your service
2. Go to **Settings** → **Public Networking**
3. Click **"Generate Domain"**

## 📱 Telegram Commands

| Command | Description |
|---------|-------------|
| `/session TOKEN` | Update API session token |
| `/status` | Check bot status |
| `/start` | Start trading |
| `/stop` | Stop trading |
| `/help` | Show commands |

## 📅 Daily Workflow

1. **9:00 AM** - Get session token from ICICI
2. **9:05 AM** - Send `/session TOKEN` via Telegram
3. **9:20 AM** - Bot auto-starts trading
4. **3:15 PM** - Positions closed automatically

## ⚙️ Strategy Settings

### Iron Condor
- Sell Call: ATM + 150
- Buy Call: ATM + 250
- Sell Put: ATM - 150
- Buy Put: ATM - 250
- Target: 50% profit
- Stop Loss: 100%

### Short Straddle
- Strike: ATM
- Target: 30% profit
- Stop Loss: 20%

## ⚠️ Disclaimer

This bot is for educational purposes only. Trading involves significant risk. Use paper trading first. The authors are not responsible for any financial losses.

## 📞 Support

For issues, create a GitHub issue or contact via Telegram.
