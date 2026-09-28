import React from 'react';
import { AlertTriangle, ShieldCheck } from 'lucide-react';

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
      <div className="modal-dialog" style={{ borderColor: 'var(--neon-red)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem' }}>
          <AlertTriangle size={28} color="var(--neon-red)" />
          <h3 className="modal-title-text" style={{ color: 'var(--neon-red)' }}>
            ACTIVATE GLOBAL PANIC OVERRIDE?
          </h3>
        </div>

        <p className="modal-body-text">
          This operation will immediately:
          <br />• Cancel all open working broker orders
          <br />• Execute instant market square-offs for all open options positions
          <br />• Halt signal generation and disconnect the strategy runner
        </p>

        <div className="modal-btn-row">
          <button className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button
            className="btn-primary-action"
            style={{ background: 'var(--neon-red)', color: '#fff' }}
            onClick={onConfirm}
          >
            EXECUTE EMERGENCY SQUARE-OFF
          </button>
        </div>
      </div>
    </div>
  );
}
