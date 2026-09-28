import React from 'react';

export default function MarketRadar({ spotLevels }) {
  const indices = [
    {
      key: 'NIFTY',
      name: 'NIFTY 50',
      badge: 'NSE',
      fallbackSpot: 24850.0,
      fallbackVwap: 24845.0,
      fallbackPdh: 24950.0,
      fallbackPdl: 24720.0
    },
    {
      key: 'BANKNIFTY',
      name: 'BANK NIFTY',
      badge: 'NSE',
      fallbackSpot: 52400.0,
      fallbackVwap: 52380.0,
      fallbackPdh: 52700.0,
      fallbackPdl: 52100.0
    },
    {
      key: 'SENSEX',
      name: 'SENSEX',
      badge: 'BSE',
      fallbackSpot: 81200.0,
      fallbackVwap: 81180.0,
      fallbackPdh: 81600.0,
      fallbackPdl: 80800.0
    },
  ];

  return (
    <div className="hud-card">
      <div className="card-header-line">
        <span>Spot Indices Telemetry</span>
        <span className="mono text-muted">Continuous Tick</span>
      </div>

      <div className="index-grid">
        {indices.map((idx) => {
          const data = spotLevels[idx.key] || {};
          const spot = data.spot > 0 ? data.spot : idx.fallbackSpot;
          const vwap = data.vwap > 0 ? data.vwap : idx.fallbackVwap;
          const pdh = data.pdh > 0 ? data.pdh : idx.fallbackPdh;
          const pdl = data.pdl > 0 ? data.pdl : idx.fallbackPdl;

          return (
            <div key={idx.key} className="index-tile">
              <div className="index-header">
                <span>{idx.name}</span>
                <span className="mono text-muted" style={{ fontSize: '0.65rem' }}>{idx.badge}</span>
              </div>
              <div className="index-price-val mono">
                {spot.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="index-meta mono">
                <span>VWAP {vwap.toFixed(1)}</span>
                <span>H {pdh} · L {pdl}</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
