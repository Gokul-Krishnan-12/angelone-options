import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  Briefcase,
  PlayCircle,
  Activity,
  FileText,
  Clock,
  Settings,
  BookOpen,
  Flame
} from 'lucide-react';
import { formatINR } from './MetricsHud';

export default function Sidebar({ state }) {
  const links = [
    { to: '/', label: 'Overview', icon: Briefcase },
    { to: '/orders', label: 'Orders & Positions', icon: FileText },
    { to: '/paper', label: 'Paper Agent', icon: Activity },
    { to: '/agent', label: 'Real Trade Agent', icon: PlayCircle },
    { to: '/workflow', label: 'Trading Logic & Guide', icon: BookOpen },
    { to: '/logs', label: 'Activity Logs', icon: Clock },
    { to: '/settings', label: 'Settings & Broker', icon: Settings },
  ];

  const rmsNet = state.broker_rms?.net ?? 0;
  const isLiveSynced = Boolean(state.broker_rms?.is_live_synced);

  return (
    <aside className="sidebar">
      <div className="sidebar-top">
        {/* Brand Header */}
        <div className="sidebar-brand">
          <div className="brand-icon-box">
            <Flame size={18} />
          </div>
          <div>
            <h1 className="brand-name">SmartAPI Sniper</h1>
            <div className="brand-tag">ILSME Quant</div>
          </div>
        </div>

        {/* Navigation Links */}
        <nav className="sidebar-nav">
          {links.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === '/'}
                className={({ isActive }) => `nav-item ${isActive ? 'active' : ''}`}
              >
                <Icon size={16} />
                <span>{item.label}</span>
              </NavLink>
            );
          })}
        </nav>
      </div>

      {/* Minimal Footer */}
      <div className="sidebar-bottom">
        <div className="sidebar-bottom-row">
          <span>Venue:</span>
          <span style={{ color: isLiveSynced ? 'var(--accent-emerald)' : 'var(--text-muted)' }}>
            {isLiveSynced ? 'Angel One' : 'Paper Sim'}
          </span>
        </div>
        <div className="sidebar-bottom-row">
          <span>Capital:</span>
          <span className="mono" style={{ color: '#fff' }}>{formatINR(rmsNet)}</span>
        </div>
      </div>
    </aside>
  );
}
