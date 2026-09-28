import React from 'react';
import { Link } from 'react-router-dom';
import MarketRadar from '../components/MarketRadar';
import PositionsTable from '../components/PositionsTable';
import { ShieldCheck, AlertCircle, Wallet, ArrowUpRight, Zap, Pause, Key } from 'lucide-react';
import { formatINR } from '../components/MetricsHud';

export default function Dashboard({
  state,
  isConfigured,
  onOpenConnectModal,
  onExitPosition,
  onStartReal,
  onPauseReal
}) {
  const rms = state.broker_rms || {};
  const isLiveSynced = Boolean(rms.is_live_synced);
  const liveNet = rms.net || 0;
  const liveCash = rms.availablecash || 0;
  const isRunning = state.real_agent_status === 'RUNNING';
  const tradesTaken = state.trades_taken_today ?? (state.paper_state?.trades_taken || 0);
  const maxTradesAllowed = state.max_trades_allowed || 2;

  // Institutional Risk Gate:
  // 1.5% risk per trade. 1 lot Nifty (25 qty) with 12% SL = ~₹750 risk.
  // Minimum required capital (x) = ₹750 / 0.015 = ₹50,000.
  const MIN_CAPITAL_REQUIRED = 50000;
  const isCapitalAdequate = liveCash >= MIN_CAPITAL_REQUIRED;
  const maxLots = Math.max(0, Math.floor((liveCash * 0.015) / 750));

  const positions = state.positions || [];
  const orders = state.orders || [];
  const hasPositions = positions.length > 0;
  const recentOrders = [...orders].reverse().slice(0, 5);

  return (
    <div className="page-container">
      {/* 1. Broker Connection Status Header */}
      {!isConfigured ? (
        <div className="banner-minimal">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-orange)' }} />
            <span style={{ color: 'var(--text-main)', fontSize: '0.78rem' }}>
              Angel One SmartAPI credentials missing — Live exchange trading inactive
            </span>
          </div>
          <button className="btn-banner-action" onClick={onOpenConnectModal}>
            Connect Live Broker →
          </button>
        </div>
      ) : (
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span className="pulse-dot" style={{ background: isLiveSynced ? 'var(--accent-emerald)' : 'var(--accent-orange)' }} />
              <h2 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff' }}>Live Execution Overview</h2>
              <span
                className="brand-badge"
                style={{
                  background: isLiveSynced ? 'rgba(16, 185, 129, 0.15)' : 'rgba(237, 76, 34, 0.15)',
                  color: isLiveSynced ? 'var(--accent-emerald)' : 'var(--accent-orange)',
                }}
              >
                {isLiveSynced ? 'Angel One RMS Verified' : 'Connecting Broker...'}
              </span>
            </div>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Real production portfolio connected to Angel One SmartAPI matching engine
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <button
              className="btn-primary"
              onClick={() => {
                if (isRunning) {
                  if (onPauseReal) onPauseReal();
                } else {
                  if (!isCapitalAdequate) {
                    alert(`Trading Locked: Your live capital is ${formatINR(liveCash)}. Minimum required capital under our 1.5% risk rule is ${formatINR(MIN_CAPITAL_REQUIRED)} (x).`);
                  } else if (onStartReal) {
                    onStartReal();
                  }
                }
              }}
              style={{
                background: isRunning ? 'var(--bg-surface-elevated)' : (isCapitalAdequate ? 'var(--accent-orange)' : 'var(--bg-surface-elevated)'),
                color: isRunning || !isCapitalAdequate ? 'var(--text-muted)' : '#fff',
                display: 'flex',
                alignItems: 'center',
                gap: '0.4rem',
                fontSize: '0.78rem',
              }}
            >
              {isRunning ? <Pause size={13} /> : <Zap size={13} />}
              <span>
                {isRunning
                  ? 'Pause Live Agent'
                  : !isCapitalAdequate
                  ? `Min ${formatINR(MIN_CAPITAL_REQUIRED)} Required`
                  : 'Start Live Trading Agent'}
              </span>
            </button>
          </div>
        </div>
      )}

      {/* 2. Live Broker RMS Metrics HUD */}
      <section className="grid-metrics">
        <div className="hud-card">
          <div className="card-header-line">
            <span>Angel One Net Capital</span>
            <span className="mono text-muted">RMS NET</span>
          </div>
          <div className="metric-big mono font-bold" style={{ color: '#fff' }}>
            {formatINR(liveNet)}
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Available Cash Margin</span>
            <span className="mono font-semibold" style={{ color: 'var(--accent-emerald)' }}>FREE CASH</span>
          </div>
          <div className="metric-big mono font-bold" style={{ color: 'var(--accent-emerald)' }}>
            {formatINR(liveCash)}
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Net Realized P&L</span>
            <span className={`mono font-semibold ${(state.net_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
              POST-CHARGES
            </span>
          </div>
          <div className={`metric-big mono font-bold ${(state.net_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
            {(state.net_pnl || 0) >= 0 ? `+${formatINR(state.net_pnl || 0)}` : formatINR(state.net_pnl || 0)}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            Gross: <span className="mono">{(state.realized_pnl || 0) >= 0 ? `+${formatINR(state.realized_pnl || 0)}` : formatINR(state.realized_pnl || 0)}</span>
          </div>
        </div>

        <div className="hud-card" style={{ borderLeft: '3px solid var(--accent-orange)' }}>
          <div className="card-header-line">
            <span>Brokerage & Taxes</span>
            <span className="mono font-semibold" style={{ color: 'var(--accent-orange)' }}>
              ANGEL ONE + TAX
            </span>
          </div>
          <div className="metric-big mono font-bold" style={{ color: 'var(--accent-orange)' }}>
            -{formatINR(state.total_brokerage || 0)}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            ₹40/trade + STT + Exch + GST
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Daily Drawdown</span>
            <span className="mono loss-text">Limit: 3.0%</span>
          </div>
          <div className="metric-big mono font-bold">
            {(state.daily_drawdown_pct || 0).toFixed(2)}%
          </div>
          <div className="drawdown-track">
            <div
              className="drawdown-fill"
              style={{ width: `${Math.min(100, ((state.daily_drawdown_pct || 0) / 3.0) * 100)}%` }}
            />
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Daily Trade Quota</span>
            <span className="mono text-muted">ILSME</span>
          </div>
          <div className="metric-big mono font-bold">
            {tradesTaken} / {maxTradesAllowed}
          </div>
          <div className="slots-container">
            {Array.from({ length: Math.max(1, maxTradesAllowed) }).map((_, i) => (
              <div
                key={i}
                className={`slot-indicator ${i < tradesTaken ? 'taken' : ''}`}
              />
            ))}
          </div>
        </div>
      </section>

      {/* 3. Live Capital Adequacy & Risk Gate (x Requirement) */}
      <div
        className="hud-card"
        style={{
          borderLeft: `4px solid ${isCapitalAdequate ? 'var(--accent-emerald)' : 'var(--accent-red)'}`,
          background: isCapitalAdequate ? 'rgba(16, 185, 129, 0.03)' : 'rgba(244, 63, 94, 0.04)',
        }}
      >
        <div className="card-header-line">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
            {isCapitalAdequate ? (
              <ShieldCheck size={15} color="var(--accent-emerald)" />
            ) : (
              <AlertCircle size={15} color="var(--accent-red)" />
            )}
            <span style={{ color: isCapitalAdequate ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
              Risk Management Capital Gate (x Parameter)
            </span>
          </div>
          <span className="mono font-semibold" style={{ color: isCapitalAdequate ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
            {isCapitalAdequate ? '● CAPITAL ADEQUATE' : '▲ INSUFFICIENT CAPITAL'}
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', marginTop: '0.5rem', marginBottom: '0.5rem' }}>
          <div className="index-tile">
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Minimum Capital Required (x)</div>
            <div className="mono font-bold" style={{ fontSize: '1.2rem', color: '#fff', margin: '0.2rem 0' }}>
              {formatINR(MIN_CAPITAL_REQUIRED)}
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)' }}>
              Formula: (1 Lot Risk ~₹750) / 0.015 (1.5%)
            </div>
          </div>

          <div className="index-tile">
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Your Live Angel One Margin</div>
            <div className={`mono font-bold ${isCapitalAdequate ? 'profit-text' : 'loss-text'}`} style={{ fontSize: '1.2rem', margin: '0.2rem 0' }}>
              {formatINR(liveCash)}
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)' }}>
              Live synced from SmartConnect RMS
            </div>
          </div>

          <div className="index-tile">
            <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Permissible Sizing</div>
            <div className="mono font-bold" style={{ fontSize: '1.2rem', color: isCapitalAdequate ? 'var(--accent-emerald)' : 'var(--text-dim)', margin: '0.2rem 0' }}>
              {maxLots} Lots ({maxLots * 25} units)
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-dim)' }}>
              Strictly enforces 1.5% institutional risk
            </div>
          </div>
        </div>

        <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', lineHeight: '1.4', borderTop: '1px solid var(--border-light)', paddingTop: '0.5rem' }}>
          {isCapitalAdequate ? (
            <span>
              <strong style={{ color: '#fff' }}>Ready for Live Orders:</strong> Your capital of {formatINR(liveCash)} satisfies the 1.5% sizing requirement. Live agent can execute up to {maxLots} lots per signal.
            </span>
          ) : (
            <span style={{ color: '#fda4af' }}>
              <strong>Execution Guard Active:</strong> You can only trade if your capital is at least <strong>{formatINR(MIN_CAPITAL_REQUIRED)} (x)</strong> as per our 1.5% risk management rule. Taking even 1 single lot of NIFTY options (25 units with ~30 pt stop loss = ₹750 risk) on a balance of {formatINR(liveCash)} would risk over 1.5% of capital. Please maintain at least {formatINR(MIN_CAPITAL_REQUIRED)} in Angel One before live trading.
            </span>
          )}
        </div>
      </div>

      {/* 4. Real Spot Indices Radar (Official Angel One Market Closing Prices) */}
      <MarketRadar spotLevels={state.spot_levels || {}} />

      {/* 5. Live Positions / Recent Real Orders */}
      {hasPositions ? (
        <PositionsTable
          positions={positions}
          onExitPosition={onExitPosition}
        />
      ) : (
        <div className="hud-card">
          <div className="card-header-line">
            <span>Recent Live Executions</span>
            <Link
              to="/orders"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.25rem',
                color: 'var(--accent-orange)',
                textDecoration: 'none',
                fontSize: '0.72rem',
                fontWeight: 600,
              }}
            >
              <span>View Full Order Book</span>
              <ArrowUpRight size={13} />
            </Link>
          </div>

          {recentOrders.length === 0 ? (
            <div style={{ padding: '1.25rem 0', textAlign: 'center', color: 'var(--text-dim)', fontSize: '0.78rem' }}>
              No active live positions or orders · Engine connected to Angel One RMS
            </div>
          ) : (
            <div className="table-wrapper">
              <table className="fintech-table">
                <thead>
                  <tr>
                    <th>Symbol</th>
                    <th>Side</th>
                    <th>Qty @ Price</th>
                    <th>Status</th>
                    <th>Time</th>
                  </tr>
                </thead>
                <tbody>
                  {recentOrders.map((ord) => {
                    const isBuy = ord.transaction_type === 'BUY';
                    const timeStr = ord.timestamp ? ord.timestamp.slice(11, 19) : '--';
                    return (
                      <tr key={ord.order_id}>
                        <td className="mono font-semibold" style={{ color: '#fff' }}>
                          {ord.symbol}
                        </td>
                        <td>
                          <span className={`mono font-semibold ${isBuy ? 'profit-text' : 'loss-text'}`}>
                            {ord.transaction_type}
                          </span>
                        </td>
                        <td className="mono">
                          {ord.quantity} @ ₹{(ord.price || 0).toFixed(2)}
                        </td>
                        <td>
                          <span
                            className="brand-badge"
                            style={{
                              background: ord.status === 'FILLED' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(56, 189, 248, 0.15)',
                              color: ord.status === 'FILLED' ? 'var(--accent-emerald)' : 'var(--accent-blue)',
                            }}
                          >
                            {ord.status}
                          </span>
                        </td>
                        <td className="mono text-muted">{timeStr}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
