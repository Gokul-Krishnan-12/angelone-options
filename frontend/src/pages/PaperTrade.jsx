import React, { useState } from 'react';
import { Play, Pause, Activity, Cpu, ShieldCheck, Zap, Sparkles, PlusCircle, CheckCircle2, Wallet, Trash2, RotateCcw, Target } from 'lucide-react';
import { formatINR } from '../components/MetricsHud';
import PositionsTable from '../components/PositionsTable';
import PnLCalendar from '../components/PnLCalendar';

export default function PaperTrade({
  state,
  onStartPaper,
  onPausePaper,
  onTriggerTestSignal,
  onExitPosition
}) {
  const paperState = state.paper_state || {};
  const isRunning = (paperState.status || state.paper_agent_status) === 'RUNNING';
  const paperCapital = paperState.capital || 50000;
  const pnl = paperState.daily_pnl || 0;
  const drawdownPct = paperState.drawdown_pct || 0;
  const tradesTaken = paperState.trades_taken || 0;
  const maxTradesAllowed = paperState.max_trades_allowed || state.max_trades_allowed || 2;

  const [customCapital, setCustomCapital] = useState('');
  const [isUpdating, setIsUpdating] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');

  const getStrikeDisplay = (tr) => {
    if (tr.strike_price && tr.strike_price > 0) {
      const opt = tr.option_type || (tr.symbol?.toUpperCase().includes('PE') ? 'PE' : 'CE');
      return { strike: tr.strike_price, type: opt };
    }
    if (tr.symbol) {
      const m = tr.symbol.match(/(\d{4,6})\s*(CE|PE)/i);
      if (m) {
        return { strike: parseFloat(m[1]), type: m[2].toUpperCase() };
      }
    }
    return { strike: null, type: tr.option_type || '--' };
  };

  const handleResetTrades = async () => {
    if (!window.confirm('Remove all paper trades and reset daily trade quota back to 0?')) return;
    setIsUpdating(true);
    try {
      const res = await fetch('/api/paper/reset_trades', { method: 'POST' });
      if (res.ok) {
        setSuccessMsg('All paper trades removed and quota reset to 0/2!');
        setTimeout(() => setSuccessMsg(''), 4000);
      }
    } catch (e) {
      alert('Failed to reset paper trades: ' + e);
    } finally {
      setIsUpdating(false);
    }
  };

  const handleDeleteTrade = async (id) => {
    try {
      const res = await fetch(`/api/paper/trade/${id}`, { method: 'DELETE' });
      if (res.ok) {
        setSuccessMsg(`Paper trade ${id} removed successfully.`);
        setTimeout(() => setSuccessMsg(''), 3000);
      }
    } catch (e) {
      alert('Failed to remove trade: ' + e);
    }
  };

  const handleSetCapital = async (amount) => {
    const val = parseFloat(amount);
    if (!val || val <= 0) return;
    setIsUpdating(true);
    setSuccessMsg('');
    try {
      const res = await fetch('/api/paper/capital', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ capital: val }),
      });
      if (res.ok) {
        setSuccessMsg(`Dummy capital updated to ${formatINR(val)}!`);
        setCustomCapital('');
        setTimeout(() => setSuccessMsg(''), 4000);
      }
    } catch (e) {
      alert('Failed to update capital: ' + e);
    } finally {
      setIsUpdating(false);
    }
  };

  const presets = [50000, 100000, 250000, 500000];

  return (
    <div className="page-container">
      {/* Top Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>Paper Trading Agent Hub</h2>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            High-fidelity simulation venue modeling adverse bid-ask slippage and matching engine latency
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span
            className="pill-badge"
            style={{
              background: isRunning ? 'rgba(30, 215, 96, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              color: isRunning ? 'var(--accent-emerald)' : 'var(--accent-red)',
              fontSize: '0.75rem',
              padding: '0.3rem 0.75rem',
            }}
          >
            {isRunning ? '● PAPER AGENT ACTIVE' : '○ PAPER AGENT PAUSED'}
          </span>

          <button
            className="btn-primary"
            onClick={isRunning ? onPausePaper : onStartPaper}
            style={{
              background: isRunning ? 'var(--bg-surface-elevated)' : 'var(--accent-blue)',
              color: isRunning ? 'var(--text-main)' : '#000',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            {isRunning ? <Pause size={14} /> : <Play size={14} />}
            <span>{isRunning ? 'Pause Paper Agent' : 'Start Paper Trading Agent'}</span>
          </button>
        </div>
      </div>

      {/* Interactive Dummy Capital Manager */}
      <div className="hud-card" style={{ borderLeft: '3px solid var(--accent-blue)' }}>
        <div className="card-header-line">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Wallet size={14} color="var(--accent-blue)" />
            <span>Manage Dummy Trading Capital</span>
          </div>
          <span className="mono text-muted">Current: {formatINR(paperCapital)}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '1rem', marginTop: '0.5rem' }}>
          {/* Presets */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Quick Presets:</span>
            {presets.map((amt) => (
              <button
                key={amt}
                className="btn-secondary"
                style={{
                  fontSize: '0.74rem',
                  padding: '0.25rem 0.65rem',
                  borderColor: paperCapital === amt ? 'var(--accent-blue)' : 'var(--border-light)',
                  color: paperCapital === amt ? '#7dd3fc' : 'var(--text-main)',
                }}
                onClick={() => handleSetCapital(amt)}
                disabled={isUpdating}
              >
                {formatINR(amt)}
              </button>
            ))}
          </div>

          {/* Custom Input */}
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSetCapital(customCapital);
            }}
            style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
          >
            <input
              type="number"
              className="form-input mono"
              placeholder="Custom capital (₹)"
              value={customCapital}
              onChange={(e) => setCustomCapital(e.target.value)}
              style={{ width: '160px', padding: '0.35rem 0.6rem', fontSize: '0.78rem' }}
            />
            <button
              type="submit"
              className="btn-primary"
              style={{ padding: '0.35rem 0.8rem', fontSize: '0.78rem' }}
              disabled={isUpdating || !customCapital}
            >
              Set Capital
            </button>
          </form>
        </div>

        {successMsg && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', color: 'var(--accent-emerald)', fontSize: '0.75rem', marginTop: '0.5rem' }}>
            <CheckCircle2 size={13} />
            <span>{successMsg}</span>
          </div>
        )}
      </div>

      {/* Metrics Row */}
      <div className="grid-metrics" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))' }}>
        <div className="hud-card">
          <div className="card-header-line">
            <span>Simulated Capital</span>
            <span className="mono text-muted">VIRTUAL</span>
          </div>
          <div className="metric-big mono font-bold">{formatINR(paperCapital)}</div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            Available Margin: <span className="mono text-main">{formatINR(paperState.available_margin || paperCapital)}</span>
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Net Realized P&L</span>
            <span className={`mono font-semibold ${(paperState.net_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
              POST-CHARGES
            </span>
          </div>
          <div className={`metric-big mono font-bold ${(paperState.net_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
            {(paperState.net_pnl || 0) >= 0 ? `+${formatINR(paperState.net_pnl || 0)}` : formatINR(paperState.net_pnl || 0)}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            Gross P&L: <span className="mono">{(paperState.realized_pnl || 0) >= 0 ? `+${formatINR(paperState.realized_pnl || 0)}` : formatINR(paperState.realized_pnl || 0)}</span>
          </div>
        </div>

        <div className="hud-card" style={{ borderLeft: '3px solid var(--accent-orange)' }}>
          <div className="card-header-line">
            <span>Brokerages</span>
            <span className="mono font-semibold" style={{ color: 'var(--accent-orange)' }}>
              TAX
            </span>
          </div>
          <div className="metric-big mono font-bold" style={{ color: 'var(--accent-orange)' }}>
            -{formatINR(paperState.total_brokerage || 0)}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
            ₹40 flat round-trip + STT + Exch + GST
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Daily Risk Used</span>
            <span className="mono loss-text">Limit: 3.0%</span>
          </div>
          <div className="metric-big mono font-bold">{drawdownPct.toFixed(2)}%</div>
          <div className="drawdown-track">
            <div
              className="drawdown-fill"
              style={{ width: `${Math.min(100, (drawdownPct / 3.0) * 100)}%` }}
            />
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Trade Quota</span>
            <span className="mono text-muted">ILSME</span>
          </div>
          <div className="metric-big mono font-bold">{tradesTaken} / {maxTradesAllowed}</div>
          <div className="slots-container">
            {Array.from({ length: Math.max(1, maxTradesAllowed) }).map((_, i) => (
              <div
                key={i}
                className={`slot-indicator ${i < tradesTaken ? 'taken' : ''}`}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Microstructure Simulation Specs */}
      <div className="hud-card">
        <div className="card-header-line">
          <span>Realistic Microstructure Execution Parameters</span>
          <Cpu size={14} color="var(--accent-orange)" />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '0.75rem', marginTop: '0.5rem' }}>
          <div className="index-tile">
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Fill Pricing Model</div>
            <div className="mono font-bold" style={{ color: '#fff', margin: '0.2rem 0' }}>
              Ask + (Spread × 0.20)
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Adverse liquidity penalty</div>
          </div>

          <div className="index-tile">
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Simulated Latency</div>
            <div className="mono font-bold" style={{ color: '#fff', margin: '0.2rem 0' }}>
              150ms – 250ms
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Network hop & exchange roundtrip</div>
          </div>

          <div className="index-tile">
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Risk Sizing Allocation</div>
            <div className="mono font-bold" style={{ color: 'var(--accent-emerald)', margin: '0.2rem 0' }}>
              1.5% of Equity
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>
              Risk Capital = {formatINR(paperCapital * 0.015)}
            </div>
          </div>
        </div>
      </div>

      {/* Manual Signal Trigger Simulator */}
      <div className="hud-card">
        <div className="card-header-line">
          <span>Interactive Signal Generator (Paper Validation)</span>
          <Sparkles size={14} color="var(--accent-blue)" />
        </div>
        <div style={{ display: 'flex', gap: '0.75rem', flexWrap: 'wrap', marginTop: '0.5rem' }}>
          <button
            className="btn-secondary"
            onClick={() => onTriggerTestSignal('NIFTY', 'BUY_CE')}
          >
            Trigger Nifty Call (CE)
          </button>
          <button
            className="btn-secondary"
            onClick={() => onTriggerTestSignal('NIFTY', 'BUY_PE')}
          >
            Trigger Nifty Put (PE)
          </button>
          <button
            className="btn-secondary"
            onClick={() => onTriggerTestSignal('BANKNIFTY', 'BUY_CE')}
          >
            Trigger BankNifty Call (CE)
          </button>
          <button
            className="btn-secondary"
            onClick={() => onTriggerTestSignal('BANKNIFTY', 'BUY_PE')}
          >
            Trigger BankNifty Put (PE)
          </button>
        </div>
      </div>

      {/* Simulated Active Positions Table */}
      <PositionsTable
        positions={state.positions || []}
        onExitPosition={onExitPosition}
      />

      {/* Historical P&L Calendar & Per-Date Breakdown */}
      <PnLCalendar liveTrades={paperState.completed_trades || []} />

      {/* Completed Paper Trades & Brokerage Ledger */}
      <div className="hud-card" style={{ marginTop: '1.25rem' }}>
        <div className="card-header-line">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Target size={14} color="var(--accent-blue)" />
            <span>Summary of Completed Paper Trades (With Brokerage & Statutory Taxes)</span>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span className="mono text-muted">{(paperState.completed_trades || []).length} Executed</span>
            {(paperState.completed_trades || []).length > 0 && (
              <button
                className="btn-secondary"
                style={{
                  padding: '0.25rem 0.6rem',
                  fontSize: '0.72rem',
                  color: 'var(--accent-red)',
                  borderColor: 'rgba(244, 63, 94, 0.3)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                }}
                onClick={handleResetTrades}
                title="Remove all paper trades and reset quota back to 0/2"
                disabled={isUpdating}
              >
                <RotateCcw size={12} />
                <span>Reset All Paper Trades</span>
              </button>
            )}
          </div>
        </div>

        {!(paperState.completed_trades && paperState.completed_trades.length > 0) ? (
          <div style={{ textAlign: 'center', padding: '1.5rem', color: 'var(--text-muted)', fontSize: '0.8rem' }}>
            No completed paper trades yet today. Trigger a test signal or let the paper agent trade autonomously.
          </div>
        ) : (
          <div>
            {/* Quick Summary Strip */}
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', background: 'rgba(255,255,255,0.02)', padding: '0.6rem 0.75rem', borderRadius: '6px', margin: '0.5rem 0', border: '1px solid var(--border-light)', fontSize: '0.76rem' }}>
              <div>
                <span className="text-muted">Total Trades: </span>
                <span className="mono font-bold text-main">{(paperState.completed_trades || []).length} / 2 Quota</span>
              </div>
              <div>
                <span className="text-muted">Strikes Traded: </span>
                <span className="mono font-semibold" style={{ color: 'var(--accent-blue)' }}>
                  {[...new Set(paperState.completed_trades.map(t => {
                    const info = getStrikeDisplay(t);
                    return info.strike ? `${info.strike} ${info.type}` : t.symbol;
                  }))].join(', ') || '--'}
                </span>
              </div>
              <div style={{ marginLeft: 'auto' }}>
                <span className="text-muted">Net Realized: </span>
                <span className={`mono font-bold ${(paperState.net_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
                  {(paperState.net_pnl || 0) >= 0 ? `+${formatINR(paperState.net_pnl || 0)}` : formatINR(paperState.net_pnl || 0)}
                </span>
              </div>
            </div>

            <div style={{ overflowX: 'auto', marginTop: '0.5rem' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>TIME</th>
                    <th>CONTRACT</th>
                    <th>STRIKE PRICE</th>
                    <th>TYPE</th>
                    <th>QTY</th>
                    <th>ENTRY</th>
                    <th>EXIT</th>
                    <th>GROSS P&L</th>
                    <th>BROKERAGE & TAXES</th>
                    <th>NET P&L</th>
                    <th style={{ textAlign: 'center' }}>ACTION</th>
                  </tr>
                </thead>
                <tbody>
                  {paperState.completed_trades.map((tr) => {
                    const strikeInfo = getStrikeDisplay(tr);
                    return (
                      <tr key={tr.id}>
                        <td className="mono text-muted" style={{ fontSize: '0.72rem' }}>{tr.timestamp}</td>
                        <td className="mono font-semibold">{tr.symbol}</td>
                        <td className="mono font-bold" style={{ color: 'var(--accent-blue)' }}>
                          {strikeInfo.strike ? `₹${strikeInfo.strike.toLocaleString('en-IN')}` : '--'}
                        </td>
                        <td>
                          <span
                            className="pill-badge"
                            style={{
                              background: strikeInfo.type === 'CE' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                              color: strikeInfo.type === 'CE' ? '#38bdf8' : '#f43f5e',
                              fontSize: '0.72rem',
                              padding: '0.15rem 0.5rem',
                            }}
                          >
                            {strikeInfo.type}
                          </span>
                        </td>
                        <td className="mono">{tr.quantity}</td>
                        <td className="mono">₹{tr.entry_price?.toFixed(1) || '-'}</td>
                        <td className="mono">₹{tr.exit_price?.toFixed(1) || '-'}</td>
                        <td className={`mono font-semibold ${(tr.gross_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
                          {(tr.gross_pnl || 0) >= 0 ? `+${formatINR(tr.gross_pnl)}` : formatINR(tr.gross_pnl)}
                        </td>
                        <td className="mono" style={{ color: 'var(--accent-orange)' }}>
                          -{formatINR(tr.total_charges || 65)}
                        </td>
                        <td className={`mono font-bold ${(tr.net_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
                          {(tr.net_pnl || 0) >= 0 ? `+${formatINR(tr.net_pnl)}` : formatINR(tr.net_pnl)}
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <button
                            className="btn-secondary"
                            style={{
                              padding: '0.2rem 0.45rem',
                              fontSize: '0.7rem',
                              color: 'var(--accent-red)',
                              borderColor: 'rgba(244, 63, 94, 0.25)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '0.25rem',
                            }}
                            onClick={() => handleDeleteTrade(tr.id)}
                            title="Remove this paper trade from ledger"
                          >
                            <Trash2 size={11} />
                            <span>Remove</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
