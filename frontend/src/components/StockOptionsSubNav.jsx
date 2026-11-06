import React from 'react';
import { Link } from 'react-router-dom';
import { ShieldCheck, Zap, Search, RefreshCw, Sparkles } from 'lucide-react';

export default function StockOptionsSubNav({ activeTab, isScanning, onScanNow }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '0.75rem',
        background: 'rgba(255, 255, 255, 0.02)',
        border: '1px solid var(--border-color)',
        borderRadius: 12,
        padding: '0.5rem 0.75rem',
        marginBottom: '1.25rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
        {/* Tab 1: Paper Trading */}
        <Link
          to="/stock-options-paper-trading"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.45rem 0.9rem',
            borderRadius: 8,
            fontSize: '0.82rem',
            fontWeight: 600,
            textDecoration: 'none',
            background: activeTab === 'paper' ? 'rgba(59, 130, 246, 0.2)' : 'transparent',
            color: activeTab === 'paper' ? '#60a5fa' : 'var(--text-muted)',
            border: `1px solid ${activeTab === 'paper' ? 'rgba(59, 130, 246, 0.4)' : 'transparent'}`,
            transition: 'all 0.15s ease',
          }}
        >
          <ShieldCheck size={15} />
          <span>Stock Options Paper</span>
          <span
            style={{
              fontSize: '0.68rem',
              padding: '0.1rem 0.45rem',
              borderRadius: 4,
              background: 'rgba(59, 130, 246, 0.25)',
              color: '#93c5fd',
              fontWeight: 700,
            }}
          >
            Autonomous
          </span>
        </Link>

        {/* Tab 2: Live Trading */}
        <Link
          to="/stock-options-trading"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.45rem 0.9rem',
            borderRadius: 8,
            fontSize: '0.82rem',
            fontWeight: 600,
            textDecoration: 'none',
            background: activeTab === 'live' ? 'rgba(237, 76, 34, 0.2)' : 'transparent',
            color: activeTab === 'live' ? 'var(--accent-orange)' : 'var(--text-muted)',
            border: `1px solid ${activeTab === 'live' ? 'rgba(237, 76, 34, 0.4)' : 'transparent'}`,
            transition: 'all 0.15s ease',
          }}
        >
          <Zap size={15} />
          <span>Stock Options Live</span>
          <span
            style={{
              fontSize: '0.68rem',
              padding: '0.1rem 0.45rem',
              borderRadius: 4,
              background: 'rgba(237, 76, 34, 0.25)',
              color: '#fb923c',
              fontWeight: 700,
            }}
          >
            Angel One RMS
          </span>
        </Link>

        {/* Tab 3: Intraday AI Scanner & Planner */}
        <Link
          to="/overnight-ai-planner"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.45rem',
            padding: '0.45rem 0.9rem',
            borderRadius: 8,
            fontSize: '0.82rem',
            fontWeight: 600,
            textDecoration: 'none',
            background: activeTab === 'scanner' ? 'rgba(168, 85, 247, 0.2)' : 'transparent',
            color: activeTab === 'scanner' ? '#c084fc' : 'var(--text-muted)',
            border: `1px solid ${activeTab === 'scanner' ? 'rgba(168, 85, 247, 0.4)' : 'transparent'}`,
            transition: 'all 0.15s ease',
          }}
        >
          <Search size={15} />
          <span>AI Scanner & Planner</span>
          <span
            style={{
              fontSize: '0.68rem',
              padding: '0.1rem 0.45rem',
              borderRadius: 4,
              background: 'rgba(168, 85, 247, 0.25)',
              color: '#e9d5ff',
              fontWeight: 700,
            }}
          >
            Gemini Flash
          </span>
        </Link>
      </div>

      {/* Quick Action: Instant Scan Trigger */}
      {onScanNow && (
        <button
          className="btn-primary"
          disabled={isScanning}
          onClick={onScanNow}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '0.45rem',
            fontSize: '0.78rem',
            padding: '0.4rem 0.85rem',
            background: 'linear-gradient(135deg, #f97316 0%, #ea580c 100%)',
            border: 'none',
            color: '#fff',
            cursor: isScanning ? 'not-allowed' : 'pointer',
            boxShadow: '0 2px 8px rgba(249, 115, 22, 0.3)',
          }}
        >
          <RefreshCw size={13} className={isScanning ? 'spin' : ''} />
          <span>{isScanning ? 'Scanning...' : '⚡ Scan Markets Now'}</span>
        </button>
      )}
    </div>
  );
}
