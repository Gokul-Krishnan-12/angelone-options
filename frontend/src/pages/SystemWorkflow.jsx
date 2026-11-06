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
  GitBranch,
  Sparkles,
  Bot,
  Activity,
  Compass,
  ArrowUpRight,
  ArrowDownRight,
  ChevronRight,
  Terminal,
  Smartphone,
  Eye,
  Sliders
} from 'lucide-react';

export default function SystemWorkflow() {
  const [activeTab, setActiveTab] = useState('index_sniper');

  const tabs = [
    { id: 'index_sniper', label: '1. Index Options Sniper', icon: Target, badge: 'NIFTY / SENSEX' },
    { id: 'stock_options', label: '2. AI Stock Options Engine', icon: Bot, badge: '200+ F&O STOCKS' },
    { id: 'lifecycle', label: '3. Trade Lifecycle & Execution', icon: GitBranch, badge: 'STEP-BY-STEP' },
    { id: 'risk_shields', label: '4. Capital Safety & Circuit Breakers', icon: Shield, badge: 'CAPITAL PRESERVATION' }
  ];

  return (
    <div className="page-container" style={{ maxWidth: '1400px', margin: '0 auto', paddingBottom: '3rem' }}>
      {/* Page Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', paddingBottom: '1.25rem', borderBottom: '1px solid var(--border-light)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <div className="brand-icon-box" style={{ width: '46px', height: '46px', background: 'rgba(237, 76, 34, 0.12)', border: '1px solid rgba(237, 76, 34, 0.3)', borderRadius: '12px' }}>
            <Compass size={24} style={{ color: 'var(--accent-orange)' }} />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 800, color: '#fff', letterSpacing: '-0.02em' }}>
                System Architecture & Trade Workflows
              </h2>
              <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: 'var(--accent-emerald)', fontSize: '0.68rem', padding: '0.2rem 0.5rem' }}>
                LIVE V2.5
              </span>
            </div>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
              Visual interactive breakdown of quantitative index strategies, autonomous AI stock options planning, and multi-stage capital protection.
            </p>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="tab-row" style={{ marginTop: '1.25rem', display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        {tabs.map((t) => {
          const Icon = t.icon;
          const isActive = activeTab === t.id;
          return (
            <button
              key={t.id}
              className={`tab-btn ${isActive ? 'active' : ''}`}
              onClick={() => setActiveTab(t.id)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.6rem',
                padding: '0.65rem 1rem',
                borderRadius: '8px',
                border: isActive ? '1px solid var(--accent-orange)' : '1px solid var(--border-light)',
                background: isActive ? 'rgba(237, 76, 34, 0.12)' : 'rgba(255, 255, 255, 0.02)',
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              <Icon size={16} style={{ color: isActive ? 'var(--accent-orange)' : 'var(--text-muted)' }} />
              <span style={{ fontWeight: isActive ? 700 : 500, color: isActive ? '#fff' : 'var(--text-muted)', fontSize: '0.86rem' }}>
                {t.label}
              </span>
              <span
                style={{
                  fontSize: '0.62rem',
                  padding: '0.1rem 0.4rem',
                  borderRadius: '4px',
                  background: isActive ? 'rgba(237, 76, 34, 0.25)' : 'rgba(255,255,255,0.06)',
                  color: isActive ? '#fff' : 'var(--text-dim)',
                  fontWeight: 600
                }}
              >
                {t.badge}
              </span>
            </button>
          );
        })}
      </div>

      {/* ======================================================== */}
      {/* TAB 1: INDEX OPTIONS SNIPER (NIFTY / SENSEX) */}
      {/* ======================================================== */}
      {activeTab === 'index_sniper' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginTop: '1.25rem' }}>
          {/* Executive Overview Banner */}
          <div className="hud-card" style={{ borderLeft: '4px solid var(--accent-orange)', background: 'linear-gradient(135deg, rgba(237, 76, 34, 0.08) 0%, rgba(18, 17, 16, 0.95) 100%)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <span className="pill-badge" style={{ background: 'rgba(237, 76, 34, 0.15)', color: 'var(--accent-orange)', border: '1px solid var(--accent-orange)', marginBottom: '0.4rem', display: 'inline-block' }}>
                  QUANTITATIVE PRICE-ACTION DISCIPLINE
                </span>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff', marginTop: '0.2rem' }}>
                  Institutional Liquidity Sweep & Momentum Expansion (ILSME)
                </h3>
              </div>
              <span className="mono" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Target Frequency: 1 to 2 High-Conviction Trades / Day
              </span>
            </div>
            <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.65rem' }}>
              Naked option buying during consolidation suffers from negative expectancy due to rapid theta decay (<span className="mono">Θ</span>) and bid-ask spread friction. The Index Sniper engine ignores random intraday noise and exclusively waits for <strong>institutional stop-runs at Previous Day Extremes</strong> followed by explosive displacement across Session VWAP.
            </p>
          </div>

          {/* 4-Step Visual Flowchart */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))', gap: '1rem' }}>
            {[
              {
                step: 'Phase 1',
                title: '15m Macro Sweep',
                icon: Eye,
                color: 'var(--accent-orange)',
                desc: 'Price pierces Previous Day High (PDH) or Low (PDL) to trigger retail stops, then closes back inside with a ≥30% rejection wick.'
              },
              {
                step: 'Phase 2',
                title: '3m Market Structure Shift',
                icon: GitBranch,
                color: 'var(--accent-blue)',
                desc: 'A powerful 3-minute candle displaces aggressively across Session VWAP in the reversal direction, violating previous pivot structure.'
              },
              {
                step: 'Phase 3',
                title: 'Displacement Stop-Limit',
                icon: Crosshair,
                color: 'var(--accent-emerald)',
                desc: 'Order is placed 1 tick above the displacement high (for CE) or below low (for PE). Eliminates chasing and ensures true momentum fill.'
              },
              {
                step: 'Phase 4',
                title: 'Noise-Filtered Execution',
                icon: Shield,
                color: '#c084fc',
                desc: 'Initial Stop-Loss set at 12%. Stop is moved to Breakeven ONLY after ≥0.65R verified profit, protecting against 20-paise spread jitter.'
              }
            ].map((card, i) => {
              const Icon = card.icon;
              return (
                <div key={i} className="hud-card" style={{ position: 'relative', overflow: 'hidden', borderTop: `3px solid ${card.color}` }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem' }}>
                    <span className="mono" style={{ fontSize: '0.72rem', color: card.color, fontWeight: 700 }}>{card.step}</span>
                    <Icon size={18} style={{ color: card.color }} />
                  </div>
                  <h4 style={{ fontSize: '0.98rem', fontWeight: 700, color: '#fff', marginBottom: '0.4rem' }}>{card.title}</h4>
                  <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>{card.desc}</p>
                </div>
              );
            })}
          </div>

          {/* Real Trade Example: Walkthrough Card */}
          <div className="hud-card" style={{ borderColor: 'rgba(16, 185, 129, 0.3)', background: 'rgba(16, 185, 129, 0.02)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <span className="pill-badge" style={{ background: 'rgba(16, 185, 129, 0.2)', color: 'var(--accent-emerald)', fontWeight: 800 }}>
                  REAL ANATOMY OF A WINNING INDEX TRADE
                </span>
                <span className="mono" style={{ fontSize: '0.92rem', fontWeight: 800, color: '#fff' }}>
                  NIFTY 24400 CE
                </span>
              </div>
              <span className="mono text-muted" style={{ fontSize: '0.76rem' }}>Execution Mode: Live SmartAPI / Paper</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
              <div>
                <h5 style={{ fontSize: '0.84rem', fontWeight: 700, color: '#fff', marginBottom: '0.5rem' }}>
                  Why did the system take this trade?
                </h5>
                <ul style={{ fontSize: '0.8rem', color: 'var(--text-muted)', listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <li style={{ display: 'flex', alignItems: 'flex-start', gap: '0.45rem' }}>
                    <CheckCircle2 size={15} style={{ color: 'var(--accent-emerald)', marginTop: '0.15rem', flexShrink: 0 }} />
                    <span><strong>15m Macro Sweep:</strong> NIFTY dipped below Previous Day Low (24,360) and formed a 45% lower wick, rejecting further downside.</span>
                  </li>
                  <li style={{ display: 'flex', alignItems: 'flex-start', gap: '0.45rem' }}>
                    <CheckCircle2 size={15} style={{ color: 'var(--accent-emerald)', marginTop: '0.15rem', flexShrink: 0 }} />
                    <span><strong>3m Displacement:</strong> A strong bullish expansion bar closed at 24,395, pushing spot comfortably above Session VWAP (24,372).</span>
                  </li>
                  <li style={{ display: 'flex', alignItems: 'flex-start', gap: '0.45rem' }}>
                    <CheckCircle2 size={15} style={{ color: 'var(--accent-emerald)', marginTop: '0.15rem', flexShrink: 0 }} />
                    <span><strong>Option Selection:</strong> Selected ATM strike <strong>24400 CE</strong> (Delta ~0.52, high liquidity, tight bid-ask spread).</span>
                  </li>
                </ul>
              </div>

              {/* Numerical Execution Metrics Box */}
              <div style={{ background: 'rgba(0,0,0,0.35)', padding: '0.85rem', borderRadius: '8px', border: '1px solid var(--border-light)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.5rem', textAlign: 'center' }}>
                  <div>
                    <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>Entry Premium</div>
                    <div className="mono font-bold" style={{ color: 'var(--accent-blue)', fontSize: '0.9rem', marginTop: '0.15rem' }}>₹149.00</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>Initial SL</div>
                    <div className="mono font-bold" style={{ color: 'var(--accent-red)', fontSize: '0.9rem', marginTop: '0.15rem' }}>₹131.00</div>
                    <div style={{ fontSize: '0.62rem', color: 'var(--accent-red)' }}>-18 pts (12%)</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>Target 1 (+2.0R)</div>
                    <div className="mono font-bold" style={{ color: 'var(--accent-emerald)', fontSize: '0.9rem', marginTop: '0.15rem' }}>₹185.00</div>
                    <div style={{ fontSize: '0.62rem', color: 'var(--accent-emerald)' }}>+36 pts (60% close)</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>Target 2 (+3.0R)</div>
                    <div className="mono font-bold" style={{ color: '#38bdf8', fontSize: '0.9rem', marginTop: '0.15rem' }}>₹203.00</div>
                    <div style={{ fontSize: '0.62rem', color: '#38bdf8' }}>+54 pts (Runner)</div>
                  </div>
                </div>

                <div style={{ marginTop: '0.75rem', paddingTop: '0.65rem', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    🛡️ <strong>Breakeven Protocol:</strong> SL moves to ₹149.00 once price reaches ₹161.00 (+0.65R).
                  </span>
                  <span className="pill-badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: 'var(--accent-emerald)', fontSize: '0.7rem' }}>
                    1 : 2.0 R:R Ratio
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Dual Strategy Comparison: ILSME vs Momentum ORB */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.25rem' }}>
            <div className="hud-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <span className="pill-badge" style={{ background: 'rgba(237, 76, 34, 0.18)', color: 'var(--accent-orange)', fontWeight: 700 }}>
                  STRATEGY A: ILSME SWEEP REVERSALS
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.72rem' }}>Mean Reversion</span>
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                Targets false breakouts at Previous Day High/Low and session extremes. When price traps breakout traders and swiftly rejects, the algorithm rides the rapid squeeze back to Session VWAP and opposite liquidity pools.
              </p>
            </div>

            <div className="hud-card">
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                <span className="pill-badge" style={{ background: 'rgba(56, 189, 248, 0.18)', color: 'var(--accent-blue)', fontWeight: 700 }}>
                  STRATEGY B: MOMENTUM OPENING RANGE (ORB)
                </span>
                <span className="mono text-muted" style={{ fontSize: '0.72rem' }}>Trend Expansion</span>
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
                Evaluates opening 15-minute range (09:15–09:30). If volatility exceeds minimum threshold (NIFTY ≥45 pts; SENSEX ≥160 pts), it waits for a clean <strong>1-candle retest</strong> of the boundary before catching directional momentum bursts.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* TAB 2: AI STOCK OPTIONS ENGINE (200+ F&O UNIVERSE) */}
      {/* ======================================================== */}
      {activeTab === 'stock_options' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginTop: '1.25rem' }}>
          {/* Executive Overview Banner */}
          <div className="hud-card" style={{ borderLeft: '4px solid #c084fc', background: 'linear-gradient(135deg, rgba(192, 132, 252, 0.08) 0%, rgba(18, 17, 16, 0.95) 100%)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <span className="pill-badge" style={{ background: 'rgba(192, 132, 252, 0.2)', color: '#c084fc', border: '1px solid #c084fc', marginBottom: '0.4rem', display: 'inline-block' }}>
                  GOOGLE GEMINI 2.5 FLASH INTEL
                </span>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff', marginTop: '0.2rem' }}>
                  Autonomous Stock Options Engine (200+ NSE F&O Universe)
                </h3>
              </div>
              <span className="mono" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Intraday & Overnight Intelligence
              </span>
            </div>
            <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.65rem' }}>
              While the index sniper specializes in macro indices, the Stock Options Engine scans the broader Indian derivative universe. It evaluates multi-factor criteria: <strong>Sectoral Confluence</strong>, <strong>Relative Volume (RVOL)</strong>, <strong>Open Interest (OI) buildup</strong>, and <strong>High-Beta 1:2.0 Risk-to-Reward profiles</strong>.
            </p>
          </div>

          {/* Dual AI Modes: Overnight Planner vs Intraday Scanner */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(420px, 1fr))', gap: '1.25rem' }}>
            <div className="hud-card" style={{ border: '1px solid rgba(251, 191, 36, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.85rem' }}>
                <div className="brand-icon-box" style={{ width: '32px', height: '32px', background: 'rgba(251, 191, 36, 0.15)', color: '#fbbf24' }}>
                  <Sparkles size={16} />
                </div>
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>Overnight AI Planner</h4>
                  <span className="mono text-muted" style={{ fontSize: '0.72rem' }}>Pre-Market Strategy Formulation</span>
                </div>
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '0.85rem' }}>
                Runs before market open (08:30–09:00 IST) or after market close. Evaluates daily trend continuity, sector strength, and pre-formulates high-conviction option candidate cards for the upcoming session.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-dim)', fontSize: '0.7rem' }}>Top 3 Focus Stocks</span>
                <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-dim)', fontSize: '0.7rem' }}>Multi-Day Trends</span>
                <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-dim)', fontSize: '0.7rem' }}>Key Level Mapping</span>
              </div>
            </div>

            <div className="hud-card" style={{ border: '1px solid rgba(56, 189, 248, 0.3)' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.85rem' }}>
                <div className="brand-icon-box" style={{ width: '32px', height: '32px', background: 'rgba(56, 189, 248, 0.15)', color: '#38bdf8' }}>
                  <Zap size={16} />
                </div>
                <div>
                  <h4 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>Intraday Live Scanner</h4>
                  <span className="mono text-muted" style={{ fontSize: '0.72rem' }}>Periodic In-Session Discovery (5–15 Mins)</span>
                </div>
              </div>
              <p style={{ fontSize: '0.82rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '0.85rem' }}>
                Scans live market breadth dynamically during trading hours. Identifies real-time momentum spikes, volume breakouts, and arms conditional trigger orders waiting for key price confirmation.
              </p>
              <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
                <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-dim)', fontSize: '0.7rem' }}>Live Breadth Telemetry</span>
                <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-dim)', fontSize: '0.7rem' }}>Armed Trigger Orders</span>
                <span className="badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-dim)', fontSize: '0.7rem' }}>Structural Invalidation</span>
              </div>
            </div>
          </div>

          {/* Stock Trade Walkthrough Card */}
          <div className="hud-card" style={{ borderColor: 'rgba(192, 132, 252, 0.3)', background: 'rgba(192, 132, 252, 0.02)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '0.75rem', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                <span className="pill-badge" style={{ background: 'rgba(192, 132, 252, 0.2)', color: '#c084fc', fontWeight: 800 }}>
                  ANATOMY OF AN AI STOCK OPTION SETUP
                </span>
                <span className="mono" style={{ fontSize: '0.92rem', fontWeight: 800, color: '#fff' }}>
                  SBIN 990 CE (750 / lot)
                </span>
              </div>
              <span className="badge" style={{ background: 'rgba(192, 132, 252, 0.15)', color: '#c084fc', fontSize: '0.7rem' }}>HIGH BETA • 1 : 2.0 R:R</span>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '1.25rem' }}>
              <div>
                <h5 style={{ fontSize: '0.84rem', fontWeight: 700, color: '#fff', marginBottom: '0.5rem' }}>
                  AI Catalyst & Market Alignment
                </h5>
                <ul style={{ fontSize: '0.8rem', color: 'var(--text-muted)', listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
                  <li style={{ display: 'flex', alignItems: 'flex-start', gap: '0.45rem' }}>
                    <CheckCircle2 size={15} style={{ color: '#c084fc', marginTop: '0.15rem', flexShrink: 0 }} />
                    <span><strong>Sector Confluence:</strong> NIFTY BANK is surging (+1.35%), with 100% banking component alignment.</span>
                  </li>
                  <li style={{ display: 'flex', alignItems: 'flex-start', gap: '0.45rem' }}>
                    <CheckCircle2 size={15} style={{ color: '#c084fc', marginTop: '0.15rem', flexShrink: 0 }} />
                    <span><strong>Volume & OI Expansion:</strong> RVOL is 2.1× higher than 20-SMA with +4.8% Open Interest addition (Long Buildup).</span>
                  </li>
                  <li style={{ display: 'flex', alignItems: 'flex-start', gap: '0.45rem' }}>
                    <CheckCircle2 size={15} style={{ color: '#c084fc', marginTop: '0.15rem', flexShrink: 0 }} />
                    <span><strong>Conditional Trigger:</strong> Setup is <em>ARMED</em> at ₹995.00. Order will NOT fire blindly at market until spot breaks trigger level.</span>
                  </li>
                </ul>
              </div>

              {/* Numerical Execution Metrics Box */}
              <div style={{ background: 'rgba(0,0,0,0.35)', padding: '0.85rem', borderRadius: '8px', border: '1px solid var(--border-light)', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.5rem', textAlign: 'center' }}>
                  <div>
                    <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>Entry Premium</div>
                    <div className="mono font-bold" style={{ color: 'var(--accent-blue)', fontSize: '0.9rem', marginTop: '0.15rem' }}>₹22.50</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>Stop Loss</div>
                    <div className="mono font-bold" style={{ color: 'var(--accent-red)', fontSize: '0.9rem', marginTop: '0.15rem' }}>₹19.80</div>
                    <div style={{ fontSize: '0.62rem', color: 'var(--accent-red)' }}>-2.7 pts (-12%)</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>Target 1 (+2.0R)</div>
                    <div className="mono font-bold" style={{ color: 'var(--accent-emerald)', fontSize: '0.9rem', marginTop: '0.15rem' }}>₹27.90</div>
                    <div style={{ fontSize: '0.62rem', color: 'var(--accent-emerald)' }}>+5.4 pts (+24%)</div>
                  </div>
                  <div>
                    <div style={{ fontSize: '0.64rem', color: 'var(--text-muted)' }}>Expected Profit</div>
                    <div className="mono font-bold" style={{ color: 'var(--accent-emerald)', fontSize: '0.9rem', marginTop: '0.15rem' }}>+₹4,050</div>
                    <div style={{ fontSize: '0.62rem', color: 'var(--accent-red)' }}>Risk: -₹2,025</div>
                  </div>
                </div>

                <div style={{ marginTop: '0.75rem', paddingTop: '0.65rem', borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                    🛑 <strong>Invalidation Level:</strong> ₹980.00 (Setup automatically cancels if spot drops below support).
                  </span>
                  <span className="pill-badge" style={{ background: 'rgba(16, 185, 129, 0.15)', color: 'var(--accent-emerald)', fontSize: '0.7rem' }}>
                    Strict 1 : 2.0 Positive Expectancy
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* TAB 3: TRADE LIFECYCLE & EXECUTION (STEP-BY-STEP) */}
      {/* ======================================================== */}
      {activeTab === 'lifecycle' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginTop: '1.25rem' }}>
          <div className="hud-card">
            <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#fff', marginBottom: '0.5rem' }}>
              The 6-Step End-to-End Trade Lifecycle
            </h3>
            <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
              Every trade follows a strict, deterministic sequence with zero human panic, emotional bias, or discretionary guesswork:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {[
                {
                  num: '01',
                  title: 'Market Scanning & Confluence Verification',
                  desc: 'Binary WebSocket ticks stream live. The system checks whether the index or stock is in a prime liquidity window (09:30–11:30 or 13:30–14:30 IST) and verifies trend alignment across Session VWAP.',
                  badge: 'PRE-TRADE FILTER'
                },
                {
                  num: '02',
                  title: 'Conditional Trigger Confirmation (No Market Chasing)',
                  desc: 'Orders are not sent blindly. The engine sets a conditional trigger price (e.g. 1 tick above a breakout high). If the price pulls back or reverses before hitting the trigger, no capital is risked.',
                  badge: 'ADVERSE SELECTION GUARD'
                },
                {
                  num: '03',
                  title: 'Institutional Position Sizing & Margin Validation',
                  desc: 'Calculates discrete integer lot sizing strictly targeting 1.5% to 2.0% risk of account equity. Checks Angel One RMS cash limits to ensure zero margin calls.',
                  badge: 'CAPITAL ALLOCATION'
                },
                {
                  num: '04',
                  title: 'Native Exchange Bracket Routing (STOPLOSS_LIMIT)',
                  desc: 'Order routes via SmartAPI as a defined-risk package: entry execution order paired immediately with a resting Exchange Stop-Loss Limit order placed at -12% premium.',
                  badge: 'EXCHANGE BRACKET'
                },
                {
                  num: '05',
                  title: 'Noise-Proof Breakeven & Stagnation Time-Stop',
                  desc: 'If the trade does not progress within 15–20 minutes, a time-stop liquidates it to eliminate theta decay. Stop-Loss moves to Breakeven ONLY after ≥0.65R verified profit, preventing spread noise exits.',
                  badge: 'DYNAMIC DEFENSE'
                },
                {
                  num: '06',
                  title: 'Target 1 Harvest (+2.0R) & Runner Trailing',
                  desc: 'Upon reaching Target 1, 60% of open lots are closed via marketable limit orders to lock in realized cash. The remaining 40% runner trails along 3-minute pivot levels until Target 2 (+3.0R).',
                  badge: 'PROFIT HARVEST'
                }
              ].map((step, idx) => (
                <div key={idx} className="spot-tile" style={{ display: 'flex', alignItems: 'flex-start', gap: '1.25rem', padding: '1rem', background: 'rgba(255, 255, 255, 0.02)', borderRadius: '8px', border: '1px solid var(--border-light)' }}>
                  <div className="mono font-bold" style={{ fontSize: '1.2rem', color: 'var(--accent-orange)', minWidth: '35px' }}>
                    {step.num}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.5rem', marginBottom: '0.35rem' }}>
                      <strong style={{ color: '#fff', fontSize: '0.92rem' }}>{step.title}</strong>
                      <span className="badge" style={{ background: 'rgba(237, 76, 34, 0.15)', color: 'var(--accent-orange)', fontSize: '0.64rem' }}>
                        {step.badge}
                      </span>
                    </div>
                    <p style={{ color: 'var(--text-muted)', fontSize: '0.82rem', lineHeight: 1.5 }}>
                      {step.desc}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* TAB 4: CAPITAL SAFETY & CIRCUIT BREAKERS */}
      {/* ======================================================== */}
      {activeTab === 'risk_shields' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem', marginTop: '1.25rem' }}>
          {/* Executive Overview Banner */}
          <div className="hud-card" style={{ borderLeft: '4px solid var(--accent-red)', background: 'linear-gradient(135deg, rgba(244, 63, 94, 0.08) 0%, rgba(18, 17, 16, 0.95) 100%)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <span className="pill-badge" style={{ background: 'rgba(244, 63, 94, 0.2)', color: 'var(--accent-red)', border: '1px solid var(--accent-red)', marginBottom: '0.4rem', display: 'inline-block' }}>
                  SURVIVAL FIRST PRINCIPLE
                </span>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff', marginTop: '0.2rem' }}>
                  Institutional Circuit Breakers & Friction Audit
                </h3>
              </div>
              <span className="mono" style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                Non-Negotiable Account Protection
              </span>
            </div>
            <p style={{ fontSize: '0.86rem', color: 'var(--text-muted)', lineHeight: 1.6, marginTop: '0.65rem' }}>
              Sustainable compounding requires eliminating devastating drawdown spikes: <span className="mono">R_compound ≈ μ - (σ² / 2)</span>. The system enforces 6 hard architectural circuit breakers that override all algorithms, preventing catastrophic runaway losses.
            </p>
          </div>

          {/* 6 Circuit Breakers Grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '1rem' }}>
            {[
              {
                title: 'Max Daily Drawdown (4.5%)',
                limit: '4.5% of Day-Start Capital',
                action: 'Liquidates all positions, cancels working orders, locks system until next morning.',
                icon: AlertTriangle,
                color: 'var(--accent-red)'
              },
              {
                title: 'Daily Trade Quota',
                limit: 'Max 2 Completed Trades',
                action: 'Freezes order generation immediately upon reaching 2 completed trades to prevent overtrading.',
                icon: Lock,
                color: 'var(--accent-orange)'
              },
              {
                title: 'Consecutive Loss Circuit',
                limit: '2 Consecutive Stop-Outs',
                action: 'Halts trading for the remainder of the session after 2 consecutive losing trades.',
                icon: Shield,
                color: '#fbbf24'
              },
              {
                title: 'Midday Chop Filter',
                limit: '11:30 to 12:30 IST',
                action: 'Rejects new signal generation during low-volume lunchtime consolidation.',
                icon: Clock,
                color: 'var(--accent-blue)'
              },
              {
                title: '0-DTE Morning Theta Guard',
                limit: 'Expiry Day before 13:00 IST',
                action: 'Blocks same-day expiring contracts during morning hours to avoid violent theta crush.',
                icon: Activity,
                color: '#c084fc'
              },
              {
                title: 'Mandatory EOD Square-Off',
                limit: '15:12 IST Sharp',
                action: 'Automatically market-liquidates all open intraday derivative contracts before exchange close.',
                icon: CheckCircle2,
                color: 'var(--accent-emerald)'
              }
            ].map((shield, i) => {
              const Icon = shield.icon;
              return (
                <div key={i} className="hud-card" style={{ borderLeft: `3px solid ${shield.color}`, padding: '1rem' }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span style={{ fontSize: '0.86rem', fontWeight: 700, color: '#fff' }}>{shield.title}</span>
                    <Icon size={16} style={{ color: shield.color }} />
                  </div>
                  <div className="mono font-bold" style={{ fontSize: '0.78rem', color: shield.color, marginBottom: '0.35rem' }}>
                    {shield.limit}
                  </div>
                  <p style={{ fontSize: '0.76rem', color: 'var(--text-muted)', lineHeight: 1.4 }}>
                    {shield.action}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Statutory Taxes & Realized Friction Table */}
          <div className="hud-card">
            <h4 style={{ fontSize: '0.98rem', fontWeight: 700, color: '#fff', marginBottom: '0.5rem' }}>
              Realistic Friction & Statutory Deductions Ledger
            </h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Unlike naive simulators that report gross theoretical returns, this platform calculates realistic post-friction net P&L on every trade:
            </p>

            <div className="table-container">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Friction Component</th>
                    <th>Standard Statutory Rate</th>
                    <th>System Implementation</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td><strong>Securities Transaction Tax (STT)</strong></td>
                    <td className="mono">0.15% on sell-side turnover</td>
                    <td>Deducted automatically from option gross premium upon sell order fill.</td>
                  </tr>
                  <tr>
                    <td><strong>Brokerage (Angel One)</strong></td>
                    <td className="mono">₹20 flat per executed order</td>
                    <td>₹40 round-trip deducted per completed position (₹20 entry + ₹20 exit).</td>
                  </tr>
                  <tr>
                    <td><strong>Exchange Turnover & GST</strong></td>
                    <td className="mono">NSE / BSE fees + 18% GST</td>
                    <td>Computed based on official transaction tariff slabs.</td>
                  </tr>
                  <tr>
                    <td><strong>Execution Slippage Modeling</strong></td>
                    <td className="mono">0.20 × Spread + 200ms latency</td>
                    <td>Applied to all paper simulations to ensure 100% parity with live execution.</td>
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
