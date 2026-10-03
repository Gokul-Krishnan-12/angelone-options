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
    { id: 'scenarios', label: '1. Dual Quantitative Engines (ILSME + ORB)', icon: Target },
    { id: 'spreads', label: '2. Vertical Debit Spreads & Greeks', icon: Layers },
    { id: 'workflow', label: '3. Real-Time Execution Pipeline', icon: GitBranch },
    { id: 'risk_math', label: '4. Capital Math & Multi-Stage Brackets', icon: Shield },
    { id: 'shields', label: '5. Circuit Breakers & Friction Audit', icon: Lock },
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
            Institutional Quantitative Options Architecture
          </h2>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
            Mathematical specifications: Vertical Debit Spreads, ILSME Stop-Limit triggers, ORB Retest rules, 15m Stagnation Time-Exits, and 4.5% Hard Circuit Breakers.
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

      {/* TAB 1: DUAL ENGINES */}
      {activeTab === 'scenarios' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
          {/* Core Philosophy Box */}
          <div className="hud-card" style={{ borderLeft: '4px solid var(--accent-orange)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem' }}>
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff' }}>
                Friction-Hardened Dual Engine (ILSME + Momentum ORB)
              </h3>
              <span className="pill-badge" style={{ background: 'rgba(237, 76, 34, 0.15)', color: 'var(--accent-orange)', border: '1px solid var(--accent-orange)' }}>
                ZERO ADVERSE SELECTION
              </span>
            </div>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.5rem' }}>
              The architecture operates two distinct, friction-hardened quantitative engines: <strong>Engine 1 (Institutional Liquidity Sweep & Momentum Expansion - ILSME)</strong> for high-probability mean-reversions at session extremes, and <strong>Engine 2 (Momentum Opening Range Breakout - ORB)</strong> for one-way trend expansions. Limit orders on deep FVG retracements are completely eliminated and replaced with <strong>Displacement Stop-Limits</strong> and <strong>1-Candle Boundary Retests</strong> to eradicate adverse execution selection.
            </p>
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.5rem' }}>
            {/* Bullish Call Scenario A: ILSME */}
            <div className="hud-card" style={{ borderColor: 'rgba(30, 215, 96, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#1ed760', color: '#000', fontWeight: 700 }}>
                  ENGINE 1: BULLISH ILSME SWEEP
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>BULL DEBIT SPREAD</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>1. Macro Anchor (15m Candle Sweep)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    15m bar pierces Previous Day Low (PDL) or Morning Session Low and closes back inside with a rejection wick ≥ 30% of total candle range.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>2. Micro Shift (3m Displacement across VWAP)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    3m candle aggressively displaces across Session VWAP and violates the previous swing high, forming a 3-candle displacement sequence.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>3. Stop-Limit Entry (No Adverse Limit Fills)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Trigger order placed <strong>1 tick above the high of Candle 3</strong>. Eliminates deep FVG retracement deadlocks where fills only occurred on high-momentum failing reversals.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-emerald)' }}>4. Volume Delta Confirmation</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Spot/Futures Cumulative Volume Delta (CVD) confirmation, or option volume clears <strong>≥ 1.8× 20-period SMA</strong>.
                  </p>
                </div>
              </div>
            </div>

            {/* Bearish Put Scenario B: ILSME */}
            <div className="hud-card" style={{ borderColor: 'rgba(244, 63, 94, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#f43f5e', color: '#fff', fontWeight: 700 }}>
                  ENGINE 1: BEARISH ILSME SWEEP
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>BEAR DEBIT SPREAD</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>1. Macro Anchor (15m Candle Sweep)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    15m bar pierces Previous Day High (PDH) or Morning Session High and closes back inside with a rejection wick ≥ 30% of total candle range.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>2. Micro Shift (3m Displacement below VWAP)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    3m candle aggressively displaces downward below Session VWAP and breaks previous swing pivot low.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>3. Stop-Limit Entry</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Trigger order placed <strong>1 tick below the low of Candle 3</strong> upon displacement completion.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: 'var(--accent-red)' }}>4. Volume & CVD Filter</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Option contract volume ≥ 1.8× 20-period SMA with negative delta displacement.
                  </p>
                </div>
              </div>
            </div>

            {/* Bullish Call Scenario C: Momentum ORB */}
            <div className="hud-card" style={{ borderColor: 'rgba(56, 189, 248, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#38bdf8', color: '#000', fontWeight: 700 }}>
                  ENGINE 2: BULLISH MOMENTUM ORB
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>RANGE BREAKOUT</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: '#38bdf8' }}>1. Volatility Expansion Benchmark (09:15–09:30)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Opening 15m range must satisfy minimum volatility: <strong>NIFTY ≥ 45 pts; SENSEX ≥ 160 pts</strong>. Narrow ranges are filtered out as low-vol chop regimes.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#38bdf8' }}>2. Dual Trend Alignment (VWAP + 50 EMA)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Spot price must be strictly above both Session VWAP and the 50-period EMA.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#38bdf8' }}>3. Retest Validation (No Chase)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Prohibits blind entry on the immediate breakout bar. Requires a <strong>1-candle pullback that tests and holds the boundary</strong> without closing back inside the 15m range.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#38bdf8' }}>4. High-Conviction Spread Routing</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Routes Long ATM Call + Short OTM Call (+100 NIFTY / +300 SENSEX) or naked buying with SL ≤ 15 pts.
                  </p>
                </div>
              </div>
            </div>

            {/* Bearish Put Scenario D: Momentum ORB */}
            <div className="hud-card" style={{ borderColor: 'rgba(217, 70, 239, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
                <span className="pill-badge" style={{ background: '#d946ef', color: '#fff', fontWeight: 700 }}>
                  ENGINE 2: BEARISH MOMENTUM ORB
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>RANGE BREAKDOWN</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', fontSize: '0.82rem' }}>
                <div className="spot-tile">
                  <strong style={{ color: '#d946ef' }}>1. Volatility Benchmark (09:15–09:30)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Opening 15m range verified ≥ 45 pts (NIFTY) or ≥ 160 pts (SENSEX).
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#d946ef' }}>2. Dual Trend Alignment (VWAP + 50 EMA)</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Spot price must be strictly below Session VWAP and the 50-period EMA.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#d946ef' }}>3. Retest & Breakdown Confirmation</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    1-candle retest holds below OR Low without closing back inside the opening 15m envelope.
                  </p>
                </div>

                <div className="spot-tile">
                  <strong style={{ color: '#d946ef' }}>4. High-Conviction Spread Routing</strong>
                  <p style={{ color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Routes Long ATM Put + Short OTM Put (-100 NIFTY / -300 SENSEX).
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: VERTICAL DEBIT SPREADS & GREEKS */}
      {activeTab === 'spreads' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="hud-card">
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff', marginBottom: '0.5rem' }}>
              Primary Derivative Instrument Architecture: Vertical Debit Spreads
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Naked option buying suffers from aggressive intraday theta decay (Θ) and post-opening implied volatility crush. Converting entries into <strong>Intraday Vertical Debit Spreads</strong> finances 60%–70% of time decay and caps unit risk strictly below ₹600 per lot.
            </p>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Strategy Direction</th>
                    <th>Long Leg (ATM)</th>
                    <th>Short Leg (OTM Offset)</th>
                    <th>Strike Step</th>
                    <th>Theta (Θ) Offset</th>
                    <th>Net Max Unit Risk</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="font-bold" style={{ color: 'var(--accent-emerald)' }}>Bullish Setup (CE)</td>
                    <td className="mono">Long 1 ATM Call (Δ ≈ 0.50)</td>
                    <td className="mono">Short 1 OTM Call (Δ ≈ 0.25 - 0.30)</td>
                    <td className="mono">+100 pts (NIFTY) / +300 pts (SENSEX)</td>
                    <td className="mono" style={{ color: '#38bdf8' }}>60% – 70% Financed</td>
                    <td className="mono font-bold">&lt; ₹600 / lot</td>
                  </tr>
                  <tr>
                    <td className="font-bold" style={{ color: 'var(--accent-red)' }}>Bearish Setup (PE)</td>
                    <td className="mono">Long 1 ATM Put (Δ ≈ -0.50)</td>
                    <td className="mono">Short 1 OTM Put (Δ ≈ -0.25 - 0.30)</td>
                    <td className="mono">-100 pts (NIFTY) / -300 pts (SENSEX)</td>
                    <td className="mono" style={{ color: '#38bdf8' }}>60% – 70% Financed</td>
                    <td className="mono font-bold">&lt; ₹600 / lot</td>
                  </tr>
                  <tr>
                    <td className="font-bold" style={{ color: '#fbbf24' }}>Secondary Naked Buy</td>
                    <td className="mono">Long 1 ATM Option (Δ ≈ 0.50)</td>
                    <td className="mono">None (Single-Lot Only)</td>
                    <td className="mono">ATM Strike</td>
                    <td className="mono" style={{ color: 'var(--accent-red)' }}>Unhedged</td>
                    <td className="mono font-bold">Capped ≤ 15 pts NIFTY</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="spot-tile" style={{ marginTop: '1.25rem', borderLeft: '3px solid var(--accent-orange)' }}>
              <strong style={{ color: 'var(--accent-orange)' }}>0-DTE Morning Execution Rule (Prior to 13:00 IST):</strong>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', marginTop: '0.25rem' }}>
                On contract expiry days prior to 13:00 IST, routing orders to next-week options is prohibited due to excessive bid-ask spreads. Instead, execution routes directly through <strong>Index Futures</strong> or <strong>Deep ITM front-month options (Δ ≥ 0.70)</strong> with high delta sensitivity and tight liquidity.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: PIPELINE WORKFLOW */}
      {activeTab === 'workflow' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="hud-card">
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff', marginBottom: '0.75rem' }}>
              Real-Time Asynchronous Execution Pipeline
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
              Zero REST polling loops. The engine uses native SmartWebSocketV2 binary streaming and thread pool asynchronous dispatches:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {[
                { step: '1. Binary WebSocket Streaming (SmartWebSocketV2)', desc: 'Direct binary packet consumption for spot indices and option chains; extracts LTP, Best 5 Bid/Ask quotes, and tick volume with microsecond latency.' },
                { step: '2. Multi-Timeframe Bar Synthesizer', desc: 'Aggregates live ticks into synchronized 3-minute and 15-minute bars; tracks true Previous Day High/Low (PDH/PDL), Session VWAP, 50-EMA, and Opening Range boundaries.' },
                { step: '3. Dual Quantitative Strategy Engine', desc: 'Evaluates ILSME displacement stop-limit triggers and ORB boundary retests during prime liquidity windows (09:30–10:15 & 13:30–14:30 IST).' },
                { step: '4. Mathematical Risk Sizing & Spread Margin Check', desc: 'Calculates discrete integer lot sizing floor (1-lot minimum) based on 1.5%–1.8% risk per trade; validates available margin and daily drawdown.' },
                { step: '5. Native Exchange Bracket Execution', desc: 'Places defined-risk entry orders with SEBI-compliant STOPLOSS_LIMIT protection; sets up 15-minute stagnation time-decay watcher.' },
                { step: '6. Post-Trade Analytics & Telegram Dispatch', desc: 'Auto-generates transparent "What Worked / What Didn’t Work" diagnostic telemetry and dispatches instant Telegram alerts to the operator.' },
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

      {/* TAB 4: CAPITAL MATH & BRACKETS */}
      {activeTab === 'risk_math' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <div className="hud-card">
            <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#fff', marginBottom: '0.5rem' }}>
              Integer Floor Position Sizing Formulation
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Eliminates capital discreteness deadlocks with discrete integer floor lot allocation:
            </p>

            <div style={{ background: 'var(--bg-dark)', padding: '1rem', borderRadius: '10px', border: '1px solid var(--border-light)', fontFamily: 'var(--font-mono)', fontSize: '0.88rem' }}>
              <div style={{ color: 'var(--accent-orange)', marginBottom: '0.35rem' }}>
                R_trade = Account_Equity × 0.020  (2.0% risk per trade)
              </div>
              <div style={{ color: '#fff', marginBottom: '0.35rem' }}>
                Unit_Risk = Entry_Price - Stop_Loss (10% Initial SL on NIFTY)
              </div>
              <div style={{ color: 'var(--accent-emerald)' }}>
                Lots = floor( R_trade / (Unit_Risk × Exchange_Lot_Size) )  [Strict 1-Lot Floor]
              </div>
            </div>

            <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff', marginTop: '1.5rem', marginBottom: '0.75rem' }}>
              Trade Management & Stagnation Time-Stop Lifecycle
            </h4>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1rem' }}>
              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>INITIAL STOP-LOSS</div>
                <div style={{ color: 'var(--accent-red)', fontWeight: 700, margin: '0.25rem 0' }}>10% Max SL (NIFTY Option)</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  Placed at technical invalidation or 10% premium drop for optimal noise tolerance.
                </p>
              </div>

              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>MANDATORY TIME-DECAY EXIT</div>
                <div style={{ color: '#fbbf24', fontWeight: 700, margin: '0.25rem 0' }}>15-Min Stagnation Stop</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  If position fails to displace to at least <strong>+0.5R within 15 minutes (5 candles on 3m chart)</strong>, automatic market exit triggers to kill theta decay.
                </p>
              </div>

              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>OPTIMAL BREAKEVEN SHIFT</div>
                <div style={{ color: 'var(--accent-orange)', fontWeight: 700, margin: '0.25rem 0' }}>Breakeven Shift at +1.2R</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  SL moves to entry automatically as soon as floating profit achieves <strong>+1.2R</strong> expansion.
                </p>
              </div>

              <div className="spot-tile">
                <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>TARGET HARVESTING</div>
                <div style={{ color: 'var(--accent-emerald)', fontWeight: 700, margin: '0.25rem 0' }}>+3.0R Target Exit</div>
                <p style={{ fontSize: '0.75rem', color: 'var(--text-dim)' }}>
                  1-lot positions exit 100% at +3.0R. Multi-lot positions exit 50% at +3.0R and trail the remainder along 3m swing pivots.
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
              Institutional Circuit Breakers & Friction Audit
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
              Rigorous risk envelopes and statutory friction accounting ensure live profitability without drawdown deadlocks:
            </p>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Safeguard / Friction Rule</th>
                    <th>Parameter Boundary</th>
                    <th>Operational Behavior</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Capital Cushion & Starting Equity</strong></td>
                    <td className="mono">₹1,00,000 Starting / ₹50,000 Safety Floor</td>
                    <td>Provides ₹50,000 risk cushion; live engine locks if Angel One balance &lt; ₹50,000.</td>
                  </tr>
                  <tr>
                    <td><strong>Max Daily Drawdown</strong></td>
                    <td className="mono" style={{ color: 'var(--accent-red)' }}>4.5% of day-start capital</td>
                    <td>Guarantees 2 consecutive maximum stop-outs will not prematurely liquidate an active 2nd trade.</td>
                  </tr>
                  <tr>
                    <td><strong>Daily Trade Quota</strong></td>
                    <td className="mono">Strict 2 completed trades / 2 losses</td>
                    <td>Locks order placement until the next session upon 2 completed trades or 2 consecutive stop-outs.</td>
                  </tr>
                  <tr>
                    <td><strong>Mandatory EOD Liquidation</strong></td>
                    <td className="mono">15:12 IST</td>
                    <td>Cancels resting exchange stop orders and liquidates all active option contracts at market.</td>
                  </tr>
                  <tr>
                    <td><strong>Securities Transaction Tax (STT)</strong></td>
                    <td className="mono">0.15% on gross premium sales</td>
                    <td>Deducted automatically from realized option gross ledger on exit.</td>
                  </tr>
                  <tr>
                    <td><strong>Turnover Charges & Taxes</strong></td>
                    <td className="mono">NSE / BSE fees + SEBI + 18% GST</td>
                    <td>Accounted for in net P&L calculations.</td>
                  </tr>
                  <tr>
                    <td><strong>Execution Slippage Modeling</strong></td>
                    <td className="mono">1.0 pt Entry / 0.8 pt Market Stop</td>
                    <td>Realistic execution penalty deducted on all backtests and paper simulations.</td>
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


