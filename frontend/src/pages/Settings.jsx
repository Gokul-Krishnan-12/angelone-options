import React, { useState, useEffect } from 'react';
import {
  Key,
  Shield,
  Save,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Wallet,
  Clock,
  Target,
  Send,
  Bot
} from 'lucide-react';
import { formatINR } from '../components/MetricsHud';

export default function Settings({ state, onRefreshBalance }) {
  // Credentials
  const [apiKey, setApiKey] = useState('');
  const [clientCode, setClientCode] = useState('');
  const [pin, setPin] = useState('');
  const [totpSecret, setTotpSecret] = useState('');
  const [isConfigured, setIsConfigured] = useState(false);
  const [maskedKey, setMaskedKey] = useState('');

  // Telegram Configuration
  const [telegramEnabled, setTelegramEnabled] = useState(true);
  const [telegramBotToken, setTelegramBotToken] = useState('8834022656:AAGsTEx46GIgP7XBar5Z4URNP2oEvZGfojM');
  const [telegramChatId, setTelegramChatId] = useState('650527213');
  const [telegramEodTime, setTelegramEodTime] = useState('15:15');
  const [isTelegramTesting, setIsTelegramTesting] = useState(false);
  const [isEodTesting, setIsEodTesting] = useState(false);

  // Risk parameters
  const [riskPerTrade, setRiskPerTrade] = useState(1.5);
  const [maxDrawdown, setMaxDrawdown] = useState(3.0);
  const [maxTrades, setMaxTrades] = useState(2);

  // Strategy Dual Engines
  const [enableIlsmeSweep, setEnableIlsmeSweep] = useState(true);
  const [enableMomentumBreakout, setEnableMomentumBreakout] = useState(true);

  // Status
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [message, setMessage] = useState(null);

  const [serverOffline, setServerOffline] = useState(false);

  useEffect(() => {
    loadSettings();
  }, []);

  const loadSettings = async () => {
    try {
      const res = await fetch('/api/settings');
      if (res.ok) {
        setServerOffline(false);
        const data = await res.json();
        const b = data.broker || {};
        setClientCode(b.client_code || '');
        setMaskedKey(b.api_key_masked || '');
        setIsConfigured(b.is_configured || false);

        const tg = data.telegram || {};
        if (tg.enabled !== undefined) setTelegramEnabled(tg.enabled);
        if (tg.bot_token) setTelegramBotToken(tg.bot_token);
        if (tg.chat_id) setTelegramChatId(tg.chat_id);
        if (tg.eod_report_time) setTelegramEodTime(tg.eod_report_time);

        const r = data.risk || {};
        if (r.risk_per_trade_pct) setRiskPerTrade(r.risk_per_trade_pct * 100);
        if (r.max_daily_drawdown_pct) setMaxDrawdown(r.max_daily_drawdown_pct * 100);
        if (r.max_trades_per_day) setMaxTrades(r.max_trades_per_day);

        const strat = data.strategy || {};
        if (strat.enable_ilsme_sweep !== undefined) setEnableIlsmeSweep(strat.enable_ilsme_sweep);
        if (strat.enable_momentum_breakout !== undefined) setEnableMomentumBreakout(strat.enable_momentum_breakout);
      } else {
        setServerOffline(true);
      }
    } catch (e) {
      console.error('Failed to load settings:', e);
      setServerOffline(true);
    }
  };

  const handleSendTelegramTest = async () => {
    setIsTelegramTesting(true);
    setMessage(null);
    try {
      const res = await fetch('/api/telegram/test', { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        setMessage({ type: 'success', text: 'Telegram test alert delivered successfully to Chat ID: ' + telegramChatId });
      } else {
        setMessage({ type: 'error', text: data.detail || 'Failed to dispatch Telegram alert' });
      }
    } catch (err) {
      const isFetchErr = err?.name === 'TypeError' || String(err).includes('Failed to fetch');
      setMessage({
        type: 'error',
        text: isFetchErr
          ? 'Backend engine offline (Failed to fetch). Please ensure Python server is active on port 5000 (./start.sh).'
          : 'Network error sending Telegram test: ' + String(err)
      });
    } finally {
      setIsTelegramTesting(false);
    }
  };

  const handleSendTelegramEod = async () => {
    setIsEodTesting(true);
    setMessage(null);
    try {
      const res = await fetch('/api/telegram/send_eod', { method: 'POST' });
      const data = await res.json();
      if (res.ok && data.status === 'success') {
        setMessage({ type: 'success', text: 'End of Day (EOD) performance report dispatched to Telegram!' });
      } else {
        setMessage({ type: 'error', text: data.detail || 'Failed to dispatch EOD report' });
      }
    } catch (err) {
      const isFetchErr = err?.name === 'TypeError' || String(err).includes('Failed to fetch');
      setMessage({
        type: 'error',
        text: isFetchErr
          ? 'Backend engine offline (Failed to fetch). Please ensure Python server is active on port 5000 (./start.sh).'
          : 'Network error sending EOD report: ' + String(err)
      });
    } finally {
      setIsEodTesting(false);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    setIsSaving(true);
    setMessage(null);

    const payload = {
      risk_per_trade_pct: parseFloat(riskPerTrade) / 100,
      max_daily_drawdown_pct: parseFloat(maxDrawdown) / 100,
      max_trades_per_day: parseInt(maxTrades),
      telegram_enabled: telegramEnabled,
      telegram_bot_token: telegramBotToken,
      telegram_chat_id: telegramChatId,
      telegram_eod_time: telegramEodTime,
      enable_ilsme_sweep: enableIlsmeSweep,
      enable_momentum_breakout: enableMomentumBreakout,
    };

    if (apiKey) payload.api_key = apiKey;
    if (clientCode) payload.client_code = clientCode;
    if (pin) payload.pin = pin;
    if (totpSecret) payload.totp_secret = totpSecret;

    try {
      const res = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const d = await res.json();
      if (res.ok) {
        setServerOffline(false);
        if (d.status === 'warning') {
          setMessage({ type: 'warning', text: d.message });
        } else {
          setMessage({ type: 'success', text: 'Settings updated successfully and saved to settings.yaml!' });
        }
        loadSettings();
      } else {
        setMessage({ type: 'error', text: d.detail || 'Failed to save settings' });
      }
    } catch (err) {
      const isFetchErr = err?.name === 'TypeError' || String(err).includes('Failed to fetch');
      setMessage({
        type: 'error',
        text: isFetchErr
          ? 'Backend engine offline (Failed to fetch). Please make sure the Python server is running on port 5000 (run ./start.sh).'
          : String(err)
      });
      if (isFetchErr) setServerOffline(true);
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestAndFetchBalance = async () => {
    setIsTesting(true);
    setMessage(null);
    try {
      const res = await fetch('/api/broker/refresh_balance', { method: 'POST' });
      const data = await res.json();
      if (data.status === 'success') {
        const net = data.data?.net || 0;
        const cash = data.data?.availablecash || 0;
        setMessage({
          type: 'success',
          text: `Angel One connection verified! Live Balance: Net ₹${net.toLocaleString()} | Available Cash ₹${cash.toLocaleString()}`,
        });
        if (onRefreshBalance) onRefreshBalance();
      } else {
        setMessage({ type: 'error', text: data.message || 'Failed to fetch RMS from Angel One' });
      }
    } catch (err) {
      const isFetchErr = err?.name === 'TypeError' || String(err).includes('Failed to fetch');
      setMessage({
        type: 'error',
        text: isFetchErr
          ? 'Backend engine offline (Failed to fetch). Start the trading engine with ./start.sh.'
          : 'Network error querying Angel One: ' + String(err)
      });
    } finally {
      setIsTesting(false);
    }
  };

  const rmsNet = state.broker_rms?.net || state.equity || 100000;
  const rmsCash = state.broker_rms?.availablecash || state.available_margin || 100000;

  return (
    <div className="page-container">
      <div>
        <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>Broker Infrastructure & Quantitative Settings</h2>
        <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
          Manage Angel One SmartAPI credentials, live margin sync, and mathematical risk boundaries
        </div>
      </div>

      {serverOffline && (
        <div
          style={{
            padding: '0.85rem 1.25rem',
            borderRadius: '10px',
            fontSize: '0.82rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            background: 'rgba(239, 68, 68, 0.15)',
            border: '1px solid rgba(239, 68, 68, 0.4)',
            color: '#fca5a5',
          }}
        >
          <AlertCircle size={18} />
          <div>
            <strong>Backend Engine Offline:</strong> Unable to connect to the trading engine on port 5000. Please start the engine in terminal using <code style={{ background: 'rgba(0,0,0,0.3)', padding: '2px 6px', borderRadius: '4px' }}>./start.sh</code>.
          </div>
        </div>
      )}

      {message && (
        <div
          style={{
            padding: '0.85rem 1.25rem',
            borderRadius: '10px',
            fontSize: '0.82rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.75rem',
            background: message.type === 'success' ? 'rgba(30, 215, 96, 0.12)' : message.type === 'warning' ? 'rgba(245, 158, 11, 0.12)' : 'rgba(244, 63, 94, 0.12)',
            border: `1px solid ${message.type === 'success' ? 'var(--accent-emerald)' : message.type === 'warning' ? 'var(--accent-orange)' : 'var(--accent-red)'}`,
            color: message.type === 'success' ? '#6ee7b7' : message.type === 'warning' ? '#fcd34d' : '#fda4af',
          }}
        >
          {message.type === 'success' ? <CheckCircle2 size={18} /> : <AlertCircle size={18} />}
          <span>{message.text}</span>
        </div>
      )}

      {/* Live Balance Overview Card */}
      <div className="hud-card">
        <div className="card-header-line">
          <span>Active Balance in Memory & Angel One RMS</span>
          <div style={{ display: 'flex', gap: '0.5rem' }}>
            <button
              className="btn-secondary"
              onClick={handleTestAndFetchBalance}
              disabled={isTesting}
              style={{ fontSize: '0.74rem', padding: '0.3rem 0.75rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
            >
              <RefreshCw size={13} style={{ animation: isTesting ? 'spin 1s linear infinite' : 'none' }} />
              <span>{isTesting ? 'Querying Angel One...' : 'Fetch Live RMS Balance'}</span>
            </button>
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginTop: '0.5rem' }}>
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>NET LIQUID CAPITAL</div>
            <div className="metric-big mono font-bold" style={{ fontSize: '1.45rem', color: '#fff' }}>
              {formatINR(rmsNet)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>AVAILABLE CASH (RMS)</div>
            <div className="metric-big mono font-bold" style={{ fontSize: '1.45rem', color: 'var(--accent-orange)' }}>
              {formatINR(rmsCash)}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>BROKER SYNC STATE</div>
            <div className="mono font-bold" style={{ fontSize: '1.1rem', color: state.broker_rms?.is_live_synced ? 'var(--accent-emerald)' : 'var(--text-muted)', marginTop: '0.2rem' }}>
              {state.broker_rms?.is_live_synced ? '● Live Broker Synced' : '○ Virtual Ledger Active'}
            </div>
          </div>
        </div>
      </div>

      <form onSubmit={handleSave}>
        <div className="settings-grid">
          {/* Card 1: Angel One Credentials */}
          <div className="hud-card">
            <div className="card-header-line">
              <span>Angel One SmartAPI Authentication</span>
              <Key size={14} color="var(--accent-orange)" />
            </div>

            <div className="form-group">
              <label className="form-label">Client Code (Angel One User ID)</label>
              <input
                type="text"
                className="form-input mono"
                placeholder="e.g. A123456"
                value={clientCode}
                onChange={(e) => setClientCode(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Developer API Key</label>
              <input
                type="password"
                className="form-input mono"
                placeholder={maskedKey ? `Configured (${maskedKey})` : 'Enter SmartAPI Key'}
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">Account PIN (Login Password)</label>
              <input
                type="password"
                className="form-input mono"
                placeholder="4-digit MPIN"
                value={pin}
                onChange={(e) => setPin(e.target.value)}
              />
            </div>

            <div className="form-group">
              <label className="form-label">TOTP Secret (Base32 QR Key)</label>
              <input
                type="password"
                className="form-input mono"
                placeholder="Enter Base32 TOTP Secret Key"
                value={totpSecret}
                onChange={(e) => setTotpSecret(e.target.value)}
              />
            </div>

            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.5rem' }}>
              Multi-factor authentication generates a dynamic 6-digit TOTP on each session boot via pyotp.
            </div>
          </div>

          {/* Card 2: Risk Limits */}
          <div className="hud-card">
            <div className="card-header-line">
              <span>Capital Preservation & Risk Limits</span>
              <Shield size={14} color="var(--accent-emerald)" />
            </div>

            <div className="form-group">
              <label className="form-label">Risk Per Trade (% of Liquid Equity)</label>
              <input
                type="number"
                step="0.1"
                className="form-input mono"
                value={riskPerTrade}
                onChange={(e) => setRiskPerTrade(e.target.value)}
              />
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Default: 1.5% fixed fractional sizing</span>
            </div>

            <div className="form-group">
              <label className="form-label">Hard Daily Drawdown Limit (%)</label>
              <input
                type="number"
                step="0.1"
                className="form-input mono"
                value={maxDrawdown}
                onChange={(e) => setMaxDrawdown(e.target.value)}
              />
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Default: 3.0% (liquidates and halts engine)</span>
            </div>

            <div className="form-group">
              <label className="form-label">Max Trades Per Day</label>
              <input
                type="number"
                className="form-input mono"
                value={maxTrades}
                onChange={(e) => setMaxTrades(e.target.value)}
              />
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Default: 2 completed setups</span>
            </div>
          </div>

          {/* Card 3: Quantitative Timing & Filters */}
          <div className="hud-card">
            <div className="card-header-line">
              <span>Regime Filters & Market Timing</span>
              <Clock size={14} color="var(--accent-orange)" />
            </div>

            <div className="form-group">
              <label className="form-label">Midday Chop Filter (IST)</label>
              <input
                type="text"
                disabled
                className="form-input mono"
                value="11:15 to 13:30 IST"
                style={{ opacity: 0.8 }}
              />
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Blocks entries during lunch consolidation</span>
            </div>

            <div className="form-group">
              <label className="form-label">Mandatory EOD Square-Off (IST)</label>
              <input
                type="text"
                disabled
                className="form-input mono"
                value="15:12 IST"
                style={{ opacity: 0.8 }}
              />
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Liquidates open intraday naked options</span>
            </div>

            <div className="form-group">
              <label className="form-label">0-DTE Expiry Theta Protection</label>
              <input
                type="text"
                disabled
                className="form-input mono"
                value="Rolls before 13:00 IST"
                style={{ opacity: 0.8 }}
              />
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Eliminates morning expiration gamma decay</span>
            </div>
          </div>

          {/* Card 4: Strategy Engines (Dual-Mode: Sweep + Momentum Breakout) */}
          <div className="hud-card">
            <div className="card-header-line">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Target size={14} color="var(--accent-orange)" />
                <span style={{ fontWeight: 700 }}>Dual Quantitative Strategy Engines</span>
              </div>
              <span className="badge badge-cyan" style={{ fontSize: '0.68rem' }}>
                Active Multi-Model
              </span>
            </div>

            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
              Operates across both Paper and Live Real Trade agents with strict 2-trades/day cap and 1.5% equity risk.
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', cursor: 'pointer', background: 'rgba(255,255,255,0.02)', padding: '0.6rem 0.8rem', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                <input
                  type="checkbox"
                  checked={enableIlsmeSweep}
                  onChange={(e) => setEnableIlsmeSweep(e.target.checked)}
                  style={{ marginTop: '0.2rem', accentColor: 'var(--accent-orange)' }}
                />
                <div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    Institutional Liquidity Sweep (ILSME Reversal)
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                    Detects structural liquidity sweeps of PDH / PDL with rejection wicks $\ge 30\%$ and 3m FVG retracement.
                  </div>
                </div>
              </label>

              <label style={{ display: 'flex', alignItems: 'flex-start', gap: '0.6rem', cursor: 'pointer', background: 'rgba(255,255,255,0.02)', padding: '0.6rem 0.8rem', borderRadius: '6px', border: '1px solid var(--border-subtle)' }}>
                <input
                  type="checkbox"
                  checked={enableMomentumBreakout}
                  onChange={(e) => setEnableMomentumBreakout(e.target.checked)}
                  style={{ marginTop: '0.2rem', accentColor: 'var(--accent-orange)' }}
                />
                <div>
                  <div style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    Momentum Trend & Opening Range Breakout (ORB)
                  </div>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                    Captures strong 1-directional trend days (15m OR Breakout + VWAP & 50-EMA trend alignment).
                  </div>
                </div>
              </label>
            </div>
          </div>

          {/* Card 5: Telegram Real-Time Alerts & Remote 2-Way Bot */}
          <div className="hud-card">
            <div className="card-header-line">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Send size={14} color="#06b6d4" />
                <span style={{ fontWeight: 700 }}>Telegram Integration & Daily EOD Report</span>
              </div>
              <span className="badge badge-emerald" style={{ fontSize: '0.68rem', display: 'flex', alignItems: 'center', gap: '0.3rem' }}>
                <Bot size={12} />
                <span>2-Way Bot Connected</span>
              </span>
            </div>

            <div style={{ fontSize: '0.74rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
              Using Angel One Swing keys. Receives real-time trade alerts (entry, TP1 +1.8R, breakeven moved, SL hit) and an automated daily EOD report.
            </div>

            <div className="form-group">
              <label className="form-label">Telegram Bot Token</label>
              <input
                type="text"
                className="form-input mono"
                value={telegramBotToken}
                onChange={(e) => setTelegramBotToken(e.target.value)}
                placeholder="Enter Telegram Bot Token"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Authorized Chat ID</label>
              <input
                type="text"
                className="form-input mono"
                value={telegramChatId}
                onChange={(e) => setTelegramChatId(e.target.value)}
                placeholder="Enter Chat ID"
              />
            </div>

            <div className="form-group">
              <label className="form-label">Automated Daily EOD Report Time (IST)</label>
              <input
                type="text"
                className="form-input mono"
                value={telegramEodTime}
                onChange={(e) => setTelegramEodTime(e.target.value)}
                placeholder="15:15"
              />
              <span style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>Daily performance report scheduled automatically at 15:15 IST</span>
            </div>

            {/* Test & Trigger Actions */}
            <div style={{ display: 'flex', gap: '0.6rem', marginTop: '1rem', flexWrap: 'wrap' }}>
              <button
                type="button"
                className="btn-secondary"
                onClick={handleSendTelegramTest}
                disabled={isTelegramTesting}
                style={{ fontSize: '0.75rem', padding: '0.45rem 0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
              >
                <Send size={13} />
                <span>{isTelegramTesting ? 'Sending Alert...' : 'Send Test Alert'}</span>
              </button>

              <button
                type="button"
                className="btn-secondary"
                onClick={handleSendTelegramEod}
                disabled={isEodTesting}
                style={{ fontSize: '0.75rem', padding: '0.45rem 0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem', borderColor: 'var(--accent-orange)' }}
              >
                <RefreshCw size={13} style={{ animation: isEodTesting ? 'spin 1s linear infinite' : 'none' }} />
                <span>{isEodTesting ? 'Compiling Report...' : 'Dispatch EOD Report Now'}</span>
              </button>
            </div>

            {/* Supported Commands Pill Box */}
            <div style={{ marginTop: '1rem', padding: '0.65rem 0.85rem', background: 'rgba(255,255,255,0.02)', borderRadius: '8px', border: '1px solid rgba(255,255,255,0.06)' }}>
              <div style={{ fontSize: '0.7rem', fontWeight: 600, color: '#06b6d4', marginBottom: '0.35rem' }}>
                Telegram Bot Remote Commands:
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
                <code>/status</code>
                <code>/positions</code>
                <code>/eod</code>
                <code>/trades</code>
                <code>/start [paper|live]</code>
                <code>/stop</code>
                <code>/squareoff</code>
              </div>
            </div>
          </div>
        </div>

        {/* Submit */}
        <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'flex-end', gap: '1rem' }}>
          <button type="submit" className="btn-primary" disabled={isSaving} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
            <Save size={15} />
            <span>{isSaving ? 'Saving...' : 'Save & Apply Settings'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}
