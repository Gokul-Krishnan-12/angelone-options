import React, { useState, useEffect, useRef } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';
import StatusBar from './components/StatusBar';
import Dashboard from './pages/Dashboard';
import Orders from './pages/Orders';
import PaperTrade from './pages/PaperTrade';
import AgentControl from './pages/AgentControl';
import Settings from './pages/Settings';
import ActivityLog from './pages/ActivityLog';
import SystemWorkflow from './pages/SystemWorkflow';
import ApiKeysModal from './components/ApiKeysModal';
import { PanicModal } from './components/Modals';
import Login from './components/Login';

export default function App() {
  const [state, setState] = useState({
    execution_mode: 'PAPER',
    starting_equity: 100000.0,
    equity: 100000.0,
    available_margin: 100000.0,
    realized_pnl: 0.0,
    unrealized_pnl: 0.0,
    daily_pnl: 0.0,
    daily_drawdown_pct: 0.0,
    trades_taken_today: 0,
    max_trades_allowed: 2,
    paper_agent_status: 'RUNNING',
    real_agent_status: 'IDLE',
    broker_rms: {
      net: 100000.0,
      availablecash: 100000.0,
      collateral: 0.0,
      utiliseddebits: 0.0,
      is_live_synced: false,
    },
    is_panic_active: false,
    is_halted: false,
    strategy_status: 'Scanning for Liquidity Sweep',
    positions: [],
    orders: [],
    trade_history: [],
    spot_levels: {
      NIFTY: { spot: 24850.0, vwap: 24845.0, pdh: 24950.0, pdl: 24720.0 },
      BANKNIFTY: { spot: 52400.0, vwap: 52380.0, pdh: 52700.0, pdl: 52100.0 },
      SENSEX: { spot: 81200.0, vwap: 81180.0, pdh: 81600.0, pdl: 80800.0 },
    },
  });

  const [isConnected, setIsConnected] = useState(false);
  const [latency, setLatency] = useState(12);
  const [isRefreshingBalance, setIsRefreshingBalance] = useState(false);
  const [isPanicModalOpen, setIsPanicModalOpen] = useState(false);
  const [isConfigured, setIsConfigured] = useState(false);
  const [isConnectModalOpen, setIsConnectModalOpen] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const [logs, setLogs] = useState([
    {
      timestamp: new Date().toTimeString().slice(0, 8),
      level: 'INFO',
      message: 'SmartAPI Sniper Options Engine initialized with Gokul Krishnan design identity.',
    },
  ]);

  const [isAuthenticated, setIsAuthenticated] = useState(null);
  const [token, setToken] = useState(() => localStorage.getItem('sniper_session_token') || '');

  const wsRef = useRef(null);
  const pingTimestampRef = useRef(0);
  const heartbeatTimerRef = useRef(null);
  const reconnectTimerRef = useRef(null);
  const isMountedRef = useRef(true);

  // Check existing session on mount
  useEffect(() => {
    checkAuthStatus();
  }, []);

  const checkAuthStatus = async () => {
    try {
      const curToken = localStorage.getItem('sniper_session_token') || '';
      const res = await fetch('/api/auth/status', {
        headers: curToken ? { Authorization: `Bearer ${curToken}` } : {},
      });
      if (res.ok) {
        const data = await res.json();
        setIsAuthenticated(Boolean(data.authenticated));
      } else {
        setIsAuthenticated(false);
      }
    } catch (e) {
      setIsAuthenticated(false);
    }
  };

  const handleLoginSuccess = (newToken) => {
    localStorage.setItem('sniper_session_token', newToken);
    setToken(newToken);
    setIsAuthenticated(true);
  };

  const handleLogout = async () => {
    try {
      const curToken = token || localStorage.getItem('sniper_session_token') || '';
      await fetch('/api/auth/logout', {
        method: 'POST',
        headers: curToken ? { Authorization: `Bearer ${curToken}` } : {},
      });
    } catch (e) {
      console.error('Logout error:', e);
    }
    localStorage.removeItem('sniper_session_token');
    setToken('');
    setIsAuthenticated(false);
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  // Main data polling & telemetry stream (active only when authenticated)
  useEffect(() => {
    if (!isAuthenticated) return;
    isMountedRef.current = true;
    fetchState();
    checkBrokerConfig();
    handleRefreshBalance();
    setupWebSocket();

    const interval = setInterval(() => {
      fetchState();
      checkBrokerConfig();
    }, 3000);
    return () => {
      isMountedRef.current = false;
      clearInterval(interval);
      if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current);
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [isAuthenticated]);

  const checkBrokerConfig = async () => {
    try {
      const res = await fetch('/api/settings');
      if (res.ok) {
        const data = await res.json();
        setIsConfigured(Boolean(data.broker?.is_configured));
      }
    } catch (e) {
      console.error('Error checking broker config:', e);
    }
  };

  const fetchState = async () => {
    try {
      const res = await fetch('/api/state');
      if (res.ok) {
        const data = await res.json();
        setState((prev) => ({
          ...prev,
          ...data,
          spot_levels: {
            ...prev.spot_levels,
            ...(data.spot_levels || {}),
          },
        }));
      }
    } catch (e) {
      console.error('Error fetching state:', e);
    }
  };

  const setupWebSocket = () => {
    if (!isMountedRef.current) return;
    const curToken = token || localStorage.getItem('sniper_session_token') || '';
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/telemetry${curToken ? `?token=${encodeURIComponent(curToken)}` : ''}`;

    try {
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
      }

      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        if (!isMountedRef.current) return;
        setIsConnected(true);
        addLog('INFO', 'Connected to SmartAPI WebSocket telemetry feed.');
        startHeartbeat();
      };

      ws.onmessage = (event) => {
        if (event.data === 'pong') {
          const lat = Math.max(1, Math.round(performance.now() - pingTimestampRef.current));
          setLatency(lat);
          return;
        }

        try {
          const msg = JSON.parse(event.data);
          handleWebSocketMessage(msg);
        } catch (err) {
          console.error('Error parsing WS message:', err);
        }
      };

      ws.onclose = () => {
        if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current);
        if (!isMountedRef.current) return;
        setIsConnected(false);
        reconnectTimerRef.current = setTimeout(setupWebSocket, 3000);
      };

      ws.onerror = () => {
        if (!isMountedRef.current) return;
        setIsConnected(false);
      };
    } catch (e) {
      console.error('WS init error:', e);
    }
  };

  const startHeartbeat = () => {
    if (heartbeatTimerRef.current) clearTimeout(heartbeatTimerRef.current);
    if (!isMountedRef.current) return;
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      pingTimestampRef.current = performance.now();
      wsRef.current.send('ping');
    }
    heartbeatTimerRef.current = setTimeout(startHeartbeat, 10000);
  };

  const handleWebSocketMessage = (msg) => {
    switch (msg.type) {
      case 'INITIAL_STATE':
      case 'SYSTEM_STATE':
        setState((prev) => ({ ...prev, ...msg.data }));
        break;
      case 'TICK': {
        const tick = msg.data;
        if (!tick) break;
        const tickToken = String(tick.token || '');

        if (['99926000', '99926009', '99919000'].includes(tickToken)) {
          const key =
            tickToken === '99926000'
              ? 'NIFTY'
              : tickToken === '99926009'
              ? 'BANKNIFTY'
              : 'SENSEX';
          setState((prev) => ({
            ...prev,
            spot_levels: {
              ...prev.spot_levels,
              [key]: {
                ...prev.spot_levels[key],
                spot: tick.ltp,
              },
            },
          }));
        }

        // Live dynamic option tick processing for open derivative positions
        setState((prev) => {
          let posChanged = false;
          const updatedPositions = (prev.positions || []).map((pos) => {
            if (String(pos.token) === tickToken || pos.symbol === tick.symbol) {
              posChanged = true;
              const newLtp = parseFloat(tick.ltp) || pos.current_ltp;
              const entry = parseFloat(pos.entry_price) || 0;
              const qty = parseInt(pos.quantity) || 0;
              const diff = newLtp - entry;
              const unrealized = Math.round(diff * qty * 100) / 100;
              const unrealizedPct = entry > 0 ? Math.round((diff / entry) * 10000) / 100 : 0;
              return {
                ...pos,
                current_ltp: newLtp,
                unrealized_pnl: unrealized,
                unrealized_pnl_pct: unrealizedPct,
                last_tick_time: Date.now(),
              };
            }
            return pos;
          });

          if (!posChanged) return prev;

          const totalUnrealized = updatedPositions.reduce(
            (sum, p) => sum + (parseFloat(p.unrealized_pnl) || 0),
            0
          );
          return {
            ...prev,
            positions: updatedPositions,
            unrealized_pnl: Math.round(totalUnrealized * 100) / 100,
          };
        });
        break;
      }
      case 'POSITION_UPDATE': {
        if (msg.data) {
          setState((prev) => {
            const pos = msg.data;
            const existingIdx = (prev.positions || []).findIndex(
              (p) => p.symbol === pos.symbol
            );
            let nextPositions;
            if (pos.is_open === false) {
              nextPositions = (prev.positions || []).filter((p) => p.symbol !== pos.symbol);
            } else if (existingIdx >= 0) {
              nextPositions = [...prev.positions];
              nextPositions[existingIdx] = { ...nextPositions[existingIdx], ...pos };
            } else {
              nextPositions = [pos, ...(prev.positions || [])];
            }
            return { ...prev, positions: nextPositions };
          });
        }
        break;
      }
      case 'LOG_ENTRY':
        addLog(msg.data.level, `[${msg.data.module}] ${msg.data.message}`, msg.data.timestamp);
        break;
      case 'ORDER_UPDATE':
        addLog('INFO', `Order ${msg.data.order_id}: ${msg.data.status} ${msg.data.symbol} (${msg.data.quantity})`);
        fetchState();
        break;
      case 'FILL':
        addLog('SUCCESS', `Execution Fill: ${msg.data.transaction_type} ${msg.data.quantity}x ${msg.data.symbol} @ ₹${msg.data.price}`);
        fetchState();
        break;
      case 'RISK_ALERT':
        addLog('WARNING', `[RISK ${msg.data.level}] ${msg.data.rule_name}: ${msg.data.message}`);
        break;
      case 'PANIC_TRIGGERED':
        setState((prev) => ({ ...prev, is_panic_active: true, is_halted: true }));
        addLog('CRITICAL', 'GLOBAL EMERGENCY PANIC TRIGGERED!');
        fetchState();
        break;
      case 'PANIC_CLEARED':
        setState((prev) => ({ ...prev, is_panic_active: false, is_halted: false }));
        addLog('INFO', 'Panic state cleared. System operational.');
        fetchState();
        break;
      default:
        break;
    }
  };

  const addLog = (level, message, timeStr) => {
    const timestamp = timeStr || new Date().toTimeString().slice(0, 8);
    setLogs((prev) => [...prev.slice(-200), { timestamp, level, message }]);
  };

  // Agent Controls
  const handleStartPaper = async () => {
    try {
      await fetch('/api/agent/paper/start', { method: 'POST' });
      setState((prev) => ({
        ...prev,
        execution_mode: 'PAPER',
        paper_agent_status: 'RUNNING',
        real_agent_status: 'PAUSED',
      }));
      addLog('INFO', 'Paper Trading Agent STARTED (Simulated adverse slippage & latency active).');
    } catch (e) {
      alert('Failed to start Paper Agent: ' + e);
    }
  };

  const handlePausePaper = async () => {
    try {
      await fetch('/api/agent/paper/pause', { method: 'POST' });
      setState((prev) => ({ ...prev, paper_agent_status: 'PAUSED' }));
      addLog('INFO', 'Paper Trading Agent PAUSED.');
    } catch (e) {
      alert('Failed to pause Paper Agent: ' + e);
    }
  };

  const handleStartReal = async () => {
    if (!isConfigured) {
      setIsConnectModalOpen(true);
      addLog('WARNING', 'Live Angel One trading requires API keys. Please configure your credentials.');
      return;
    }

    const rms = state.broker_rms || {};
    const isLiveSynced = Boolean(rms.is_live_synced);
    const MIN_CAPITAL_REQUIRED = 50000;
    const currentCapital = isLiveSynced ? (rms.availablecash || rms.net || 0) : (state.available_margin || state.equity || 0);

    if (currentCapital < MIN_CAPITAL_REQUIRED) {
      alert(`Trading Locked: Insufficient Capital.\n\nYour live Angel One balance is ₹${currentCapital.toLocaleString('en-IN', { minimumFractionDigits: 2 })}.\nMinimum required capital is ₹${MIN_CAPITAL_REQUIRED.toLocaleString('en-IN', { minimumFractionDigits: 2 })} to satisfy the 1.5% risk rule for 1 lot.`);
      return;
    }

    if (window.confirm('Engage LIVE PRODUCTION TRADING with Angel One SmartAPI? Real orders will be routed to exchange matching engines.')) {
      try {
        const res = await fetch('/api/agent/real/start', { method: 'POST' });
        const d = await res.json();
        if (!res.ok || d.status !== 'success') {
          throw new Error(d.detail || d.message || 'Server rejected start request');
        }
        setState((prev) => ({
          ...prev,
          execution_mode: 'LIVE',
          real_agent_status: 'RUNNING',
          paper_agent_status: 'PAUSED',
        }));
        addLog('WARNING', 'REAL TRADING AGENT STARTED - Live Angel One RMS Orders Armed.');
        handleRefreshBalance();
      } catch (e) {
        alert('Failed to start Real Agent: ' + e.message);
      }
    }
  };

  const handlePauseReal = async () => {
    try {
      await fetch('/api/agent/real/pause', { method: 'POST' });
      setState((prev) => ({ ...prev, real_agent_status: 'PAUSED' }));
      addLog('WARNING', 'REAL TRADING AGENT PAUSED.');
    } catch (e) {
      alert('Failed to pause Real Agent: ' + e);
    }
  };

  // Live Angel One Balance Sync
  const handleRefreshBalance = async () => {
    setIsRefreshingBalance(true);
    try {
      const res = await fetch('/api/broker/refresh_balance', { method: 'POST' });
      const d = await res.json();
      if (d.status === 'success' && d.data) {
        setState((prev) => ({
          ...prev,
          broker_rms: d.data,
          available_margin: d.data.availablecash || prev.available_margin,
          equity: d.data.net || prev.equity,
        }));
        addLog('SUCCESS', `Angel One RMS Synced: Net ₹${d.data.net} | Cash ₹${d.data.availablecash}`);
      }
    } catch (e) {
      console.error('Error syncing RMS balance:', e);
    } finally {
      setIsRefreshingBalance(false);
    }
  };

  // Emergency Panic Override
  const handleConfirmPanic = async () => {
    try {
      await fetch('/api/panic', { method: 'POST' });
      setIsPanicModalOpen(false);
      setState((prev) => ({ ...prev, is_panic_active: true, is_halted: true }));
      fetchState();
    } catch (e) {
      alert('Failed to trigger panic: ' + e);
    }
  };

  const handleResetPanic = async () => {
    try {
      await fetch('/api/reset_panic', { method: 'POST' });
      setState((prev) => ({ ...prev, is_panic_active: false, is_halted: false }));
      fetchState();
    } catch (e) {
      alert('Failed to reset panic: ' + e);
    }
  };

  // Surgical position liquidation
  const handleExitPosition = async (symbol) => {
    if (window.confirm(`Execute immediate surgical liquidation for ${symbol}?`)) {
      try {
        await fetch(`/api/exit_position/${symbol}`, { method: 'POST' });
        addLog('INFO', `Liquidating position: ${symbol}...`);
        fetchState();
      } catch (e) {
        alert('Failed to liquidate position: ' + e);
      }
    }
  };

  // Interactive Test Signal Dispatch
  const handleTriggerTestSignal = async (underlying, signalType) => {
    try {
      addLog('INFO', `Dispatching test setup: ${underlying} ${signalType}...`);
      await fetch('/api/test_signal', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ underlying, signal_type: signalType }),
      });
      fetchState();
    } catch (e) {
      alert('Failed to trigger test signal: ' + e);
    }
  };

  // Security gate: Loading state
  if (isAuthenticated === null) {
    return (
      <div className="login-viewport" style={{ background: 'var(--bg-dark)' }}>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '0.9rem' }}>
          <div className="pulse-dot" style={{ width: 14, height: 14, background: 'var(--accent-orange)' }} />
          <span className="mono text-muted" style={{ fontSize: '0.8rem' }}>Verifying 2FA session status...</span>
        </div>
      </div>
    );
  }

  // Security gate: Unauthenticated state -> render Login Screen
  if (isAuthenticated === false) {
    return <Login onLoginSuccess={handleLoginSuccess} />;
  }

  return (
    <BrowserRouter>
      <div className="app-shell">
        {/* Persistent Navigation Sidebar with Mobile Drawer */}
        <Sidebar
          state={state}
          isOpen={isMobileMenuOpen}
          onClose={() => setIsMobileMenuOpen(false)}
        />

        <div className="main-wrapper">
          {/* Persistent Top Header */}
          <TopBar
            state={state}
            isConnected={isConnected}
            latency={latency}
            onStartPaper={handleStartPaper}
            onPausePaper={handlePausePaper}
            onStartReal={handleStartReal}
            onPauseReal={handlePauseReal}
            onRefreshBalance={handleRefreshBalance}
            onOpenPanic={() => setIsPanicModalOpen(true)}
            isRefreshingBalance={isRefreshingBalance}
            onLogout={handleLogout}
            onToggleMobileMenu={() => setIsMobileMenuOpen((prev) => !prev)}
          />

          {/* Panic Override Warning Banner */}
          {state.is_panic_active && (
            <div
              style={{
                background: 'linear-gradient(90deg, rgba(225, 29, 72, 0.3) 0%, rgba(190, 18, 60, 0.2) 100%)',
                borderBottom: '1px solid var(--accent-red)',
                padding: '0.85rem 2rem',
                display: 'flex',
                justifyContent: 'center',
                alignItems: 'center',
                gap: '1.5rem',
              }}
            >
              <span className="mono font-bold" style={{ color: 'var(--accent-red)' }}>
                ⚠️ EMERGENCY PANIC ACTIVE — STRATEGY HALTED & ALL POSITIONS LIQUIDATED
              </span>
              <button className="btn-secondary" style={{ fontSize: '0.78rem', padding: '0.3rem 0.85rem' }} onClick={handleResetPanic}>
                Clear Panic & Resume Strategy
              </button>
            </div>
          )}

          {/* Routed Page Content */}
          <Routes>
            <Route
              path="/"
              element={
                <Dashboard
                  state={state}
                  isConfigured={isConfigured}
                  onOpenConnectModal={() => setIsConnectModalOpen(true)}
                  onExitPosition={handleExitPosition}
                  onStartReal={handleStartReal}
                  onPauseReal={handlePauseReal}
                />
              }
            />
            <Route
              path="/orders"
              element={
                <Orders
                  state={state}
                  onExitPosition={handleExitPosition}
                  onRefresh={fetchState}
                />
              }
            />
            <Route
              path="/paper"
              element={
                <PaperTrade
                  state={state}
                  onStartPaper={handleStartPaper}
                  onPausePaper={handlePausePaper}
                  onTriggerTestSignal={handleTriggerTestSignal}
                  onExitPosition={handleExitPosition}
                />
              }
            />
            <Route
              path="/agent"
              element={
                <AgentControl
                  state={state}
                  isConfigured={isConfigured}
                  onOpenConnectModal={() => setIsConnectModalOpen(true)}
                  onStartReal={handleStartReal}
                  onPauseReal={handlePauseReal}
                  onRefreshBalance={handleRefreshBalance}
                  onExitPosition={handleExitPosition}
                  onOpenPanic={() => setIsPanicModalOpen(true)}
                />
              }
            />
            <Route
              path="/workflow"
              element={<SystemWorkflow />}
            />
            <Route
              path="/settings"
              element={
                <Settings
                  state={state}
                  onRefreshBalance={handleRefreshBalance}
                />
              }
            />
            <Route
              path="/logs"
              element={
                <ActivityLog
                  logs={logs}
                  onClearLogs={() => setLogs([])}
                />
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>

          {/* Persistent Bottom Status Bar */}
          <StatusBar state={state} isConnected={isConnected} latency={latency} />
        </div>

        {/* Global Panic Confirmation Modal */}
        <PanicModal
          isOpen={isPanicModalOpen}
          onClose={() => setIsPanicModalOpen(false)}
          onConfirm={handleConfirmPanic}
        />

        {/* API Credentials Setup Modal */}
        <ApiKeysModal
          isOpen={isConnectModalOpen}
          onClose={() => setIsConnectModalOpen(false)}
          onSaveSuccess={() => {
            checkBrokerConfig();
            handleRefreshBalance();
            fetchState();
          }}
        />
      </div>
    </BrowserRouter>
  );
}
