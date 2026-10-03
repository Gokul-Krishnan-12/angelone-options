import React, { useState } from 'react';
import {
  BookOpen,
  Zap,
  TrendingUp,
  Target,
  Shield,
  Layers,
  Clock,
  CheckCircle2,
  AlertTriangle,
  ArrowRight,
  Crosshair,
  BarChart3,
  Cpu,
  Lock,
  GitBranch
} from 'lucide-react';

export default function SystemWorkflow() {
  const [activeTab, setActiveTab] = useState('scenarios');

  const tabs = [
    { id: 'scenarios', label: '1. Trading Scenarios (Dual Engine)', icon: Target },
    { id: 'workflow', label: '2. System Pipeline Workflow', icon: GitBranch },
    { id: 'strikes', label: '3. Strike Selection & Expiry', icon: Layers },
    { id: 'risk_math', label: '4. 1.5% Risk & Multi-Stage Brackets', icon: Shield },
    { id: 'shields', label: '5. Hard Circuit Breakers', icon: Lock },
  ];

  return (
    <div className="page-container" style={{ maxWidth: '1400px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border-light)' }}>
        <div className="brand-icon-box" style={{ width: '42px', height: '42px' }}>
          <BookOpen size={22} />
        </div>
        <div>
          <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#fff' }}>
            System Workflow & Dual-Engine Trading Logic
          </h2>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Mathematical specifications, dual-engine setups (ILSME Sweeps + Momentum ORB Breakouts), dynamic strike mapping, and hard risk boundaries
          </p>
        </div>
      </div>

      {/* Tabs */}
      <div className="tab-row" style={{ marginTop: '0.5rem' }}>
        {tabs.map((t) => {
          const Icon = t.icon;
          return (
            <button
              key={t.id}
              className={`tab-btn ${activeTab === t.id ? 'active' : ''}`}
              onClick={() => setActiveTab(t.id)}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
            >
              <Icon size={15} />
              <span>{t.label}</span>
            </button>
          );
        })}
      </div>

      {/* TAB 1: TRADING SCENARIOS */}
      {activeTab === 'scenarios' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Core Philosophy Box */}
          <div className="hud-card" style={{ borderLeft: '4px solid var(--accent-orange)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff' }}>
                Why Dual-Engine Architecture (ILSME Sweeps + Momentum Trend Breakouts)?
              </h3>
              <span className="pill-badge" style={{ background: 'rgba(237, 76, 34, 0.15)', color: 'var(--accent-orange)', border: '1px solid var(--accent-orange)' }}>
                HYBRID REGIME ADAPTABILITY
              </span>
            </div>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.5rem' }}>
              Options markets exhibit two distinct market regimes: <strong>Range-bound Liquidity Sweeps</strong> (70% of days) and <strong>Sustained One-Way Trend Days</strong> (30% of days). Single-engine sweep models starve on clean trend days, while pure trend-following models suffer drawdown in range sweeps. The dual-engine unifies institutional liquidity sweeps with a high-conviction 15-minute Opening Range Breakout (ORB) + VWAP trend engine to harvest alpha in all market conditions.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
            {/* Bullish Call Scenario A: Sweep */}
            <div className="hud-card" style={{ borderColor: 'rgba(30, 215, 96, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#1ed760', color: '#000', fontWeight: 700 }}>
                  SCENARIO A: LONG CALL (BUY CE)
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>ENGINE 1: REVERSAL SWEEP</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>Step 1: 15m Macro Liquidity Sweep</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Index spot pierces below Previous Day Low (PDL) or Morning Low, grabbing liquidity, but <strong>closes back above</strong> the level with a prominent lower rejection wick (wick ≥ 30% of total bar range).
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>Step 2: 3m Micro MSS & Displacement across VWAP</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    On the 3-minute chart, price displaces aggressively upward across the intraday Volume-Weighted Average Price (VWAP) and closes above the recent swing high, confirming a Market Structure Shift (MSS).
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>Step 3: Bullish Fair Value Gap (FVG) Imbalance</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Displacement generates an unfilled Fair Value Gap where <strong>Candle 3 Low &gt; Candle 1 High</strong>, leaving an institutional imbalance zone [C1 High, C3 Low].
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>Step 4: Option Volume Spike & Entry</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    ATM Call tick volume clears <strong>1.8× its 20-period volume SMA</strong>. Execution router submits a Limit/Market Buy order as spot retraces into the upper FVG boundary.
                  </p>
                </div>
              </div>
            </div>

            {/* Bearish Put Scenario B: Sweep */}
            <div className="hud-card" style={{ borderColor: 'rgba(244, 63, 94, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#f43f5e', color: '#fff', fontWeight: 700 }}>
                  SCENARIO B: SHORT PUT (BUY PE)
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>ENGINE 1: REVERSAL SWEEP</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>Step 1: 15m Macro Liquidity Sweep</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Index spot pierces above Previous Day High (PDH) or Morning High, trapping breakout buyers, but <strong>closes back below</strong> the level with a prominent upper rejection wick (wick ≥ 30% of total bar range).
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>Step 2: 3m Micro MSS & Displacement below VWAP</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    On the 3-minute chart, price displaces aggressively downward below session VWAP and violates the recent swing low, confirming institutional shift to the downside.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>Step 3: Bearish Fair Value Gap (FVG) Imbalance</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Displacement generates a bearish imbalance where <strong>Candle 3 High &lt; Candle 1 Low</strong>, leaving an imbalance zone [C3 High, C1 Low].
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>Step 4: Option Volume Spike & Entry</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    ATM Put tick volume clears <strong>1.8× its 20-period volume SMA</strong>. Execution router submits a Limit/Market Buy order for the ATM Put as spot pulls back into the lower FVG boundary.
                  </p>
                </div>
              </div>
            </div>

            {/* Bullish Call Scenario C: Momentum ORB */}
            <div className="hud-card" style={{ borderColor: 'rgba(56, 189, 248, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#38bdf8', color: '#000', fontWeight: 700 }}>
                  SCENARIO C: TREND CALL (BUY CE)
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>ENGINE 2: MOMENTUM ORB</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: '#38bdf8' }}>Step 1: 15-Minute Opening Range Establishment</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    The 09:15–09:30 IST opening 15m candle establishes initial session boundary [<span className="mono">OR_High, OR_Low</span>]. The engine tracks breakout expansion past 09:30.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#38bdf8' }}>Step 2: 3m Candle Body Close Above OR_High</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    A subsequent 3-minute candle records a decisive close above the Opening Range High, signaling institutional trend continuation rather than false wick deviation.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#38bdf8' }}>Step 3: Dual Trend Filter (VWAP + 50-EMA)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Confirmation requires spot price to be strictly above both <strong>Session VWAP</strong> and the <strong>50-period EMA</strong>, guaranteeing alignment with institutional orderflow.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#38bdf8' }}>Step 4: ATM CE Momentum Entry & Rapid Trail</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Direct execution on ATM Call option. Initial Stop-Loss is positioned at the 3m breakout bar low or VWAP (whichever is closer).
                  </p>
                </div>
              </div>
            </div>

            {/* Bearish Put Scenario D: Momentum ORB */}
            <div className="hud-card" style={{ borderColor: 'rgba(217, 70, 239, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#d946ef', color: '#fff', fontWeight: 700 }}>
                  SCENARIO D: TREND PUT (BUY PE)
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>ENGINE 2: MOMENTUM ORB</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: '#d946ef' }}>Step 1: 15-Minute Opening Range Establishment</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    The 09:15–09:30 IST opening 15m candle establishes initial session boundary [<span className="mono">OR_High, OR_Low</span>].
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#d946ef' }}>Step 2: 3m Candle Body Close Below OR_Low</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    A subsequent 3-minute candle records a decisive close below the Opening Range Low, signaling sustained institutional downside liquidation.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#d946ef' }}>Step 3: Dual Trend Filter (VWAP + 50-EMA)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Confirmation requires spot price to be strictly below both <strong>Session VWAP</strong> and the <strong>50-period EMA</strong>, filtering out counter-trend bull traps.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#d946ef' }}>Step 4: ATM PE Momentum Entry & Rapid Trail</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Direct execution on ATM Put option. Initial Stop-Loss is positioned at the 3m breakout bar high or VWAP (whichever is closer).
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: SYSTEM PIPELINE WORKFLOW */}
      {activeTab === 'workflow' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="hud-card">
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff', marginBottom: '0.75rem' }}>
              Unidirectional Event-Driven Pipeline
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
              The system operates on an internal asynchronous Pub/Sub Event Bus with zero polling loops. Market events flow strictly in one direction:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {[
                { step: '1. Market Data Ingestion (WebSocket V2)', desc: 'SmartWebSocketV2 streams binary packets for spot index tokens and active ATM strikes; parses LTP, Best 5 Bid/Ask spread, and cumulative tick volume.' },
                { step: '2. Candle Aggregator & Technical State', desc: 'Tick events aggregate into rolling 3-minute and 15-minute OHLCV candles, continuously computing session VWAP (∑ P×V / ∑ V), 50-EMA, and Opening Range boundaries.' },
                { step: '3. Dual Quantitative Strategy Engine', desc: 'Simultaneously evaluates Engine 1 (15m Macro Sweep + 3m MSS + FVG retracement) and Engine 2 (15m ORB Breakout + VWAP/EMA trend alignment). User toggles in Settings can isolate either engine.' },
                { step: '4. Mathematical Risk Engine', desc: 'Verifies liquid capital, enforces exact 1.5% fixed fractional sizing, verifies daily 3.0% drawdown limit, checks 2-trade daily quota, and validates margin requirements.' },
                { step: '5. Dynamic Strike Resolver & Execution Venue', desc: 'Resolves live ATM contract per SEBI expiry rules; routes orders through Abstract Execution Engine: PaperEngine applies realistic slippage (Ask + 0.2×spread); LiveEngine signs JWT headers to Angel One endpoints.' },
                { step: '6. State Telemetry Broadcast & Telegram Alerts', desc: 'StateManager updates cash, equity, active brackets, and broadcasts real-time telemetry over WebSockets to this React control plane and instant Telegram notifications.' },
              ].map((item, idx) => (
                <div key={idx} className="spot-tile" style={{ display: 'flex', alignItems: 'flex-start', gap: '1rem' }}>
                  <div className="brand-icon-box" style={{ width: '28px', height: '28px', fontSize: '0.8rem', fontWeight: 800 }}>
                    {idx + 1}
                  </div>
                  <div>
                    <strong style={{ color: '#fff', fontSize: '0.88rem' }}>{item.step}</strong>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: '0.2rem' }}>{item.desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: STRIKE SELECTION & EXPIRY RULES */}
      {activeTab === 'strikes' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="hud-card">
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff', marginBottom: '0.5rem' }}>
              Dynamic Contract Resolution & SEBI Derivative Compliance
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Trading far Out-of-The-Money (OTM) options undermines naked buying because low delta (Δ &lt; 0.30) requires massive underlying moves to overcome theta decay and bid-ask spread friction. The system resolves strictly ATM or +1 ITM strikes.
            </p>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Index Underlying</th>
                    <th>Exchange</th>
                    <th>Lot Size</th>
                    <th>Expiry Cycle</th>
                    <th>Strike Step</th>
                    <th>Preferred Delta (Δ)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="mono font-bold" style={{ color: '#fff' }}>NIFTY 50</td>
                    <td>NSE (NFO)</td>
                    <td>65 units</td>
                    <td><span className="pill-badge" style={{ background: '#0284c7', color: '#fff' }}>Weekly (Thu)</span></td>
                    <td className="mono">50 pts</td>
                    <td className="mono">0.48 – 0.55 (ATM / +1 ITM)</td>
                  </tr>
                  <tr>
                    <td className="mono font-bold" style={{ color: '#fff' }}>BANK NIFTY</td>
                    <td>NSE (NFO)</td>
                    <td>30 units</td>
                    <td><span className="pill-badge" style={{ background: '#f59e0b', color: '#000' }}>Monthly Only (SEBI)</span></td>
                    <td className="mono">100 pts</td>
                    <td className="mono">0.50 – 0.58 (ATM / +1 ITM)</td>
                  </tr>
                  <tr>
                    <td className="mono font-bold" style={{ color: '#fff' }}>BSE SENSEX</td>
                    <td>BSE (BFO)</td>
                    <td>20 units</td>
                    <td><span className="pill-badge" style={{ background: '#a855f7', color: '#fff' }}>Weekly (Fri)</span></td>
                    <td className="mono">100 pts</td>
                    <td className="mono">0.48 – 0.55 (ATM / +1 ITM)</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="spot-tile" style={{ marginTop: '1.25rem', borderLeft: '3px solid var(--accent-orange)' }}>
              <strong style={{ color: 'var(--accent-orange)' }}>Morning 0-DTE Expiry Theta Protection Protocol:</strong>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
                On expiration days, trading 0-days-to-expiry contracts prior to <strong>13:00 IST</strong> is strictly blocked to eliminate rapid morning theta crush. Signals triggered before 13:00 IST automatically resolve to the <strong>subsequent contract cycle (next weekly/monthly expiry)</strong>.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: RISK MATH & BRACKETS */}
      {activeTab === 'risk_math' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="hud-card">
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff', marginBottom: '0.5rem' }}>
              Mathematical Position Sizing Formulation
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Position sizing is dynamically computed on each setup using exact liquid capital:
            </p>

            <div style={{ background: 'var(--bg-dark)', padding: '1rem', borderRadius: '10px', border: '1px solid var(--border-light)', fontFamily: 'var(--font-mono)', fontSize: '0.88rem' }}>
              <div style={{ color: 'var(--accent-orange)', marginBottom: '0.35rem' }}>
                R_trade = Capital_t × 0.015  (Exact 1.5% capital risk per trade)
              </div>
              <div style={{ color: '#fff', marginBottom: '0.35rem' }}>
                Unit_Risk = Entry_Price - Stop_Loss_Price
              </div>
              <div style={{ color: 'var(--accent-emerald)' }}>
                Lots = floor( R_trade / (Unit_Risk × Lot_Size) )
              </div>
            </div>

            <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff', marginTop: '1.5rem', marginBottom: '0.75rem' }}>
              3-Stage Multi-Tier Bracket Trade Management
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>INITIAL DEFENSE</div>
                <div style={{ color: 'var(--accent-red)', fontWeight: 700, margin: '0.25rem 0' }}>Displacement SL (10% - 15%)</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Placed at the low/high of the 3m displacement or breakout candle, capping maximum single-trade downside to exactly 1.5% of equity.
                </p>
              </div>

              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>STAGE 1: RISK REMOVAL</div>
                <div style={{ color: 'var(--accent-orange)', fontWeight: 700, margin: '0.25rem 0' }}>Breakeven Shift at +0.6R / +1.0R</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  When floating gain achieves initial expansion (+0.6R in ORB / +1.0R in Sweeps), Stop-Loss shifts to Entry Price + Brokerage, neutralizing risk.
                </p>
              </div>

              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>STAGE 2: PROFIT HARVEST</div>
                <div style={{ color: 'var(--accent-emerald)', fontWeight: 700, margin: '0.25rem 0' }}>Partial TP at +2.0R to +2.2R</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  At +2.0R to +2.2R gain, 60% of open lots are exited to lock in compounding alpha. Remaining 40% runner trails closed 3m swing pivots.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 5: HARD CIRCUIT BREAKERS */}
      {activeTab === 'shields' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="hud-card">
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff', marginBottom: '0.5rem' }}>
              Automated Account Shields & Safeguards
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Strict risk boundaries prevent overtrading, tilt, and catastrophic tail risk across both Paper and Live modes:
            </p>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Safeguard Rule</th>
                    <th>Enforcement Boundary</th>
                    <th>Automated System Response</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Daily Trade Quota</strong></td>
                    <td className="mono">Exactly 2 completed trades / day</td>
                    <td>Disables entry evaluation for the remainder of the session.</td>
                  </tr>
                  <tr>
                    <td><strong>Max Daily Drawdown</strong></td>
                    <td className="mono" style={{ color: 'var(--accent-red)' }}>3.0% of day start equity</td>
                    <td>Instantly liquidates all open positions, cancels pending orders, and halts engine.</td>
                  </tr>
                  <tr>
                    <td><strong>Consecutive Loss Circuit</strong></td>
                    <td className="mono">2 consecutive losses</td>
                    <td>Locks order placement until the next trading session.</td>
                  </tr>
                  <tr>
                    <td><strong>Midday Chop Filter</strong></td>
                    <td className="mono">11:15 to 13:30 IST</td>
                    <td>Blocks all new entries; active brackets continue managing trailing stops.</td>
                  </tr>
                  <tr>
                    <td><strong>Mandatory EOD Square-Off</strong></td>
                    <td className="mono">15:12 IST</td>
                    <td>Cancels pending orders and closes all remaining positions at market.</td>
                  </tr>
                  <tr>
                    <td><strong>Live Safety Capital Floor</strong></td>
                    <td className="mono">₹50,000.00 Min Balance</td>
                    <td>Live trader strictly blocks live orders if Angel One funds &lt; ₹50,000.</td>
                  </tr>
                  <tr>
                    <td><strong>Broker Rate Limiter</strong></td>
                    <td className="mono">≤ 10 requests / sec</td>
                    <td>Token-bucket throttling avoids Angel One HTTP 429 rate limit errors.</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

