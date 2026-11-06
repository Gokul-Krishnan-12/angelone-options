import React from 'react';
import { AlertTriangle, ShieldCheck, ShieldAlert, X } from 'lucide-react';

export function ModeModal({ isOpen, currentMode, onClose, onConfirm }) {
  if (!isOpen) return null;
  const targetMode = currentMode === 'PAPER' ? 'LIVE' : 'PAPER';
  const isGoingLive = targetMode === 'LIVE';

  return (
    <div className="modal-backdrop">
      <div className="modal-dialog">
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
          {isGoingLive ? (
            <AlertTriangle size={24} color="var(--neon-red)" />
          ) : (
            <ShieldCheck size={24} color="var(--neon-cyan)" />
          )}
          <h3 className="modal-title-text" style={{ color: isGoingLive ? 'var(--neon-red)' : 'var(--neon-cyan)' }}>
            Confirm Switch to {targetMode} Mode
          </h3>
        </div>

        <p className="modal-body-text">
          {isGoingLive ? (
            <>
              <strong>CRITICAL WARNING:</strong> You are about to engage <strong>LIVE PRODUCTION ROUTING</strong> directly with Angel One SmartAPI RMS. Real market orders will be dispatched to exchange matching engines!
            </>
          ) : (
            <>
              Switching execution venue to <strong>Simulated PAPER Trading Mode</strong>. Virtual order ledger with latency and spread slippage will be active.
            </>
          )}
        </p>

        <div className="modal-btn-row">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-primary-action"
            style={{
              background: isGoingLive ? 'var(--neon-red)' : 'var(--neon-cyan)',
              color: isGoingLive ? '#fff' : '#000',
            }}
            onClick={() => onConfirm(targetMode)}
          >
            Confirm Switch to {targetMode}
          </button>
        </div>
      </div>
    </div>
  );
}

export function PanicModal({ isOpen, onClose, onConfirm }) {
  if (!isOpen) return null;

  return (
    <div className="modal-backdrop">
      <div
        className="modal-dialog"
        style={{
          maxWidth: 480,
          background: 'linear-gradient(180deg, #181414 0%, #111010 100%)',
          border: '1px solid rgba(244, 63, 94, 0.45)',
          boxShadow: '0 0 35px rgba(244, 63, 94, 0.22), 0 20px 50px rgba(0, 0, 0, 0.85)',
          borderRadius: 12,
          padding: '1.5rem',
          position: 'relative'
        }}
      >
        {/* Close Icon */}
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '1rem',
            right: '1rem',
            background: 'none',
            border: 'none',
            color: 'var(--text-muted)',
            cursor: 'pointer'
          }}
          title="Close dialog"
        >
          <X size={18} />
        </button>

        {/* Warning Badge */}
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', padding: '0.2rem 0.6rem', borderRadius: 4, background: 'rgba(244, 63, 94, 0.15)', border: '1px solid rgba(244, 63, 94, 0.35)', color: 'var(--accent-red)', fontSize: '0.7rem', fontWeight: 700, letterSpacing: '0.04em' }}>
          <ShieldAlert size={13} />
          <span>COMMON EMERGENCY OVERRIDE</span>
        </div>

        <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff', margin: '0.6rem 0 0.25rem 0', letterSpacing: '-0.01em' }}>
          Activate Emergency Kill Switch?
        </h3>
        <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1.1rem', lineHeight: 1.45 }}>
          This operation engages the global fail-safe matching engine. All active broker sessions will be liquidated immediately:
        </p>

        {/* Action Checklist */}
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
              <strong>Market Square-Off:</strong> Instant market exits submitted for all open Index & Stock Options positions.
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', padding: '0.55rem 0.75rem', background: 'rgba(0, 0, 0, 0.35)', borderRadius: 6, border: '1px solid var(--border-light)' }}>
            <span style={{ color: 'var(--accent-red)', fontSize: '0.85rem', lineHeight: 1 }}>🔒</span>
            <div style={{ fontSize: '0.74rem', color: 'var(--text-main)', lineHeight: 1.35 }}>
              <strong>Halt Trading Agents:</strong> Live execution engines and autonomous dispatch loops will be paused.
            </div>
          </div>
        </div>

        {/* Buttons Row */}
        <div className="modal-btn-row" style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.65rem' }}>
          <button className="btn-secondary" onClick={onClose} style={{ padding: '0.45rem 1rem', fontSize: '0.78rem' }}>
            Abort / Keep Positions
          </button>
          <button
            className="panic-button"
            style={{ padding: '0.45rem 1.15rem', fontSize: '0.78rem' }}
            onClick={onConfirm}
          >
            <ShieldAlert size={14} />
            <span>Liquidate All Positions</span>
          </button>
        </div>
      </div>
    </div>
  );
}
