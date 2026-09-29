import React, { useState } from 'react';
import { RefreshCw, Activity, ShieldCheck, AlertCircle, ArrowUpRight, ArrowDownRight, Zap } from 'lucide-react';
import { formatINR } from './MetricsHud';

export default function PositionsTable({
  positions = [],
  onExitPosition,
  title = 'Active Derivatives Exposure & Bracket Management',
  emptyText = 'No active options positions. Engine scanning for Institutional Liquidity Sweep setup.',
  showVenueTabs = false
}) {
  const [filterVenue, setFilterVenue] = useState('ALL');
  const [isRefreshingLtp, setIsRefreshingLtp] = useState(false);
  const [refreshNotice, setRefreshNotice] = useState('');

  // Handle manual LTP refresh from Angel One exchange
  const handleRefreshLtp = async () => {
    setIsRefreshingLtp(true);
    setRefreshNotice('');
    try {
      const res = await fetch('/api/positions/refresh_ltp', { method: 'POST' });
      if (res.ok) {
        const data = await res.json();
        setRefreshNotice(`Refreshed ${data.updated || 0} position(s) from exchange`);
        setTimeout(() => setRefreshNotice(''), 3000);
      }
    } catch (e) {
      console.error('Error refreshing position LTP:', e);
    } finally {
      setIsRefreshingLtp(false);
    }
  };

  // Filter positions by selected venue tab if enabled
  const displayedPositions = (positions || []).filter((pos) => {
    if (filterVenue === 'REAL') {
      return !pos.is_paper && pos.execution_mode === 'LIVE';
    }
    if (filterVenue === 'PAPER') {
      return pos.is_paper || pos.execution_mode === 'PAPER';
    }
    return true;
  });

  const hasPositions = displayedPositions.length > 0;
  const totalUnrealizedPnl = displayedPositions.reduce((acc, p) => acc + (parseFloat(p.unrealized_pnl) || 0), 0);

  return (
    <section className="hud-card">
      <div className="card-header-line" style={{ flexWrap: 'wrap', gap: '0.75rem', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 700, color: '#fff', fontSize: '0.85rem' }}>{title}</span>
          <span className="mono text-muted" style={{ fontSize: '0.7rem' }}>Delta ~0.50-0.55 Contracts</span>
        </div>

        {/* Live Controls & Real-time Indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
          {/* Live Feed Status Pill */}
          <div className="live-feed-pill" title="Real-time WebSocket & Tick Engine Active">
            <span className="live-pulse-dot" />
            <span className="mono" style={{ fontSize: '0.7rem' }}>Realtime Feed</span>
          </div>

          {/* Quick Refresh LTP Button */}
          <button
            className="btn-refresh-ltp"
            onClick={handleRefreshLtp}
            disabled={isRefreshingLtp || !hasPositions}
            title="Fetch immediate real-time LTP from Angel One / Exchange"
          >
            <RefreshCw size={12} className={isRefreshingLtp ? 'spin-anim' : ''} />
            <span>{isRefreshingLtp ? 'Syncing...' : 'Refresh Live LTP'}</span>
          </button>

          {/* Optional Venue Filter Tabs */}
          {showVenueTabs && (
            <div className="venue-filter-group">
              <button
                className={`venue-filter-btn ${filterVenue === 'ALL' ? 'active' : ''}`}
                onClick={() => setFilterVenue('ALL')}
              >
                All ({positions.length})
              </button>
              <button
                className={`venue-filter-btn ${filterVenue === 'REAL' ? 'active' : ''}`}
                onClick={() => setFilterVenue('REAL')}
              >
                Real ({positions.filter(p => !p.is_paper && p.execution_mode === 'LIVE').length})
              </button>
              <button
                className={`venue-filter-btn ${filterVenue === 'PAPER' ? 'active' : ''}`}
                onClick={() => setFilterVenue('PAPER')}
              >
                Paper ({positions.filter(p => p.is_paper || p.execution_mode === 'PAPER').length})
              </button>
            </div>
          )}
        </div>
      </div>

      {refreshNotice && (
        <div style={{ padding: '0.35rem 0.75rem', background: 'rgba(16, 185, 129, 0.1)', border: '1px solid rgba(16, 185, 129, 0.25)', borderRadius: '6px', fontSize: '0.72rem', color: '#34d399', marginBottom: '0.75rem' }}>
          ✓ {refreshNotice}
        </div>
      )}

      {/* Realtime P&L Summary Bar when positions exist */}
      {hasPositions && (
        <div className="positions-pnl-summary-bar">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Activity size={13} color="var(--accent-orange)" />
            <span className="mono" style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              Total Open Unrealized P&L:
            </span>
            <strong
              className={`mono ${totalUnrealizedPnl >= 0 ? 'profit-text' : 'loss-text'}`}
              style={{ fontSize: '0.85rem' }}
            >
              {totalUnrealizedPnl >= 0 ? `+${formatINR(totalUnrealizedPnl)}` : formatINR(totalUnrealizedPnl)}
            </strong>
          </div>
          <span className="mono text-muted" style={{ fontSize: '0.7rem' }}>
            Mark-to-Market Auto Re-evaluating
          </span>
        </div>
      )}

      <div className="table-wrapper">
        <table className="fintech-table">
          <thead>
            <tr>
              <th>Contract Symbol</th>
              <th>Venue</th>
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
                  colSpan={10}
                  style={{
                    textAlign: 'center',
                    color: 'var(--text-muted)',
                    padding: '2.5rem',
                  }}
                >
                  {emptyText}
                </td>
              </tr>
            ) : (
              displayedPositions.map((pos) => {
                const isPaper = pos.is_paper || pos.execution_mode === 'PAPER' || pos.execution_venue === 'PAPER';
                const pnl = parseFloat(pos.unrealized_pnl) || 0;
                const pnlPct = parseFloat(pos.unrealized_pnl_pct) || 0;
                const isProfitable = pnl >= 0;
                const ltp = parseFloat(pos.current_ltp) || parseFloat(pos.entry_price) || 0;
                const entry = parseFloat(pos.entry_price) || 0;
                const sl = parseFloat(pos.stop_loss) || 0;
                const t1 = parseFloat(pos.target_1) || 0;

                // Points distance to SL and Target 1
                const slDistPts = sl > 0 ? (ltp - sl).toFixed(2) : null;
                const t1DistPts = t1 > 0 ? (t1 - ltp).toFixed(2) : null;

                return (
                  <tr key={pos.symbol} className="position-row">
                    <td className="mono font-bold" style={{ color: '#fff' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.15rem' }}>
                        <span>{pos.symbol}</span>
                        <span style={{ fontSize: '0.65rem', color: 'var(--text-dim)', fontFamily: 'var(--font-sans)', fontWeight: 400 }}>
                          {pos.underlying || 'Index Option'} • Exch: {pos.exchange || 'NFO'}
                        </span>
                      </div>
                    </td>
                    <td>
                      <span
                        className="venue-pill"
                        style={{
                          background: isPaper ? 'rgba(56, 189, 248, 0.12)' : 'rgba(16, 185, 129, 0.12)',
                          color: isPaper ? '#38bdf8' : 'var(--accent-emerald)',
                          border: `1px solid ${isPaper ? 'rgba(56, 189, 248, 0.25)' : 'rgba(16, 185, 129, 0.25)'}`,
                        }}
                      >
                        {isPaper ? '📝 PAPER' : '⚡ LIVE'}
                      </span>
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
                    <td className="mono">₹{entry.toFixed(2)}</td>
                    <td className="mono">
                      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                        <span className="live-pulse-dot" style={{ width: 5, height: 5 }} />
                        <strong style={{ color: '#fff', fontSize: '0.85rem' }}>
                          ₹{ltp.toFixed(2)}
                        </strong>
                      </div>
                    </td>
                    <td className={`mono font-bold ${isProfitable ? 'profit-text' : 'loss-text'}`}>
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span>
                          {isProfitable ? `+${formatINR(pnl)}` : formatINR(pnl)}
                        </span>
                        <span style={{ fontSize: '0.72rem', opacity: 0.9 }}>
                          {isProfitable ? `+${pnlPct.toFixed(2)}%` : `${pnlPct.toFixed(2)}%`}
                        </span>
                      </div>
                    </td>
                    <td className="mono loss-text">
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span>{sl > 0 ? `₹${sl.toFixed(2)}` : '--'}</span>
                        {slDistPts && (
                          <span style={{ fontSize: '0.67rem', color: 'var(--text-dim)' }}>
                            {slDistPts > 0 ? `${slDistPts} pts buffer` : 'SL Breached'}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="mono profit-text">
                      <div style={{ display: 'flex', flexDirection: 'column' }}>
                        <span>{t1 > 0 ? `₹${t1.toFixed(2)}` : '--'}</span>
                        {t1DistPts && (
                          <span style={{ fontSize: '0.67rem', color: 'var(--text-dim)' }}>
                            {t1DistPts > 0 ? `${t1DistPts} pts away` : 'Target Hit'}
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <button
                        className="btn-liquidate"
                        onClick={() => onExitPosition(pos.symbol)}
                        title={`Immediately close ${pos.symbol}`}
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
