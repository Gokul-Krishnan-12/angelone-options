import React from 'react';
import { Zap, Pause, Play, ShieldAlert, CheckCircle2, AlertTriangle, Wallet, Lock, Key, ArrowRight, ShieldCheck, AlertCircle } from 'lucide-react';
import { formatINR } from '../components/MetricsHud';
import PositionsTable from '../components/PositionsTable';

export default function AgentControl({
  state,
  isConfigured,
  onOpenConnectModal,
  onStartReal,
  onPauseReal,
  onRefreshBalance,
  onExitPosition,
  onOpenPanic
}) {
  const isRunning = state.real_agent_status === 'RUNNING';
  const rms = state.broker_rms || {};
  const isLiveSynced = Boolean(rms.is_live_synced);

  // Risk Management Capital Requirement Calculation:
  // - Fixed Risk per Trade: 1.5% (0.015)
  // - 1 Lot NIFTY Options: 25 Qty
  // - Typical 12% - 15% SL on ATM/Slightly ITM option (~30 pts): Risk per lot = 25 * 30 = ₹750
  // - Minimum Capital Required (x) = (Risk per Lot) / 0.015 = 750 / 0.015 = ₹50,000
  const MIN_CAPITAL_REQUIRED = 50000;
  const currentCapital = isLiveSynced ? (rms.availablecash || rms.net || 0) : (state.available_margin || state.equity || 0);
  const isCapitalAdequate = currentCapital >= MIN_CAPITAL_REQUIRED;
  const maxLotsPossible = Math.max(0, Math.floor((currentCapital * 0.015) / 750));

  return (
    <div className="page-container">
      {/* 1. Missing Keys Notice if not configured */}
      {!isConfigured && (
        <div className="banner-minimal">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: 'var(--accent-orange)' }} />
            <span style={{ color: 'var(--text-main)', fontSize: '0.8rem' }}>
              Angel One SmartAPI credentials missing — Live exchange orders cannot be routed
            </span>
          </div>
          <button className="btn-banner-action" onClick={onOpenConnectModal}>
            Connect API Credentials →
          </button>
        </div>
      )}

      {/* Top Banner */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>Real Trading Agent Hub</h2>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Live production execution venue directly connected to Angel One SmartAPI RMS
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <span
            className="pill-badge"
            style={{
              background: isRunning ? 'rgba(237, 76, 34, 0.15)' : 'rgba(244, 63, 94, 0.15)',
              color: isRunning ? 'var(--accent-orange)' : 'var(--accent-red)',
              fontSize: '0.75rem',
              padding: '0.3rem 0.75rem',
            }}
          >
            {isRunning ? '● REAL AGENT RUNNING (LIVE RMS)' : '○ REAL AGENT PAUSED'}
          </span>

          <button
            className="btn-primary"
            onClick={() => {
              if (isRunning) {
                onPauseReal();
              } else {
                if (!isConfigured) {
                  onOpenConnectModal();
                } else if (!isCapitalAdequate) {
                  alert(`Insufficient Capital: Your live capital is ${formatINR(currentCapital)}. You need at least ${formatINR(MIN_CAPITAL_REQUIRED)} (x) to satisfy the 1.5% risk rule for 1 lot.`);
                } else {
                  onStartReal();
                }
              }
            }}
            style={{
              background: isRunning ? 'var(--bg-surface-elevated)' : (isCapitalAdequate && isConfigured ? 'var(--accent-orange)' : 'var(--bg-surface-elevated)'),
              color: isRunning || !isCapitalAdequate ? 'var(--text-muted)' : '#fff',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            {isRunning ? <Pause size={14} /> : <Zap size={14} />}
            <span>
              {isRunning
                ? 'Pause Real Agent'
                : !isConfigured
                ? 'Connect Keys to Trade'
                : !isCapitalAdequate
                ? `Min ${formatINR(MIN_CAPITAL_REQUIRED)} Required`
                : 'Start Real Trading Agent'}
            </span>
          </button>
        </div>
      </div>

      {/* 2. Capital Adequacy & Risk Gate Card (x Requirement) */}
      <div
        className="hud-card"
        style={{
          borderLeft: `4px solid ${isCapitalAdequate ? 'var(--accent-emerald)' : 'var(--accent-red)'}`,
          background: isCapitalAdequate ? 'rgba(16, 185, 129, 0.04)' : 'rgba(244, 63, 94, 0.05)',
        }}
      >
        <div className="card-header-line">
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            {isCapitalAdequate ? (
              <ShieldCheck size={16} color="var(--accent-emerald)" />
            ) : (
              <AlertCircle size={16} color="var(--accent-red)" />
            )}
            <span style={{ color: isCapitalAdequate ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
              Capital Adequacy & Risk Management Gate
            </span>
          </div>
          <span className="mono font-semibold" style={{ color: isCapitalAdequate ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
            {isCapitalAdequate ? '● CAPITAL ADEQUATE' : '▲ INSUFFICIENT CAPITAL'}
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem', marginTop: '0.75rem', marginBottom: '0.75rem' }}>
          <div className="index-tile">
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Minimum Required Capital (x)</div>
            <div className="mono font-bold" style={{ fontSize: '1.25rem', color: '#fff', margin: '0.2rem 0' }}>
              {formatINR(MIN_CAPITAL_REQUIRED)}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>
              Formula: (1 Lot Risk ~₹750) / 0.015 (1.5%)
            </div>
          </div>

          <div className="index-tile">
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Your Current Liquid Capital</div>
            <div className={`mono font-bold ${isCapitalAdequate ? 'profit-text' : 'loss-text'}`} style={{ fontSize: '1.25rem', margin: '0.2rem 0' }}>
              {formatINR(currentCapital)}
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>
              {isLiveSynced ? 'Angel One RMS Available Cash' : 'Virtual Ledger Margin'}
            </div>
          </div>

          <div className="index-tile">
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Max Permissible Sizing</div>
            <div className="mono font-bold" style={{ fontSize: '1.25rem', color: isCapitalAdequate ? 'var(--accent-emerald)' : 'var(--text-dim)', margin: '0.2rem 0' }}>
              {maxLotsPossible} Lots ({maxLotsPossible * 25} units)
            </div>
            <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>
              Strictly capped at 1.5% max risk per trade
            </div>
          </div>
        </div>

        {/* Institutional Explanation */}
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', lineHeight: '1.5', borderTop: '1px solid var(--border-light)', paddingTop: '0.65rem' }}>
          {isCapitalAdequate ? (
            <span>
              <strong style={{ color: '#fff' }}>Risk Protocol Satisfied:</strong> Your capital of {formatINR(currentCapital)} allows you to safely trade <strong>{maxLotsPossible} lot(s)</strong> under the 1.5% risk limit (₹{(currentCapital * 0.015).toFixed(2)} risk budget per trade). 
            </span>
          ) : (
            <span style={{ color: '#fda4af' }}>
              <strong>Trading Locked:</strong> As per our strict 1.5% risk management rule, you can only trade if your capital is at least <strong>{formatINR(MIN_CAPITAL_REQUIRED)} (x)</strong>. Taking even 1 single lot of NIFTY options (25 qty with ~₹30 stop loss = ₹750 risk) on a capital lower than {formatINR(MIN_CAPITAL_REQUIRED)} would exceed the 1.5% risk limit and trigger immediate risk governor rejection. Please maintain at least {formatINR(MIN_CAPITAL_REQUIRED)} in Angel One before trading.
            </span>
          )}
        </div>
      </div>

      {/* 3. Angel One RMS Live Balance Breakdown */}
      <div className="grid-metrics">
        <div className="hud-card">
          <div className="card-header-line">
            <span>Net Equity</span>
            <Wallet size={13} color="var(--accent-emerald)" />
          </div>
          <div className="metric-big mono font-bold">
            {formatINR(rms.net || state.equity || 100000)}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            {isLiveSynced ? '● Synced from Angel One' : '○ Virtual Ledger'}
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Available Cash</span>
            <span className="mono text-muted">RMS</span>
          </div>
          <div className="metric-big mono font-bold" style={{ color: 'var(--accent-emerald)' }}>
            {formatINR(rms.availablecash || state.available_margin || 100000)}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            Free liquid capital for options buying
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Collateral Value</span>
            <span className="mono text-muted">HOLDINGS</span>
          </div>
          <div className="metric-big mono font-bold">
            {formatINR(rms.collateral || 0)}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            Pledged securities margin
          </div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Utilised Debits</span>
            <span className="mono loss-text">MARGIN USED</span>
          </div>
          <div className="metric-big mono font-bold" style={{ color: (rms.utiliseddebits || 0) > 0 ? 'var(--accent-red)' : 'var(--text-muted)' }}>
            {formatINR(rms.utiliseddebits || 0)}
          </div>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)', marginTop: '0.25rem' }}>
            Blocked in active positions
          </div>
        </div>
      </div>

      {/* 4. Active Real Positions Table */}
      <PositionsTable
        positions={state.positions || []}
        onExitPosition={onExitPosition}
      />
    </div>
  );
}
