import React from 'react';
import { formatINR } from './MetricsHud';

export default function PositionsTable({ positions, onExitPosition }) {
  const hasPositions = positions && positions.length > 0;

  return (
    <section className="hud-card">
      <div className="card-header-line">
        <span>Active Derivatives Exposure & Bracket Management</span>
        <span className="mono text-muted">Delta ~0.50-0.55 Contracts</span>
      </div>

      <div className="table-wrapper">
        <table className="fintech-table">
          <thead>
            <tr>
              <th>Contract Symbol</th>
              <th>Type</th>
              <th>Lots (Units)</th>
              <th>Entry Price</th>
              <th>Live LTP</th>
              <th>Unrealized P&L</th>
              <th>Stop Loss (Hard)</th>
              <th>Target 1 (+2.0R)</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            {!hasPositions ? (
              <tr>
                <td
                  colSpan={9}
                  style={{
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                    padding: '2.5rem',
                  }}
                >
                  No active options positions. Engine scanning for Institutional Liquidity Sweep setup.
                </td>
              </tr>
            ) : (
              positions.map((pos) => {
                const pnl = pos.unrealized_pnl || 0;
                const pnlPct = pos.unrealized_pnl_pct || 0;
                const isProfitable = pnl >= 0;

                return (
                  <tr key={pos.symbol}>
                    <td className="mono font-bold" style={{ color: '#fff' }}>
                      {pos.symbol}
                    </td>
                    <td>
                      <span
                        className="brand-badge"
                        style={{
                          background: pos.option_type === 'CE' ? '#0284c7' : '#e11d48',
                          color: '#fff',
                        }}
                      >
                        {pos.option_type}
                      </span>
                    </td>
                    <td>
                      {pos.lots} lots ({pos.quantity} units)
                    </td>
                    <td className="mono">₹{(pos.entry_price || 0).toFixed(2)}</td>
                    <td className="mono">₹{(pos.current_ltp || 0).toFixed(2)}</td>
                    <td className={`mono font-bold ${isProfitable ? 'profit-text' : 'loss-text'}`}>
                      {isProfitable ? `+${formatINR(pnl)}` : formatINR(pnl)} ({pnlPct.toFixed(2)}%)
                    </td>
                    <td className="mono loss-text">
                      {pos.stop_loss ? `₹${pos.stop_loss.toFixed(2)}` : '--'}
                    </td>
                    <td className="mono profit-text">
                      {pos.target_1 ? `₹${pos.target_1.toFixed(2)}` : '--'}
                    </td>
                    <td>
                      <button
                        className="btn-liquidate"
                        onClick={() => onExitPosition(pos.symbol)}
                      >
                        Liquidate
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
