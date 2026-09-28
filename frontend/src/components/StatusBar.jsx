import React, { useState, useEffect } from 'react';
import { Radio, Shield, Clock, Wifi, Moon } from 'lucide-react';

export default function StatusBar({ state, isConnected, latency }) {
  const [istTime, setIstTime] = useState('');
  const [marketStatus, setMarketStatus] = useState({ isOpen: false, label: 'CLOSED' });

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      // Format IST parts accurately
      const formatter = new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Kolkata',
        weekday: 'short',
        hour: 'numeric',
        minute: 'numeric',
        second: 'numeric',
        hour12: false,
      });
      const parts = formatter.formatToParts(now);
      const partMap = {};
      parts.forEach((p) => {
        partMap[p.type] = p.value;
      });

      const weekday = partMap.weekday; // 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'
      let hour = parseInt(partMap.hour, 10);
      if (hour === 24) hour = 0; // Handle 24h edge cases in some browser Intl implementations
      const minute = parseInt(partMap.minute, 10);
      const second = parseInt(partMap.second, 10);

      const totalMinutes = hour * 60 + minute;
      const isWeekend = weekday === 'Sat' || weekday === 'Sun';

      let statusLabel = 'OPEN';
      let isOpen = false;

      if (isWeekend) {
        statusLabel = 'CLOSED (WEEKEND)';
      } else if (totalMinutes < 555) {
        // before 09:15 IST
        statusLabel = 'CLOSED (PRE-MARKET • OPENS 09:15 IST)';
      } else if (totalMinutes >= 930) {
        // after 15:30 IST
        statusLabel = 'CLOSED (AFTER HOURS • OPENS 09:15 IST)';
      } else {
        statusLabel = 'OPEN';
        isOpen = true;
      }

      setMarketStatus({ isOpen, label: statusLabel });
      setIstTime(
        `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}:${String(second).padStart(2, '0')}`
      );
    };
    updateTime();
    const interval = setInterval(updateTime, 1000);
    return () => clearInterval(interval);
  }, []);

  const isLive = state.execution_mode === 'LIVE';

  return (
    <footer className="bottom-status-bar">
      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Radio size={12} style={{ color: isLive ? 'var(--accent-orange)' : 'var(--accent-blue)' }} />
          <span>VENUE:</span>
          <strong style={{ color: '#fff' }}>
            {isLive ? 'Angel One SmartAPI (Live RMS)' : 'Paper Execution (Simulated)'}
          </strong>
        </div>

        <div>
          <span>MARKET:</span>{' '}
          <strong style={{ color: marketStatus.isOpen ? 'var(--accent-emerald)' : 'var(--accent-orange)' }}>
            {marketStatus.label}
          </strong>
        </div>

        <div>
          <span>BROKER SYNC:</span>{' '}
          <strong style={{ color: state.broker_rms?.is_live_synced ? 'var(--accent-emerald)' : 'var(--text-muted)' }}>
            {state.broker_rms?.is_live_synced ? 'Angel One Active' : 'Virtual Ledger'}
          </strong>
        </div>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Wifi size={12} style={{ color: isConnected ? 'var(--accent-emerald)' : 'var(--accent-red)' }} />
          <span>{isConnected ? `FEED: ${latency}ms` : 'FEED: DISCONNECTED'}</span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
          <Clock size={12} />
          <span>IST: {istTime}</span>
        </div>
      </div>
    </footer>
  );
}
