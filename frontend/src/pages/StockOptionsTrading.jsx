import React, { useState, useEffect } from 'react';
import {
  Play,
  Pause,
  Square,
  AlertOctagon,
  ShieldAlert,
  ShieldCheck,
  TrendingUp,
  TrendingDown,
  RefreshCw,
  Clock,
  Layers,
  Zap,
  CheckCircle2,
  XCircle,
  FileText,
  Activity,
  AlertTriangle
} from 'lucide-react';
import { formatINR } from '../components/MetricsHud';
import { authFetch } from '../utils/api';

const FO_LOT_SIZES = {
  RELIANCE: 250,
  TCS: 175,
  INFY: 400,
  HDFCBANK: 550,
  ICICIBANK: 700,
  SBIN: 750,
  BHARTIARTL: 950,
  KOTAKBANK: 400,
  LT: 175,
  AXISBANK: 625,
  BAJFINANCE: 125,
  MARUTI: 50,
  TATAMOTORS: 1425,
  SUNPHARMA: 350,
  ITC: 1600,
  HINDUNILVR: 300,
  NTPC: 1500,
  TATASTEEL: 5500,
  WIPRO: 1500,
  'M&M': 350,
  COFORGE: 150,
  PERSISTENT: 100,
  DIXON: 100,
  POLYCAB: 125,
  INDUSINDBK: 500,
  CANBK: 6750,
  DLF: 825,
  FEDERALBNK: 5000,
  PFC: 1300,
  RECLTD: 1400,
  BHEL: 2625,
  TRENT: 100,
  HAL: 150,
  BEL: 2850,
  ADANIENT: 300,
  ADANIPORTS: 400,
};

const HIGH_BETA_SYMBOLS = new Set([
  'COFORGE', 'PERSISTENT', 'DIXON', 'POLYCAB', 'INDUSINDBK',
  'BHEL', 'DLF', 'ADANIENT', 'ADANIPORTS', 'TRENT', 'HAL',
  'BEL', 'CANBK', 'FEDERALBNK', 'PFC', 'RECLTD', 'TATASTEEL',
  'HINDALCO', 'TATAMOTORS', 'SBIN'
]);

const getEffectiveLotSize = (sym, rawLot) => {
  const parsed = Number(rawLot);
  if (parsed && parsed > 10) return parsed;
  return FO_LOT_SIZES[sym?.toUpperCase()] || 250;
};

export default function StockOptionsTrading({ state, onOpenPanic }) {
  const [liveStatus, setLiveStatus] = useState(null);
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [latestPlan, setLatestPlan] = useState(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isKillModalOpen, setIsKillModalOpen] = useState(false);
  const [autoExecute, setAutoExecute] = useState(false);
  const [actionNotice, setActionNotice] = useState(null);

  useEffect(() => {
    fetchLiveStockData();
    const interval = setInterval(fetchLiveStockData, 5000);
    return () => clearInterval(interval);
  }, []);

  const fetchLiveStockData = async () => {
    try {
      const [stRes, posRes, ordRes, planRes] = await Promise.all([
        authFetch('/api/stock-options/live/status'),
        authFetch('/api/stock-options/live/positions'),
        authFetch('/api/stock-options/live/orders?limit=15'),
        authFetch('/api/stock-options/planner/latest')
      ]);

      if (stRes.ok) {
        const stData = await stRes.json();
        setLiveStatus(stData);
        setAutoExecute(Boolean(stData.auto_execute));
      }
      if (posRes.ok) setPositions(await posRes.json());
      if (ordRes.ok) setOrders(await ordRes.json());
      if (planRes.ok) {
        const pData = await planRes.json();
        if (pData.plan_id) setLatestPlan(pData);
      }
    } catch (e) {
      console.error('Error fetching live stock options data:', e);
    }
  };

  const showNotification = (msg, isError = false) => {
    setActionNotice({ text: msg, isError });
    setTimeout(() => setActionNotice(null), 5000);
  };

  const handleStartAgent = async () => {
    try {
      const res = await authFetch('/api/stock-options/live/start', { method: 'POST' });
      if (res.ok) {
        showNotification('Live Stock Options Agent started. RMS protection active.');
        fetchLiveStockData();
      }
    } catch (e) {
      showNotification('Failed to start live agent.', true);
    }
  };

  const handlePauseAgent = async () => {
    try {
      const res = await authFetch('/api/stock-options/live/pause', { method: 'POST' });
      if (res.ok) {
        showNotification('Live Agent paused. New entries halted.');
        fetchLiveStockData();
      }
    } catch (e) {
      showNotification('Failed to pause live agent.', true);
    }
  };

  const handleStopAgent = async () => {
    try {
      const res = await authFetch('/api/stock-options/live/stop', { method: 'POST' });
      if (res.ok) {
        showNotification('Live Agent stopped.');
        fetchLiveStockData();
      }
    } catch (e) {
      showNotification('Failed to stop live agent.', true);
    }
  };

  const handleToggleAutoExecute = async () => {
    const nextVal = !autoExecute;
    try {
      const res = await authFetch(`/api/stock-options/live/auto-execute?enabled=${nextVal}`, { method: 'POST' });
      if (res.ok) {
        setAutoExecute(nextVal);
        showNotification(`Auto-Execution ${nextVal ? 'ENABLED' : 'DISABLED'}.`);
      }
    } catch (e) {
      showNotification('Failed to toggle auto execution.', true);
    }
  };

  const handleExecuteCandidate = async (candidate) => {
    try {
      const res = await authFetch('/api/stock-options/live/execute-candidate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate, plan_id: latestPlan?.plan_id || '' })
      });
      const data = await res.json();
      if (data.status === 'success') {
        showNotification(`Order dispatched for ${candidate.symbol} to Angel One RMS!`);
        fetchLiveStockData();
      } else {
        showNotification(`RMS / Validator Rejected: ${data.reason || data.message}`, true);
      }
    } catch (e) {
      showNotification('Error executing live candidate.', true);
    }
  };

  const handleTriggerKillSwitch = async () => {
    try {
      const res = await authFetch('/api/stock-options/live/kill-switch', { method: 'POST' });
      const data = await res.json();
      setIsKillModalOpen(false);
      showNotification(`Emergency Kill Switch executed: Closed ${data.closed_positions || 0} position(s).`);
      fetchLiveStockData();
    } catch (e) {
      showNotification('Emergency kill switch failed!', true);
    }
  };

  const status = liveStatus?.status || 'IDLE';
  const isLiveSynced = Boolean(state?.broker_rms?.is_live_synced);
  const isRunning = status === 'RUNNING';

  const totalUnrealized = positions.reduce((acc, p) => acc + (parseFloat(p.unrealized_pnl) || 0), 0);
  const totalRealized = positions.reduce((acc, p) => acc + (parseFloat(p.realized_pnl) || 0), 0);

  return (
    <div className="page-container">
      {/* 1. Missing Keys / Connection Banner if not synced */}
      {!isLiveSynced && (
        <div className="banner-minimal">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-orange)' }} />
            <span style={{ color: 'var(--text-main)', fontSize: '0.8rem' }}>
              Angel One SmartAPI session initializing or offline — Live broker RMS orders pending synchronization
            </span>
          </div>
          <span className="pill-badge" style={{ background: 'rgba(237, 76, 34, 0.15)', color: 'var(--accent-orange)' }}>
            RMS Sync Standby
          </span>
        </div>
      )}

      {/* Top Header matching AgentControl & Dashboard */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem', marginBottom: '1.25rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div className="brand-icon-box" style={{ background: 'var(--accent-orange)' }}>
              <Zap size={18} color="#fff" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="pulse-dot" style={{ background: isRunning ? 'var(--accent-emerald)' : 'var(--accent-orange)' }} />
                <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#fff', margin: 0 }}>
                  Stock Options Real Trading Hub
                </h2>
                <span
                  className="brand-badge"
                  style={{
                    background: isRunning ? 'rgba(16, 185, 129, 0.15)' : 'rgba(237, 76, 34, 0.15)',
                    color: isRunning ? 'var(--accent-emerald)' : 'var(--accent-orange)',
                  }}
                >
                  {isRunning ? 'Angel One Live Active' : 'Agent Standby'}
                </span>
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                Real-money production execution venue directly connected to Angel One SmartAPI matching engine
              </div>
            </div>
          </div>
        </div>

        {/* Live Controls */}
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <span
            className="pill-badge"
            style={{
              background: isRunning ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              color: isRunning ? 'var(--accent-emerald)' : 'var(--accent-red)',
              fontSize: '0.75rem',
              border: `1px solid ${isRunning ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`
            }}
          >
            <span className={`status-dot ${isRunning ? 'active' : ''}`} style={{ marginRight: 6 }} />
            {isRunning ? 'LIVE RMS RUNNING' : 'AGENT PAUSED'}
          </span>

          {isRunning ? (
            <button
              className="btn-secondary"
              onClick={handlePauseAgent}
              style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', padding: '0.45rem 1rem' }}
            >
              <Pause size={14} />
              <span>Pause Live Agent</span>
            </button>
          ) : (
            <button
              className="btn-primary"
              onClick={handleStartAgent}
              style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', padding: '0.45rem 1rem' }}
            >
              <Zap size={14} />
              <span>Start Live Agent</span>
            </button>
          )}

          <button
            className="panic-button"
            onClick={() => {
              if (onOpenPanic) {
                onOpenPanic();
              } else {
                setIsKillModalOpen(true);
              }
            }}
            style={{ padding: '0.45rem 0.85rem', fontSize: '0.78rem' }}
            title="Emergency Kill Switch — Liquidate all live stock options & index positions"
          >
            <ShieldAlert size={14} />
            <span>Emergency Kill Switch</span>
          </button>
        </div>
      </div>

      {actionNotice && (
        <div style={{
          padding: '0.75rem 1rem',
          borderRadius: 8,
          marginBottom: '1rem',
          fontSize: '0.82rem',
          background: actionNotice.isError ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.15)',
          border: `1px solid ${actionNotice.isError ? 'var(--accent-red)' : 'var(--accent-emerald)'}`,
          color: actionNotice.isError ? 'var(--accent-red)' : 'var(--accent-emerald)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <span>{actionNotice.text}</span>
          <button onClick={() => setActionNotice(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>×</button>
        </div>
      )}

      {/* Real Capital & RMS Exposure Metric HUD */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '0.75rem', marginBottom: '1.25rem' }}>
        <div className="hud-card" style={{ padding: '0.85rem' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Broker RMS Equity</div>
          <div className="mono" style={{ fontSize: '1.3rem', fontWeight: 800, color: '#fff', marginTop: '0.2rem' }}>
            {formatINR(state?.broker_rms?.net ?? 100000)}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
            Available Margin: <span className="mono" style={{ color: 'var(--accent-emerald)' }}>{formatINR(state?.broker_rms?.availablecash ?? 100000)}</span>
          </div>
        </div>

        <div className="hud-card" style={{ padding: '0.85rem' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Realized P&L (Today)</div>
          <div className="mono" style={{
            fontSize: '1.3rem',
            fontWeight: 800,
            marginTop: '0.2rem',
            color: totalRealized >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)'
          }}>
            {formatINR(totalRealized)}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
            Closed Real Money Positions
          </div>
        </div>

        <div className="hud-card" style={{ padding: '0.85rem' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Floating Unrealized P&L</div>
          <div className="mono" style={{
            fontSize: '1.3rem',
            fontWeight: 800,
            marginTop: '0.2rem',
            color: totalUnrealized >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)'
          }}>
            {formatINR(totalUnrealized)}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
            {positions.length} Active Real Positions
          </div>
        </div>

        <div className="hud-card" style={{ padding: '0.85rem' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Auto-Execution Guard</div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.35rem' }}>
            <span style={{ fontSize: '0.85rem', fontWeight: 700, color: autoExecute ? 'var(--accent-emerald)' : 'var(--accent-orange)' }}>
              {autoExecute ? 'AUTO DISPATCH' : 'MANUAL CONFIRM'}
            </span>
            <button
              className={`btn-secondary ${autoExecute ? 'active' : ''}`}
              style={{ padding: '0.25rem 0.65rem', fontSize: '0.72rem' }}
              onClick={handleToggleAutoExecute}
            >
              Toggle
            </button>
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            {autoExecute ? 'Approves & places orders automatically' : 'Requires operator 1-click confirmation'}
          </div>
        </div>
      </div>

      {/* Main Grid: Approved Plan Queue + Live Positions / Orders */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
        
        {/* Left Column: Approved Candidate Queue Ready for Execution */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="hud-card">
            <div className="card-header-line">
              <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Overnight / Scanner Candidate Queue</span>
              <span className="badge mono" style={{ background: 'rgba(237, 76, 34, 0.15)', color: 'var(--accent-orange)' }}>
                {latestPlan?.candidates?.length || 0} / 3 Max
              </span>
            </div>

            {(!latestPlan?.candidates || latestPlan.candidates.filter(c => c.symbol && !['ALL_FO', 'ALL', 'AUTO_DISCOVER'].includes(c.symbol.toUpperCase())).length === 0) ? (
              <div style={{ textAlign: 'center', padding: '2rem 1rem', color: 'var(--text-dim)', fontSize: '0.82rem' }}>
                No active stock option candidates in queue. Generate a plan from Overnight AI Planner.
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                {latestPlan.candidates
                  .filter(c => c.symbol && !['ALL_FO', 'ALL', 'AUTO_DISCOVER'].includes(c.symbol.toUpperCase()))
                  .map((cand, idx) => {
                  const isBullish = cand.bias === 'BULLISH';
                  const contract = cand.primary_contract || {};
                  const mgmt = cand.trade_management || {};

                  const sym = cand.symbol || '';
                  const lotUnits = getEffectiveLotSize(sym, contract.lot_size);
                  const entryPrice = parseFloat(contract.indicative_premium || cand.entry_price || mgmt.entry_price || 0);
                  const slPrice = parseFloat(mgmt.stop_loss || cand.stop_loss || 0);
                  const target1Price = parseFloat(mgmt.target_1 || cand.target_1 || 0);

                  const isHighBeta = HIGH_BETA_SYMBOLS.has(sym.toUpperCase()) || Number(mgmt.risk_reward_ratio) >= 2.0;

                  // Expected Profit & Loss math
                  const profitPts = target1Price > entryPrice ? (target1Price - entryPrice) : (entryPrice * (isHighBeta ? 0.30 : 0.22));
                  const expectedProfit = Math.round(profitPts * lotUnits);
                  const profitPct = entryPrice > 0 ? ((profitPts / entryPrice) * 100).toFixed(1) : (isHighBeta ? '30.0' : '22.0');

                  const lossPts = (slPrice > 0 && slPrice < entryPrice) ? (entryPrice - slPrice) : (entryPrice * 0.15);
                  const expectedLoss = Math.round(lossPts * lotUnits);
                  const lossPct = entryPrice > 0 ? ((lossPts / entryPrice) * 100).toFixed(1) : '15.0';

                  return (
                    <div
                      key={cand.symbol || idx}
                      style={{
                        padding: '0.85rem',
                        background: 'rgba(18, 17, 16, 0.75)',
                        borderRadius: 10,
                        border: `1px solid ${isBullish ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)'}`,
                        boxShadow: '0 4px 14px rgba(0, 0, 0, 0.35)',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '0.65rem'
                      }}
                    >
                      {/* Top Header: Symbol + Glowing Badge + High Beta R:R */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                          <span className="mono" style={{ fontWeight: 800, color: '#fff', fontSize: '1.05rem', letterSpacing: '-0.01em' }}>
                            {cand.symbol}
                          </span>

                          {/* Premium Glowing Pill Badge */}
                          <div
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.45rem',
                              padding: '0.24rem 0.65rem',
                              borderRadius: 20,
                              background: isBullish
                                ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(5, 150, 105, 0.08) 100%)'
                                : 'linear-gradient(135deg, rgba(244, 63, 94, 0.2) 0%, rgba(225, 29, 72, 0.08) 100%)',
                              border: `1px solid ${isBullish ? 'rgba(16, 185, 129, 0.45)' : 'rgba(244, 63, 94, 0.45)'}`,
                              boxShadow: isBullish
                                ? '0 0 10px rgba(16, 185, 129, 0.15)'
                                : '0 0 10px rgba(244, 63, 94, 0.15)'
                            }}
                          >
                            <span
                              style={{
                                width: 7,
                                height: 7,
                                borderRadius: '50%',
                                background: isBullish ? '#10b981' : '#f43f5e',
                                boxShadow: `0 0 6px ${isBullish ? '#10b981' : '#f43f5e'}`
                              }}
                            />
                            <span
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: 800,
                                letterSpacing: '0.04em',
                                color: isBullish ? '#34d399' : '#fb7185'
                              }}
                            >
                              {isBullish ? 'BULLISH' : 'BEARISH'}
                            </span>
                            <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)' }}>•</span>
                            <span
                              style={{
                                fontSize: '0.72rem',
                                fontWeight: 800,
                                color: '#fff',
                                background: 'rgba(255,255,255,0.12)',
                                padding: '0.05rem 0.35rem',
                                borderRadius: 4
                              }}
                            >
                              {contract.option_type || (isBullish ? 'CE' : 'PE')}
                            </span>
                          </div>
                        </div>

                        {/* Adaptive Risk-Reward Badge */}
                        <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
                          {isHighBeta && (
                            <span
                              style={{
                                fontSize: '0.64rem',
                                fontWeight: 800,
                                color: '#c084fc',
                                background: 'rgba(192, 132, 252, 0.16)',
                                border: '1px solid rgba(192, 132, 252, 0.4)',
                                padding: '0.15rem 0.45rem',
                                borderRadius: 4,
                                letterSpacing: '0.04em'
                              }}
                            >
                              HIGH BETA
                            </span>
                          )}
                          <span
                            className="mono"
                            style={{
                              fontSize: '0.75rem',
                              fontWeight: 700,
                              color: isHighBeta ? '#c084fc' : 'var(--accent-orange)',
                              background: isHighBeta ? 'rgba(192, 132, 252, 0.12)' : 'rgba(237, 76, 34, 0.12)',
                              border: `1px solid ${isHighBeta ? 'rgba(192, 132, 252, 0.3)' : 'rgba(237, 76, 34, 0.25)'}`,
                              padding: '0.2rem 0.55rem',
                              borderRadius: 4
                            }}
                          >
                            1 : {mgmt.risk_reward_ratio ? Number(mgmt.risk_reward_ratio).toFixed(1) : (isHighBeta ? '2.0' : '1.5')} R:R
                          </span>
                        </div>
                      </div>

                      {/* 4-Tile Pricing & Contract Grid */}
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(4, 1fr)',
                          gap: '0.45rem',
                          background: 'rgba(0,0,0,0.35)',
                          padding: '0.55rem',
                          borderRadius: 8,
                          border: '1px solid var(--border-light)'
                        }}
                      >
                        <div>
                          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Contract</div>
                          <div className="mono" style={{ fontSize: '0.82rem', fontWeight: 700, color: '#fff', marginTop: '0.1rem' }}>
                            {contract.strike_price} {contract.option_type || (isBullish ? 'CE' : 'PE')}
                          </div>
                          <div style={{ fontSize: '0.64rem', color: 'var(--text-dim)' }}>{lotUnits} / lot</div>
                        </div>

                        <div>
                          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Entry Price</div>
                          <div className="mono" style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--accent-blue)', marginTop: '0.1rem' }}>
                            ₹{entryPrice.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '0.64rem', color: 'var(--text-dim)' }}>Est. Premium</div>
                        </div>

                        <div>
                          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Stop Loss</div>
                          <div className="mono" style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--accent-red)', marginTop: '0.1rem' }}>
                            ₹{slPrice.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '0.64rem', color: 'var(--accent-red)' }}>-{lossPts.toFixed(2)} pts</div>
                        </div>

                        <div>
                          <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Target 1</div>
                          <div className="mono" style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--accent-emerald)', marginTop: '0.1rem' }}>
                            ₹{target1Price.toFixed(2)}
                          </div>
                          <div style={{ fontSize: '0.64rem', color: 'var(--accent-emerald)' }}>+{profitPts.toFixed(2)} pts</div>
                        </div>
                      </div>

                      {/* Expected Profit vs Expected Loss Box */}
                      <div
                        style={{
                          display: 'grid',
                          gridTemplateColumns: '1fr 1fr',
                          gap: '0.5rem',
                          background: 'rgba(255, 255, 255, 0.02)',
                          borderRadius: 8,
                          padding: '0.5rem 0.65rem',
                          border: '1px solid rgba(255, 255, 255, 0.05)'
                        }}
                      >
                        {/* Expected Profit */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: '0.66rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                              Expected Profit (1 Lot)
                            </span>
                            <span
                              className="badge"
                              style={{
                                background: 'rgba(16, 185, 129, 0.15)',
                                color: 'var(--accent-emerald)',
                                fontSize: '0.64rem',
                                padding: '0.05rem 0.35rem'
                              }}
                            >
                              +{profitPct}%
                            </span>
                          </div>
                          <div className="mono" style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>
                            +{formatINR(expectedProfit)}
                          </div>
                        </div>

                        {/* Expected Loss */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem', borderLeft: '1px solid var(--border-light)', paddingLeft: '0.65rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: '0.66rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                              Max Risk / Loss (1 Lot)
                            </span>
                            <span
                              className="badge"
                              style={{
                                background: 'rgba(244, 63, 94, 0.15)',
                                color: 'var(--accent-red)',
                                fontSize: '0.64rem',
                                padding: '0.05rem 0.35rem'
                              }}
                            >
                              -{lossPct}%
                            </span>
                          </div>
                          <div className="mono" style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--accent-red)' }}>
                            -{formatINR(expectedLoss)}
                          </div>
                        </div>
                      </div>

                      {/* Daily News Catalyst & Sentiment Confluence Box */}
                      {(cand.catalyst_summary || cand.technical?.technical_rationale) && (
                        <div
                          style={{
                            fontSize: '0.71rem',
                            color: 'var(--text-muted)',
                            background: 'rgba(255, 255, 255, 0.025)',
                            padding: '0.45rem 0.65rem',
                            borderRadius: 6,
                            border: '1px solid rgba(255, 255, 255, 0.07)',
                            display: 'flex',
                            alignItems: 'flex-start',
                            gap: '0.45rem'
                          }}
                        >
                          <Zap size={13} style={{ color: '#fbbf24', flexShrink: 0, marginTop: 1 }} />
                          <div>
                            <strong style={{ color: '#fff', marginRight: 4 }}>Catalyst & Sentiment:</strong>
                            <span>{cand.catalyst_summary || cand.technical?.technical_rationale}</span>
                          </div>
                        </div>
                      )}

                      {/* Card Footer: RMS Notice & Action Button */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-light)', paddingTop: '0.5rem' }}>
                        <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                          Mandatory RMS Risk Gate Active
                        </div>
                        <button
                          className="btn-primary"
                          style={{ padding: '0.4rem 0.95rem', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                          onClick={() => handleExecuteCandidate(cand)}
                          disabled={!isRunning}
                        >
                          <Zap size={13} />
                          <span>Dispatch Real Order</span>
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Real Broker Orders Book */}
          <div className="hud-card">
            <div className="card-header-line">
              <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Angel One Real Orders Book</span>
              <FileText size={14} color="var(--text-muted)" />
            </div>

            <div className="table-container" style={{ marginTop: '0.5rem' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Order ID</th>
                    <th>Contract</th>
                    <th>Type</th>
                    <th>Qty</th>
                    <th>Price</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.length === 0 ? (
                    <tr>
                      <td colSpan="6" style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '1.25rem' }}>
                        No real orders placed today.
                      </td>
                    </tr>
                  ) : (
                    orders.map(o => (
                      <tr key={o.order_id}>
                        <td className="mono" style={{ fontSize: '0.74rem' }}>{o.order_id}</td>
                        <td className="mono" style={{ fontWeight: 600 }}>{o.symbol}</td>
                        <td>{o.transaction_type}</td>
                        <td className="mono">{o.quantity}</td>
                        <td className="mono">₹{o.price}</td>
                        <td>
                          <span className="badge" style={{
                            background: o.status === 'FILLED' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(237, 76, 34, 0.15)',
                            color: o.status === 'FILLED' ? 'var(--accent-emerald)' : 'var(--accent-orange)'
                          }}>
                            {o.status}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Right Column: Active Live Stock Positions & Bracket Telemetry */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          <div className="hud-card">
            <div className="card-header-line">
              <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Active Live Stock Options Positions</span>
              <Activity size={15} color="var(--accent-emerald)" />
            </div>

            {positions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '2.5rem 1rem', color: 'var(--text-dim)' }}>
                <Activity size={28} style={{ opacity: 0.3, marginBottom: '0.5rem' }} />
                <div style={{ fontSize: '0.85rem' }}>No open live stock options positions.</div>
                <div style={{ fontSize: '0.72rem', marginTop: '0.2rem' }}>Approved signals execute through Angel One SmartAPI RMS.</div>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                {positions.map(pos => {
                  const pnl = parseFloat(pos.unrealized_pnl) || 0;
                  return (
                    <div key={pos.symbol} style={{
                      padding: '0.85rem',
                      background: 'rgba(0,0,0,0.3)',
                      borderRadius: 8,
                      border: '1px solid var(--border-medium)'
                    }}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
                        <div>
                          <div className="mono" style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
                            {pos.symbol}
                          </div>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>
                            Underlying: {pos.underlying} • Qty: {pos.quantity} units ({pos.lots} Lot)
                          </div>
                        </div>

                        <div style={{ textAlign: 'right' }}>
                          <div className="mono" style={{
                            fontSize: '1.1rem',
                            fontWeight: 700,
                            color: pnl >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)'
                          }}>
                            {formatINR(pnl)}
                          </div>
                          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Unrealized</div>
                        </div>
                      </div>

                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.4rem', fontSize: '0.72rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
                        <div>Entry: <span className="mono" style={{ color: '#fff' }}>₹{pos.entry_price}</span></div>
                        <div>Current LTP: <span className="mono" style={{ color: 'var(--accent-blue)' }}>₹{pos.current_ltp}</span></div>
                        <div>Stop Loss: <span className="mono" style={{ color: 'var(--accent-red)' }}>₹{pos.stop_loss}</span></div>
                        <div>Target 1: <span className="mono" style={{ color: 'var(--accent-emerald)' }}>₹{pos.target_1}</span></div>
                      </div>

                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-light)', paddingTop: '0.5rem' }}>
                        <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-emerald)' }}>
                          Native Exchange Stop-Loss Active
                        </span>
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                          Trailing Breakeven at +1.5R
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Mandatory Risk Manager Safeguards Card */}
          <div className="hud-card">
            <div className="card-header-line">
              <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Mandatory RMS Rules & Safeguards</span>
              <ShieldCheck size={15} color="var(--accent-emerald)" />
            </div>

            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: '0.45rem', marginTop: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Fixed Fractional Risk per Trade:</span>
                <span className="mono" style={{ color: '#fff' }}>1.5% of Equity</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Max Daily Drawdown Circuit Breaker:</span>
                <span className="mono" style={{ color: 'var(--accent-red)' }}>3.0% Hard Stop</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Consecutive Loss Auto-Halt:</span>
                <span className="mono" style={{ color: 'var(--accent-orange)' }}>2 Losses</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Midday Chop Avoidance Filter:</span>
                <span className="mono" style={{ color: '#fff' }}>11:15 - 13:30 IST</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span>Mandatory Intraday Square-Off:</span>
                <span className="mono" style={{ color: 'var(--accent-orange)' }}>15:12 IST</span>
              </div>
            </div>
          </div>
        </div>

      </div>

      {/* Emergency Kill Switch Modal */}
      {isKillModalOpen && (
        <div className="modal-backdrop">
          <div
            className="modal-box"
            style={{
              maxWidth: 480,
              background: 'linear-gradient(145deg, #181414 0%, #100c0c 100%)',
              border: '1px solid rgba(244, 63, 94, 0.4)',
              boxShadow: '0 20px 45px rgba(0, 0, 0, 0.8), 0 0 25px rgba(244, 63, 94, 0.2)',
              position: 'relative'
            }}
          >
            {/* Warning Badge */}
            <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.2rem 0.6rem', borderRadius: 4, background: 'rgba(244, 63, 94, 0.15)', border: '1px solid rgba(244, 63, 94, 0.35)', color: 'var(--accent-red)', fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.04em' }}>
              <ShieldAlert size={13} />
              <span>STOCK F&O EMERGENCY OVERRIDE</span>
            </div>

            <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff', margin: '0.6rem 0 0.25rem 0', letterSpacing: '-0.01em' }}>
              Activate Emergency Kill Switch?
            </h3>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1.1rem', lineHeight: 1.45 }}>
              This operation engages the global fail-safe matching engine. All active broker sessions will be liquidated immediately:
            </p>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', marginBottom: '1.25rem' }}>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', padding: '0.55rem 0.75rem', background: 'rgba(0, 0, 0, 0.35)', borderRadius: 6, border: '1px solid var(--border-light)' }}>
                <span style={{ color: 'var(--accent-red)', fontSize: '0.85rem', lineHeight: 1 }}>🛑</span>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-main)', lineHeight: 1.35 }}>
                  <strong>Cancel Working Orders:</strong> All open exchange limit & trigger orders will be cancelled.
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', padding: '0.55rem 0.75rem', background: 'rgba(0, 0, 0, 0.35)', borderRadius: 6, border: '1px solid var(--border-light)' }}>
                <span style={{ color: 'var(--accent-red)', fontSize: '0.85rem', lineHeight: 1 }}>⚡</span>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-main)', lineHeight: 1.35 }}>
                  <strong>Market Square-Off:</strong> Instant market exits submitted for all open Stock Options positions.
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', padding: '0.55rem 0.75rem', background: 'rgba(0, 0, 0, 0.35)', borderRadius: 6, border: '1px solid var(--border-light)' }}>
                <span style={{ color: 'var(--accent-red)', fontSize: '0.85rem', lineHeight: 1 }}>🔒</span>
                <div style={{ fontSize: '0.74rem', color: 'var(--text-main)', lineHeight: 1.35 }}>
                  <strong>Halt Live Agent:</strong> Live execution engine paused immediately.
                </div>
              </div>
            </div>

            <div className="modal-btn-row" style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.65rem' }}>
              <button className="btn-secondary" onClick={() => setIsKillModalOpen(false)} style={{ padding: '0.45rem 1rem', fontSize: '0.78rem' }}>
                Abort / Keep Positions
              </button>
              <button
                className="panic-button"
                style={{ padding: '0.45rem 1.15rem', fontSize: '0.78rem' }}
                onClick={handleTriggerKillSwitch}
              >
                <ShieldAlert size={14} />
                <span>Liquidate All Positions</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
