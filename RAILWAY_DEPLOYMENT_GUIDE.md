# 🚂 Railway.app Deployment Guide
## Deploy Trading Bot in 5 Minutes

---

## 📋 What You'll Get

| Component | URL |
|-----------|-----|
| Dashboard | `https://your-app.railway.app` |
| Trading Bot | Runs 24/7 in background |
| Telegram Alerts | On your phone |

---

## 🚀 Step-by-Step Deployment

### Step 1: Create GitHub Repository

1. Go to [github.com](https://github.com) → Sign up/Login
2. Click **"New Repository"**
3. Name: `trading-bot`
4. ✅ Private (recommended)
5. Click **"Create repository"**

### Step 2: Upload Bot Files

Upload these files to your GitHub repo:

```
trading-bot/
├── config.py
├── iron_condor_bot.py
├── straddle_bot.py
├── telegram_alerts.py
├── dashboard.py
├── backtest.py
├── requirements.txt
├── Procfile
├── railway.json
└── runtime.txt
```

**Important**: I've included `Procfile`, `railway.json`, and `runtime.txt` in this package - these are required for Railway!

### Step 3: Create Railway Account

1. Go to [railway.app](https://railway.app)
2. Click **"Login"** → **"Login with GitHub"**
3. Authorize Railway to access your GitHub

### Step 4: Create New Project

1. Click **"New Project"**
2. Select **"Deploy from GitHub repo"**
3. Choose your `trading-bot` repository
4. Railway will auto-detect Python and start deploying

### Step 5: Add Environment Variables

⚠️ **IMPORTANT**: Never put API keys in code files!

1. In Railway dashboard → Click your project
2. Go to **"Variables"** tab
3. Add these variables:

| Variable | Value |
|----------|-------|
| `API_KEY` | Your ICICI API Key |
| `API_SECRET` | Your ICICI API Secret |
| `API_SESSION` | Daily session token |
| `TELEGRAM_BOT_TOKEN` | From @BotFather |
| `TELEGRAM_CHAT_ID` | From @userinfobot |
| `CAPITAL` | 500000 |
| `STRATEGY` | iron_condor |

### Step 6: Deploy!

1. Railway auto-deploys when you push to GitHub
2. Watch the deployment logs
3. Once deployed, click **"Generate Domain"**
4. Your dashboard is live at: `https://your-app.railway.app`

---

## 📁 Required Files Explained

### `Procfile`
Tells Railway how to run your app:
```
web: python dashboard.py
worker: python bot_runner.py
```

### `railway.json`
Railway configuration:
```json
{
  "build": {
    "builder": "NIXPACKS"
  },
  "deploy": {
    "restartPolicyType": "ON_FAILURE"
  }
}
```

### `runtime.txt`
Python version:
```
python-3.10.12
```

### `requirements.txt`
All dependencies:
```
breeze-connect>=1.0.0
flask>=2.0.0
gunicorn>=21.0.0
pandas>=1.5.0
numpy>=1.21.0
requests>=2.28.0
python-dateutil>=2.8.0
```

---

## 🔄 Daily Session Token Update

Since ICICI session expires daily, you have 2 options:

### Option A: Manual Update (Simple)
1. Every morning, get new session token
2. Go to Railway → Variables
3. Update `API_SESSION` value
4. Railway auto-restarts

### Option B: Telegram Command (Automated)
Send session token via Telegram:
```
/session YOUR_NEW_TOKEN
```
(Bot will update automatically - this feature is included!)

---

## 📊 Accessing Your Dashboard

After deployment:

1. Go to Railway dashboard
2. Click your project → **"Settings"**
3. Click **"Generate Domain"**
4. Your URL: `https://trading-bot-xxxx.railway.app`

Open this URL on any device to monitor trades!

---

## 🔧 Troubleshooting

| Issue | Solution |
|-------|----------|
| Deploy failed | Check logs in Railway dashboard |
| Bot not running | Verify environment variables |
| API error | Check API_KEY and API_SECRET |
| No Telegram alerts | Verify TELEGRAM_BOT_TOKEN |

### View Logs
1. Railway dashboard → Your project
2. Click **"Deployments"**
3. Click latest deployment → **"View Logs"**

---

## 💰 Railway Pricing

| Plan | Hours/Month | Cost |
|------|-------------|------|
| Free | 500 hours | $0 |
| Hobby | Unlimited | $5/month |
| Pro | Unlimited | $20/month |

**Note**: Free tier = ~16 hours/day. For 24/7 trading, upgrade to Hobby ($5/month).

---

## ⚠️ Important Notes

1. **Free tier sleeps after inactivity** - Use Hobby plan for 24/7
2. **Session token expires daily** - Update every morning
3. **Railway servers are in US** - ~200ms latency to NSE
4. **For serious trading** - Consider DigitalOcean Mumbai

---

## 🔐 Security Best Practices

1. ✅ Keep repository **Private**
2. ✅ Use **Environment Variables** for secrets
3. ✅ Never commit API keys to GitHub
4. ✅ Enable **2FA** on Railway and GitHub

---

## 📞 Support

- Railway Docs: [docs.railway.app](https://docs.railway.app)
- Railway Discord: [discord.gg/railway](https://discord.gg/railway)

---

Happy Trading! 🚀
