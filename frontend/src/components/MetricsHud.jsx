import React from 'react';

export function formatINR(val) {
  const num = parseFloat(val) || 0;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2,
  }).format(num);
}

export default function MetricsHud({ state }) {
  const pnl = state.daily_pnl || 0;
  const startEq = state.starting_equity || 100000;
  const pnlPct = ((pnl / startEq) * 100).toFixed(2);
  const drawdownPct = state.daily_drawdown_pct || 0;
  const tradesTaken = state.trades_taken_today || 0;
  const maxTrades = state.max_trades_allowed || 2;
  const fillWidth = Math.min(100, (drawdownPct / 3.0) * 100);

  return (
    <section className="grid-metrics">
      {/* 1. Real-Time P&L */}
      <div className="hud-card">
        <div className="card-header-line">
          <span>Intraday P&L</span>
          <span className={`mono font-semibold ${pnl >= 0 ? 'profit-text' : 'loss-text'}`}>
            {pnl >= 0 ? `+${pnlPct}%` : `${pnlPct}%`}
          </span>
        </div>
        <div className={`metric-big mono ${pnl >= 0 ? 'profit-text' : 'loss-text'}`}>
          {pnl >= 0 ? `+${formatINR(pnl)}` : formatINR(pnl)}
        </div>
      </div>

      {/* 2. Account Equity */}
      <div className="hud-card">
        <div className="card-header-line">
          <span>Total Capital</span>
          <span className="mono text-muted">Margin: {formatINR(state.available_margin || startEq)}</span>
        </div>
        <div className="metric-big mono" style={{ color: '#fff' }}>
          {formatINR(state.equity || startEq)}
        </div>
      </div>

      {/* 3. Daily Risk Monitor */}
      <div className="hud-card">
        <div className="card-header-line">
          <span>Daily Risk (Max 3%)</span>
          <span className="mono" style={{ color: drawdownPct >= 2.0 ? 'var(--accent-red)' : 'var(--text-muted)' }}>
            {drawdownPct.toFixed(2)}%
          </span>
        </div>
        <div className="drawdown-track">
          <div className="drawdown-fill" style={{ width: `${fillWidth}%` }} />
        </div>
      </div>

      {/* 4. Trades Quota */}
      <div className="hud-card">
        <div className="card-header-line">
          <span>Trades Taken</span>
          <span className="mono text-muted">{tradesTaken} of {maxTrades}</span>
        </div>
        <div className="slots-container">
          {Array.from({ length: Math.max(1, maxTrades) }).map((_, i) => (
            <div
              key={i}
              className={`slot-indicator ${i < tradesTaken ? 'taken' : ''}`}
            />
          ))}
        </div>
      </div>
    </section>
  );
}
