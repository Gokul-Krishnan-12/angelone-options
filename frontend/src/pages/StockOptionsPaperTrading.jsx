import React, { useState, useEffect, useMemo } from 'react';
import {
  Activity,
  Play,
  Pause,
  RotateCcw,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Layers,
  Settings,
  ShieldCheck,
  CheckCircle2,
  XCircle,
  FileText,
  AlertTriangle,
  Zap,
  DollarSign,
  Search,
  ChevronLeft,
  ChevronRight,
  Calendar,
  Filter,
  Clock,
  ArrowUpRight,
  ArrowDownRight
} from 'lucide-react';
import { formatINR } from '../components/MetricsHud';
import { authFetch } from '../utils/api';
import PnLCalendar from '../components/PnLCalendar';

const FO_LOT_SIZES = {
  RELIANCE: 250,
  TCS: 175,
  INFY: 400,
  HDFCBANK: 550,
  ICICIBANK: 700,
  SBIN: 750,
  BHARTIARTL: 950,
  KOTAKBANK: 400,
  LT: 175,
  AXISBANK: 625,
  BAJFINANCE: 125,
  MARUTI: 50,
  TATAMOTORS: 1425,
  SUNPHARMA: 350,
  ITC: 1600,
  HINDUNILVR: 300,
  NTPC: 1500,
  TATASTEEL: 5500,
  WIPRO: 1500,
  'M&M': 350,
  COFORGE: 150,
  PERSISTENT: 100,
  DIXON: 100,
  POLYCAB: 125,
  INDUSINDBK: 500,
  CANBK: 6750,
  DLF: 825,
  FEDERALBNK: 5000,
  PFC: 1300,
  RECLTD: 1400,
  BHEL: 2625,
  TRENT: 100,
  HAL: 150,
  BEL: 2850,
  ADANIENT: 300,
  ADANIPORTS: 400,
};

const HIGH_BETA_SYMBOLS = new Set([
  'COFORGE', 'PERSISTENT', 'DIXON', 'POLYCAB', 'INDUSINDBK',
  'BHEL', 'DLF', 'ADANIENT', 'ADANIPORTS', 'TRENT', 'HAL',
  'BEL', 'CANBK', 'FEDERALBNK', 'PFC', 'RECLTD', 'TATASTEEL',
  'HINDALCO', 'TATAMOTORS', 'SBIN'
]);

const getEffectiveLotSize = (sym, rawLot) => {
  const parsed = Number(rawLot);
  if (parsed && parsed > 10) return parsed;
  return FO_LOT_SIZES[sym?.toUpperCase()] || 250;
};

export default function StockOptionsPaperTrading() {
  const [paperStatus, setPaperStatus] = useState(null);
  const [positions, setPositions] = useState([]);
  const [orders, setOrders] = useState([]);
  const [trades, setTrades] = useState([]);
  const [latestPlan, setLatestPlan] = useState(null);

  const [activeTab, setActiveTab] = useState('active'); // 'active' | 'orders' | 'trades' | 'analytics'

  // Orders Filtering & Pagination
  const [ordersSearch, setOrdersSearch] = useState('');
  const [ordersStatusFilter, setOrdersStatusFilter] = useState('ALL');
  const [ordersPage, setOrdersPage] = useState(1);
  const [ordersPageSize, setOrdersPageSize] = useState(10);

  // Trades Filtering & Pagination
  const [tradesSearch, setTradesSearch] = useState('');
  const [tradesOutcomeFilter, setTradesOutcomeFilter] = useState('ALL'); // 'ALL' | 'WIN' | 'LOSS'
  const [tradesPage, setTradesPage] = useState(1);
  const [tradesPageSize, setTradesPageSize] = useState(10);

  // Positions Search
  const [positionsSearch, setPositionsSearch] = useState('');

  // Modals & Notifications
  const [virtualCapitalInput, setVirtualCapitalInput] = useState('500000');
  const [slippageInput, setSlippageInput] = useState('0.35');
  const [riskPctInput, setRiskPctInput] = useState('2.0');
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [showResetModal, setShowResetModal] = useState(false);
  const [notification, setNotification] = useState(null);

  useEffect(() => {
    fetchPaperData();
    const interval = setInterval(fetchPaperData, 4000);
    return () => clearInterval(interval);
  }, []);

  const fetchPaperData = async () => {
    try {
      const [stRes, posRes, ordRes, trRes, pRes] = await Promise.all([
        authFetch('/api/stock-options/paper/status'),
        authFetch('/api/stock-options/paper/positions'),
        authFetch('/api/stock-options/paper/orders?limit=100'),
        authFetch('/api/stock-options/paper/trades?limit=100'),
        authFetch('/api/stock-options/planner/latest')
      ]);

      if (stRes.ok) {
        const stData = await stRes.json();
        setPaperStatus(stData);
        setVirtualCapitalInput(String(stData.virtual_capital || '500000'));
        setSlippageInput(String(stData.slippage_pct || '0.35'));
        setRiskPctInput(String(stData.risk_per_trade_pct || '2.0'));
      }
      if (posRes.ok) setPositions(await posRes.json());
      if (ordRes.ok) setOrders(await ordRes.json());
      if (trRes.ok) setTrades(await trRes.json());
      if (pRes.ok) {
        const pData = await pRes.json();
        if (pData.plan_id) setLatestPlan(pData);
      }
    } catch (e) {
      console.error('Error fetching paper trading data:', e);
    }
  };

  const showNotice = (msg, isError = false) => {
    setNotification({ text: msg, isError });
    setTimeout(() => setNotification(null), 5000);
  };

  const handleStartPaper = async () => {
    try {
      const res = await authFetch('/api/stock-options/paper/start', { method: 'POST' });
      if (res.ok) {
        showNotice('Paper Trading Agent started.');
        fetchPaperData();
      }
    } catch (e) {
      showNotice('Failed to start paper agent.', true);
    }
  };

  const handlePausePaper = async () => {
    try {
      const res = await authFetch('/api/stock-options/paper/pause', { method: 'POST' });
      if (res.ok) {
        showNotice('Paper Trading Agent paused.');
        fetchPaperData();
      }
    } catch (e) {
      showNotice('Failed to pause paper agent.', true);
    }
  };

  const handleSavePaperConfig = async () => {
    try {
      const res = await authFetch('/api/stock-options/paper/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          virtual_capital: parseFloat(virtualCapitalInput),
          slippage_pct: parseFloat(slippageInput),
          risk_per_trade_pct: parseFloat(riskPctInput)
        })
      });
      if (res.ok) {
        showNotice('Independent paper trading configuration updated.');
        setShowConfigModal(false);
        fetchPaperData();
      }
    } catch (e) {
      showNotice('Failed to update paper settings.', true);
    }
  };

  const handleResetPaper = async () => {
    try {
      const cap = parseFloat(virtualCapitalInput) || 500000;
      const res = await authFetch(`/api/stock-options/paper/reset?capital=${cap}`, { method: 'POST' });
      if (res.ok) {
        showNotice(`Virtual paper ledger reset to ${formatINR(cap)}.`);
        setShowResetModal(false);
        fetchPaperData();
      }
    } catch (e) {
      showNotice('Failed to reset paper ledger.', true);
    }
  };

  const handleExecutePaperCandidate = async (candidate) => {
    try {
      const res = await authFetch('/api/stock-options/paper/execute-candidate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate, plan_id: latestPlan?.plan_id || '' })
      });
      const data = await res.json();
      if (data.status === 'success') {
        showNotice(`Simulated order filled for ${candidate.symbol}!`);
        fetchPaperData();
      } else {
        showNotice(`Paper execution rejected: ${data.reason || data.message}`, true);
      }
    } catch (e) {
      showNotice('Error simulating trade execution.', true);
    }
  };

  const handleClosePosition = async (symbol, currentLtp) => {
    try {
      const res = await authFetch('/api/stock-options/paper/close-position', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, exit_price: currentLtp, reason: 'Operator Manual Square-off' })
      });
      const data = await res.json();
      if (data.status === 'success') {
        showNotice(`Closed simulated position ${symbol} @ ₹${data.exit_price}`);
        fetchPaperData();
      } else {
        showNotice(data.message || 'Error closing position', true);
      }
    } catch (e) {
      showNotice('Failed to close position', true);
    }
  };

  const status = paperStatus?.status || 'RUNNING';
  const isRunning = status === 'RUNNING';
  const perf = paperStatus?.performance || {};

  const totalUnrealized = positions.reduce((acc, p) => acc + (parseFloat(p.unrealized_pnl) || 0), 0);
  const totalNetRealized = perf.total_net_pnl || 0;

  const formatTimestamp = (ts) => {
    if (!ts) return '—';
    try {
      const d = new Date(ts);
      if (isNaN(d.getTime())) return ts;
      return d.toLocaleString('en-IN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
      });
    } catch {
      return ts;
    }
  };

  // --- Filtering & Pagination for Orders ---
  const filteredOrders = useMemo(() => {
    return (orders || []).filter((o) => {
      const q = ordersSearch.trim().toLowerCase();
      const matchSearch =
        !q ||
        (o.symbol && o.symbol.toLowerCase().includes(q)) ||
        (o.order_id && o.order_id.toLowerCase().includes(q)) ||
        (o.underlying && o.underlying.toLowerCase().includes(q));

      const matchStatus =
        ordersStatusFilter === 'ALL' ||
        (o.status && o.status.toUpperCase() === ordersStatusFilter);

      return matchSearch && matchStatus;
    });
  }, [orders, ordersSearch, ordersStatusFilter]);

  const totalOrderPages = Math.max(1, Math.ceil(filteredOrders.length / ordersPageSize));
  const paginatedOrders = useMemo(() => {
    const start = (ordersPage - 1) * ordersPageSize;
    return filteredOrders.slice(start, start + ordersPageSize);
  }, [filteredOrders, ordersPage, ordersPageSize]);

  // --- Filtering & Pagination for Trades ---
  const filteredTrades = useMemo(() => {
    return (trades || []).filter((t) => {
      const q = tradesSearch.trim().toLowerCase();
      const matchSearch =
        !q ||
        (t.symbol && t.symbol.toLowerCase().includes(q)) ||
        (t.underlying && t.underlying.toLowerCase().includes(q)) ||
        (t.exit_reason && t.exit_reason.toLowerCase().includes(q));

      const net = parseFloat(t.net_pnl) || 0;
      let matchOutcome = true;
      if (tradesOutcomeFilter === 'WIN') matchOutcome = net > 0;
      if (tradesOutcomeFilter === 'LOSS') matchOutcome = net < 0;

      return matchSearch && matchOutcome;
    });
  }, [trades, tradesSearch, tradesOutcomeFilter]);

  const totalTradePages = Math.max(1, Math.ceil(filteredTrades.length / tradesPageSize));
  const paginatedTrades = useMemo(() => {
    const start = (tradesPage - 1) * tradesPageSize;
    return filteredTrades.slice(start, start + tradesPageSize);
  }, [filteredTrades, tradesPage, tradesPageSize]);

  // --- Filtered Open Positions ---
  const filteredPositions = useMemo(() => {
    if (!positionsSearch.trim()) return positions;
    const q = positionsSearch.trim().toLowerCase();
    return positions.filter(
      (p) =>
        (p.symbol && p.symbol.toLowerCase().includes(q)) ||
        (p.underlying && p.underlying.toLowerCase().includes(q))
    );
  }, [positions, positionsSearch]);

  const candidatesList = useMemo(() => {
    if (!latestPlan?.candidates) return [];
    return latestPlan.candidates.filter(
      (c) => c.symbol && !['ALL_FO', 'ALL', 'AUTO_DISCOVER'].includes(c.symbol.toUpperCase())
    );
  }, [latestPlan]);

  return (
    <div className="page-container">
      {/* STRICT PERSISTENT BANNER */}
      <div
        className="banner-minimal"
        style={{
          borderColor: 'rgba(56, 189, 248, 0.4)',
          background: 'rgba(56, 189, 248, 0.05)',
          marginBottom: '1.25rem'
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
          <ShieldCheck size={18} color="var(--accent-blue)" />
          <span style={{ fontSize: '0.82rem', fontWeight: 700, letterSpacing: '0.04em', color: '#fff' }}>
            PAPER TRADING — SIMULATED ORDERS ONLY — ZERO BROKER CAPITAL EXPOSURE
          </span>
        </div>
        <span
          className="pill-badge"
          style={{ background: 'rgba(56, 189, 248, 0.15)', color: 'var(--accent-blue)', fontSize: '0.72rem' }}
        >
          Independent Virtual Simulation Ledger
        </span>
      </div>

      {/* Header & Controls */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '1rem',
          marginBottom: '1.25rem'
        }}
      >
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div className="brand-icon-box" style={{ background: 'var(--accent-blue)' }}>
              <Activity size={18} color="#fff" />
            </div>
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span className="pulse-dot" style={{ background: isRunning ? 'var(--accent-blue)' : 'var(--accent-orange)' }} />
                <h2 style={{ fontSize: '1.35rem', fontWeight: 800, color: '#fff', margin: 0 }}>
                  Stock Options Paper Trading
                </h2>
                <span
                  className="brand-badge"
                  style={{
                    background: isRunning ? 'rgba(56, 189, 248, 0.15)' : 'rgba(237, 76, 34, 0.15)',
                    color: isRunning ? 'var(--accent-blue)' : 'var(--accent-orange)'
                  }}
                >
                  {isRunning ? 'Simulation Active' : 'Simulation Paused'}
                </span>
              </div>
              <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                Pure virtual simulation • +0.35% ask/bid slippage & statutory tax modeling • Safe testing environment
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <span
            className="pill-badge"
            style={{
              background: isRunning ? 'rgba(56, 189, 248, 0.15)' : 'rgba(237, 76, 34, 0.15)',
              color: isRunning ? 'var(--accent-blue)' : 'var(--accent-orange)',
              fontSize: '0.75rem',
              border: `1px solid ${isRunning ? 'rgba(56, 189, 248, 0.3)' : 'rgba(237, 76, 34, 0.3)'}`
            }}
          >
            <span className={`status-dot ${isRunning ? 'active' : ''}`} style={{ marginRight: 6 }} />
            {isRunning ? 'PAPER RUNNING' : 'PAPER PAUSED'}
          </span>

          {isRunning ? (
            <button
              className="btn-secondary"
              onClick={handlePausePaper}
              style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', padding: '0.45rem 1rem' }}
            >
              <Pause size={14} />
              <span>Pause Paper</span>
            </button>
          ) : (
            <button
              className="btn-primary"
              onClick={handleStartPaper}
              style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.8rem', padding: '0.45rem 1rem' }}
            >
              <Zap size={14} />
              <span>Start Paper</span>
            </button>
          )}

          <button
            className="btn-secondary"
            onClick={() => setShowConfigModal(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.78rem', padding: '0.45rem 0.85rem' }}
          >
            <Settings size={13} />
            <span>Settings</span>
          </button>

          <button
            className="btn-secondary danger"
            onClick={() => setShowResetModal(true)}
            style={{ display: 'flex', alignItems: 'center', gap: '0.45rem', fontSize: '0.78rem', padding: '0.45rem 0.85rem' }}
          >
            <RotateCcw size={13} />
            <span>Reset Ledger</span>
          </button>
        </div>
      </div>

      {notification && (
        <div
          style={{
            padding: '0.75rem 1rem',
            borderRadius: 8,
            marginBottom: '1rem',
            fontSize: '0.82rem',
            background: notification.isError ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.15)',
            border: `1px solid ${notification.isError ? 'var(--accent-red)' : 'var(--accent-emerald)'}`,
            color: notification.isError ? 'var(--accent-red)' : 'var(--accent-emerald)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between'
          }}
        >
          <span>{notification.text}</span>
          <button
            onClick={() => setNotification(null)}
            style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer', fontSize: '1.1rem' }}
          >
            ×
          </button>
        </div>
      )}

      {/* Metrics HUD: Virtual Capital & Overall Performance */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))',
          gap: '0.75rem',
          marginBottom: '1.25rem'
        }}
      >
        <div className="hud-card" style={{ padding: '0.85rem' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Virtual Capital</div>
          <div className="mono" style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--accent-blue)', marginTop: '0.2rem' }}>
            {formatINR(paperStatus?.virtual_capital ?? 500000)}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
            Available: <span className="mono" style={{ color: '#fff' }}>{formatINR(paperStatus?.available_virtual_balance ?? 500000)}</span>
          </div>
        </div>

        <div className="hud-card" style={{ padding: '0.85rem' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Net Realized P&L</div>
          <div
            className="mono"
            style={{
              fontSize: '1.3rem',
              fontWeight: 800,
              marginTop: '0.2rem',
              color: totalNetRealized >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)'
            }}
          >
            {formatINR(totalNetRealized)}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
            Gross: {formatINR(perf.total_gross_pnl || 0)} (Charges: {formatINR(perf.total_charges || 0)})
          </div>
        </div>

        <div className="hud-card" style={{ padding: '0.85rem' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Win Rate / Profit Factor</div>
          <div className="mono" style={{ fontSize: '1.3rem', fontWeight: 800, color: '#fff', marginTop: '0.2rem' }}>
            {perf.win_rate_pct || 0}% <span style={{ fontSize: '0.85rem', color: 'var(--accent-orange)' }}>({perf.profit_factor || 1.0} PF)</span>
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
            Wins: {perf.wins || 0} / Losses: {perf.losses || 0} ({perf.total_trades || 0} Closed)
          </div>
        </div>

        <div className="hud-card" style={{ padding: '0.85rem' }}>
          <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>Floating Unrealized P&L</div>
          <div
            className="mono"
            style={{
              fontSize: '1.3rem',
              fontWeight: 800,
              marginTop: '0.2rem',
              color: totalUnrealized >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)'
            }}
          >
            {formatINR(totalUnrealized)}
          </div>
          <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)', marginTop: '0.15rem' }}>
            {positions.length} Open Virtual Contract{positions.length === 1 ? '' : 's'}
          </div>
        </div>
      </div>

      {/* Main Tabbed Navigation Bar */}
      <div className="tab-row" style={{ marginBottom: '1.25rem', display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
        <button
          className={`tab-btn ${activeTab === 'active' ? 'active' : ''}`}
          onClick={() => setActiveTab('active')}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
        >
          <Activity size={15} />
          <span>Active Trading</span>
          {positions.length > 0 && (
            <span
              style={{
                fontSize: '0.7rem',
                padding: '0.1rem 0.45rem',
                borderRadius: 12,
                background: 'rgba(56, 189, 248, 0.2)',
                color: 'var(--accent-blue)',
                fontWeight: 700
              }}
            >
              {positions.length} Open
            </span>
          )}
        </button>

        <button
          className={`tab-btn ${activeTab === 'orders' ? 'active' : ''}`}
          onClick={() => setActiveTab('orders')}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
        >
          <FileText size={15} />
          <span>Orders Audit</span>
          <span
            style={{
              fontSize: '0.7rem',
              padding: '0.1rem 0.45rem',
              borderRadius: 12,
              background: 'rgba(255, 255, 255, 0.08)',
              color: 'var(--text-muted)',
              fontWeight: 700
            }}
          >
            {orders.length}
          </span>
        </button>

        <button
          className={`tab-btn ${activeTab === 'trades' ? 'active' : ''}`}
          onClick={() => setActiveTab('trades')}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
        >
          <Layers size={15} />
          <span>Trade Journal</span>
          <span
            style={{
              fontSize: '0.7rem',
              padding: '0.1rem 0.45rem',
              borderRadius: 12,
              background: 'rgba(255, 255, 255, 0.08)',
              color: 'var(--text-muted)',
              fontWeight: 700
            }}
          >
            {trades.length}
          </span>
        </button>

        <button
          className={`tab-btn ${activeTab === 'analytics' ? 'active' : ''}`}
          onClick={() => setActiveTab('analytics')}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.85rem' }}
        >
          <Calendar size={15} />
          <span>P&L Calendar & Analytics</span>
        </button>
      </div>

      {/* =========================================================================
          TAB 1: ACTIVE TRADING (Open Positions + Candidate Dispatches)
      ========================================================================= */}
      {activeTab === 'active' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.25rem' }}>
          
          {/* Column 1: Open Simulated Positions */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="hud-card">
              <div className="card-header-line" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Activity size={15} color="var(--accent-blue)" />
                  <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>
                    Open Simulated Positions ({positions.length})
                  </span>
                </div>
                {positions.length > 2 && (
                  <div style={{ position: 'relative', width: 140 }}>
                    <Search size={12} style={{ position: 'absolute', left: 7, top: 7, color: 'var(--text-dim)' }} />
                    <input
                      type="text"
                      placeholder="Filter..."
                      value={positionsSearch}
                      onChange={(e) => setPositionsSearch(e.target.value)}
                      style={{
                        width: '100%',
                        padding: '0.25rem 0.45rem 0.25rem 1.6rem',
                        fontSize: '0.72rem',
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid var(--border-light)',
                        borderRadius: 4,
                        color: '#fff'
                      }}
                    />
                  </div>
                )}
              </div>

              {filteredPositions.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-dim)' }}>
                  <Activity size={32} style={{ opacity: 0.25, marginBottom: '0.65rem' }} />
                  <div style={{ fontSize: '0.88rem', fontWeight: 600 }}>No open simulated positions</div>
                  <div style={{ fontSize: '0.74rem', marginTop: '0.25rem' }}>
                    Click "Simulate Entry" on any candidate plan on the right to open a virtual position.
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                  {filteredPositions.map((pos) => {
                    const pnl = parseFloat(pos.unrealized_pnl) || 0;
                    const isProfit = pnl >= 0;
                    return (
                      <div
                        key={pos.symbol}
                        style={{
                          padding: '0.85rem',
                          background: 'rgba(0,0,0,0.3)',
                          borderRadius: 8,
                          border: `1px solid ${isProfit ? 'rgba(16, 185, 129, 0.3)' : 'rgba(244, 63, 94, 0.3)'}`
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.5rem' }}>
                          <div>
                            <div className="mono" style={{ fontSize: '1rem', fontWeight: 700, color: '#fff' }}>
                              {pos.symbol}
                            </div>
                            <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>
                              Underlying: <strong style={{ color: '#fff' }}>{pos.underlying}</strong> • Qty: {pos.quantity} ({pos.lots} Lot)
                            </div>
                          </div>

                          <div style={{ textAlign: 'right' }}>
                            <div
                              className="mono"
                              style={{
                                fontSize: '1.15rem',
                                fontWeight: 800,
                                color: isProfit ? 'var(--accent-emerald)' : 'var(--accent-red)'
                              }}
                            >
                              {isProfit ? `+${formatINR(pnl)}` : formatINR(pnl)}
                            </div>
                            <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Floating Unrealized</div>
                          </div>
                        </div>

                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(4, 1fr)',
                            gap: '0.4rem',
                            fontSize: '0.72rem',
                            color: 'var(--text-muted)',
                            background: 'rgba(255,255,255,0.02)',
                            padding: '0.45rem',
                            borderRadius: 6,
                            marginBottom: '0.65rem'
                          }}
                        >
                          <div>Entry: <span className="mono" style={{ color: '#fff' }}>₹{pos.entry_price}</span></div>
                          <div>Current: <span className="mono" style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>₹{pos.current_ltp}</span></div>
                          <div>Stop Loss: <span className="mono" style={{ color: 'var(--accent-red)' }}>₹{pos.stop_loss}</span></div>
                          <div>Target 1: <span className="mono" style={{ color: 'var(--accent-emerald)' }}>₹{pos.target_1}</span></div>
                        </div>

                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-light)', paddingTop: '0.5rem' }}>
                          <span
                            className="badge"
                            style={{
                              background: 'rgba(56, 189, 248, 0.12)',
                              color: 'var(--accent-blue)',
                              fontSize: '0.7rem'
                            }}
                          >
                            Simulated Bracket Active
                          </span>
                          <button
                            className="btn-secondary danger"
                            style={{ padding: '0.35rem 0.75rem', fontSize: '0.74rem' }}
                            onClick={() => handleClosePosition(pos.symbol, pos.current_ltp)}
                          >
                            Simulate Square-off
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Column 2: Candidate Queue for Simulation */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            <div className="hud-card">
              <div className="card-header-line" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <Sparkles size={15} color="var(--accent-orange)" />
                  <span style={{ fontWeight: 700, fontSize: '0.9rem' }}>
                    AI Discovered Setups Ready for Simulation ({candidatesList.length})
                  </span>
                </div>
                {latestPlan?.session_date && (
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                    Session: {latestPlan.session_date}
                  </span>
                )}
              </div>

              {candidatesList.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '3rem 1rem', color: 'var(--text-dim)', fontSize: '0.82rem' }}>
                  <Sparkles size={32} style={{ opacity: 0.25, marginBottom: '0.65rem' }} />
                  <div style={{ fontSize: '0.88rem', fontWeight: 600 }}>No candidates in active plan</div>
                  <div style={{ fontSize: '0.74rem', marginTop: '0.25rem' }}>
                    Run an Intraday Scan or Overnight AI Plan to discover high-probability F&O setups.
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', marginTop: '0.5rem' }}>
                  {candidatesList.map((cand, idx) => {
                    const isBullish = cand.bias === 'BULLISH';
                    const contract = cand.primary_contract || {};
                    const mgmt = cand.trade_management || {};

                    const sym = cand.symbol || '';
                    const lotUnits = getEffectiveLotSize(sym, contract.lot_size);
                    const entryPrice = parseFloat(contract.indicative_premium || cand.entry_price || mgmt.entry_price || 0);
                    const slPrice = parseFloat(mgmt.stop_loss || cand.stop_loss || 0);
                    const target1Price = parseFloat(mgmt.target_1 || cand.target_1 || 0);

                    const isHighBeta = HIGH_BETA_SYMBOLS.has(sym.toUpperCase()) || Number(mgmt.risk_reward_ratio) >= 2.0;

                    // Expected Profit & Loss math
                    const profitPts = target1Price > entryPrice ? (target1Price - entryPrice) : (entryPrice * (isHighBeta ? 0.30 : 0.22));
                    const expectedProfit = Math.round(profitPts * lotUnits);
                    const profitPct = entryPrice > 0 ? ((profitPts / entryPrice) * 100).toFixed(1) : (isHighBeta ? '30.0' : '22.0');

                    const lossPts = (slPrice > 0 && slPrice < entryPrice) ? (entryPrice - slPrice) : (entryPrice * 0.15);
                    const expectedLoss = Math.round(lossPts * lotUnits);
                    const lossPct = entryPrice > 0 ? ((lossPts / entryPrice) * 100).toFixed(1) : '15.0';

                    return (
                      <div
                        key={cand.symbol || idx}
                        style={{
                          padding: '0.85rem',
                          background: 'rgba(18, 17, 16, 0.75)',
                          borderRadius: 10,
                          border: `1px solid ${isBullish ? 'rgba(16, 185, 129, 0.25)' : 'rgba(244, 63, 94, 0.25)'}`,
                          boxShadow: '0 4px 14px rgba(0, 0, 0, 0.35)',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: '0.65rem'
                        }}
                      >
                        {/* Top Header: Symbol + Glowing Badge + High Beta R:R */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
                            <span className="mono" style={{ fontWeight: 800, color: '#fff', fontSize: '1.05rem', letterSpacing: '-0.01em' }}>
                              {cand.symbol}
                            </span>

                            {/* Premium Glowing Pill Badge */}
                            <div
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '0.45rem',
                                padding: '0.24rem 0.65rem',
                                borderRadius: 20,
                                background: isBullish
                                  ? 'linear-gradient(135deg, rgba(16, 185, 129, 0.2) 0%, rgba(5, 150, 105, 0.08) 100%)'
                                  : 'linear-gradient(135deg, rgba(244, 63, 94, 0.2) 0%, rgba(225, 29, 72, 0.08) 100%)',
                                border: `1px solid ${isBullish ? 'rgba(16, 185, 129, 0.45)' : 'rgba(244, 63, 94, 0.45)'}`,
                                boxShadow: isBullish
                                  ? '0 0 10px rgba(16, 185, 129, 0.15)'
                                  : '0 0 10px rgba(244, 63, 94, 0.15)'
                              }}
                            >
                              <span
                                style={{
                                  width: 7,
                                  height: 7,
                                  borderRadius: '50%',
                                  background: isBullish ? '#10b981' : '#f43f5e',
                                  boxShadow: `0 0 6px ${isBullish ? '#10b981' : '#f43f5e'}`
                                }}
                              />
                              <span
                                style={{
                                  fontSize: '0.72rem',
                                  fontWeight: 800,
                                  letterSpacing: '0.04em',
                                  color: isBullish ? '#34d399' : '#fb7185'
                                }}
                              >
                                {isBullish ? 'BULLISH' : 'BEARISH'}
                              </span>
                              <span style={{ fontSize: '0.65rem', color: 'rgba(255,255,255,0.3)' }}>•</span>
                              <span
                                style={{
                                  fontSize: '0.72rem',
                                  fontWeight: 800,
                                  color: '#fff',
                                  background: 'rgba(255,255,255,0.12)',
                                  padding: '0.05rem 0.35rem',
                                  borderRadius: 4
                                }}
                              >
                                {contract.option_type || (isBullish ? 'CE' : 'PE')}
                              </span>
                            </div>
                          </div>

                          {/* Adaptive Risk-Reward Badge */}
                          <div style={{ display: 'flex', gap: '0.35rem', alignItems: 'center' }}>
                            {isHighBeta && (
                              <span
                                style={{
                                  fontSize: '0.64rem',
                                  fontWeight: 800,
                                  color: '#c084fc',
                                  background: 'rgba(192, 132, 252, 0.16)',
                                  border: '1px solid rgba(192, 132, 252, 0.4)',
                                  padding: '0.15rem 0.45rem',
                                  borderRadius: 4,
                                  letterSpacing: '0.04em'
                                }}
                              >
                                HIGH BETA
                              </span>
                            )}
                            <span
                              className="mono"
                              style={{
                                fontSize: '0.75rem',
                                fontWeight: 700,
                                color: isHighBeta ? '#c084fc' : 'var(--accent-orange)',
                                background: isHighBeta ? 'rgba(192, 132, 252, 0.12)' : 'rgba(237, 76, 34, 0.12)',
                                border: `1px solid ${isHighBeta ? 'rgba(192, 132, 252, 0.3)' : 'rgba(237, 76, 34, 0.25)'}`,
                                padding: '0.2rem 0.55rem',
                                borderRadius: 4
                              }}
                            >
                              1 : {mgmt.risk_reward_ratio ? Number(mgmt.risk_reward_ratio).toFixed(1) : (isHighBeta ? '2.0' : '1.5')} R:R
                            </span>
                          </div>
                        </div>

                        {/* 4-Tile Pricing & Contract Grid */}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: 'repeat(4, 1fr)',
                            gap: '0.45rem',
                            background: 'rgba(0,0,0,0.35)',
                            padding: '0.55rem',
                            borderRadius: 8,
                            border: '1px solid var(--border-light)'
                          }}
                        >
                          <div>
                            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Contract</div>
                            <div className="mono" style={{ fontSize: '0.82rem', fontWeight: 700, color: '#fff', marginTop: '0.1rem' }}>
                              {contract.strike_price} {contract.option_type || (isBullish ? 'CE' : 'PE')}
                            </div>
                            <div style={{ fontSize: '0.64rem', color: 'var(--text-dim)' }}>{lotUnits} / lot</div>
                          </div>

                          <div>
                            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Entry Price</div>
                            <div className="mono" style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--accent-blue)', marginTop: '0.1rem' }}>
                              ₹{entryPrice.toFixed(2)}
                            </div>
                            <div style={{ fontSize: '0.64rem', color: 'var(--text-dim)' }}>Est. Premium</div>
                          </div>

                          <div>
                            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Stop Loss</div>
                            <div className="mono" style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--accent-red)', marginTop: '0.1rem' }}>
                              ₹{slPrice.toFixed(2)}
                            </div>
                            <div style={{ fontSize: '0.64rem', color: 'var(--accent-red)' }}>-{lossPts.toFixed(2)} pts</div>
                          </div>

                          <div>
                            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>Target 1</div>
                            <div className="mono" style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--accent-emerald)', marginTop: '0.1rem' }}>
                              ₹{target1Price.toFixed(2)}
                            </div>
                            <div style={{ fontSize: '0.64rem', color: 'var(--accent-emerald)' }}>+{profitPts.toFixed(2)} pts</div>
                          </div>
                        </div>

                        {/* Expected Profit vs Expected Loss Box */}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 1fr',
                            gap: '0.5rem',
                            background: 'rgba(255, 255, 255, 0.02)',
                            borderRadius: 8,
                            padding: '0.5rem 0.65rem',
                            border: '1px solid rgba(255, 255, 255, 0.05)'
                          }}
                        >
                          {/* Expected Profit */}
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                              <span style={{ fontSize: '0.66rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                                Expected Profit (1 Lot)
                              </span>
                              <span
                                className="badge"
                                style={{
                                  background: 'rgba(16, 185, 129, 0.15)',
                                  color: 'var(--accent-emerald)',
                                  fontSize: '0.64rem',
                                  padding: '0.05rem 0.35rem'
                                }}
                              >
                                +{profitPct}%
                              </span>
                            </div>
                            <div className="mono" style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--accent-emerald)' }}>
                              +{formatINR(expectedProfit)}
                            </div>
                          </div>

                          {/* Expected Loss */}
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem', borderLeft: '1px solid var(--border-light)', paddingLeft: '0.65rem' }}>
                            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                              <span style={{ fontSize: '0.66rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                                Max Risk / Loss (1 Lot)
                              </span>
                              <span
                                className="badge"
                                style={{
                                  background: 'rgba(244, 63, 94, 0.15)',
                                  color: 'var(--accent-red)',
                                  fontSize: '0.64rem',
                                  padding: '0.05rem 0.35rem'
                                }}
                              >
                                -{lossPct}%
                              </span>
                            </div>
                            <div className="mono" style={{ fontSize: '1rem', fontWeight: 800, color: 'var(--accent-red)' }}>
                              -{formatINR(expectedLoss)}
                            </div>
                          </div>
                        </div>

                        {/* Daily News Catalyst & Sentiment Confluence Box */}
                        {(cand.catalyst_summary || cand.technical?.technical_rationale) && (
                          <div
                            style={{
                              fontSize: '0.71rem',
                              color: 'var(--text-muted)',
                              background: 'rgba(255, 255, 255, 0.025)',
                              padding: '0.45rem 0.65rem',
                              borderRadius: 6,
                              border: '1px solid rgba(255, 255, 255, 0.07)',
                              display: 'flex',
                              alignItems: 'flex-start',
                              gap: '0.45rem'
                            }}
                          >
                            <Zap size={13} style={{ color: '#fbbf24', flexShrink: 0, marginTop: 1 }} />
                            <div>
                              <strong style={{ color: '#fff', marginRight: 4 }}>Catalyst & Sentiment:</strong>
                              <span>{cand.catalyst_summary || cand.technical?.technical_rationale}</span>
                            </div>
                          </div>
                        )}

                        {/* Card Footer: Slippage Notice & Simulate Entry Button */}
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderTop: '1px solid var(--border-light)', paddingTop: '0.5rem' }}>
                          <div style={{ fontSize: '0.7rem', color: 'var(--text-dim)' }}>
                            Virtual Fill: +0.35% Slippage Model
                          </div>
                          <button
                            className="btn-primary"
                            style={{ padding: '0.4rem 0.95rem', fontSize: '0.78rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}
                            onClick={() => handleExecutePaperCandidate(cand)}
                            disabled={!isRunning}
                          >
                            <Play size={12} />
                            <span>Simulate Entry</span>
                          </button>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

        </div>
      )}

      {/* =========================================================================
          TAB 2: ORDERS AUDIT LOG (Paginated, Searchable, Filterable)
      ========================================================================= */}
      {activeTab === 'orders' && (
        <div className="hud-card">
          <div className="card-header-line" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <FileText size={16} color="var(--accent-blue)" />
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>
                Simulated Orders Audit ({filteredOrders.length} matching / {orders.length} total)
              </span>
            </div>

            {/* Controls: Search, Status Filter, Page Size */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
              {/* Search */}
              <div style={{ position: 'relative', width: 180 }}>
                <Search size={13} style={{ position: 'absolute', left: 8, top: 8, color: 'var(--text-dim)' }} />
                <input
                  type="text"
                  placeholder="Search contract / ID..."
                  value={ordersSearch}
                  onChange={(e) => {
                    setOrdersSearch(e.target.value);
                    setOrdersPage(1);
                  }}
                  style={{
                    width: '100%',
                    padding: '0.3rem 0.5rem 0.3rem 1.8rem',
                    fontSize: '0.76rem',
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid var(--border-light)',
                    borderRadius: 6,
                    color: '#fff'
                  }}
                />
              </div>

              {/* Status Filter */}
              <div style={{ display: 'flex', gap: '0.25rem', background: 'rgba(0,0,0,0.25)', padding: '0.2rem', borderRadius: 6 }}>
                {['ALL', 'FILLED', 'REJECTED', 'PENDING'].map((st) => (
                  <button
                    key={st}
                    onClick={() => {
                      setOrdersStatusFilter(st);
                      setOrdersPage(1);
                    }}
                    style={{
                      background: ordersStatusFilter === st ? 'rgba(56, 189, 248, 0.2)' : 'transparent',
                      color: ordersStatusFilter === st ? 'var(--accent-blue)' : 'var(--text-muted)',
                      border: 'none',
                      borderRadius: 4,
                      padding: '0.25rem 0.55rem',
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    {st}
                  </button>
                ))}
              </div>

              {/* Page Size Selector */}
              <select
                value={ordersPageSize}
                onChange={(e) => {
                  setOrdersPageSize(Number(e.target.value));
                  setOrdersPage(1);
                }}
                style={{
                  background: 'rgba(0,0,0,0.3)',
                  border: '1px solid var(--border-light)',
                  color: 'var(--text-muted)',
                  fontSize: '0.74rem',
                  padding: '0.25rem 0.45rem',
                  borderRadius: 6
                }}
              >
                <option value={10}>10 / page</option>
                <option value={25}>25 / page</option>
                <option value={50}>50 / page</option>
              </select>
            </div>
          </div>

          {/* Full Width Table */}
          <div className="table-container" style={{ marginTop: '0.75rem' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Timestamp</th>
                  <th>Order ID</th>
                  <th>Contract</th>
                  <th>Action</th>
                  <th>Quantity</th>
                  <th>Nominal</th>
                  <th>Fill Price</th>
                  <th>Slippage</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {paginatedOrders.length === 0 ? (
                  <tr>
                    <td colSpan="9" style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '2rem' }}>
                      No orders found matching the filter criteria.
                    </td>
                  </tr>
                ) : (
                  paginatedOrders.map((o) => {
                    const slipDiff = o.average_price && o.price ? (o.average_price - o.price).toFixed(2) : '0.00';
                    return (
                      <tr key={o.order_id}>
                        <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {formatTimestamp(o.created_at)}
                        </td>
                        <td className="mono" style={{ fontSize: '0.72rem', color: 'var(--text-dim)' }}>
                          {o.order_id}
                        </td>
                        <td className="mono" style={{ fontWeight: 700, color: '#fff' }}>
                          {o.symbol}
                        </td>
                        <td>
                          <span
                            className="badge"
                            style={{
                              background: o.transaction_type === 'BUY' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                              color: o.transaction_type === 'BUY' ? 'var(--accent-emerald)' : 'var(--accent-red)',
                              fontSize: '0.7rem'
                            }}
                          >
                            {o.transaction_type}
                          </span>
                        </td>
                        <td className="mono">{o.quantity}</td>
                        <td className="mono" style={{ color: 'var(--text-muted)' }}>₹{o.price}</td>
                        <td className="mono" style={{ fontWeight: 700, color: '#fff' }}>
                          ₹{o.average_price || o.price}
                        </td>
                        <td className="mono" style={{ fontSize: '0.72rem', color: 'var(--accent-orange)' }}>
                          +{slipDiff} pts
                        </td>
                        <td>
                          <span
                            className="badge"
                            style={{
                              background: o.status === 'FILLED' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(237, 76, 34, 0.15)',
                              color: o.status === 'FILLED' ? 'var(--accent-blue)' : 'var(--accent-orange)'
                            }}
                          >
                            {o.status}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          {filteredOrders.length > 0 && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginTop: '1rem',
                paddingTop: '0.75rem',
                borderTop: '1px solid var(--border-light)',
                fontSize: '0.76rem',
                color: 'var(--text-muted)'
              }}
            >
              <div>
                Showing {(ordersPage - 1) * ordersPageSize + 1} to{' '}
                {Math.min(ordersPage * ordersPageSize, filteredOrders.length)} of {filteredOrders.length} orders
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <button
                  className="btn-secondary"
                  disabled={ordersPage <= 1}
                  onClick={() => setOrdersPage((p) => Math.max(1, p - 1))}
                  style={{ padding: '0.25rem 0.55rem', fontSize: '0.74rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                >
                  <ChevronLeft size={14} />
                  <span>Prev</span>
                </button>
                <span className="mono" style={{ padding: '0 0.4rem', color: '#fff' }}>
                  {ordersPage} / {totalOrderPages}
                </span>
                <button
                  className="btn-secondary"
                  disabled={ordersPage >= totalOrderPages}
                  onClick={() => setOrdersPage((p) => Math.min(totalOrderPages, p + 1))}
                  style={{ padding: '0.25rem 0.55rem', fontSize: '0.74rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                >
                  <span>Next</span>
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 3: TRADE JOURNAL (Closed Trades History, Paginated & Searchable)
      ========================================================================= */}
      {activeTab === 'trades' && (
        <div className="hud-card">
          <div className="card-header-line" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Layers size={16} color="var(--accent-emerald)" />
              <span style={{ fontWeight: 700, fontSize: '0.95rem' }}>
                Simulated Trade Journal ({filteredTrades.length} trades recorded)
              </span>
            </div>

            {/* Controls: Search, Outcome Filter, Page Size */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', flexWrap: 'wrap' }}>
              {/* Search */}
              <div style={{ position: 'relative', width: 180 }}>
                <Search size={13} style={{ position: 'absolute', left: 8, top: 8, color: 'var(--text-dim)' }} />
                <input
                  type="text"
                  placeholder="Search symbol / reason..."
                  value={tradesSearch}
                  onChange={(e) => {
                    setTradesSearch(e.target.value);
                    setTradesPage(1);
                  }}
                  style={{
                    width: '100%',
                    padding: '0.3rem 0.5rem 0.3rem 1.8rem',
                    fontSize: '0.76rem',
                    background: 'rgba(0,0,0,0.3)',
                    border: '1px solid var(--border-light)',
                    borderRadius: 6,
                    color: '#fff'
                  }}
                />
              </div>

              {/* Outcome Filter */}
              <div style={{ display: 'flex', gap: '0.25rem', background: 'rgba(0,0,0,0.25)', padding: '0.2rem', borderRadius: 6 }}>
                {[
                  { id: 'ALL', label: 'All' },
                  { id: 'WIN', label: 'Winners 🟢' },
                  { id: 'LOSS', label: 'Losses 🔴' }
                ].map((item) => (
                  <button
                    key={item.id}
                    onClick={() => {
                      setTradesOutcomeFilter(item.id);
                      setTradesPage(1);
                    }}
                    style={{
                      background: tradesOutcomeFilter === item.id ? 'rgba(16, 185, 129, 0.2)' : 'transparent',
                      color: tradesOutcomeFilter === item.id ? 'var(--accent-emerald)' : 'var(--text-muted)',
                      border: 'none',
                      borderRadius: 4,
                      padding: '0.25rem 0.55rem',
                      fontSize: '0.7rem',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>

              {/* Page Size Selector */}
              <select
                value={tradesPageSize}
                onChange={(e) => {
                  setTradesPageSize(Number(e.target.value));
                  setTradesPage(1);
                }}
                style={{
                  background: 'rgba(0,0,0,0.3)',
                  border: '1px solid var(--border-light)',
                  color: 'var(--text-muted)',
                  fontSize: '0.74rem',
                  padding: '0.25rem 0.45rem',
                  borderRadius: 6
                }}
              >
                <option value={10}>10 / page</option>
                <option value={25}>25 / page</option>
                <option value={50}>50 / page</option>
              </select>
            </div>
          </div>

          {/* Full Width Table */}
          <div className="table-container" style={{ marginTop: '0.75rem' }}>
            <table className="data-table">
              <thead>
                <tr>
                  <th>Closed Time</th>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Entry Price</th>
                  <th>Exit Price</th>
                  <th>Gross P&L</th>
                  <th>Charges & Taxes</th>
                  <th>Net P&L</th>
                  <th>Exit Rationale</th>
                </tr>
              </thead>
              <tbody>
                {paginatedTrades.length === 0 ? (
                  <tr>
                    <td colSpan="9" style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '2rem' }}>
                      No completed trades found matching the criteria.
                    </td>
                  </tr>
                ) : (
                  paginatedTrades.map((t) => {
                    const net = parseFloat(t.net_pnl) || 0;
                    const gross = parseFloat(t.gross_pnl) || 0;
                    const charges = parseFloat(t.charges) || 0;
                    const isProfit = net >= 0;

                    return (
                      <tr key={t.trade_id}>
                        <td style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {formatTimestamp(t.exit_time || t.created_at)}
                        </td>
                        <td className="mono" style={{ fontWeight: 700, color: '#fff' }}>
                          {t.symbol}
                        </td>
                        <td className="mono">{t.quantity}</td>
                        <td className="mono">₹{t.entry_price}</td>
                        <td className="mono">₹{t.exit_price}</td>
                        <td className="mono" style={{ color: gross >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)' }}>
                          {formatINR(gross)}
                        </td>
                        <td className="mono" style={{ color: 'var(--text-dim)', fontSize: '0.74rem' }}>
                          ₹{charges.toFixed(2)}
                        </td>
                        <td
                          className="mono"
                          style={{
                            fontWeight: 800,
                            color: isProfit ? 'var(--accent-emerald)' : 'var(--accent-red)'
                          }}
                        >
                          {isProfit ? `+${formatINR(net)}` : formatINR(net)}
                        </td>
                        <td style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
                          {t.exit_reason || 'Manual Square-off'}
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* Pagination Footer */}
          {filteredTrades.length > 0 && (
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginTop: '1rem',
                paddingTop: '0.75rem',
                borderTop: '1px solid var(--border-light)',
                fontSize: '0.76rem',
                color: 'var(--text-muted)'
              }}
            >
              <div>
                Showing {(tradesPage - 1) * tradesPageSize + 1} to{' '}
                {Math.min(tradesPage * tradesPageSize, filteredTrades.length)} of {filteredTrades.length} trades
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <button
                  className="btn-secondary"
                  disabled={tradesPage <= 1}
                  onClick={() => setTradesPage((p) => Math.max(1, p - 1))}
                  style={{ padding: '0.25rem 0.55rem', fontSize: '0.74rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                >
                  <ChevronLeft size={14} />
                  <span>Prev</span>
                </button>
                <span className="mono" style={{ padding: '0 0.4rem', color: '#fff' }}>
                  {tradesPage} / {totalTradePages}
                </span>
                <button
                  className="btn-secondary"
                  disabled={tradesPage >= totalTradePages}
                  onClick={() => setTradesPage((p) => Math.min(totalTradePages, p + 1))}
                  style={{ padding: '0.25rem 0.55rem', fontSize: '0.74rem', display: 'flex', alignItems: 'center', gap: '0.2rem' }}
                >
                  <span>Next</span>
                  <ChevronRight size={14} />
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* =========================================================================
          TAB 4: CALENDAR & PERFORMANCE ANALYTICS
      ========================================================================= */}
      {activeTab === 'analytics' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          <PnLCalendar
            liveTrades={trades || []}
            apiEndpoint="/api/stock-options/paper/calendar"
            title="Stock Options Paper Trading P&L Calendar"
            subtitle="Actual simulated stock options trades executed, daily net profit/loss, slippage & simulated fees"
          />
        </div>
      )}

      {/* Simulation Configuration Modal */}
      {showConfigModal && (
        <div className="modal-backdrop">
          <div className="modal-box" style={{ maxWidth: 440 }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#fff', marginBottom: '0.5rem' }}>
              Independent Paper Simulation Settings
            </h3>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Changing paper settings will never modify live account limits or broker risk configurations.
            </p>

            <div className="form-group" style={{ marginBottom: '0.75rem' }}>
              <label className="form-label">Virtual Capital (₹)</label>
              <input
                type="number"
                className="form-input mono"
                value={virtualCapitalInput}
                onChange={(e) => setVirtualCapitalInput(e.target.value)}
              />
            </div>

            <div className="form-group" style={{ marginBottom: '0.75rem' }}>
              <label className="form-label">Simulated Slippage (%)</label>
              <input
                type="number"
                step="0.05"
                className="form-input mono"
                value={slippageInput}
                onChange={(e) => setSlippageInput(e.target.value)}
              />
              <span style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>Default: 0.35% ask/bid slippage penalty</span>
            </div>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">Risk Per Trade (%)</label>
              <input
                type="number"
                step="0.1"
                className="form-input mono"
                value={riskPctInput}
                onChange={(e) => setRiskPctInput(e.target.value)}
              />
            </div>

            <div className="modal-btn-row" style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.25rem' }}>
              <button className="btn-secondary" onClick={() => setShowConfigModal(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleSavePaperConfig}>
                Save Paper Settings
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Reset Confirmation Modal */}
      {showResetModal && (
        <div className="modal-backdrop">
          <div className="modal-box" style={{ maxWidth: 440, border: '1px solid var(--accent-orange)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--accent-orange)', marginBottom: '0.5rem' }}>
              <AlertTriangle size={20} />
              <h3 style={{ fontSize: '1.05rem', fontWeight: 700, margin: 0 }}>
                Reset Paper Trading Ledger?
              </h3>
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1rem', lineHeight: 1.45 }}>
              This will clear all simulated positions, orders, and trade journal history. Live trading data is completely unaffected.
            </p>

            <div className="modal-btn-row" style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem', marginTop: '1.25rem' }}>
              <button className="btn-secondary" onClick={() => setShowResetModal(false)}>
                Cancel
              </button>
              <button
                className="btn-primary danger"
                style={{ background: 'var(--accent-orange)', color: '#fff' }}
                onClick={handleResetPaper}
              >
                Confirm Reset
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
