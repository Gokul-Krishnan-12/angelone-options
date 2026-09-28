import React from 'react';
import { ShieldAlert, Zap, Radio } from 'lucide-react';

export default function Header({
  mode,
  isConnected,
  latency,
  onOpenModeModal,
  onOpenPanicModal
}) {
  return (
    <header className="app-header">
      <div className="brand-section">
        <div className="brand-badge">
          <Zap size={14} />
          ILSME v2.0
        </div>
        <div>
          <h1 className="brand-title">ANGEL ONE SMARTAPI SNIPER</h1>
          <div className="brand-subtitle">Low-Frequency Index Options Quantitative Plane (React)</div>
        </div>
      </div>

      <div className="header-controls">
        {/* Heartbeat Status */}
        <div className="heartbeat-pill">
          <span className={`pulse-indicator ${!isConnected ? 'offline' : ''}`} />
          <span className="mono font-semibold" style={{ fontSize: '0.75rem' }}>
            {isConnected ? 'FEED CONNECTED' : 'DISCONNECTED'}
          </span>
          <span className="text-muted">|</span>
          <span className="mono text-muted" style={{ fontSize: '0.75rem' }}>
            {isConnected ? `${latency}ms` : '--'}
          </span>
        </div>

        {/* Mode Switcher */}
        <button
          className={`btn-mode ${mode === 'LIVE' ? 'live' : 'paper'}`}
          onClick={onOpenModeModal}
          title="Click to toggle execution mode"
        >
          <span
            className="pulse-indicator"
            style={
              mode === 'LIVE'
                ? { background: 'var(--neon-red)', boxShadow: '0 0 10px var(--neon-red)' }
                : {}
            }
          />
          {mode === 'LIVE' ? 'LIVE TRADING [Angel One RMS]' : 'PAPER TRADING [Simulated]'}
        </button>

        {/* Emergency Panic Switch */}
        <button
          className="btn-panic"
          onClick={onOpenPanicModal}
          title="Cancel all orders & liquidate positions immediately"
        >
          <ShieldAlert size={16} />
          PANIC / KILL SWITCH
        </button>
      </div>
    </header>
  );
}
