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
    { id: 'scenarios', label: '1. Trading Scenarios (Call / Put)', icon: Target },
    { id: 'workflow', label: '2. System Pipeline Workflow', icon: GitBranch },
    { id: 'strikes', label: '3. Strike Selection & Expiry', icon: Layers },
    { id: 'risk_math', label: '4. 1.5% Risk & 3-Stage Brackets', icon: Shield },
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
            System Workflow & Algorithmic Trading Logic
          </h2>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Mathematical specifications, entry directives, multi-timeframe liquidity sweep mechanics, and risk protocols
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
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff', marginBottom: '0.4rem' }}>
              Why Low-Frequency Sniper Options Buying?
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', lineHeight: 1.6 }}>
              Frequent intraday scalping on index options suffers from negative statistical expectancy due to theta decay (<span className="mono">Θ = ∂V/∂t</span>) and crossing the bid-ask spread. The <strong>Institutional Liquidity Sweep and Momentum Expansion (ILSME)</strong> framework executes exclusively when a major directional impulse offsets decay and triggers rapid gamma expansion (<span className="mono">Γ = ∂Δ/∂S</span>).
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
            {/* Bullish Call Scenario */}
            <div className="hud-card" style={{ borderColor: 'rgba(30, 215, 96, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#1ed760', color: '#000' }}>
                  SCENARIO A: LONG CALL (BUY CE)
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>BULLISH REVERSAL SWEEP</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>Step 1: 15m Macro Liquidity Sweep</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Index spot pierces below Previous Day Low (PDL) or Morning Session Low, triggering stop-losses and breakout sellers, but <strong>closes back above</strong> the level with a prominent lower rejection wick (wick ≥ 30% of total bar range).
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
                  <strong style={{ color: 'var(--accent-emerald)' }}>Step 4: Option Volume Spike & Limit Entry</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    ATM Call tick volume clears <strong>1.8× its 20-period volume SMA</strong>. Execution router submits a Limit Buy order as spot retraces into the upper FVG boundary.
                  </p>
                </div>
              </div>
            </div>

            {/* Bearish Put Scenario */}
            <div className="hud-card" style={{ borderColor: 'rgba(244, 63, 94, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#f43f5e', color: '#fff' }}>
                  SCENARIO B: SHORT PUT (BUY PE)
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>BEARISH REVERSAL SWEEP</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>Step 1: 15m Macro Liquidity Sweep</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Index spot pierces above Previous Day High (PDH) or Morning Session High, trapping breakout buyers, but <strong>closes back below</strong> the level with a prominent upper rejection wick (wick ≥ 30% of total bar range).
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
                  <strong style={{ color: 'var(--accent-red)' }}>Step 4: Option Volume Spike & Limit Entry</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    ATM Put tick volume clears <strong>1.8× its 20-period volume SMA</strong>. Execution router submits a Limit Buy order for the ATM Put as spot pulls back into the lower FVG boundary.
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
              The system operates on an internal asynchronous Pub/Sub Event Bus. Data flows unidirectionally without polling loops:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {[
                { step: '1. Market Data Ingestion', desc: 'SmartWebSocketV2 streams binary packets for spot tokens and active ATM strikes; parses LTP, Best 5 Bid/Ask spread, and cumulative tick volume.' },
                { step: '2. Candle Aggregator', desc: 'Tick events aggregate into rolling 3-minute and 15-minute OHLCV candles, continuously computing session VWAP (∑ P×V / ∑ V).' },
                { step: '3. Quantitative Strategy Engine', desc: 'Evaluates structural sweeps on 15m closed bars, confirms 3m displacement across VWAP, arms FVG retracement zones, and checks contract volume multiplier.' },
                { step: '4. Mathematical Risk Engine', desc: 'Verifies liquid capital, enforces exact 1.5% fixed fractional sizing, verifies daily 3.0% drawdown limit, checks 2-trade daily quota, and validates margin.' },
                { step: '5. Abstract Execution Venue', desc: 'Routes validated orders through ExecutionEngine(ABC): PaperEngine applies live Ask + (Spread × 0.2) slippage and 200ms delay; LiveEngine signs JWT headers and routes to Angel One REST endpoints (≤10 req/s).' },
                { step: '6. State Telemetry Broadcast', desc: 'StateManager updates cash, equity, active brackets, and broadcasts real-time telemetry over WebSockets to this React control plane.' },
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
              Trading far Out-of-The-Money (OTM) options undermines naked buying because low delta (Δ &lt; 0.30) requires massive underlying moves to overcome theta decay and bid-ask spread friction.
            </p>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Index Underlying</th>
                    <th>Exchange</th>
                    <th>Lot Size</th>
                    <th>Expiry Cycle</th>
                    <th>Preferred Delta (Δ)</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="mono font-bold" style={{ color: '#fff' }}>NIFTY 50</td>
                    <td>NSE (NFO)</td>
                    <td>65 units</td>
                    <td><span className="pill-badge" style={{ background: '#0284c7', color: '#fff' }}>Weekly</span></td>
                    <td className="mono">0.48 – 0.55 (ATM / +1 ITM)</td>
                  </tr>
                  <tr>
                    <td className="mono font-bold" style={{ color: '#fff' }}>BANK NIFTY</td>
                    <td>NSE (NFO)</td>
                    <td>30 units</td>
                    <td><span className="pill-badge" style={{ background: '#f59e0b', color: '#000' }}>Monthly Only (SEBI)</span></td>
                    <td className="mono">0.50 – 0.58 (ATM / +1 ITM)</td>
                  </tr>
                  <tr>
                    <td className="mono font-bold" style={{ color: '#fff' }}>BSE SENSEX</td>
                    <td>BSE (BFO)</td>
                    <td>20 units</td>
                    <td><span className="pill-badge" style={{ background: '#a855f7', color: '#fff' }}>Weekly</span></td>
                    <td className="mono">0.48 – 0.55 (ATM / +1 ITM)</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="spot-tile" style={{ marginTop: '1.25rem', borderLeft: '3px solid var(--accent-orange)' }}>
              <strong style={{ color: 'var(--accent-orange)' }}>Morning 0-DTE Expiry Theta Protection Protocol:</strong>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
                On expiration days, trading 0-days-to-expiry contracts prior to <strong>13:00 IST</strong> is strictly blocked to eliminate morning theta crush. Signals triggered before 13:00 IST automatically resolve to the <strong>subsequent contract cycle (next weekly/monthly expiry)</strong>.
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
                <div style={{ color: 'var(--accent-red)', fontWeight: 700, margin: '0.25rem 0' }}>Hard Displacement SL (~12%)</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Placed at technical invalidation of the 3m displacement bar, typically representing a 10%–15% decline in option premium.
                </p>
              </div>

              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>STAGE 1: RISK REMOVAL</div>
                <div style={{ color: 'var(--accent-orange)', fontWeight: 700, margin: '0.25rem 0' }}>Breakeven Shift at +1.0R</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  When floating gain hits +1.0× R_trade, Stop-Loss shifts to the entry price, creating a completely risk-free position.
                </p>
              </div>

              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>STAGE 2: PROFIT HARVEST</div>
                <div style={{ color: 'var(--accent-emerald)', fontWeight: 700, margin: '0.25rem 0' }}>Lock 60% Lots at +2.0R</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  At +2.0R profit, 60% of open lots are exited at marketable limit to secure capital compounding. Remaining 40% trail closed 3m candle swings.
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
              Strict risk boundaries prevent overtrading, tilt, and catastrophic tail risk:
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
                    <td className="mono">Exactly 2 completed trades</td>
                    <td>Disables sniper evaluation for the rest of the session.</td>
                  </tr>
                  <tr>
                    <td><strong>Max Daily Drawdown</strong></td>
                    <td className="mono" style={{ color: 'var(--accent-red)' }}>3.0% of day start equity</td>
                    <td>Instantly liquidates all positions, cancels orders, and shuts down engine.</td>
                  </tr>
                  <tr>
                    <td><strong>Consecutive Loss Circuit</strong></td>
                    <td className="mono">2 consecutive losses</td>
                    <td>Locks order placement until the next trading day.</td>
                  </tr>
                  <tr>
                    <td><strong>Midday Chop Filter</strong></td>
                    <td className="mono">11:15 to 13:30 IST</td>
                    <td>Rejects all new entries; manages existing positions only.</td>
                  </tr>
                  <tr>
                    <td><strong>Mandatory EOD Square-Off</strong></td>
                    <td className="mono">15:12 IST</td>
                    <td>Cancels pending orders and closes all positions at market.</td>
                  </tr>
                  <tr>
                    <td><strong>Broker Rate Limiter</strong></td>
                    <td className="mono">≤ 10 requests / sec</td>
                    <td>Token-bucket throttling avoids Angel One 429 throttling.</td>
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
