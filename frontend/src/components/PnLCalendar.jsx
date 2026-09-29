import React, { useState, useEffect, useMemo } from 'react';
import {
  Calendar as CalendarIcon,
  ChevronLeft,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  RotateCcw,
  CheckCircle2,
  CalendarCheck,
  HelpCircle
} from 'lucide-react';
import { formatINR } from './MetricsHud';

export default function PnLCalendar({ liveTrades = [] }) {
  // Always initialize with actual real-world current date
  const now = new Date();
  const [viewDate, setViewDate] = useState(new Date(now.getFullYear(), now.getMonth(), 1));
  const [calendarData, setCalendarData] = useState({ days: {}, summary: {} });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  
  // Format today's date YYYY-MM-DD
  const todayStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
  const [selectedDate, setSelectedDate] = useState(todayStr);
  const [jumpDate, setJumpDate] = useState('');

  const year = viewDate.getFullYear();
  const month = viewDate.getMonth(); // 0-indexed
  const monthStr = `${year}-${String(month + 1).padStart(2, '0')}`;

  const monthNames = [
    'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December'
  ];

  // Fetch genuine historical paper trades from SQLite
  const fetchCalendar = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`/api/paper/calendar?month=${monthStr}`);
      if (res.ok) {
        const json = await res.json();
        setCalendarData(json);
      } else {
        setError('Failed to load paper calendar ledger.');
      }
    } catch (e) {
      console.error('Error fetching calendar:', e);
      setError('Network error loading calendar.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchCalendar();
  }, [monthStr, liveTrades.length]);

  const handlePrevMonth = () => {
    setViewDate(new Date(year, month - 1, 1));
  };

  const handleNextMonth = () => {
    setViewDate(new Date(year, month + 1, 1));
  };

  const handleJumpToToday = () => {
    setViewDate(new Date(now.getFullYear(), now.getMonth(), 1));
    setSelectedDate(todayStr);
    setJumpDate('');
  };

  const handleJumpToDate = (e) => {
    const val = e.target.value;
    setJumpDate(val);
    if (val) {
      setSelectedDate(val);
      const parts = val.split('-');
      if (parts.length === 3) {
        const y = parseInt(parts[0], 10);
        const m = parseInt(parts[1], 10) - 1;
        setViewDate(new Date(y, m, 1));
      }
    }
  };

  // Build calendar matrix (Sunday to Saturday)
  const calendarCells = useMemo(() => {
    const firstDayIndex = new Date(year, month, 1).getDay(); // 0 = Sun
    const totalDaysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthTotalDays = new Date(year, month, 0).getDate();

    const cells = [];

    // 1. Previous month leading padding
    for (let i = firstDayIndex - 1; i >= 0; i--) {
      const dayNum = prevMonthTotalDays - i;
      const prevMonth = month === 0 ? 11 : month - 1;
      const prevYear = month === 0 ? year - 1 : year;
      const dateStr = `${prevYear}-${String(prevMonth + 1).padStart(2, '0')}-${String(dayNum).padStart(2, '0')}`;
      cells.push({
        dayNum,
        dateStr,
        isCurrentMonth: false,
      });
    }

    // 2. Current month days
    for (let d = 1; d <= totalDaysInMonth; d++) {
      const dateStr = `${year}-${String(month + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      cells.push({
        dayNum: d,
        dateStr,
        isCurrentMonth: true,
      });
    }

    // 3. Next month trailing padding to fill 35 or 42 grid cells
    const remaining = 35 - (cells.length % 35);
    const fillCount = (remaining > 0 && remaining < 7) ? remaining : (cells.length <= 35 ? 35 - cells.length : 42 - cells.length);
    for (let d = 1; d <= fillCount; d++) {
      const nextMonth = month === 11 ? 0 : month + 1;
      const nextYear = month === 11 ? year + 1 : year;
      const dateStr = `${nextYear}-${String(nextMonth + 1).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
      cells.push({
        dayNum: d,
        dateStr,
        isCurrentMonth: false,
      });
    }

    return cells;
  }, [year, month]);

  const daysData = calendarData.days || {};
  const summary = calendarData.summary || {};

  // Selected date's data
  const selectedDayData = selectedDate ? daysData[selectedDate] : null;

  const formatDateDisplay = (isoStr) => {
    if (!isoStr) return '--';
    try {
      const parts = isoStr.split('-');
      if (parts.length === 3) {
        const d = new Date(parseInt(parts[0]), parseInt(parts[1]) - 1, parseInt(parts[2]));
        return d.toLocaleDateString('en-IN', {
          weekday: 'long',
          year: 'numeric',
          month: 'long',
          day: 'numeric'
        });
      }
    } catch {
      return isoStr;
    }
    return isoStr;
  };

  const getStrikeBadge = (tr) => {
    let strike = tr.strike_price || 0;
    let opt = tr.option_type || '';

    if (tr.symbol) {
      const m5 = tr.symbol.match(/(\d{5})\s*(CE|PE)$/i);
      if (m5) {
        strike = parseFloat(m5[1]);
        if (!opt) opt = m5[2].toUpperCase();
      } else {
        const m4 = tr.symbol.match(/(\d{4})\s*(CE|PE)$/i);
        if (m4) {
          strike = parseFloat(m4[1]);
          if (!opt) opt = m4[2].toUpperCase();
        }
      }
    }

    if (strike > 100000) {
      strike = strike % 100000;
    }

    if (!opt && tr.symbol) {
      opt = tr.symbol.toUpperCase().includes('PE') ? 'PE' : 'CE';
    }

    return { strike: strike > 0 ? strike : null, type: opt || '--' };
  };

  const isToday = (dateStr) => {
    return dateStr === todayStr;
  };

  return (
    <div className="hud-card" style={{ marginTop: '1.5rem', borderLeft: '3px solid var(--accent-emerald)' }}>
      {/* Header Line */}
      <div className="card-header-line" style={{ flexWrap: 'wrap', gap: '0.75rem', paddingBottom: '0.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
          <CalendarIcon size={18} color="var(--accent-emerald)" />
          <div>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, color: '#fff', margin: 0 }}>
              Paper Trading P&L Calendar
            </h3>
            <span style={{ fontSize: '0.74rem', color: 'var(--text-muted)' }}>
              Actual paper trades executed, daily net profit/loss, brokerage & statutory charges
            </span>
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem', flexWrap: 'wrap' }}>
          {/* Quick Date Picker */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', background: 'rgba(255,255,255,0.03)', padding: '0.2rem 0.5rem', borderRadius: '6px', border: '1px solid var(--border-light)' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Jump to Date:</span>
            <input
              type="date"
              className="mono"
              value={jumpDate || selectedDate || ''}
              onChange={handleJumpToDate}
              style={{
                background: 'transparent',
                border: 'none',
                color: '#fff',
                fontSize: '0.75rem',
                outline: 'none',
                cursor: 'pointer'
              }}
            />
          </div>

          {/* Jump to Today Button */}
          <button
            className="btn-secondary"
            onClick={handleJumpToToday}
            style={{ fontSize: '0.72rem', padding: '0.3rem 0.6rem' }}
          >
            Today
          </button>

          {/* Refresh Button */}
          <button
            className="btn-secondary"
            onClick={fetchCalendar}
            disabled={loading}
            style={{
              padding: '0.3rem 0.6rem',
              fontSize: '0.72rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.3rem'
            }}
            title="Refresh calendar data"
          >
            <RotateCcw size={12} className={loading ? 'animate-spin' : ''} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Guide Banner */}
      <div style={{
        background: 'rgba(56, 189, 248, 0.05)',
        border: '1px solid rgba(56, 189, 248, 0.18)',
        borderRadius: '8px',
        padding: '0.6rem 0.85rem',
        margin: '0.5rem 0 1rem 0',
        display: 'flex',
        alignItems: 'center',
        gap: '0.75rem',
        fontSize: '0.75rem',
        color: 'var(--text-main)'
      }}>
        <HelpCircle size={16} color="var(--accent-blue)" style={{ flexShrink: 0 }} />
        <div>
          <span style={{ fontWeight: 600, color: 'var(--accent-blue)' }}>How to check Profit or Loss on any date: </span>
          Click on any day in the calendar grid below (green for profit, red for loss) or pick a date using <strong>Jump to Date</strong>.
          The trade ledger underneath displays that day's net realized P&L, brokerage fees, and actual option contracts taken.
        </div>
      </div>

      {/* Monthly Navigation Bar & KPI Strip */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: '1rem',
        background: 'rgba(255, 255, 255, 0.02)',
        padding: '0.75rem 1rem',
        borderRadius: '8px',
        border: '1px solid var(--border-light)',
        marginBottom: '1rem'
      }}>
        {/* Month Selector */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem' }}>
            <button
              className="btn-secondary"
              onClick={handlePrevMonth}
              style={{ padding: '0.35rem 0.5rem' }}
              title="Previous Month"
            >
              <ChevronLeft size={15} />
            </button>
            <span style={{ fontSize: '1.05rem', fontWeight: 800, color: '#fff', minWidth: '150px', textAlign: 'center' }}>
              {monthNames[month]} {year}
            </span>
            <button
              className="btn-secondary"
              onClick={handleNextMonth}
              style={{ padding: '0.35rem 0.5rem' }}
              title="Next Month"
            >
              <ChevronRight size={15} />
            </button>
          </div>
        </div>

        {/* Month Summary KPIs */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem', flexWrap: 'wrap', fontSize: '0.78rem' }}>
          <div>
            <span style={{ color: 'var(--text-muted)' }}>Net Realized P&L: </span>
            <span className={`mono font-bold ${(summary.total_net_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
              {(summary.total_net_pnl || 0) >= 0 ? `+${formatINR(summary.total_net_pnl || 0)}` : formatINR(summary.total_net_pnl || 0)}
            </span>
          </div>

          <div>
            <span style={{ color: 'var(--text-muted)' }}>Win Rate: </span>
            <span className="mono font-bold" style={{ color: 'var(--accent-emerald)' }}>
              {summary.win_rate_pct || 0}%
            </span>
            <span style={{ color: 'var(--text-dim)', fontSize: '0.7rem', marginLeft: '0.25rem' }}>
              ({summary.winning_days || 0}W / {summary.losing_days || 0}L)
            </span>
          </div>

          <div>
            <span style={{ color: 'var(--text-muted)' }}>Actual Trades: </span>
            <span className="mono font-bold text-main">{summary.total_trades || 0}</span>
          </div>

          <div>
            <span style={{ color: 'var(--text-muted)' }}>Taxes & Charges: </span>
            <span className="mono font-semibold" style={{ color: 'var(--accent-orange)' }}>
              -{formatINR(summary.total_charges || 0)}
            </span>
          </div>
        </div>
      </div>

      {/* 7-Column Day Header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '6px',
        textAlign: 'center',
        marginBottom: '6px'
      }}>
        {['SUN', 'MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT'].map((day, idx) => (
          <div
            key={day}
            style={{
              fontSize: '0.7rem',
              fontWeight: 700,
              letterSpacing: '0.05em',
              color: idx === 0 || idx === 6 ? 'var(--text-dim)' : 'var(--text-muted)',
              padding: '0.35rem 0',
              background: 'rgba(255, 255, 255, 0.015)',
              borderRadius: '4px'
            }}
          >
            {day}
          </div>
        ))}
      </div>

      {/* Calendar Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(7, 1fr)',
        gap: '6px',
      }}>
        {calendarCells.map((cell) => {
          const dayData = daysData[cell.dateStr];
          const hasTrades = Boolean(dayData && dayData.trade_count > 0);
          const isSelected = selectedDate === cell.dateStr;
          const isCurrentToday = isToday(cell.dateStr);

          // Colors based on PnL
          let bgColor = 'rgba(255, 255, 255, 0.02)';
          let borderColor = 'var(--border-light)';
          let pnlColor = 'var(--text-muted)';

          if (hasTrades) {
            if (dayData.net_pnl > 0) {
              bgColor = 'rgba(16, 185, 129, 0.1)';
              borderColor = 'rgba(16, 185, 129, 0.35)';
              pnlColor = 'var(--accent-emerald)';
            } else if (dayData.net_pnl < 0) {
              bgColor = 'rgba(244, 63, 94, 0.1)';
              borderColor = 'rgba(244, 63, 94, 0.35)';
              pnlColor = 'var(--accent-red)';
            } else {
              bgColor = 'rgba(148, 163, 184, 0.08)';
              borderColor = 'rgba(148, 163, 184, 0.25)';
              pnlColor = '#cbd5e1';
            }
          }

          if (isSelected) {
            borderColor = 'var(--accent-blue)';
            bgColor = hasTrades
              ? (dayData.net_pnl >= 0 ? 'rgba(16, 185, 129, 0.2)' : 'rgba(244, 63, 94, 0.2)')
              : 'rgba(56, 189, 248, 0.12)';
          }

          return (
            <div
              key={cell.dateStr}
              onClick={() => setSelectedDate(cell.dateStr)}
              style={{
                minHeight: '82px',
                padding: '0.45rem',
                borderRadius: '6px',
                background: bgColor,
                border: `1px solid ${borderColor}`,
                cursor: 'pointer',
                opacity: cell.isCurrentMonth ? 1 : 0.35,
                transition: 'all 0.18s ease',
                position: 'relative',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
                boxShadow: isSelected ? '0 0 10px rgba(56, 189, 248, 0.35)' : 'none',
              }}
              className="calendar-day-tile"
              title={`Click to view trade breakdown for ${cell.dateStr}`}
            >
              {/* Tile Header */}
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span
                  style={{
                    fontSize: '0.78rem',
                    fontWeight: isSelected ? 800 : 600,
                    color: isSelected ? '#fff' : (cell.isCurrentMonth ? 'var(--text-main)' : 'var(--text-dim)')
                  }}
                >
                  {cell.dayNum}
                </span>

                {isCurrentToday && (
                  <span
                    style={{
                      fontSize: '0.55rem',
                      fontWeight: 800,
                      background: 'var(--accent-blue)',
                      color: '#000',
                      padding: '0.1rem 0.3rem',
                      borderRadius: '3px',
                      letterSpacing: '0.04em'
                    }}
                  >
                    TODAY
                  </span>
                )}
              </div>

              {/* Tile Content */}
              {hasTrades ? (
                <div style={{ marginTop: 'auto' }}>
                  <div
                    className="mono font-bold"
                    style={{
                      fontSize: '0.78rem',
                      color: pnlColor,
                      lineHeight: 1.2
                    }}
                  >
                    {dayData.net_pnl >= 0 ? `+${formatINR(dayData.net_pnl)}` : formatINR(dayData.net_pnl)}
                  </div>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '0.2rem', fontSize: '0.62rem', color: 'var(--text-muted)' }}>
                    <span>{dayData.trade_count} {dayData.trade_count === 1 ? 'trade' : 'trades'}</span>
                    <span style={{ display: 'flex', gap: '2px' }}>
                      {Array.from({ length: dayData.wins }).map((_, i) => (
                        <span key={`w-${i}`} style={{ width: '5px', height: '5px', borderRadius: '50%', background: 'var(--accent-emerald)' }} />
                      ))}
                      {Array.from({ length: dayData.losses }).map((_, i) => (
                        <span key={`l-${i}`} style={{ width: '5px', height: '5px', borderRadius: '50%', background: 'var(--accent-red)' }} />
                      ))}
                    </span>
                  </div>
                </div>
              ) : (
                <div style={{ marginTop: 'auto', textAlign: 'center', fontSize: '0.65rem', color: 'var(--text-dim)' }}>
                  --
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Selected Date Breakdown Section */}
      {selectedDate && (
        <div style={{
          marginTop: '1.5rem',
          padding: '1.1rem',
          borderRadius: '8px',
          background: 'rgba(255, 255, 255, 0.02)',
          border: '1px solid var(--border-medium)',
        }}>
          {/* Header of Date Breakdown */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.75rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '0.75rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              <CalendarCheck size={18} color="var(--accent-blue)" />
              <div>
                <h4 style={{ fontSize: '1rem', fontWeight: 800, color: '#fff', margin: 0 }}>
                  Performance for: {formatDateDisplay(selectedDate)}
                </h4>
                <div className="mono text-muted" style={{ fontSize: '0.72rem' }}>
                  Date: {selectedDate}
                </div>
              </div>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '0.6rem' }}>
              {selectedDayData ? (
                <span
                  className="pill-badge"
                  style={{
                    background: selectedDayData.net_pnl >= 0 ? 'rgba(16, 185, 129, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                    color: selectedDayData.net_pnl >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)',
                    fontSize: '0.74rem',
                    padding: '0.25rem 0.65rem'
                  }}
                >
                  {selectedDayData.net_pnl >= 0 ? '● WINNING SESSION' : '○ LOSS SESSION'}
                </span>
              ) : (
                <span className="pill-badge" style={{ background: 'rgba(255,255,255,0.05)', color: 'var(--text-muted)', fontSize: '0.74rem' }}>
                  NO PAPER TRADES ON THIS DATE
                </span>
              )}
            </div>
          </div>

          {/* Date Summary Cards */}
          {selectedDayData ? (
            <div>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))',
                gap: '0.75rem',
                margin: '1rem 0'
              }}>
                {/* Net P&L */}
                <div className="index-tile" style={{ borderLeft: `3px solid ${selectedDayData.net_pnl >= 0 ? 'var(--accent-emerald)' : 'var(--accent-red)'}` }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Net Realized P&L</div>
                  <div className={`mono font-bold ${selectedDayData.net_pnl >= 0 ? 'profit-text' : 'loss-text'}`} style={{ fontSize: '1.2rem', margin: '0.2rem 0' }}>
                    {selectedDayData.net_pnl >= 0 ? `+${formatINR(selectedDayData.net_pnl)}` : formatINR(selectedDayData.net_pnl)}
                  </div>
                  <div style={{ fontSize: '0.66rem', color: 'var(--text-dim)' }}>After all brokerage & taxes</div>
                </div>

                {/* Gross P&L */}
                <div className="index-tile">
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Gross Trading P&L</div>
                  <div className={`mono font-bold ${selectedDayData.gross_pnl >= 0 ? 'profit-text' : 'loss-text'}`} style={{ fontSize: '1.1rem', margin: '0.2rem 0' }}>
                    {selectedDayData.gross_pnl >= 0 ? `+${formatINR(selectedDayData.gross_pnl)}` : formatINR(selectedDayData.gross_pnl)}
                  </div>
                  <div style={{ fontSize: '0.66rem', color: 'var(--text-dim)' }}>Raw execution gain/loss</div>
                </div>

                {/* Charges */}
                <div className="index-tile" style={{ borderLeft: '3px solid var(--accent-orange)' }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Brokerage & Taxes</div>
                  <div className="mono font-bold" style={{ fontSize: '1.1rem', color: 'var(--accent-orange)', margin: '0.2rem 0' }}>
                    -{formatINR(selectedDayData.total_charges)}
                  </div>
                  <div style={{ fontSize: '0.66rem', color: 'var(--text-dim)' }}>₹40 flat + STT + Exch + GST</div>
                </div>

                {/* Trade Quota & Win Rate */}
                <div className="index-tile">
                  <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>Trades Executed</div>
                  <div className="mono font-bold" style={{ fontSize: '1.1rem', color: '#fff', margin: '0.2rem 0' }}>
                    {selectedDayData.trade_count} / 2 Quota
                  </div>
                  <div style={{ fontSize: '0.66rem', color: 'var(--accent-emerald)' }}>
                    {selectedDayData.wins} Win · {selectedDayData.losses} Loss
                  </div>
                </div>
              </div>

              {/* Table of Trades for Selected Date */}
              <div style={{ overflowX: 'auto', marginTop: '0.8rem' }}>
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>TRADE ID / TIME</th>
                      <th>CONTRACT</th>
                      <th>STRIKE</th>
                      <th>TYPE</th>
                      <th>QTY</th>
                      <th>ENTRY</th>
                      <th>EXIT</th>
                      <th>GROSS P&L</th>
                      <th>TAXES & FEES</th>
                      <th>NET P&L</th>
                      <th>EXIT REASON</th>
                    </tr>
                  </thead>
                  <tbody>
                    {selectedDayData.trades.map((tr) => {
                      const strikeInfo = getStrikeBadge(tr);
                      return (
                        <tr key={tr.id}>
                          <td>
                            <div className="mono font-semibold" style={{ fontSize: '0.74rem', color: '#fff' }}>{tr.id}</div>
                            <div className="mono text-muted" style={{ fontSize: '0.68rem' }}>{tr.timestamp}</div>
                          </td>
                          <td className="mono font-semibold">{tr.symbol}</td>
                          <td className="mono font-bold" style={{ color: 'var(--accent-blue)' }}>
                            {strikeInfo.strike ? `₹${strikeInfo.strike.toLocaleString('en-IN')}` : '--'}
                          </td>
                          <td>
                            <span
                              className="pill-badge"
                              style={{
                                background: strikeInfo.type === 'CE' ? 'rgba(56, 189, 248, 0.15)' : 'rgba(244, 63, 94, 0.15)',
                                color: strikeInfo.type === 'CE' ? '#38bdf8' : '#f43f5e',
                                fontSize: '0.72rem',
                                padding: '0.15rem 0.5rem',
                              }}
                            >
                              {strikeInfo.type}
                            </span>
                          </td>
                          <td className="mono">{tr.quantity}</td>
                          <td className="mono">₹{tr.entry_price?.toFixed(1) || '-'}</td>
                          <td className="mono">₹{tr.exit_price?.toFixed(1) || '-'}</td>
                          <td className={`mono font-semibold ${(tr.gross_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
                            {(tr.gross_pnl || 0) >= 0 ? `+${formatINR(tr.gross_pnl)}` : formatINR(tr.gross_pnl)}
                          </td>
                          <td className="mono" style={{ color: 'var(--accent-orange)' }}>
                            -{formatINR(tr.total_charges || 65)}
                          </td>
                          <td className={`mono font-bold ${(tr.net_pnl || 0) >= 0 ? 'profit-text' : 'loss-text'}`}>
                            {(tr.net_pnl || 0) >= 0 ? `+${formatINR(tr.net_pnl)}` : formatINR(tr.net_pnl)}
                          </td>
                          <td>
                            <span
                              className="pill-badge"
                              style={{
                                background: 'rgba(255, 255, 255, 0.05)',
                                color: tr.exit_reason?.toLowerCase().includes('target') ? 'var(--accent-emerald)' : (tr.exit_reason?.toLowerCase().includes('stop') ? 'var(--accent-red)' : 'var(--text-main)'),
                                fontSize: '0.7rem',
                                padding: '0.2rem 0.5rem'
                              }}
                            >
                              {tr.exit_reason || 'Manual Exit'}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          ) : (
            <div style={{
              textAlign: 'center',
              padding: '2.5rem 1rem',
              color: 'var(--text-muted)',
              fontSize: '0.82rem'
            }}>
              <CalendarIcon size={32} color="var(--text-dim)" style={{ marginBottom: '0.5rem' }} />
              <div>No paper trades recorded on <strong>{formatDateDisplay(selectedDate)}</strong>.</div>
              <div style={{ fontSize: '0.74rem', color: 'var(--text-dim)', marginTop: '0.35rem' }}>
                Only actual trades taken during paper trading sessions will appear here.
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
