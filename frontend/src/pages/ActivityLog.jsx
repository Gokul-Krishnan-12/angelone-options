import React, { useState, useRef, useEffect } from 'react';
import { Terminal, Trash2, Search, Filter } from 'lucide-react';

export default function ActivityLog({ logs, onClearLogs }) {
  const [filter, setFilter] = useState('');
  const [levelFilter, setLevelFilter] = useState('ALL');
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  const filteredLogs = logs.filter((l) => {
    const matchesText =
      !filter ||
      l.message.toLowerCase().includes(filter.toLowerCase()) ||
      l.level.toLowerCase().includes(filter.toLowerCase());
    const matchesLevel = levelFilter === 'ALL' || l.level === levelFilter;
    return matchesText && matchesLevel;
  });

  return (
    <div className="page-container" style={{ height: 'calc(100vh - 120px)' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <div>
          <h2 style={{ fontSize: '1.4rem', fontWeight: 800, color: '#fff' }}>Activity & Execution Logs</h2>
          <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Real-time streaming Loguru telemetry across market feeds, sniper signals, and execution fills
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          {/* Level Filter */}
          <select
            value={levelFilter}
            onChange={(e) => setLevelFilter(e.target.value)}
            style={{
              background: 'var(--bg-dark)',
              border: '1px solid var(--border-light)',
              borderRadius: '8px',
              padding: '0.45rem 0.75rem',
              color: 'var(--text-main)',
              fontSize: '0.78rem',
              fontFamily: 'var(--font-mono)',
            }}
          >
            <option value="ALL">All Levels</option>
            <option value="INFO">INFO</option>
            <option value="WARNING">WARNING</option>
            <option value="CRITICAL">CRITICAL</option>
            <option value="SUCCESS">SUCCESS</option>
          </select>

          {/* Search Box */}
          <div style={{ position: 'relative' }}>
            <input
              type="text"
              placeholder="Search telemetry..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="form-input mono"
              style={{ padding: '0.45rem 0.85rem', width: '220px', fontSize: '0.78rem' }}
            />
          </div>

          {/* Clear Button */}
          <button
            className="btn-secondary"
            onClick={onClearLogs}
            style={{ padding: '0.45rem 0.85rem', display: 'flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.78rem' }}
          >
            <Trash2 size={14} />
            <span>Clear</span>
          </button>
        </div>
      </div>

      {/* Main Console Box */}
      <div
        className="hud-card"
        style={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          padding: '1rem',
          background: '#090807',
          border: '1px solid var(--border-light)',
        }}
      >
        <div
          ref={scrollRef}
          style={{
            flex: 1,
            overflowY: 'auto',
            fontFamily: 'var(--font-mono)',
            fontSize: '0.8rem',
            lineHeight: 1.6,
          }}
        >
          {filteredLogs.length === 0 ? (
            <div style={{ color: 'var(--text-dim)', padding: '2rem', textAlign: 'center' }}>
              No log events matching active search filter.
            </div>
          ) : (
            filteredLogs.map((item, idx) => (
              <div key={idx} style={{ display: 'flex', gap: '0.75rem', marginBottom: '0.25rem' }}>
                <span style={{ color: 'var(--text-dim)' }}>[{item.timestamp}]</span>
                <span
                  style={{
                    fontWeight: 700,
                    color:
                      item.level === 'CRITICAL'
                        ? 'var(--accent-red)'
                        : item.level === 'WARNING'
                        ? 'var(--accent-amber)'
                        : item.level === 'SUCCESS'
                        ? 'var(--accent-emerald)'
                        : 'var(--accent-orange)',
                  }}
                >
                  [{item.level}]
                </span>
                <span style={{ color: '#e5e5e0' }}>{item.message}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
