import React, { useState, useEffect } from 'react';
import { formatINR } from '../components/MetricsHud';
import { FileText, RefreshCw, Briefcase, Clock, CheckCircle2, AlertCircle } from 'lucide-react';

export default function Orders({ state, onExitPosition, onRefresh }) {
  const [activeTab, setActiveTab] = useState('positions');
  const [ordersData, setOrdersData] = useState({
    positions: state.positions || [],
    orders: state.orders || [],
    trade_history: state.trade_history || [],
  });
  const [isRefreshing, setIsRefreshing] = useState(false);

  useEffect(() => {
    loadOrders();
  }, [state]);

  const loadOrders = async () => {
    setIsRefreshing(true);
    try {
      const res = await fetch('/api/orders');
      if (res.ok) {
        const data = await res.json();
        setOrdersData(data);
      }
    } catch (e) {
      console.error('Failed to load orders:', e);
    } finally {
      setIsRefreshing(false);
    }
  };

  const isPaperOrder = (ord) => {
    if (ord.is_paper) return true;
    const id = ord.order_id || '';
    return id.startsWith('ORD_NIFTY_') || id.startsWith('ORD_BANKNIFTY_') || id.startsWith('ORD_SENSEX_') || id.startsWith('ORD_EXIT_PARTIAL_') || id.startsWith('ORD_SL_') || id.startsWith('MANUAL_EXIT_');
  };

  const positions = (ordersData.positions || []).filter(p => !p.is_paper && p.execution_mode === 'LIVE' && p.quantity > 0);
  const orders = (ordersData.orders || []).filter(o => !isPaperOrder(o));
  const history = (ordersData.trade_history || []).filter(h => !h.is_paper);

  return (
    <div className="page-container">
      {/* Top Controls & Metrics */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>Orders & Derivatives Book</h2>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Live exposure, working orders, and completed execution audit log
          </div>
        </div>

        <button
          className="btn-secondary"
          onClick={loadOrders}
          style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}
        >
          <RefreshCw size={14} style={{ animation: isRefreshing ? 'spin 1s linear infinite' : 'none' }} />
          <span>Refresh Book</span>
        </button>
      </div>

      {/* Summary Stat Cards */}
      <div className="grid-metrics">
        <div className="hud-card">
          <div className="card-header-line">
            <span>Open Positions</span>
            <Briefcase size={14} color="var(--accent-orange)" />
          </div>
          <div className="metric-big mono">{positions.length}</div>
          <div className="metric-sub">Active index contracts</div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Total Orders Placed</span>
            <FileText size={14} color="var(--accent-blue)" />
          </div>
          <div className="metric-big mono">{orders.length}</div>
          <div className="metric-sub">Today's audit entries</div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Unrealized P&L</span>
            <span className="mono">M2M</span>
          </div>
          <div className={`metric-big mono ${state.unrealized_pnl >= 0 ? 'profit-text' : 'loss-text'}`}>
            {state.unrealized_pnl >= 0 ? `+${formatINR(state.unrealized_pnl)}` : formatINR(state.unrealized_pnl)}
          </div>
          <div className="metric-sub">Active options floating gain</div>
        </div>

        <div className="hud-card">
          <div className="card-header-line">
            <span>Realized P&L</span>
            <CheckCircle2 size={14} color="var(--accent-emerald)" />
          </div>
          <div className={`metric-big mono ${state.realized_pnl >= 0 ? 'profit-text' : 'loss-text'}`}>
            {state.realized_pnl >= 0 ? `+${formatINR(state.realized_pnl)}` : formatINR(state.realized_pnl)}
          </div>
          <div className="metric-sub">Locked daily return</div>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="hud-card">
        <div className="tab-row">
          <button
            className={`tab-btn ${activeTab === 'positions' ? 'active' : ''}`}
            onClick={() => setActiveTab('positions')}
          >
            Active Positions ({positions.length})
          </button>
          <button
            className={`tab-btn ${activeTab === 'orders' ? 'active' : ''}`}
            onClick={() => setActiveTab('orders')}
          >
            Order Book ({orders.length})
          </button>
          <button
            className={`tab-btn ${activeTab === 'history' ? 'active' : ''}`}
            onClick={() => setActiveTab('history')}
          >
            Trade History ({history.length})
          </button>
        </div>

        {/* Tab 1: Positions */}
        {activeTab === 'positions' && (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Option Type</th>
                  <th>Lots / Units</th>
                  <th>Entry Price</th>
                  <th>Live LTP</th>
                  <th>Floating P&L</th>
                  <th>Hard SL</th>
                  <th>Target 1 (+2.0R)</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {positions.length === 0 ? (
                  <tr>
                    <td colSpan={9} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)' }}>
                      No active derivatives positions open.
                    </td>
                  </tr>
                ) : (
                  positions.map((pos) => {
                    const pnl = pos.unrealized_pnl || 0;
                    const pnlPct = pos.unrealized_pnl_pct || 0;
                    const isProfit = pnl >= 0;

                    return (
                      <tr key={pos.symbol}>
                        <td className="mono font-bold" style={{ color: '#fff' }}>{pos.symbol}</td>
                        <td>
                          <span
                            className="pill-badge"
                            style={{
                              background: pos.option_type === 'CE' ? '#0284c7' : '#e11d48',
                              color: '#fff',
                            }}
                          >
                            {pos.option_type}
                          </span>
                        </td>
                        <td>{pos.lots} lots ({pos.quantity} units)</td>
                        <td className="mono">₹{(pos.entry_price || 0).toFixed(2)}</td>
                        <td className="mono">₹{(pos.current_ltp || 0).toFixed(2)}</td>
                        <td className={`mono font-bold ${isProfit ? 'profit-text' : 'loss-text'}`}>
                          {isProfit ? `+${formatINR(pnl)}` : formatINR(pnl)} ({pnlPct.toFixed(2)}%)
                        </td>
                        <td className="mono loss-text">
                          {pos.stop_loss ? `₹${pos.stop_loss.toFixed(2)}` : '--'}
                        </td>
                        <td className="mono profit-text">
                          {pos.target_1 ? `₹${pos.target_1.toFixed(2)}` : '--'}
                        </td>
                        <td>
                          <button
                            className="btn-liquidate"
                            onClick={() => onExitPosition(pos.symbol)}
                          >
                            Liquidate
                          </button>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab 2: Orders */}
        {activeTab === 'orders' && (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Order ID</th>
                  <th>Symbol</th>
                  <th>Side</th>
                  <th>Order Type</th>
                  <th>Quantity @ Limit</th>
                  <th>Avg Price</th>
                  <th>Status</th>
                  <th>Timestamp</th>
                </tr>
              </thead>
              <tbody>
                {orders.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)' }}>
                      No live broker orders have been dispatched today. (Paper simulation orders are logged in Paper Agent).
                    </td>
                  </tr>
                ) : (
                  [...orders].reverse().map((ord) => {
                    const isBuy = ord.transaction_type === 'BUY';
                    const timeStr = ord.timestamp ? ord.timestamp.slice(11, 19) : '--';
                    const isFilled = ord.status === 'FILLED';

                    return (
                      <tr key={ord.order_id}>
                        <td className="mono text-muted" style={{ fontSize: '0.75rem' }}>{ord.order_id}</td>
                        <td className="mono font-bold" style={{ color: '#fff' }}>{ord.symbol}</td>
                        <td>
                          <span className={`mono font-bold ${isBuy ? 'profit-text' : 'loss-text'}`}>
                            {ord.transaction_type}
                          </span>
                        </td>
                        <td className="mono text-muted">{ord.order_type}</td>
                        <td className="mono">{ord.quantity} @ ₹{(ord.price || 0).toFixed(2)}</td>
                        <td className="mono">{ord.average_price ? `₹${ord.average_price.toFixed(2)}` : '--'}</td>
                        <td>
                          <span
                            className="pill-badge"
                            style={{
                              background: isFilled ? '#10b981' : (ord.status === 'REJECTED' ? '#f43f5e' : '#38bdf8'),
                              color: '#fff',
                            }}
                          >
                            {ord.status}
                          </span>
                        </td>
                        <td className="mono text-muted">{timeStr}</td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}

        {/* Tab 3: History */}
        {activeTab === 'history' && (
          <div className="table-container">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Trade #</th>
                  <th>Contract</th>
                  <th>Strike Price</th>
                  <th>Entry</th>
                  <th>Exit</th>
                  <th>Lots</th>
                  <th>Realized P&L</th>
                  <th>Result</th>
                </tr>
              </thead>
              <tbody>
                {history.length === 0 ? (
                  <tr>
                    <td colSpan={8} style={{ textAlign: 'center', padding: '2.5rem', color: 'var(--text-muted)' }}>
                      No completed live broker trades today. (Paper trading performance is tracked in Paper Agent).
                    </td>
                  </tr>
                ) : (
                  history.map((h, i) => {
                    const strike = h.strike_price || (() => {
                      const m = h.symbol?.match(/(\d{4,6})\s*(CE|PE)/i);
                      return m ? `${m[1]} ${m[2].toUpperCase()}` : '--';
                    })();
                    const pnl = h.net_pnl !== undefined ? h.net_pnl : (h.pnl !== undefined ? h.pnl : (h.gross_pnl || 0));
                    return (
                      <tr key={h.id || i}>
                        <td className="mono">#{i + 1}</td>
                        <td className="mono font-bold">{h.symbol}</td>
                        <td className="mono font-bold" style={{ color: 'var(--accent-blue)' }}>
                          {typeof strike === 'number' ? `₹${strike.toLocaleString('en-IN')}` : strike}
                        </td>
                        <td className="mono">₹{Number(h.entry_price || 0).toFixed(2)}</td>
                        <td className="mono">₹{Number(h.exit_price || 0).toFixed(2)}</td>
                        <td className="mono">{h.lots || Math.ceil((h.quantity || 0) / (h.lot_size || 20))}</td>
                        <td className={`mono font-bold ${pnl >= 0 ? 'profit-text' : 'loss-text'}`}>
                          {pnl >= 0 ? `+${formatINR(pnl)}` : formatINR(pnl)}
                        </td>
                        <td>
                          <span
                            className="pill-badge"
                            style={{
                              background: pnl >= 0 ? '#10b981' : '#f43f5e',
                              color: '#fff',
                            }}
                          >
                            {pnl >= 0 ? 'WIN' : 'LOSS'}
                          </span>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
