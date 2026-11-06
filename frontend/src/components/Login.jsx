import React, { useState, useEffect, useRef } from 'react';
import { ShieldCheck, Send, ArrowRight, Lock, AlertCircle, CheckCircle2, RefreshCw, KeyRound } from 'lucide-react';

export default function Login({ onLoginSuccess }) {
  const [otp, setOtp] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [isVerifying, setIsVerifying] = useState(false);
  const [message, setMessage] = useState(null); // { type: 'success' | 'error', text: '' }
  const [cooldown, setCooldown] = useState(0);
  const [hasSentOnce, setHasSentOnce] = useState(false);

  const inputRef = useRef(null);

  // Cooldown countdown timer
  useEffect(() => {
    if (cooldown <= 0) return;
    const timer = setInterval(() => {
      setCooldown((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(timer);
  }, [cooldown]);

  const handleSendOtp = async () => {
    if (cooldown > 0 || isSending) return;
    setIsSending(true);
    setMessage(null);

    try {
      const res = await fetch('/api/auth/send_otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
      });
      const data = await res.json();

      if (res.ok) {
        setMessage({
          type: 'success',
          text: data.message || 'Passcode dispatched to your Telegram bot!',
        });
        setCooldown(data.cooldown || 25);
        setHasSentOnce(true);
        setTimeout(() => inputRef.current?.focus(), 100);
      } else {
        setMessage({
          type: 'error',
          text: data.detail || 'Failed to send OTP to Telegram. Check bot configuration.',
        });
      }
    } catch (err) {
      setMessage({
        type: 'error',
        text: 'Network error communicating with authentication service.',
      });
    } finally {
      setIsSending(false);
    }
  };

  const handleVerifyOtp = async (e) => {
    e?.preventDefault();
    const cleanOtp = otp.trim();
    if (cleanOtp.length < 6 || isVerifying) return;

    setIsVerifying(true);
    setMessage(null);

    try {
      const res = await fetch('/api/auth/verify_otp', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ otp: cleanOtp }),
      });
      const data = await res.json();

      if (res.ok && data.token) {
        setMessage({
          type: 'success',
          text: 'Passcode verified! Accessing trading terminal...',
        });
        setTimeout(() => {
          onLoginSuccess(data.token);
        }, 400);
      } else {
        setMessage({
          type: 'error',
          text: data.detail || 'Invalid verification passcode. Please try again.',
        });
      }
    } catch (err) {
      setMessage({
        type: 'error',
        text: 'Network error validating passcode.',
      });
    } finally {
      setIsVerifying(false);
    }
  };

  return (
    <div className="login-viewport">
      <div className="login-card">
        {/* Glow Header */}
        <div className="login-badge-row">
          <div className="login-icon-bubble">
            <Lock size={20} style={{ color: 'var(--accent-orange)' }} />
          </div>
          <span className="pill-badge" style={{ background: 'rgba(237, 76, 34, 0.12)', color: 'var(--accent-orange)', border: '1px solid rgba(237, 76, 34, 0.25)' }}>
            OPERATOR 2FA ACCESS
          </span>
        </div>

        <div className="login-header">
          <h1 className="login-title">ANGEL ONE SMARTAPI SNIPER</h1>
          <p className="login-subtitle">
            ILSME Quantitative Algorithmic Execution Plane
          </p>
        </div>

        {/* Security Notice */}
        <div className="login-notice">
          <ShieldCheck size={14} style={{ color: 'var(--accent-emerald)', flexShrink: 0 }} />
          <span>Protected endpoint. Verification codes are dispatched directly to your Telegram bot.</span>
        </div>

        {/* Status / Error Banner */}
        {message && (
          <div className={`login-alert ${message.type === 'error' ? 'alert-error' : 'alert-success'}`}>
            {message.type === 'error' ? <AlertCircle size={15} style={{ flexShrink: 0 }} /> : <CheckCircle2 size={15} style={{ flexShrink: 0 }} />}
            <span>{message.text}</span>
          </div>
        )}

        <form onSubmit={handleVerifyOtp} className="login-form">
          {/* Step 1: Dispatch OTP */}
          <div className="login-action-row">
            <button
              type="button"
              className="send-otp-btn"
              onClick={handleSendOtp}
              disabled={cooldown > 0 || isSending}
            >
              {isSending ? (
                <>
                  <RefreshCw size={13} className="spin" />
                  <span>Dispatching to Telegram...</span>
                </>
              ) : cooldown > 0 ? (
                <>
                  <Send size={13} />
                  <span>Resend in {cooldown}s</span>
                </>
              ) : (
                <>
                  <KeyRound size={13} />
                  <span>{hasSentOnce ? 'Send New Passcode' : 'Send Code to Telegram'}</span>
                </>
              )}
            </button>
          </div>

          {/* Step 2: Input OTP */}
          <div className="input-group">
            <label className="input-label">
              <span>6-Digit Passcode</span>
              {hasSentOnce && <span className="mono text-dim" style={{ fontSize: '0.7rem' }}>Valid for 5 mins</span>}
            </label>
            <input
              ref={inputRef}
              type="text"
              inputMode="numeric"
              maxLength={6}
              autoComplete="one-time-code"
              className="mono otp-input"
              placeholder="······"
              value={otp}
              onChange={(e) => setOtp(e.target.value.replace(/\D/g, '').slice(0, 6))}
              disabled={isVerifying}
            />
          </div>

          {/* Step 3: Submit Button */}
          <button
            type="submit"
            className="login-submit-btn"
            disabled={otp.trim().length !== 6 || isVerifying}
          >
            {isVerifying ? (
              <>
                <RefreshCw size={14} className="spin" />
                <span>Verifying Passcode...</span>
              </>
            ) : (
              <>
                <span>Enter Trading Terminal</span>
                <ArrowRight size={14} />
              </>
            )}
          </button>
        </form>

        <div className="login-footer">
          <span className="mono text-dim">SEBI COMPLIANT // SMARTAPI SECURE 2FA HANDSHAKE</span>
        </div>
      </div>
    </div>
  );
}
