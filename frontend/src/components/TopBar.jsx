import React from 'react';
import { ShieldAlert, Play, Pause, RefreshCw, Wallet, Zap, LogOut, Menu } from 'lucide-react';
import { formatINR } from './MetricsHud';

export default function TopBar({
  state,
  isConnected,
  latency,
  onStartPaper,
  onPausePaper,
  onStartReal,
  onPauseReal,
  onRefreshBalance,
  onOpenPanic,
  isRefreshingBalance,
  onLogout,
  onToggleMobileMenu
}) {
  const isPaper = state.execution_mode === 'PAPER';
  const isLive = state.execution_mode === 'LIVE';
  const realRunning = state.real_agent_status === 'RUNNING';
  const rmsCash = state.broker_rms?.availablecash ?? 0;
  const isLiveSynced = Boolean(state.broker_rms?.is_live_synced);

  return (
    <header className="top-bar">
      <div className="top-bar-left">
        {/* Mobile Hamburger Toggle */}
        <button
          className="mobile-hamburger-btn"
          onClick={onToggleMobileMenu}
          title="Open Menu"
          aria-label="Open Navigation Drawer"
        >
          <Menu size={19} />
        </button>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.45rem' }}>
          <span className="pulse-dot" style={{ background: isConnected ? 'var(--accent-emerald)' : 'var(--accent-red)' }} />
          <span className="mono topbar-stream-text" style={{ fontSize: '0.72rem', color: isConnected ? 'var(--text-muted)' : 'var(--accent-red)' }}>
            {isConnected ? `Stream ${latency}ms` : 'Disconnected'}
          </span>
        </div>

        <span
          className="pill-badge topbar-broker-badge"
          style={{
            background: isLiveSynced ? 'rgba(16, 185, 129, 0.12)' : 'rgba(237, 76, 34, 0.12)',
            color: isLiveSynced ? 'var(--accent-emerald)' : 'var(--accent-orange)',
            border: `1px solid ${isLiveSynced ? 'rgba(16, 185, 129, 0.25)' : 'rgba(237, 76, 34, 0.25)'}`,
          }}
        >
          {isLiveSynced ? 'ANGEL ONE CONNECTED' : 'BROKER DISCONNECTED'}
        </span>
      </div>

      <div className="top-bar-right">
        {/* Real Live Agent Toggle (Paper controls are strictly enclosed in /paper) */}
        <button
          className={`agent-toggle-btn ${realRunning ? 'active-real' : ''}`}
          onClick={realRunning ? onPauseReal : onStartReal}
          title={realRunning ? 'Click to Pause Real Agent' : 'Click to Start Real Agent'}
          style={{
            background: realRunning ? 'rgba(237, 76, 34, 0.18)' : 'var(--bg-surface-elevated)',
            color: realRunning ? '#ff8a65' : 'var(--text-muted)',
            border: '1px solid var(--border-light)',
          }}
        >
          {realRunning ? <Pause size={12} /> : <Zap size={12} />}
          <span className="btn-label-desktop">Real Agent {realRunning ? 'Live' : 'Paused'}</span>
          <span className="btn-label-mobile">{realRunning ? 'Live' : 'Off'}</span>
        </button>

        {/* Live Angel One Balance Chip */}
        <div
          className="balance-chip"
          onClick={onRefreshBalance}
          title="Click to refresh Angel One live RMS balance"
        >
          <Wallet size={13} style={{ color: isLiveSynced ? 'var(--accent-emerald)' : 'var(--text-muted)' }} />
          <span className="mono font-bold" style={{ color: '#fff', fontSize: '0.75rem' }}>
            {formatINR(rmsCash)}
          </span>
          <RefreshCw
            size={11}
            style={{
              color: 'var(--text-muted)',
              animation: isRefreshingBalance ? 'spin 1s linear infinite' : 'none',
            }}
          />
        </div>

        {/* Minimal Panic Switch */}
        <button className="panic-button" onClick={onOpenPanic} title="Emergency Kill Switch">
          <ShieldAlert size={13} />
          <span>Panic</span>
        </button>

        {/* 2FA Logout Button */}
        <button
          className="logout-button"
          onClick={onLogout}
          title="Lock / Logout of terminal"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.35rem',
            background: 'var(--bg-surface-elevated)',
            border: '1px solid var(--border-light)',
            color: 'var(--text-muted)',
            borderRadius: '6px',
            padding: '0.4rem 0.65rem',
            fontSize: '0.72rem',
            cursor: 'pointer',
            transition: 'all 0.15s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.color = 'var(--accent-orange)';
            e.currentTarget.style.borderColor = 'rgba(237, 76, 34, 0.4)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.color = 'var(--text-muted)';
            e.currentTarget.style.borderColor = 'var(--border-light)';
          }}
        >
          <LogOut size={12} />
          <span>Lock</span>
        </button>
      </div>
    </header>
  );
}
