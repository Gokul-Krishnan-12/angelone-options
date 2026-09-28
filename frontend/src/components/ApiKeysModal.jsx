import React, { useState } from 'react';
import { Key, Shield, AlertTriangle, CheckCircle2, Lock, X, RefreshCw } from 'lucide-react';

export default function ApiKeysModal({ isOpen, onClose, onSaveSuccess }) {
  if (!isOpen) return null;

  const [apiKey, setApiKey] = useState('');
  const [clientCode, setClientCode] = useState('');
  const [pin, setPin] = useState('');
  const [totpSecret, setTotpSecret] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!clientCode.trim() || !apiKey.trim() || !pin.trim() || !totpSecret.trim()) {
      setErrorMsg('All fields are mandatory to connect Angel One SmartAPI.');
      return;
    }

    setIsSubmitting(true);
    setErrorMsg('');

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_code: clientCode.trim(),
          api_key: apiKey.trim(),
          pin: pin.trim(),
          totp_secret: totpSecret.trim(),
        }),
      });

      const data = await res.json();
      if (res.ok) {
        // Trigger live balance refresh
        await fetch('/api/broker/refresh_balance', { method: 'POST' });
        if (onSaveSuccess) onSaveSuccess();
        onClose();
      } else {
        setErrorMsg(data.detail || 'Failed to save broker credentials.');
      }
    } catch (err) {
      const isFetchErr = err?.name === 'TypeError' || String(err).includes('Failed to fetch');
      setErrorMsg(
        isFetchErr
          ? 'Backend engine offline (Failed to fetch). Ensure the Python engine is running on port 5000 (./start.sh).'
          : 'Network error connecting to broker: ' + String(err)
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="modal-backdrop">
      <div className="modal-dialog" style={{ maxWidth: '520px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div className="brand-icon-box" style={{ width: '32px', height: '32px' }}>
              <Key size={16} />
            </div>
            <div>
              <h3 style={{ fontSize: '1.15rem', fontWeight: 800, color: '#fff' }}>Connect Angel One Account</h3>
              <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Required for Live Production Trading & Real RMS Margin Sync</p>
            </div>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        {errorMsg && (
          <div
            style={{
              padding: '0.75rem 1rem',
              borderRadius: '8px',
              fontSize: '0.78rem',
              background: 'rgba(244, 63, 94, 0.15)',
              border: '1px solid var(--accent-red)',
              color: '#fda4af',
              marginBottom: '1rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
            }}
          >
            <AlertTriangle size={16} />
            <span>{errorMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit}>
          <div className="form-group">
            <label className="form-label">Client Code (Angel One User ID)</label>
            <input
              type="text"
              className="form-input mono"
              placeholder="e.g. G123456"
              value={clientCode}
              onChange={(e) => setClientCode(e.target.value)}
              autoFocus
            />
          </div>

          <div className="form-group">
            <label className="form-label">SmartAPI Developer Key</label>
            <input
              type="password"
              className="form-input mono"
              placeholder="Paste Developer API Key from SmartAPI Portal"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
            <div className="form-group">
              <label className="form-label">Account MPIN</label>
              <input
                type="password"
                className="form-input mono"
                placeholder="4-digit PIN"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">TOTP Secret (Base32)</label>
              <input
                type="password"
                className="form-input mono"
                placeholder="Base32 Key"
                value={totpSecret}
                onChange={(e) => setTotpSecret(e.target.value)}
              />
            </div>
          </div>

          <div
            style={{
              fontSize: '0.72rem',
              color: 'var(--text-muted)',
              background: 'var(--bg-dark)',
              padding: '0.75rem',
              borderRadius: '8px',
              border: '1px solid var(--border-light)',
              marginTop: '0.5rem',
              marginBottom: '1.25rem',
              display: 'flex',
              alignItems: 'flex-start',
              gap: '0.5rem',
            }}
          >
            <Lock size={14} style={{ color: 'var(--accent-orange)', flexShrink: 0, marginTop: '2px' }} />
            <span>
              Credentials are securely written to your local <code className="mono">settings.yaml</code> and protected under SEBI static-IP guidelines. pyotp generates fresh dynamic 6-digit MFA codes for session handshakes.
            </span>
          </div>

          <div className="modal-btn-row">
            <button type="button" className="btn-secondary" onClick={onClose} disabled={isSubmitting}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={isSubmitting}
              style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
            >
              {isSubmitting ? <RefreshCw size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Key size={14} />}
              <span>{isSubmitting ? 'Verifying...' : 'Save & Connect Live Broker'}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
