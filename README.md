# SmartAPI Low-Frequency Index Options Algorithmic Trading Framework
### Institutional Liquidity Sweep & Momentum Expansion (ILSME) Sniper Engine with Operator Control Plane

A production-grade, asynchronous quantitative trading system designed for naked index options buying on Indian derivatives (**Nifty 50**, **Bank Nifty**, and **BSE Sensex**) using Angel One's SmartAPI.

---

## 1. Architectural Highlights

- **Decoupled Dual-Mode Execution Framework**: Complete behavioral parity between simulated **PAPER** execution and **LIVE** exchange routing via the `ExecutionEngine(ABC)` interface abstraction.
- **Microstructure & Slippage Modeling**:
  - Buy fill price: $\text{Fill Price}_{\text{Paper, Buy}} = \text{Ask}_{\text{Live}} + (\text{Spread} \times \kappa)$ with $\kappa = 0.20$
  - Sell fill price: $\text{Fill Price}_{\text{Paper, Sell}} = \text{Bid}_{\text{Live}} - (\text{Spread} \times \kappa)$
  - Artificial network and matching engine latency simulation (150–300 ms).
- **Asynchronous Pub/Sub Event Bus**: Unidirectional event pipeline (`TICK` $\rightarrow$ `BAR` $\rightarrow$ `SIGNAL` $\rightarrow$ `ORDER_SUBMIT` $\rightarrow$ `FILL` $\rightarrow$ `POSITION_UPDATE` $\rightarrow$ `TELEMETRY`).
- **Resilient Instrument Master Loader**: Streams the 37+ MB Angel One `OpenAPIScripMaster.json`, caches locally in SQLite with sub-millisecond strike and ATM lookup queries.
- **SmartWebSocketV2 Streamer**: Dynamic subscription, heartbeat management (10s ping), automatic reconnection with exponential backoff, and synthetic paper tick generation.
- **Cyberpunk / Warm Obsidian FinTech UI**: Styled using Gokul Krishnan's personal design identity (`--bg-dark: #121110;`, `--bg-dark-card: #1c1a18;`, and signature burnt orange accent `--accent-orange: #ed4c22;` with glowing indicators).
- **Navigation & Page Architecture (Inspired by `angelone-swing`)**:
  - `Overview / Dashboard` (`/`): Telemetry HUD, Spot Radar, Sniper State Machine, Active Positions, Orders.
  - `Orders & Positions` (`/orders`): Tabs for Active Positions, Order Book, and Completed Trade History with surgical liquidation.
  - `Paper Trade Agent Hub` (`/paper`): Dedicated Paper Trading Agent with separate Start/Pause controls and simulated microstructure parameters.
  - `Real Trade Agent Hub` (`/agent`): Dedicated Real Money Agent with separate Start/Pause controls directly executing on Angel One RMS.
  - `Settings & Broker` (`/settings`): Angel One SmartAPI credentials, live balance fetch & test connection, risk configuration.
  - `Activity Logs` (`/logs`): Streaming execution audit trail with level filters and keyword search.
- **Dedicated Dual Agent Controls**:
  - Separate `Start Paper Agent` / `Pause Paper Agent` buttons.
  - Separate `Start Real Agent` / `Pause Real Agent` buttons.
  - Both agents execute the **exact same quantitative principles** (ILSME Sniper strategy, 1.5% sizing, 3% drawdown stop).
- **Live Angel One RMS Balance Fetching**: Direct query to Angel One's `rmsLimit()` endpoint (`net`, `availablecash`, `collateral`, `utiliseddebits`) with manual or auto-sync.

---

## 2. Directory Layout

```
options/
├── frontend/                  # Modern React UI (Vite, Vanilla CSS, Lucide Icons)
│   ├── src/
│   │   ├── components/
│   │   │   ├── Header.jsx         # Controls, heartbeat, mode switch & panic switch
│   │   │   ├── MetricsHud.jsx     # Real-time P&L, Equity, Margin, Risk Drawdown gauge
│   │   │   ├── MarketRadar.jsx    # Spot NIFTY, BANKNIFTY, SENSEX, VWAP & levels
│   │   │   ├── SniperMonitor.jsx  # ILSME state machine & trigger simulator
│   │   │   ├── PositionsTable.jsx # Derivatives positions with surgical liquidation
│   │   │   ├── OrdersTable.jsx    # Working & filled orders audit trail
│   │   │   ├── EventConsole.jsx   # Live event console with search filter
│   │   │   └── Modals.jsx         # Mode switch & panic confirmation modals
│   │   ├── App.jsx                # Reactive WebSocket telemetry coordinator
│   │   └── index.css              # Cyber-fintech dark glassmorphism design system
│   ├── vite.config.js         # Proxy configuration to FastAPI backend (port 8000)
│   └── package.json
├── smartapi_trader/
│   ├── config/
│   │   ├── settings.yaml      # Broker credentials, risk limits, trading parameters
│   │   └── symbols.yaml       # Index tokens, lot sizes, exchange segments
│   ├── core/
│   │   ├── event_bus.py       # Async pub/sub event router
│   │   ├── events.py          # Event dataclasses (Tick, Bar, Signal, Order, Fill)
│   │   └── state_manager.py   # Centralized position, order, and P&L state tracker
│   ├── data/
│   │   ├── instrument_loader.py # Resilient scrip master loader & SQLite indexer
│   │   ├── stream_client.py   # SmartWebSocketV2 wrapper with auto-reconnect
│   │   └── candle_builder.py  # Real-time tick-to-ohlcv aggregator (3m, 15m, VWAP)
│   ├── strategy/
│   │   ├── base_strategy.py   # Abstract strategy class
│   │   └── sniper_ilsme.py    # Institutional Liquidity Sweep & Momentum Expansion logic
│   ├── risk/
│   │   └── risk_manager.py    # Position sizing, daily drawdown, hard limits, circuit breakers
│   ├── execution/
│   │   ├── base_engine.py     # Abstract execution engine interface
│   │   ├── paper_engine.py    # In-memory execution simulation with slippage/latency modeling
│   │   └── live_smartapi.py   # Production Angel One REST API integration (<=10 req/s)
│   ├── web/
│   │   └── app.py             # FastAPI server with WebSocket state streaming & React serving
│   └── utils/
│       ├── auth.py            # TOTP auto-generation and JWT session refresher
│       └── logger.py          # Loguru structured logging with daily file rotation
├── main.py                    # Orchestration entry point
└── requirements.txt
```

---

## 3. Quantitative Strategy Mechanics: ILSME Sniper

Naked options buying during consolidation suffers from negative expectancy due to rapid theta decay ($\Theta = \partial V / \partial t$) and bid-ask friction. The **Institutional Liquidity Sweep and Momentum Expansion (ILSME)** framework targets low-frequency, high-impulse turning points:

1. **15-Minute Macro Timeframe**:
   - Monitors Previous Day High (PDH), Previous Day Low (PDL), and Session Extremes.
   - **Liquidity Sweep**: Price breaches the extreme to trigger stop orders and breakout buyers/sellers, but closes back inside the prior range with a prominent rejection wick ($\text{wick} \ge 30\%$ of total candle range).
2. **3-Minute Micro Timeframe**:
   - **Market Structure Shift (MSS)**: Strong displacement bar crossing the session Volume-Weighted Average Price (VWAP) in the reversal direction.
   - **Fair Value Gap (FVG)**: Imbalance where Candle 3 does not overlap Candle 1:
     - Bullish FVG: $\text{Candle 3 Low} > \text{Candle 1 High}$
     - Bearish FVG: $\text{Candle 3 High} < \text{Candle 1 Low}$
   - **Limit Entry**: Enters on price retracement into the FVG boundary.
3. **Volume Filter**:
   - Target option contract tick volume must exceed $1.8 \times$ its 20-period moving average.
4. **Dynamic Strike Selection & SEBI Compliance**:
   - Targets ATM or immediate ITM options with delta $\Delta \in [0.48, 0.60]$.
   - **Nifty 50**: Weekly expiries (Lot size: 65)
   - **Bank Nifty**: Monthly contracts exclusively (Lot size: 30)
   - **Sensex**: Weekly expiries (Lot size: 20)
   - **Morning 0-DTE Protection**: On expiration days, trading 0-DTE contracts before 13:00 IST is blocked to prevent morning theta crush; orders automatically roll to the subsequent contract cycle.

---

## 4. Risk Engineering & Capital Preservation

Sustainable account growth requires minimizing portfolio variance ($\sigma^2$) to eliminate volatility drag:

$$R_{\text{compound}} \approx \mu - \frac{\sigma^2}{2}$$

### Position Sizing Formulation
For liquid capital $C_t$ and risk fraction $\alpha = 0.015$ (1.5% of equity):

$$R_{\text{trade}} = C_t \times \alpha$$
$$\text{Unit Risk} = P_{\text{entry}} - P_{\text{stop}}$$
$$N = \left\lfloor \frac{R_{\text{trade}}}{\text{Unit Risk} \times L} \right\rfloor$$

If $N = 0$, the risk manager rejects the order.

### Multi-Stage Position Management
- **Initial Hard Stop-Loss**: Placed at displacement candle invalidation (~10%–15% option premium decline).
- **Stage 1 (Breakeven Trigger)**: At $+1.0R$ profit, the stop-loss moves to the entry price ($P_{\text{entry}}$), eliminating all downside risk.
- **Stage 2 (Partial Profit Booking)**: At $+2.0R$ profit, 60% of open lots are closed via marketable limit order.
- **Stage 3 (Swing Trailing)**: The remaining 40% trail closed 3-minute candle swings until target invalidation or market close.

### Hard Account Circuit Breakers
| Risk Parameter | Enforcement Boundary | Automated System Action |
|---|---|---|
| **Max Trades Per Day** | Exactly 2 completed trades | Halts signal evaluation for the session |
| **Max Daily Drawdown** | 3.0% of starting equity | Liquidates positions, cancels orders, shuts down engine |
| **Consecutive Loss Circuit**| 2 consecutive losses | Locks order generation until the next trading day |
| **Midday Chop Filter** | 11:15 to 13:30 IST | Rejects new entries; manages existing positions only |
| **Mandatory EOD Square-Off**| 15:12 IST | Cancels open orders, closes all positions at market |
| **Slippage Threshold** | $> 2.0\%$ deviation | Aborts entry to avoid chasing spikes |

---

## 5. Quickstart & Installation

### Step 1: Create Virtual Environment & Install Dependencies
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2: Configure Settings
Edit `smartapi_trader/config/settings.yaml` with your Angel One SmartAPI credentials:
```yaml
broker:
  api_key: "YOUR_SMARTAPI_API_KEY"
  client_code: "YOUR_CLIENT_CODE"
  pin: "YOUR_PIN"
  totp_secret: "YOUR_BASE32_TOTP_SECRET"

execution:
  execution_mode: "PAPER"   # Set to "PAPER" for simulation or "LIVE" for broker routing
```

> **Note**: If left with placeholder credentials, the system automatically runs in high-fidelity simulated **PAPER** mode with simulated tick streaming so you can explore all features immediately.

### Step 3: Launch Engine & Operator Web Dashboard

#### Unified Production Server (FastAPI + Built React SPA)
```bash
python main.py
```
Open **`http://localhost:8000`** in your browser.

#### Vite React Development Server (Hot Module Reloading)
In a separate terminal:
```bash
cd frontend
npm run dev
```
Open **`http://localhost:3000`** (requests to `/api` and `/ws` automatically proxy to the Python backend on port 8000).

To rebuild the React production bundle after making frontend changes:
```bash
cd frontend
npm run build
```

---

## 6. Operator Web Control Plane Features

- **Mode Segregation Display**:
  - `PAPER TRADING [Simulated]` (Cyan)
  - `LIVE TRADING [Angel One RMS]` (Crimson/Emerald)
  - Interactive safety confirmation modal before switching to LIVE.
- **Global Panic / Kill Switch**: Prominent red button that immediately halts the strategy, cancels all pending orders, and liquidates active positions at market.
- **Real-Time Telemetry HUD**: Live P&L (₹ and %), Account Equity, Available Margin, 3.0% Daily Drawdown Gauge, and Trade Budget Counter ("X of 2 Trades Taken").
- **Market Radar**: Live spot prices, session VWAP, and PDH/PDL structural levels for NIFTY, BANKNIFTY, and SENSEX.
- **Sniper State Machine**: Visual state indicator displaying:
  $$\text{Scanning} \longrightarrow \text{Sweep Detected} \longrightarrow \text{FVG Armed} \longrightarrow \text{In Trade}$$
- **Interactive Trigger Simulator**: Buttons to fire test sniper setups for Nifty CE/PE and Bank Nifty CE directly from the UI.
- **Active Positions Table**: Real-time position tracking with individual surgical **Liquidate** buttons.
- **Live Event Console**: Real-time auto-scrolling log console streaming Loguru telemetry over WebSockets.

---

## 7. Production Deployment (Linux VPS / systemd)

For production deployment on an Ubuntu 22.04 LTS VPS (e.g. AWS `ap-south-1` in Mumbai with an Elastic IP whitelisted on SmartAPI):

### 1. Install systemd Service
Copy `smartapi_trader.service` to `/etc/systemd/system/`:
```bash
sudo cp smartapi_trader.service /etc/systemd/system/smartapi_trader.service
sudo systemctl daemon-reload
sudo systemctl enable smartapi_trader
sudo systemctl start smartapi_trader
```

### 2. Secure Access via SSH Tunnel
Access the dashboard securely without exposing ports publicly:
```bash
ssh -L 8000:localhost:8000 user@your_vps_ip
```
Then navigate to `http://localhost:8000` in your local browser.
