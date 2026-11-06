# 🎯 SmartAPI Algorithmic Options Trading Suite
### Institutional Index Sniper (Nifty / Sensex) + AI Stock Options Engine (200+ F&O Universe)
#### Powered by Angel One SmartAPI, Google Gemini 2.5 Flash, React 18 & FastAPI

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10%2B-green.svg)](https://www.python.org/)
[![Node: 18+](https://img.shields.io/badge/Node-18%2B-orange.svg)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI%20%7C%20Uvicorn-009688.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/Frontend-React%20%7C%20Vite-61DAFB.svg)](https://react.dev/)
[![Angel One SmartAPI](https://img.shields.io/badge/Broker-Angel%20One%20SmartAPI-F58220.svg)](https://smartapi.angelbroking.com/)

A production-ready algorithmic trading and risk management platform designed for the Indian derivatives market (NSE & BSE). The system integrates **low-frequency quantitative index options buying** with an **autonomous LLM-powered stock options engine** capable of scanning, planning, and executing defined-risk intraday option setups.

---

## 📑 Table of Contents
1. [System Architecture & Capabilities](#-system-architecture--capabilities)
2. [Required Keys & Credentials (Complete Guide)](#-required-keys--credentials-complete-guide)
3. [Quickstart & Installation](#-quickstart--installation)
4. [How to Use the App (Step-by-Step Guide)](#-how-to-use-the-app-step-by-step-guide)
5. [The Two Trading Systems Explained](#-the-two-trading-systems-explained)
6. [Telegram Copilot & Remote Controls](#-telegram-copilot--remote-controls)
7. [Production Deployment & Server Commands](#-production-deployment--server-commands)
8. [Risk Rules & Circuit Breakers](#-risk-rules--circuit-breakers)
9. [Troubleshooting & FAQs](#-troubleshooting--faqs)

---

## 🏛️ System Architecture & Capabilities

The platform operates two independent, friction-hardened trading engines sharing a centralized risk controller:

```
                                  ┌───────────────────────────────┐
                                  │      Angel One SmartAPI       │
                                  │   (WebSocket V2 + REST RMS)   │
                                  └───────────────┬───────────────┘
                                                  │
                 ┌────────────────────────────────┴────────────────────────────────┐
                 ▼                                                                 ▼
   ┌─────────────────────────────┐                                   ┌─────────────────────────────┐
   │    Index Options Sniper     │                                   │   AI Stock Options Engine   │
   │  (NIFTY 50 / BSE SENSEX)    │                                   │     (200+ NSE F&O Stocks)   │
   ├─────────────────────────────┤                                   ├─────────────────────────────┤
   │ • 15m Macro Liquidity Sweep │                                   │ • Gemini 2.5 Flash / GPT-4o │
   │ • 3m MSS & VWAP Cross       │                                   │ • Overnight Strategy Plan   │
   │ • Displacement Stop-Limits  │                                   │ • Real-Time Intraday Scans  │
   │ • Breakeven & Dynamic Trail │                                   │ • Sector & Volume Confluence│
   │ • SEBI 0-DTE Morning Guard  │                                   │ • High-Beta 1:2.0 R:R Rules │
   └──────────────┬──────────────┘                                   └──────────────┬──────────────┘
                  │                                                                 │
                  └───────────────────────────────┬─────────────────────────────────┘
                                                  ▼
                                  ┌───────────────────────────────┐
                                  │   Centralized Risk Manager    │
                                  │  • 4.5% Daily Drawdown Circuit│
                                  │  • Max 2 Trades / 2 SL Losses │
                                  │  • Capital Floor & Sizing Math│
                                  │  • Emergency Global Panic Stop│
                                  └───────────────┬───────────────┘
                                                  │
                 ┌────────────────────────────────┴────────────────────────────────┐
                 ▼                                                                 ▼
   ┌─────────────────────────────┐                                   ┌─────────────────────────────┐
   │    Cyberpunk Web Control    │                                   │   Telegram Copilot & Bot    │
   │    (React 18 SPA HUD)       │                                   │  (Live Alerts + OTP Auth)   │
   └─────────────────────────────┘                                   └─────────────────────────────┘
```

---

## 🔑 Required Keys & Credentials (Complete Guide)

Before running the application, you need three sets of credentials:

### 1. Angel One SmartAPI (Broker Connectivity)
| Setting Key | Description | Where to Get It |
| :--- | :--- | :--- |
| `api_key` | SmartAPI Trading Application Key | Create an app on [smartapi.angelbroking.com](https://smartapi.angelbroking.com/) |
| `client_code` | Your Angel One Client ID | E.g. `AACI163472` (from your Angel One profile) |
| `pin` | 4-Digit Login PIN | Your Angel One account MPIN |
| `totp_secret` | 2FA Base32 Secret Key | See below on how to obtain |

#### 💡 How to Get Your `totp_secret`:
1. Log into your Angel One mobile app or web portal.
2. Go to **Security / Enable Authenticator (TOTP)**.
3. Angel One will show a QR code. Click on **"Can't scan QR?"** or **"Copy Key"**.
4. You will receive a 16–32 character alphanumeric string (e.g. `JBSWY3DPEHPK3PXP`).
5. Paste this key into `totp_secret`. The system generates time-based OTPs automatically on every login.

---

### 2. AI Brain API Keys (Stock Options Analysis)
You can choose either **Google Gemini** (Recommended: free tier, fastest) or **OpenAI**:

| Provider | Setting Key | Default Model | Where to Get It |
| :--- | :--- | :--- | :--- |
| **Google Gemini** *(Recommended)* | `gemini_api_key` | `gemini-2.5-flash` | Get a free API key at [aistudio.google.com](https://aistudio.google.com/) |
| **OpenAI** | `openai_api_key` | `gpt-4o-mini` | Generate an API key at [platform.openai.com](https://platform.openai.com/api-keys) |

> [!TIP]
> Google Gemini 2.5 Flash is recommended. It delivers comprehensive market reasoning, calculates support/resistance triggers, and evaluates sectoral momentum in under 1.5 seconds.

---

### 3. Telegram Bot (Alerts & Mobile Control)
| Setting Key | Description | Where to Get It |
| :--- | :--- | :--- |
| `bot_token` | Telegram Bot Token | Create a bot via [@BotFather](https://t.me/botfather) on Telegram |
| `chat_id` | Your Personal Telegram Numeric ID | Message [@userinfobot](https://t.me/userinfobot) to get your chat ID |

The bot provides real-time notifications for trade entries, target hits, stop-loss movements, 2FA OTP verification, and commands to pause/start or trigger panic liquidation remotely.

---

## 🚀 Quickstart & Installation

### Step 1: Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/Gokul-Krishnan-12/angelone-options.git
cd angelone-options

# Create Python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install backend dependencies
pip install -r requirements.txt
```

### Step 2: Configure Credentials
Copy the example configuration:
```bash
cp smartapi_trader/config/settings.example.yaml smartapi_trader/config/settings.yaml
```

Edit `smartapi_trader/config/settings.yaml` and enter your keys:
```yaml
broker:
  api_key: "YOUR_SMARTAPI_KEY"
  client_code: "YOUR_CLIENT_CODE"
  pin: "YOUR_4_DIGIT_PIN"
  totp_secret: "YOUR_BASE32_TOTP_SECRET"

ai:
  provider: "GEMINI"              # GEMINI or OPENAI
  model: "gemini-2.5-flash"
  gemini_api_key: "YOUR_GEMINI_API_KEY"
  openai_api_key: ""

telegram:
  enabled: true
  bot_token: "YOUR_TELEGRAM_BOT_TOKEN"
  chat_id: "YOUR_TELEGRAM_CHAT_ID"

execution:
  execution_mode: "PAPER"         # "PAPER" for simulation, "LIVE" for broker execution
```

Alternatively, you can configure these keys dynamically directly through the web UI under **Settings (`/settings`)**.

### Step 3: Launch the Application

#### Option A: Unified Production Server (Recommended)
This serves both the FastAPI REST/WebSocket backend and the compiled React production frontend on a single port:
```bash
# Build frontend bundle
cd frontend && npm install && npm run build && cd ..

# Launch backend & dashboard
./venv/bin/python main.py
```
Open **`http://localhost:5000`** in your browser.

#### Option B: Development Mode (Hot Reloading)
```bash
# Terminal 1: Backend
./venv/bin/python main.py

# Terminal 2: React Dev Server
cd frontend
npm run dev
```
Open **`http://localhost:5173`** in your browser (proxies API & WebSocket calls to port 5000).

---

## 🖥️ How to Use the App (Step-by-Step Guide)

### 1. Dashboard Overview (`/`)
* **Real-time Telemetry HUD**: Shows today's Net P&L, Account Equity, Available Margin, and the 4.5% Daily Drawdown circuit gauge.
* **Spot Market Radar**: Live spot levels, session VWAP, and Previous Day High/Low for Nifty 50 and Sensex.
* **Sniper State Machine**: Shows the live algorithmic phase: `Scanning` $\rightarrow$ `Sweep Detected` $\rightarrow$ `Displacement Armed` $\rightarrow$ `In Trade`.
* **Surgical Panic Button**: One-click kill switch to halt all engines, cancel resting exchange orders, and liquidate open positions immediately.

### 2. Paper vs Live Agent Controls
The app features isolated agent controls in the navigation bar:
* **Paper Trading Hub (`/paper`)**: Executes trades in a realistic virtual sandbox modeled with bid-ask spread slippage (0.2x spread) and simulated order latency (150–250ms).
* **Live Trading Hub (`/agent`)**: Routes native RMS orders directly to Angel One's matching engines with strict pre-trade checks.
* Both engines adhere to the same quantitative discipline, risk limits, and exit rules.

### 3. Stock Options AI Hub (`/stock-options-paper-trading` & `/stock-options-trading`)
* **⚡ Scan Live Markets Now**: Triggers the AI scanner to analyze 200+ NSE F&O stocks against live market breadth, VWAP confluence, sector momentum, and OI buildup.
* **Armed Candidates**: Setups waiting for breakout or dip confirmation (e.g., "Waiting for breakout: Spot ₹991.00 < Trigger ₹995.00"). Once triggered, the trade executes automatically.
* **Expected Profit & Max Risk Math**: Cards clearly display the contract (strike + type), entry premium, stop-loss (-12%), Target 1 (+1.8R to +2.0R), expected INR profit, and maximum INR risk.

### 4. Overnight AI Planner (`/overnight-ai-planner`)
* Run before market open (08:30–09:00 IST) or after market close.
* Scans the full F&O universe, identifies multi-day trend continuations, and formulates high-conviction trade cards ready for the opening bell.

### 5. Architectural Workflow (`/workflow`)
* Explains the entire mathematical mechanics of both quantitative index trading and AI stock options.
* Illustrates trade lifecycles, retest validation rules, and circuit breaker logic.

### 6. Settings (`/settings`)
* Live broker balance sync (Cash, Collateral, Net Equity).
* Test broker connectivity and refresh session.
* Configure risk parameters (risk per trade, max loss, trailing buffers).

---

## 📊 The Two Trading Systems Explained

### System 1: Index Options Quantitative Sniper
* **Underlyings**: Nifty 50, BSE Sensex, Bank Nifty.
* **Methodology**: Low-frequency institutional setup.
  1. **15-Minute Macro Sweep**: Spot breaches Previous Day High (PDH) or Low (PDL) and rejects with a long wick ($\ge 30\%$).
  2. **3-Minute MSS & Displacement**: Aggressive expansion candle displacing across Session VWAP.
  3. **Stop-Limit Entry**: Order placed at the breakout boundary; eliminates chasing and adverse selection.
  4. **Dynamic Trade Management**:
     * Protective Hard SL (-12% premium).
     * Breakeven shift armed once profit reaches **$\ge +0.65\text{R}$ to $+0.85\text{R}$** (preventing premature 1-second noise exits).
     * Target 1 partial booking (+2.0R) and remainder runner trailing.

### System 2: AI Stock Options Engine
* **Underlyings**: Top 200+ NSE F&O Stocks.
* **Methodology**: Autonomous AI multi-factor screener.
  1. **Sector Alignment**: Stock must align with sector momentum (e.g., FMCG, IT, Auto, Banking).
  2. **Technical Filtering**: Relative Volume (RVOL) $\ge 1.5\times$, VWAP clearance $\ge 0.5\%$, OI buildup verification.
  3. **High-Beta Adaptive R:R**: Enforces minimum **1:2.0 Risk-to-Reward** for volatile stocks and **1:1.8** for standard large-caps.
  4. **Conditional Execution**: Setups are armed with entry triggers (breakout or pullback dip) and structural invalidation levels.

---

## 📱 Telegram Copilot & Remote Controls

Connect your Telegram bot to receive instant alerts and remotely control your bot:

```
                      TELEGRAM OPERATOR CHAT
                                │
          ┌─────────────────────┴─────────────────────┐
          ▼                                           ▼
   Real-Time Alerts                           Remote Commands
   • 🟢 Trade Entry Alert                     • /status   - Strategy & position audit
   • 🎯 Target 1 Booked                       • /balance  - Angel One cash & margin
   • 🛡️ Breakeven Shift                        • /report   - Today's detailed P&L
   • 🛑 Stop-Loss Executed                    • /start_real - Arm live execution
   • 🔐 2FA OTP Request                       • /pause_real - Halt live trading
                                              • /panic    - Emergency liquidation
```

---

## 🛠️ Production Deployment & Server Commands

For running 24/7 on an Ubuntu Linux VPS (e.g., AWS EC2, Oracle Cloud):

### 1. Systemd Service Setup
```bash
sudo cp smartapi_trader.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable smartapi_trader
sudo systemctl start smartapi_trader
```

### 2. Common Maintenance Commands
| Action | Shell Command |
| :--- | :--- |
| **Check Status** | `sudo systemctl status smartapi_trader` |
| **Restart Service** | `sudo systemctl restart smartapi_trader` |
| **Stop Service** | `sudo systemctl stop smartapi_trader` |
| **View Live Logs** | `journalctl -u smartapi_trader -f` |
| **View Application Log** | `tail -f logs/trader_$(date +%F).log` |
| **Rebuild Frontend** | `cd frontend && npm run build && cd .. && sudo systemctl restart smartapi_trader` |
| **Run Regression Tests** | `./venv/bin/python scripts/run_regression_tests.py` |

---

## 🛡️ Risk Rules & Circuit Breakers

To guarantee long-term survival, the system enforces non-negotiable capital safety rules:

| Risk Rule | Boundary | System Response |
| :--- | :--- | :--- |
| **Max Daily Loss** | ₹5,000 / 4.5% Equity | Shuts down engine, liquidates all open positions |
| **Daily Trade Quota** | Exactly 2 completed trades | Halts further entries for the day |
| **Consecutive Losses** | 2 consecutive stop-outs | Freezes new orders until next morning session |
| **Midday Chop Filter** | 11:30–12:30 IST | Blocks new entries during low-volume lunchtime chop |
| **EOD Mandatory Square-Off** | 15:12 IST | Liquidates all intraday derivative positions at market |
| **0-DTE Morning Guard** | Before 13:00 IST | Blocks same-day expiring contracts to avoid morning theta burn |
| **Noise-Filtered Breakeven** | $\ge 0.65\text{R}$ verified gain | Protects trades from exiting on 10-paise bid-ask jitter |

---

## ❓ Troubleshooting & FAQs

### Q: Why does the system ask for an OTP?
Angel One requires a daily TOTP handshake. The system handles this automatically using your `totp_secret`. If Angel One triggers an SMS/Telegram 2FA prompt, the bot sends an alert to your Telegram chat with a direct link or prompt to verify.

### Q: Why did the scanner take 0 trades today?
1. The scanner checks underlying conditions (breakout triggers, VWAP clearance, and volume). If the market is choppy or consolidating, trades are withheld to protect capital.
2. Orders are armed and wait for the underlying spot to cross the specified entry trigger. If the stock does not reach the trigger, it expires safely without entering.

### Q: Can I run both Paper and Live trading simultaneously?
Yes. Paper trading operates in an isolated virtual sandbox, allowing you to test AI discoveries and index triggers without routing orders to the exchange.

---

## ⚖️ Disclaimer

*This software is intended for educational, quantitative research, and paper-simulation purposes. Trading derivatives, options, and futures involves substantial risk of loss. Always perform comprehensive backtesting and paper simulation before allocating live capital. The authors assume no responsibility for financial losses incurred through the use of this system.*
