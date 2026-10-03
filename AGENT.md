# AGENT.md: Operational Blueprint & Developer Intelligence Guide

> **Target Audience**: Future AI Agents, Quantitative Engineers, and System Operators maintaining or extending this codebase.
> **Repository Purpose**: Institutional Liquidity Sweep & Momentum Expansion (ILSME) Algorithmic Options Trading Engine with Angel One SmartAPI and Real-Time Web Control Plane.

---

## 1. System Overview & Core Philosophy

This repository is a production-grade algorithmic options trading system specialized for naked buying of Indian Index Options (**NIFTY 50**, **BANK NIFTY**, and **BSE SENSEX**).

The core principle is **low-frequency, high-impulse liquidity sniper trading**:
- **Why Options Buying**: Consolidating markets bleed option buyers due to theta decay ($\Theta = \partial V / \partial t$) and bid-ask spreads. This engine avoids churn by executing at most **2 high-conviction trades per day** and strictly avoiding the midday chop zone (11:15–13:30 IST).
- **Institutional ICT / ILSME Framework**: Detects institutional liquidity sweeps of key session boundaries (Previous Day High/Low, Session Extremes), waits for a structural shift with a Fair Value Gap (FVG), and enters on the displacement retracement.
- **Asymmetric Expectancy**: High Reward-to-Risk ratio ($3.0R$ Target vs $1.0R$ Stop with an automatic Breakeven shift at $+1.2R$) that generates consistent net profitability even at conservative ~31% win rates under heavy SEBI/brokerage friction.
- **Dual Agent Architecture**: A completely isolated **Paper Trading Agent** and a live **Real Trading Agent** operate concurrently with identical strategy mechanics, allowing risk-free verification under realistic simulated microstructure friction before engaging live broker routing.

---

## 2. Repository Architecture & Directory Map

```
options/
├── AGENT.md                       # This document (system guide for AI agents)
├── README.md                      # Human-facing overview & mathematical formulations
├── start.sh / stop.sh             # Background daemon process control scripts
├── requirements.txt               # Python package dependencies
├── main.py                        # Root launcher script
├── scripts/
│   ├── recursive_strategy_optimizer.py # Multi-core strategy parameter optimizer (3888+ combos)
│   ├── run_regression_tests.py    # Automated end-to-end regression & math verification test suite
│   ├── run_friction_backtest.py   # Historical backtester accounting for statutory friction
│   └── run_paper_backtest.py      # Simulation runner with realistic fill delays
├── data/
│   ├── instruments.db             # SQLite local cache of Angel One OpenAPIScripMaster
│   └── historical/                # Historical JSON OHLCV backtest data
├── logs/                          # Daily rotated loguru logs (e.g. trader_YYYY-MM-DD.log)
├── frontend/                      # Modern React Control Plane UI
│   ├── package.json               # Vite + React 18 + Lucide Icons
│   ├── vite.config.js             # Dev server config & proxy to FastAPI (port 5000)
│   ├── dist/                      # Production build bundle (served by FastAPI at /)
│   └── src/
│       ├── App.jsx                # Telemetry router & WebSocket message dispatcher
│       ├── index.css              # Cyber-fintech obsidian design system
│       ├── components/            # Header, MetricsHud, PositionsTable, OrdersTable, EventConsole, Modals
│       └── pages/
│           ├── Dashboard.jsx      # Telemetry HUD, Spot Radar, Positions & Working Orders
│           ├── Orders.jsx         # Orders & Derivatives Book (Positions, Orders, Trade History)
│           ├── PaperTrade.jsx     # Paper Trading Hub, Dummy Capital, Trade Summary Ledger & Quota Reset
│           ├── AgentControl.jsx   # Real Money Angel One RMS Live Execution Hub
│           ├── Settings.jsx       # Broker API Credentials, Risk Limits & Telegram Configuration
│           ├── SystemWorkflow.jsx # Interactive 8-stage architectural pipeline walkthrough
│           └── Logs.jsx           # Live system audit log viewer
└── smartapi_trader/               # Core Python Quantitative Engine
    ├── main.py                    # TradingOrchestrator tying data, strategy, risk, execution & web
    ├── config/
    │   ├── settings.yaml          # Active risk parameters, execution mode, broker & telegram config
    │   └── symbols.yaml           # Index tokens, lot sizes, tick sizes, strike intervals
    ├── core/
    │   ├── event_bus.py           # Async pub/sub EventBus
    │   ├── events.py              # Dataclasses (Tick, Bar, Signal, Order, Fill, Position, RiskAlert)
    │   └── state_manager.py       # In-memory central telemetry state, RMS sync, paper ledger & scale checks
    ├── data/
    │   ├── candle_builder.py      # Tick-to-OHLCV aggregator (3m & 15m candles with VWAP)
    │   ├── instrument_loader.py   # Scrip master downloader, SQLite cache & strike resolver
    │   └── stream_client.py       # SmartStreamClient WebSocket wrapper with synthetic paper fallback
    ├── strategy/
    │   ├── base_strategy.py       # Abstract BaseStrategy interface
    │   └── sniper_ilsme.py        # Institutional Liquidity Sweep & Momentum Expansion strategy
    ├── risk/
    │   └── risk_manager.py        # Position sizing (2.0%), daily drawdown stop (4.0%), native bracket manager
    ├── execution/
    │   ├── base_engine.py         # Abstract ExecutionEngine interface
    │   ├── paper_engine.py        # Simulated fills with Ask + (Spread * 0.20) slippage & 200ms latency
    │   └── live_smartapi.py       # Production Angel One REST API integration (<=10 req/s rate limits)
    ├── web/
    │   └── app.py                 # FastAPI server, WebSocket hub, REST endpoints & static server
    └── utils/
        ├── auth.py                # TOTP auto-generation & Angel One session initialization
        ├── charges.py             # Official SEBI & Angel One brokerage and statutory tax calculator
        ├── logger.py              # Loguru logger with WebSocket broadcast integration
        └── telegram_notifier.py   # 2-way Telegram bot controller, slippage telemetry & scaling advisor
```

---

## 3. Quantitative Mechanics: ILSME Sniper Strategy

File: [smartapi_trader/strategy/sniper_ilsme.py](file:///home/gokul/Desktop/angelone-options/smartapi_trader/strategy/sniper_ilsme.py)

1. **Macro Regime (15-Minute Timeframe)**:
   - Tracks Previous Day High (PDH), Previous Day Low (PDL), and Day High/Low extremes.
   - **Liquidity Sweep**: Price breaches the extreme to trigger stop runs, then closes back inside with a rejection wick $\ge 30\%$ of the candle range.
2. **Micro Structure Shift & FVG (3-Minute Timeframe)**:
   - **Market Structure Shift (MSS)**: Strong displacement bar crossing VWAP in the reversal direction.
   - **Fair Value Gap (FVG)**: 3-candle imbalance (Bullish: Candle 3 Low > Candle 1 High; Bearish: Candle 3 High < Candle 1 Low).
   - **Entry Trigger**: Limit order positioned at the FVG retracement boundary.
3. **Volume Confirmation**:
   - Contract volume must exceed $1.8\times$ its 20-period moving average.
4. **Contract Selection & Strike Mechanics**:
   - Dynamically targets At-The-Money (ATM) or immediate In-The-Money (ITM) options ($\Delta \approx 0.50 - 0.55$).
   - **Nifty 50**: Weekly expiries, lot size = 65 (default primary engine).
   - **Bank Nifty**: Monthly expiries exclusively, lot size = 30.
   - **Sensex**: Weekly expiries, lot size = 20.
   - **Morning 0-DTE Filter**: On expiry day, 0-DTE contracts are blocked before 13:00 IST to avoid morning theta crush, automatically rolling to the next expiry cycle.

---

## 4. Audited Optimal Parameters & Mathematical Expectancy

The parameters currently active in [settings.yaml](file:///home/gokul/Desktop/angelone-options/smartapi_trader/config/settings.yaml) were determined via empirical grid optimization across 3,888 permutations on 251 historical trading sessions (accounting for all SEBI turnover taxes, STT, exchange charges, GST, and ₹40 round-trip brokerage).

### Live Production Configuration

| Parameter | Optimized Value | Quantitative Rationale |
|---|---|---|
| **Risk Per Trade ($\alpha$)** | **2.0%** | Optimal fractional Kelly sizing preventing geometric drawdown |
| **Initial Stop Loss** | **10.0%** | Invalidation level based on displacement bar low |
| **Breakeven Shift Trigger** | **+1.2R** | Moves SL to exact entry price once $+1.2R$ is tagged |
| **Target Profit (TP)** | **+3.0R** | Asymmetric reward harvesting (Reward:Risk ratio = 3.11:1) |
| **Max Daily Drawdown** | **4.0%** | Hard circuit breaker halting engine for the session |
| **Max Trades Per Day** | **2** | Eliminates overtrading in chop regimes |
| **Trailing Stop Type** | **Breakeven (+0.0 pts)** | Backtests prove adding friction buffers causes premature stop-outs |
| **Time Filter** | **09:30–11:15 & 13:30–15:00** | Strict avoidance of midday dead zones |

### Backtest Expectancy & Returns Profile
- **Initial Capital**: ₹1,00,000
- **Net Annual Profit**: +₹52,774.71 (+52.8% ROI after all taxes & brokerage)
- **Total Trades Taken**: 147 (Win Rate: 31.3%, Win/Loss Payoff Ratio: 3.11:1)
- **Profit Factor**: 1.41
- **Max Strategy Drawdown**: 12.4% (Max consecutive losses: 6)

---

## 5. Risk Management & Native Exchange Execution Safeguards

Files: [smartapi_trader/risk/risk_manager.py](file:///home/gokul/Desktop/angelone-options/smartapi_trader/risk/risk_manager.py), [smartapi_trader/execution/live_smartapi.py](file:///home/gokul/Desktop/angelone-options/smartapi_trader/execution/live_smartapi.py)

### 1. Position Sizing Formula
$$R_{\text{trade}} = \text{Capital} \times 0.02$$
$$\text{Lots} = \left\lfloor \frac{R_{\text{trade}}}{(P_{\text{entry}} - P_{\text{stop}}) \times \text{LotSize}} \right\rfloor$$
- **1-Lot Pilot Floor**: For live pilot validation, lots can be pinned to 1 lot (65 units for NIFTY) to measure live exchange slippage.

### 2. Native Exchange STOPLOSS_LIMIT Orders
- **No Client-Side Polling Risk**: Stop loss orders are immediately placed on Angel One's server as native `STOPLOSS_LIMIT` orders.
- **Trigger-to-Price Buffer**: A 0.8% to 1.0% limit price buffer below the trigger price is enforced to guarantee order fills without suffering market order slippage on sudden index flushes.
- **Modification Protocol**: When the position hits $+1.2R$, the system calls Angel One's `modifyOrder` endpoint to shift the trigger price directly to $P_{\text{entry}}$.

### 3. Circuit Breakers
- **Daily Drawdown Limit**: 4.0% of starting equity triggers immediate liquidation and scanner halt.
- **Consecutive Loss Lock**: 2 consecutive losses pause trading for the remainder of the session.
- **Mandatory EOD Liquidation**: Hard square-off at **15:12 IST** (prior to broker auto-squareoff charges).

---

## 6. Telegram Telemetry, Slippage Tracking & Automated Governance

File: [smartapi_trader/utils/telegram_notifier.py](file:///home/gokul/Desktop/angelone-options/smartapi_trader/utils/telegram_notifier.py)

### 1. Live Slippage Delta Telemetry
Every trade entry and exit notification explicitly calculates and reports the difference between the theoretical signal price and the actual broker fill price:
```
🎯 TRADE ENTRY: NIFTY26OCT24800CE
---------------------------------
• Type: BUY_CE
• Lots: 1 (65 Qty)
• Signal Price: ₹142.50
• Executed Fill: ₹143.20
• Slippage Delta: +₹0.70 (+0.49%)  ⚠️ Adverse
• Initial Stop Loss: ₹128.90 (-10.0%)
• Target (3.0R): ₹184.40 (+29.4%)
```

### 2. Automated Scaling Milestone Notifications
When the state manager detects positive performance milestones (e.g. 30 sessions completed with Profit Factor $\ge 1.30$, Win Rate $\ge 28\%$, and average slippage $\le 1.2$ pts), it triggers `notify_scaling_advisory()` recommending capital scale-up.

### 3. Automated Quarantine & Discard Alerts
If performance breaches risk bounds (e.g. Drawdown $> 15\%$, 7 consecutive losses, or average slippage $> 2.5$ pts), the system triggers `notify_discard_alert()` with a **RED QUARANTINE WARNING**, pausing live trading until parameters are re-optimized.

---

## 7. Dual Agent Architecture & Ledger Isolation

File: [smartapi_trader/core/state_manager.py](file:///home/gokul/Desktop/angelone-options/smartapi_trader/core/state_manager.py)

1. **Enclosed Paper Trading Ledger (`paper_state`)**:
   - Has its own virtual starting capital, available margin, net P&L, and trade quota count.
   - Deducts realistic Angel One brokerage (₹40 round-trip flat + STT + exchange fees + GST) via `calculate_option_charges()`.
   - Features dedicated endpoints for managing dummy capital and resetting or removing paper trades.
   - **NEVER** touches live Angel One RMS capital or broker balance.
2. **Live Angel One RMS Ledger (`broker_rms`)**:
   - Directly queried from Angel One SmartAPI `rmsLimit()`.
   - Tracks `net`, `availablecash`, `collateral`, and `utiliseddebits`.
   - Used by the Real Trading Agent (`/agent`).

---

## 8. Web Control Plane & REST/WebSocket Endpoints

File: [smartapi_trader/web/app.py](file:///home/gokul/Desktop/angelone-options/smartapi_trader/web/app.py)

### Key REST Endpoints

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Serves React UI from `frontend/dist/index.html` |
| `GET` | `/api/state` | Returns full system snapshot (telemetry, positions, orders, paper_state) |
| `GET` | `/api/broker/balance` | Fetches live Angel One RMS balance |
| `POST` | `/api/agent/paper/start` | Starts the Paper Trading Agent |
| `POST` | `/api/agent/paper/pause` | Pauses the Paper Trading Agent |
| `POST` | `/api/agent/real/start` | Starts Real Trading Agent (armed for Angel One live orders) |
| `POST` | `/api/agent/real/pause` | Pauses Real Trading Agent |
| `POST` | `/api/paper/capital` | Sets dummy paper trading capital (e.g. ₹50,000, ₹1,00,000) |
| `POST` | `/api/paper/reset_trades`| Clears all paper trades and resets paper quota back to 0/2 |
| `DELETE` | `/api/paper/trade/{id}` | Deletes a specific paper trade from the ledger and recalculates net P&L |
| `POST` | `/api/test_signal` | Simulates an ILSME sniper signal (`NIFTY`/`BANKNIFTY`, `BUY_CE`/`BUY_PE`) |
| `POST` | `/api/exit_position/{sym}`| Surgically liquidates a specific open position |
| `POST` | `/api/panic` | Global emergency switch: cancels all orders, closes all positions, halts runner |
| `POST` | `/api/reset_panic` | Clears panic state and re-arms scanner |
| `GET/POST`| `/api/settings` | Gets or updates credentials, risk limits, and Telegram config |

### WebSocket Telemetry (`/ws`)
Broadcasts real-time events to connected clients:
- `SYSTEM_STATE`: Periodic or event-triggered full state update
- `TICK`: Live LTP, bid, ask, and spread
- `ORDER_UPDATE`: Working, filled, or rejected order telemetry
- `FILL`: Execution fills with slippage details
- `POSITION_UPDATE`: Unrealized P&L, stop loss, and target levels
- `LOG_ENTRY`: Structured application logs streamed live to the UI Event Console

---

## 9. Common Operator & Developer Workflows

### How to Start the Engine
```bash
./start.sh
# or directly in workspace root:
./venv/bin/python main.py
```
Starts the FastAPI server and engine orchestrator on `http://localhost:5000`.

### How to Stop the Engine
```bash
./stop.sh
# or via command line:
pkill -f "python main.py"
```
Gracefully terminates the background engine process and releases port 5000.

### How to Run / Build the React Frontend
```bash
cd frontend
# For development with hot reloading (port 3000):
npm run dev

# To compile production assets into frontend/dist (served by FastAPI):
npm run build
```
> **CRITICAL**: Whenever editing files in `frontend/src/`, always run `npm run build` so that `frontend/dist/` is updated and served immediately by FastAPI.

### How to Run Automated Tests
```bash
./venv/bin/python scripts/run_regression_tests.py
```

### How to Inspect Logs
```bash
tail -f logs/trader_$(date +%F).log
```

---

## 10. Critical Guidelines for Future AI Agents

1. **Maintain Paper / Live Ledger Separation**:
   - `paper_state` fields (`paper_capital`, `paper_completed_trades`, `paper_trades_taken`) must **never** write to or overwrite `broker_rms` or live balance.
   - Live orders must only be dispatched if `self.execution_mode == "LIVE"` and `real_agent_status == "RUNNING"`.
2. **Preserve Strike Price & Charges Tracking**:
   - Every completed trade record **must** include `strike_price`, `option_type`, `gross_pnl`, `total_charges`, and `net_pnl`.
   - When closing positions in `app.py`, `risk_manager.py`, or `telegram_notifier.py`, always pass `strike_price=getattr(pos, 'strike_price', 0.0)` and `option_type=getattr(pos, 'option_type', '')`.
3. **Strict Parameter Consistency**:
   - Keep `smartapi_trader/config/settings.yaml`, `frontend/src/pages/Settings.jsx`, and `frontend/src/pages/SystemWorkflow.jsx` in complete synchronization with the audited values (`risk_pct=2.0`, `stop_loss_pct=10.0`, `breakeven_trigger_r=1.2`, `target_profit_r=3.0`, `max_daily_drawdown_pct=4.0`, `max_trades_per_day=2`).
4. **Process Management**:
   - The backend runs via `./venv/bin/python main.py`. Check running processes with `ps aux | grep main.py` or port `5000` via `ss -tulpn`.
   - Never spawn duplicate instances of `main.py` simultaneously on port `5000`.
5. **UI Styling & Aesthetics**:
   - Preserve Gokul Krishnan's dark obsidian cyberpunk visual design (`#121110`, `#1c1a18`, `#ed4c22`, `#38bdf8`, `#10b981`, `#f43f5e`).
   - Use JetBrains Mono / Space Grotesk typography for numerical displays and financial metrics.
