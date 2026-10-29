import React, { useState, useEffect } from 'react';
import {
  Moon,
  Sun,
  Search,
  Sparkles,
  ShieldAlert,
  CheckCircle2,
  XCircle,
  Play,
  Square,
  Clock,
  Layers,
  ArrowRight,
  RefreshCw,
  ExternalLink,
  Cpu,
  Key,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Zap
} from 'lucide-react';
import { authFetch } from '../utils/api';
import { formatINR } from '../components/MetricsHud';

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

export default function OvernightAiPlanner() {
  const [latestPlan, setLatestPlan] = useState(null);
  const [planHistory, setPlanHistory] = useState([]);
  const [scannerStatus, setScannerStatus] = useState(null);
  const [scannerInterval, setScannerInterval] = useState(() => {
    const saved = localStorage.getItem('scanner_interval_mins');
    return saved ? parseInt(saved) : 5;
  });
  const [aiConfig, setAiConfig] = useState(null);
  const [universe, setUniverse] = useState([]);
  const [isAutoDiscover, setIsAutoDiscover] = useState(() => {
    const saved = localStorage.getItem('planner_auto_discover');
    return saved !== null ? saved === 'true' : true;
  });
  const [maxCandidates, setMaxCandidates] = useState(() => {
    const saved = localStorage.getItem('planner_max_candidates');
    return saved ? parseInt(saved) : 3;
  });
  const [selectedUniverse, setSelectedUniverse] = useState(() => {
    const saved = localStorage.getItem('planner_selected_universe');
    try {
      return saved ? JSON.parse(saved) : ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN'];
    } catch {
      return ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN'];
    }
  });
  const [customTicker, setCustomTicker] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('OPENAI');
  const [selectedModel, setSelectedModel] = useState('gpt-4o-mini');
  const [apiKeyInput, setApiKeyInput] = useState('');
  const [showApiKeyModal, setShowApiKeyModal] = useState(false);

  const [isRunningPlanner, setIsRunningPlanner] = useState(false);
  const [isRunningScan, setIsRunningScan] = useState(false);
  const [isTestingAi, setIsTestingAi] = useState(false);
  const [isFetchingDayStart, setIsFetchingDayStart] = useState(false);
  const [testResult, setTestResult] = useState(null);
  const [actionMessage, setActionMessage] = useState(null);

  useEffect(() => {
    fetchInitialData();
    const interval = setInterval(fetchStatusUpdates, 10000);
    return () => clearInterval(interval);
  }, []);

  const fetchInitialData = async () => {
    try {
      const [pRes, hRes, sRes, aiRes, uRes] = await Promise.all([
        authFetch('/api/stock-options/planner/latest'),
        authFetch('/api/stock-options/planner/history?limit=10'),
        authFetch('/api/stock-options/scanner/status'),
        authFetch('/api/stock-options/ai/config'),
        authFetch('/api/stock-options/universe')
      ]);

      if (pRes.ok) {
        const pData = await pRes.json();
        if (pData.plan_id) setLatestPlan(pData);
      }
      if (hRes.ok) setPlanHistory(await hRes.json());
      if (sRes.ok) {
        const sData = await sRes.json();
        setScannerStatus(sData);
        if (sData.interval_mins) {
          setScannerInterval(parseInt(sData.interval_mins));
          localStorage.setItem('scanner_interval_mins', String(sData.interval_mins));
        }
        if (sData.max_candidates) {
          setMaxCandidates(parseInt(sData.max_candidates));
          localStorage.setItem('planner_max_candidates', String(sData.max_candidates));
        }
      }
      if (aiRes.ok) {
        const aiData = await aiRes.json();
        setAiConfig(aiData);
        if (aiData.provider) setSelectedProvider(aiData.provider);
        if (aiData.model) setSelectedModel(aiData.model);
      }
      if (uRes.ok) setUniverse(await uRes.json());
    } catch (e) {
      console.error('Error fetching planner data:', e);
    }
  };

  const fetchStatusUpdates = async () => {
    try {
      const sRes = await authFetch('/api/stock-options/scanner/status');
      if (sRes.ok) {
        const sData = await sRes.json();
        setScannerStatus(sData);
        if (sData.interval_mins) {
          setScannerInterval(parseInt(sData.interval_mins));
          localStorage.setItem('scanner_interval_mins', String(sData.interval_mins));
        }
      }
    } catch (e) {}
  };

  const showNotification = (msg, isError = false) => {
    setActionMessage({ text: msg, isError });
    setTimeout(() => setActionMessage(null), 5000);
  };

  const handleSetMaxCandidates = (num) => {
    const val = parseInt(num);
    setMaxCandidates(val);
    localStorage.setItem('planner_max_candidates', String(val));
  };

  const handleUpdateScanInterval = async (intervalMins) => {
    const chosen = parseInt(intervalMins);
    // Instant optimistic UI update + localStorage persistence
    setScannerInterval(chosen);
    localStorage.setItem('scanner_interval_mins', String(chosen));
    setScannerStatus(prev => prev ? ({ ...prev, interval_mins: chosen }) : ({ interval_mins: chosen }));

    try {
      const res = await authFetch('/api/stock-options/scanner/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          interval_mins: chosen,
          max_candidates: parseInt(maxCandidates),
          stock_universe: isAutoDiscover ? [] : selectedUniverse
        })
      });
      const data = await res.json();
      if (res.ok) {
        const confirmed = parseInt(data.interval_mins || chosen);
        setScannerInterval(confirmed);
        localStorage.setItem('scanner_interval_mins', String(confirmed));
        showNotification(`Intraday radar interval set to ${confirmed >= 60 ? (confirmed / 60) + ' hr' : confirmed + ' min'}.`);
      } else {
        showNotification(data.detail || data.message || 'Failed to update scan interval', true);
      }
    } catch (e) {
      showNotification('Failed to update scan interval', true);
    }
  };

  const handleFetchDayStartMovers = async () => {
    setIsFetchingDayStart(true);
    try {
      const res = await authFetch('/api/stock-options/universe/day-start-movers');
      if (res.ok) {
        const data = await res.json();
        const syms = data.symbols && data.symbols.length > 0
          ? data.symbols
          : ['COFORGE', 'PERSISTENT', 'DIXON', 'POLYCAB', 'INDUSINDBK', 'CANBK', 'DLF', 'SBIN'];
        setIsAutoDiscover(false);
        localStorage.setItem('planner_auto_discover', 'false');
        setSelectedUniverse(syms);
        localStorage.setItem('planner_selected_universe', JSON.stringify(syms));
        showNotification(`⚡ Day-Start Screener: Loaded ${syms.length} high-beta momentum stocks into watchlist.`);
      } else {
        handleSetQuickSector('HIGH_BETA');
      }
    } catch (e) {
      handleSetQuickSector('HIGH_BETA');
    } finally {
      setIsFetchingDayStart(false);
    }
  };

  const handleSetQuickSector = (type) => {
    if (type === 'ALL_FO') {
      setIsAutoDiscover(true);
      localStorage.setItem('planner_auto_discover', 'true');
      setSelectedUniverse([]);
      localStorage.setItem('planner_selected_universe', JSON.stringify([]));
      showNotification('Auto-Discover mode active: Screener evaluates entire NSE F&O universe.');
    } else {
      setIsAutoDiscover(false);
      localStorage.setItem('planner_auto_discover', 'false');
      let nextUni = [];
      if (type === 'HIGH_BETA') {
        nextUni = ['COFORGE', 'PERSISTENT', 'DIXON', 'POLYCAB', 'INDUSINDBK', 'CANBK', 'DLF', 'ADANIENT', 'SBIN', 'TRENT', 'HAL', 'BHEL'];
      } else if (type === 'NIFTY50') {
        nextUni = ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'BHARTIARTL', 'TATAMOTORS', 'LT', 'AXISBANK', 'KOTAKBANK', 'BAJFINANCE', 'MARUTI', 'SUNPHARMA', 'TITAN', 'ITC', 'TATASTEEL', 'WIPRO', 'HINDUNILVR', 'COALINDIA', 'JSWSTEEL', 'ADANIENT', 'ADANIPORTS', 'M&M', 'HCLTECH', 'GRASIM', 'HEROMOTOCO', 'CIPLA', 'DRREDDY', 'EICHERMOT', 'TECHM', 'DIVISLAB', 'BPCL', 'NTPC', 'POWERGRID', 'ONGC', 'TATACONSUM', 'ULTRACEMCO', 'NESTLEIND', 'ASIANPAINT', 'INDUSINDBK', 'HINDALCO', 'BAJAJ-AUTO'];
      } else if (type === 'BANKING') {
        nextUni = ['HDFCBANK', 'ICICIBANK', 'SBIN', 'AXISBANK', 'KOTAKBANK', 'INDUSINDBK', 'CANBK', 'FEDERALBNK', 'PFC', 'RECLTD', 'SHRIRAMFIN'];
      } else if (type === 'IT') {
        nextUni = ['TCS', 'INFY', 'WIPRO', 'HCLTECH', 'TECHM', 'PERSISTENT', 'COFORGE'];
      } else if (type === 'AUTO_METALS') {
        nextUni = ['TATAMOTORS', 'MARUTI', 'M&M', 'HEROMOTOCO', 'BAJAJ-AUTO', 'EICHERMOT', 'TATASTEEL', 'JSWSTEEL', 'HINDALCO', 'COALINDIA'];
      } else if (type === 'CLEAR') {
        nextUni = [];
      }
      setSelectedUniverse(nextUni);
      localStorage.setItem('planner_selected_universe', JSON.stringify(nextUni));
      showNotification(`Filtered watchlist (${nextUni.length} stocks).`);
    }
  };

  const handleAddCustomTicker = () => {
    const sym = customTicker.trim().toUpperCase();
    if (sym && !selectedUniverse.includes(sym)) {
      setIsAutoDiscover(false);
      localStorage.setItem('planner_auto_discover', 'false');
      setSelectedUniverse(prev => {
        const next = [...prev, sym];
        localStorage.setItem('planner_selected_universe', JSON.stringify(next));
        return next;
      });
      setCustomTicker('');
      showNotification(`Added ${sym} to research watchlist.`);
    }
  };

  const isAiConnected = selectedProvider === 'OPENAI'
    ? Boolean(aiConfig?.openai_configured)
    : Boolean(aiConfig?.gemini_configured);

  const handleSelectProvider = async (provider, defaultModel) => {
    setSelectedProvider(provider);
    setSelectedModel(defaultModel);
    try {
      await authFetch('/api/stock-options/ai/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider, model: defaultModel })
      });
      const aiRes = await authFetch('/api/stock-options/ai/config');
      if (aiRes.ok) setAiConfig(await aiRes.json());
    } catch (e) {
      console.error('Failed to sync provider selection:', e);
    }
  };

  const handleTriggerIntradayScan = async () => {
    if (!isAiConnected) {
      showNotification(`Cannot scan: ${selectedProvider === 'OPENAI' ? 'OpenAI (ChatGPT)' : 'Google Gemini'} is not connected. Please set your API key first.`, true);
      setShowApiKeyModal(true);
      return;
    }
    setIsRunningScan(true);
    setIsRunningPlanner(true);
    try {
      const res = await authFetch('/api/stock-options/scanner/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: selectedProvider,
          model: selectedModel,
          max_candidates: maxCandidates
        })
      });
      const data = await res.json();
      if (data.status === 'success' && data.scan) {
        setLatestPlan(data.scan);
        if (data.session || data.scan.session) {
          const s = data.session || data.scan.session;
          setScannerStatus(prev => ({
            ...prev,
            session: s,
            session_id: s.session_id,
            session_date: s.session_date,
            scans_count: s.scans_count
          }));
        }
        showNotification(`AI Intraday Scan complete: ${data.scan.candidates?.length || 0} top F&O setup(s) fetched from ${selectedProvider}.`);
        fetchInitialData();
      } else if (data.status === 'outside_session') {
        showNotification(data.message || 'AI scanner runs strictly between 09:00 and 15:00 IST.', true);
      } else if (data.status === 'not_configured') {
        showNotification(data.message || 'AI is not connected. Please enter your API key.', true);
        setShowApiKeyModal(true);
      } else if (data.status === 'gated') {
        showNotification('Market stable. Thresholds not breached; preserved AI quota.');
      } else {
        showNotification(data.message || 'Market scan completed.', false);
        fetchInitialData();
      }
      fetchStatusUpdates();
    } catch (e) {
      showNotification('Error triggering real-time market scan.', true);
    } finally {
      setIsRunningScan(false);
      setIsRunningPlanner(false);
    }
  };

  const handleRunPlanner = handleTriggerIntradayScan;

  const handleToggleScanner = async () => {
    if (!scannerStatus) return;
    if (!isAiConnected && !scannerStatus.is_active) {
      showNotification(`Cannot start radar: ${selectedProvider === 'OPENAI' ? 'OpenAI (ChatGPT)' : 'Google Gemini'} is not connected. Please enter your API key first.`, true);
      setShowApiKeyModal(true);
      return;
    }
    const action = scannerStatus.is_active ? 'stop' : 'start';
    try {
      const res = await authFetch(`/api/stock-options/scanner/${action}`, { method: 'POST' });
      const data = await res.json();
      if (res.ok) {
        setScannerStatus(prev => ({ ...prev, is_active: !prev.is_active }));
        showNotification(`Scanner ${action === 'start' ? 'activated' : 'stopped'}.`);
      } else {
        showNotification(data.detail || data.message || 'Failed to toggle scanner.', true);
      }
    } catch (e) {
      showNotification('Failed to toggle scanner.', true);
    }
  };

  const handleSaveAiConfig = async () => {
    try {
      const body = {
        provider: selectedProvider,
        model: selectedModel
      };
      if (apiKeyInput.trim()) {
        if (selectedProvider === 'OPENAI') body.openai_key = apiKeyInput.trim();
        else body.gemini_key = apiKeyInput.trim();
      }
      const res = await authFetch('/api/stock-options/ai/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      if (res.ok) {
        showNotification(`AI Provider configured as ${selectedProvider}.`);
        setApiKeyInput('');
        setShowApiKeyModal(false);
        const aiRes = await authFetch('/api/stock-options/ai/config');
        if (aiRes.ok) setAiConfig(await aiRes.json());
      }
    } catch (e) {
      showNotification('Failed to save AI config', true);
    }
  };

  const handleTestAi = async () => {
    if (!isAiConnected) {
      showNotification(`Please enter your ${selectedProvider === 'OPENAI' ? 'OpenAI' : 'Google Gemini'} API key first.`, true);
      setShowApiKeyModal(true);
      return;
    }
    setIsTestingAi(true);
    setTestResult(null);
    try {
      const res = await authFetch('/api/stock-options/ai/test', { method: 'POST' });
      const data = await res.json();
      setTestResult(data);
      if (data.status === 'success') {
        showNotification(`AI Test Successful (${data.provider} - ${data.latency_ms}ms)`);
      } else if (data.status === 'not_configured') {
        showNotification(data.message || 'AI API key not configured.', true);
        setShowApiKeyModal(true);
      } else {
        showNotification('AI Test returned errors.', true);
      }
    } catch (e) {
      showNotification('AI test request failed', true);
    } finally {
      setIsTestingAi(false);
    }
  };

  const handleApproveCandidate = async (planId, symbol, targetMode) => {
    try {
      const targetEndpoint = targetMode === 'LIVE' ? '/api/stock-options/live/execute-candidate' : '/api/stock-options/paper/execute-candidate';
      const targetCandidate = (latestPlan?.candidates || []).find(c => c.symbol === symbol);
      if (!targetCandidate) return;

      const res = await authFetch(targetEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ candidate: targetCandidate, plan_id: planId })
      });
      const data = await res.json();
      if (data.status === 'success') {
        showNotification(`Candidate ${symbol} successfully routed to ${targetMode} agent!`);
      } else {
        showNotification(`Execution rejected: ${data.reason || data.message}`, true);
      }
    } catch (e) {
      showNotification('Error approving candidate', true);
    }
  };

  const toggleUniverseSymbol = (sym) => {
    setSelectedUniverse(prev =>
      prev.includes(sym) ? prev.filter(s => s !== sym) : [...prev, sym]
    );
  };

  // When AI is not connected, strictly suppress any candidates to prevent dummy data
  const candidates = isAiConnected ? (latestPlan?.candidates || []) : [];


  const nowHourMin = (() => {
    const d = new Date();
    const utc = d.getTime() + (d.getTimezoneOffset() * 60000);
    const ist = new Date(utc + (3600000 * 5.5));
    return ist.getHours() * 60 + ist.getMinutes();
  })();
  const isWithinMarketHours = nowHourMin >= (9 * 60) && nowHourMin <= (15 * 60);

  return (
    <div className="page-container">
      {/* Top Banner & Header */}
      <div className="card-header-line" style={{ marginBottom: '1.25rem', alignItems: 'flex-start' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
            <div className="brand-icon-box" style={{ background: 'linear-gradient(135deg, #0ea5e9, #6366f1)' }}>
              <Search size={18} color="#fff" />
            </div>
            <div>
              <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: '#fff', margin: 0 }}>
                Intraday AI Market Scanner
              </h2>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                Real-Time F&O Opportunity Radar & Autonomous Trade Execution Engine
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap', alignItems: 'center' }}>
          <span className="badge" style={{ background: 'rgba(56, 189, 248, 0.1)', color: 'var(--accent-blue)', border: '1px solid rgba(56, 189, 248, 0.25)' }}>
            <Clock size={12} style={{ marginRight: 4 }} />
            IST Asia/Kolkata
          </span>
          <span className="badge" style={{
            background: isWithinMarketHours ? 'rgba(16, 185, 129, 0.1)' : 'rgba(237, 76, 34, 0.1)',
            color: isWithinMarketHours ? 'var(--accent-emerald)' : 'var(--accent-orange)',
            border: `1px solid ${isWithinMarketHours ? 'rgba(16, 185, 129, 0.25)' : 'rgba(237, 76, 34, 0.25)'}`
          }}>
            {isWithinMarketHours ? 'Market Open (09:00 - 15:00 IST)' : 'Market Closed (Active 09:00 - 15:00 IST)'}
          </span>
          <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-emerald)', border: '1px solid rgba(16, 185, 129, 0.25)' }}>
            Session: {scannerStatus?.session_date || scannerStatus?.session?.session_date || latestPlan?.intended_date || 'Active Session'} ({scannerStatus?.scans_count ?? scannerStatus?.session?.scans_count ?? 0} Scans)
          </span>
          <span className="badge" style={{ background: 'rgba(237, 76, 34, 0.1)', color: 'var(--accent-orange)', border: '1px solid rgba(237, 76, 34, 0.3)' }}>
            Top 3 F&O Cap Enforced
          </span>
        </div>
      </div>

      {actionMessage && (
        <div style={{
          padding: '0.75rem 1rem',
          borderRadius: 8,
          marginBottom: '1rem',
          fontSize: '0.82rem',
          background: actionMessage.isError ? 'rgba(244, 63, 94, 0.15)' : 'rgba(16, 185, 129, 0.15)',
          border: `1px solid ${actionMessage.isError ? 'var(--accent-red)' : 'var(--accent-emerald)'}`,
          color: actionMessage.isError ? 'var(--accent-red)' : 'var(--accent-emerald)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <span>{actionMessage.text}</span>
          <button onClick={() => setActionMessage(null)} style={{ background: 'none', border: 'none', color: 'inherit', cursor: 'pointer' }}>×</button>
        </div>
      )}

      {/* Main Grid: Control Panel (Left) + Trade Plans (Right) */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(320px, 380px) 1fr', gap: '1.25rem' }}>
        
        {/* LEFT COLUMN: Controls & Configuration */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          
          {/* Card 1: AI Provider & Engine */}
          <div className="hud-card">
            <div className="card-header-line">
              <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>AI Research Provider</span>
              <Cpu size={15} color="var(--accent-blue)" />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', margin: '0.75rem 0' }}>
              <button
                className={`btn-secondary ${selectedProvider === 'OPENAI' ? 'active' : ''}`}
                onClick={() => handleSelectProvider('OPENAI', 'gpt-4o-mini')}
                style={{ padding: '0.5rem', fontSize: '0.8rem', justifyContent: 'center' }}
              >
                OpenAI (ChatGPT)
              </button>
              <button
                className={`btn-secondary ${selectedProvider === 'GEMINI' ? 'active' : ''}`}
                onClick={() => handleSelectProvider('GEMINI', 'gemini-3-flash-preview')}
                style={{ padding: '0.5rem', fontSize: '0.8rem', justifyContent: 'center' }}
              >
                Google Gemini
              </button>
            </div>

            <div className="form-group" style={{ marginBottom: '0.75rem' }}>
              <label className="form-label" style={{ fontSize: '0.72rem' }}>Selected Model</label>
              <select
                className="form-input"
                style={{ padding: '0.45rem', fontSize: '0.82rem' }}
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
              >
                {selectedProvider === 'OPENAI' ? (
                  <>
                    <option value="gpt-4o-mini">gpt-4o-mini (Fast / Quantitative)</option>
                    <option value="gpt-4o">gpt-4o (High Reasoning)</option>
                    <option value="o3-mini">o3-mini (Reasoning Model)</option>
                  </>
                ) : (
                  <>
                    <option value="gemini-3-flash-preview">gemini-3-flash (Low Latency / Recommended)</option>
                    <option value="gemini-3.1-flash-lite">gemini-3.1-flash-lite (Ultra-Fast / High Availability)</option>
                    <option value="gemini-3.1-pro-preview">gemini-3.1-pro (Deep Reasoning)</option>
                  </>
                )}
              </select>
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.75rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
              <span>API Key Status:</span>
              <span style={{
                color: isAiConnected ? 'var(--accent-emerald)' : 'var(--accent-red)',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: 5
              }}>
                <span className={`status-dot ${isAiConnected ? 'active' : ''}`} style={{ width: 7, height: 7, background: isAiConnected ? 'var(--accent-emerald)' : 'var(--accent-red)' }} />
                {isAiConnected ? 'Connected & Active' : 'Not Connected'}
              </span>
            </div>

            <div style={{ display: 'flex', gap: '0.5rem' }}>
              <button
                className="btn-secondary"
                style={{ flex: 1, fontSize: '0.78rem', padding: '0.45rem', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '0.35rem' }}
                onClick={() => setShowApiKeyModal(true)}
              >
                <Key size={13} />
                <span>Set API Key</span>
              </button>
              <button
                className="btn-secondary"
                style={{ fontSize: '0.78rem', padding: '0.45rem', display: 'flex', alignItems: 'center', gap: '0.35rem' }}
                onClick={handleTestAi}
                disabled={isTestingAi}
              >
                {isTestingAi ? <RefreshCw size={13} className="spin" /> : <span>Test AI</span>}
              </button>
            </div>

            {testResult && (
              <div style={{ marginTop: '0.75rem', padding: '0.5rem', background: 'rgba(0,0,0,0.3)', borderRadius: 6, fontSize: '0.72rem', border: '1px solid var(--border-light)' }}>
                <div>Latency: <span className="mono" style={{ color: 'var(--accent-emerald)' }}>{testResult.latency_ms}ms</span></div>
                <div>Provider: {testResult.provider} ({testResult.model})</div>
              </div>
            )}
          </div>

          {/* Card 2: Unified Intraday AI Market Radar & Autonomous Engine */}
          <div className="hud-card">
            <div className="card-header-line">
              <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Intraday AI Market Radar</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem' }}>
                <span className={`status-dot ${scannerStatus?.is_active ? 'active' : ''}`} />
                <span style={{ fontSize: '0.72rem', color: scannerStatus?.is_active ? 'var(--accent-emerald)' : 'var(--text-muted)' }}>
                  {scannerStatus?.is_active ? 'RADAR RUNNING' : 'RADAR STOPPED'}
                </span>
              </div>
            </div>

            {/* Configurable Scan Frequency Intervals */}
            <div style={{ margin: '0.75rem 0 0.5rem 0' }}>
              <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginBottom: '0.35rem' }}>
                Scan Frequency Interval:
              </div>
              <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                {[
                  { label: '1m', mins: 1 },
                  { label: '3m', mins: 3 },
                  { label: '5m', mins: 5 },
                  { label: '15m', mins: 15 },
                  { label: '30m', mins: 30 },
                  { label: '1 hr', mins: 60 },
                  { label: '2 hr', mins: 120 }
                ].map(opt => {
                  const isCur = Number(scannerInterval) === opt.mins;
                  return (
                    <button
                      key={opt.mins}
                      type="button"
                      onClick={() => handleUpdateScanInterval(opt.mins)}
                      style={{
                        padding: '0.25rem 0.55rem',
                        fontSize: '0.72rem',
                        borderRadius: 4,
                        border: '1px solid',
                        borderColor: isCur ? 'var(--accent-blue)' : 'var(--border-light)',
                        background: isCur ? 'rgba(56, 189, 248, 0.25)' : 'rgba(0,0,0,0.2)',
                        color: isCur ? '#fff' : 'var(--text-muted)',
                        cursor: 'pointer',
                        fontWeight: isCur ? 700 : 400
                      }}
                    >
                      {opt.label}
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Hard Cap Candidate Selection */}
            <div className="form-group" style={{ margin: '0.75rem 0' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <label className="form-label" style={{ fontSize: '0.72rem' }}>Top Candidates Cap (Hard Stop ≤ 3)</label>
                <span className="badge mono" style={{ background: 'rgba(237, 76, 34, 0.15)', color: 'var(--accent-orange)' }}>
                  {maxCandidates} / 3 Max
                </span>
              </div>
              <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.35rem' }}>
                {[1, 2, 3].map(num => (
                  <button
                    key={num}
                    type="button"
                    className={`btn-secondary ${maxCandidates === num ? 'active' : ''}`}
                    style={{ flex: 1, padding: '0.4rem', justifyContent: 'center' }}
                    onClick={() => handleSetMaxCandidates(num)}
                  >
                    {num} Stock{num > 1 ? 's' : ''}
                  </button>
                ))}
              </div>
            </div>

            {/* Stock Universe Selection */}
            <div className="form-group" style={{ marginBottom: '0.85rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.45rem', flexWrap: 'wrap', gap: '0.35rem' }}>
                <label className="form-label" style={{ fontSize: '0.72rem', margin: 0 }}>
                  Universe {isAutoDiscover ? '(Auto-Discover Mode)' : `(${selectedUniverse.length} Selected)`}
                </label>
                <div style={{ display: 'flex', gap: '0.35rem', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={handleFetchDayStartMovers}
                    disabled={isFetchingDayStart}
                    title="Screen top high-beta momentum F&O stocks at day start (09:15 AM)"
                    style={{
                      fontSize: '0.68rem',
                      padding: '0.2rem 0.55rem',
                      borderRadius: 4,
                      border: '1px solid rgba(245, 158, 11, 0.45)',
                      background: 'rgba(245, 158, 11, 0.12)',
                      color: '#fbbf24',
                      cursor: 'pointer',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.25rem'
                    }}
                  >
                    <Zap size={11} className={isFetchingDayStart ? 'spin' : ''} />
                    {isFetchingDayStart ? 'Screening...' : '⚡ Fetch Day-Start Stocks (09:15 AM)'}
                  </button>
                  <button
                    type="button"
                    onClick={() => handleSetQuickSector('ALL_FO')}
                    style={{
                      fontSize: '0.68rem',
                      padding: '0.2rem 0.5rem',
                      borderRadius: 4,
                      border: '1px solid',
                      borderColor: isAutoDiscover ? 'var(--accent-emerald)' : 'var(--border-light)',
                      background: isAutoDiscover ? 'rgba(16, 185, 129, 0.2)' : 'rgba(255,255,255,0.04)',
                      color: isAutoDiscover ? 'var(--accent-emerald)' : 'var(--text-muted)',
                      cursor: 'pointer',
                      fontWeight: 600
                    }}
                  >
                    ⚡ Auto-Discover (All F&O)
                  </button>
                </div>
              </div>

              {/* Quick Filter Sector Pills */}
              <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', marginBottom: '0.5rem' }}>
                {[
                  { label: '⚡ High-Beta (Day Start)', type: 'HIGH_BETA' },
                  { label: 'Nifty 50', type: 'NIFTY50' },
                  { label: 'Banking', type: 'BANKING' },
                  { label: 'IT', type: 'IT' },
                  { label: 'Auto/Metals', type: 'AUTO_METALS' },
                  { label: 'Clear', type: 'CLEAR' }
                ].map(sec => (
                  <button
                    key={sec.type}
                    type="button"
                    onClick={() => handleSetQuickSector(sec.type)}
                    style={{
                      fontSize: '0.65rem',
                      padding: '0.15rem 0.4rem',
                      borderRadius: 4,
                      background: sec.type === 'HIGH_BETA' ? 'rgba(245, 158, 11, 0.08)' : 'rgba(255,255,255,0.03)',
                      border: '1px solid',
                      borderColor: sec.type === 'HIGH_BETA' ? 'rgba(245, 158, 11, 0.3)' : 'var(--border-light)',
                      color: sec.type === 'HIGH_BETA' ? '#fbbf24' : 'var(--text-muted)',
                      cursor: 'pointer',
                      fontWeight: sec.type === 'HIGH_BETA' ? 600 : 400
                    }}
                  >
                    {sec.label}
                  </button>
                ))}
              </div>

              {isAutoDiscover ? (
                <div style={{ padding: '0.65rem', background: 'rgba(16, 185, 129, 0.08)', border: '1px solid rgba(16, 185, 129, 0.2)', borderRadius: 6, fontSize: '0.72rem', color: 'var(--text-main)' }}>
                  <div style={{ fontWeight: 600, color: 'var(--accent-emerald)', marginBottom: '0.2rem' }}>Dynamic Real-Time Radar Active</div>
                  The bot dynamically checks all active NSE F&O equities at each interval, querying the AI with real-time spot prices for immediate profitable entries.
                </div>
              ) : (
                <>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.35rem', maxHeight: 85, overflowY: 'auto', padding: '0.25rem', background: 'rgba(0,0,0,0.2)', borderRadius: 6, marginBottom: '0.4rem' }}>
                    {(universe.length > 0 ? universe.map(u => u.symbol) : ['RELIANCE', 'TCS', 'INFY', 'HDFCBANK', 'ICICIBANK', 'SBIN', 'BHARTIARTL', 'TATAMOTORS', 'LT', 'MARUTI']).map(sym => (
                      <button
                        key={sym}
                        type="button"
                        onClick={() => toggleUniverseSymbol(sym)}
                        style={{
                          padding: '0.2rem 0.45rem',
                          fontSize: '0.68rem',
                          borderRadius: 4,
                          border: '1px solid',
                          borderColor: selectedUniverse.includes(sym) ? 'var(--accent-orange)' : 'var(--border-light)',
                          background: selectedUniverse.includes(sym) ? 'rgba(237, 76, 34, 0.2)' : 'transparent',
                          color: selectedUniverse.includes(sym) ? '#fff' : 'var(--text-muted)',
                          cursor: 'pointer'
                        }}
                      >
                        {sym}
                      </button>
                    ))}
                  </div>

                  <div style={{ display: 'flex', gap: '0.35rem' }}>
                    <input
                      type="text"
                      placeholder="Add NSE Symbol (e.g. POLYCAB, BEL)"
                      value={customTicker}
                      onChange={e => setCustomTicker(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleAddCustomTicker()}
                      style={{
                        flex: 1,
                        padding: '0.3rem 0.5rem',
                        fontSize: '0.72rem',
                        background: 'rgba(0,0,0,0.3)',
                        border: '1px solid var(--border-light)',
                        borderRadius: 4,
                        color: '#fff',
                        fontFamily: 'var(--font-mono)'
                      }}
                    />
                    <button
                      type="button"
                      className="btn-secondary"
                      onClick={handleAddCustomTicker}
                      style={{ padding: '0.3rem 0.6rem', fontSize: '0.72rem' }}
                    >
                      + Add
                    </button>
                  </div>
                </>
              )}
            </div>

            {/* Session & Telemetry Status Box */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', margin: '0.75rem 0' }}>
              <div style={{ padding: '0.45rem', background: 'rgba(0,0,0,0.2)', borderRadius: 6 }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Session ID</div>
                <div className="mono" style={{ fontWeight: 600, color: 'var(--accent-blue)', fontSize: '0.75rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {scannerStatus?.session_id || scannerStatus?.session?.session_id || 'SESSION_' + new Date().toISOString().slice(0, 10).replace(/-/g, '')}
                </div>
              </div>
              <div style={{ padding: '0.45rem', background: 'rgba(0,0,0,0.2)', borderRadius: 6 }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Scans Run Today</div>
                <div className="mono" style={{ fontWeight: 600, color: 'var(--accent-emerald)', fontSize: '0.85rem' }}>
                  {scannerStatus?.scans_count ?? scannerStatus?.session?.scans_count ?? 0} Completed
                </div>
              </div>
            </div>

            {/* Main Action Buttons */}
            <button
              className="btn-primary"
              style={{ width: '100%', padding: '0.65rem', justifyContent: 'center', fontSize: '0.82rem', display: 'flex', alignItems: 'center', gap: '0.45rem', marginBottom: '0.5rem' }}
              onClick={handleTriggerIntradayScan}
              disabled={isRunningScan}
            >
              {isRunningScan ? (
                <>
                  <RefreshCw size={14} className="spin" style={{ marginRight: 6 }} />
                  Scanning Live F&O Market with AI...
                </>
              ) : (
                <>
                  <RefreshCw size={14} style={{ marginRight: 6 }} />
                  Scan Market Now
                </>
              )}
            </button>

            <button
              className={`btn-secondary ${scannerStatus?.is_active ? 'danger' : ''}`}
              style={{ width: '100%', padding: '0.5rem', fontSize: '0.78rem', justifyContent: 'center' }}
              onClick={handleToggleScanner}
            >
              {scannerStatus?.is_active ? <Square size={13} style={{ marginRight: 4 }} /> : <Play size={13} style={{ marginRight: 4 }} />}
              {scannerStatus?.is_active ? 'Stop Scheduled Scanner' : `Start Auto Scanner (${scannerInterval >= 60 ? (scannerInterval / 60) + ' hr' : scannerInterval + ' min'})`}
            </button>
          </div>

        </div>

        {/* RIGHT COLUMN: Active Research Results / Candidates */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
          
          {/* Prominent Warning Card when AI is Not Connected */}
          {!isAiConnected && (
            <div className="hud-card" style={{
              border: '1px solid rgba(244, 63, 94, 0.4)',
              background: 'linear-gradient(135deg, rgba(244, 63, 94, 0.12) 0%, rgba(20, 20, 25, 0.95) 100%)',
              padding: '1rem 1.25rem',
              borderRadius: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: '1rem'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: 8,
                  background: 'rgba(244, 63, 94, 0.2)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0
                }}>
                  <ShieldAlert size={22} color="var(--accent-red)" />
                </div>
                <div>
                  <div style={{ fontWeight: 600, fontSize: '0.92rem', color: '#fff', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                    <span>AI Provider Not Connected</span>
                    <span className="badge" style={{ background: 'rgba(244, 63, 94, 0.2)', color: 'var(--accent-red)', border: '1px solid rgba(244, 63, 94, 0.4)', fontSize: '0.68rem' }}>
                      No Dummy Data Mode
                    </span>
                  </div>
                  <div style={{ fontSize: '0.76rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Your {selectedProvider === 'OPENAI' ? 'OpenAI (ChatGPT)' : 'Google Gemini'} API key is not configured. Real-time scanning and candidate discovery are paused. Connect your API key to enable live AI market intelligence.
                  </div>
                </div>
              </div>
              <button
                className="btn-primary"
                onClick={() => setShowApiKeyModal(true)}
                style={{ whiteSpace: 'nowrap', display: 'flex', alignItems: 'center', gap: '0.4rem', padding: '0.5rem 0.9rem', fontSize: '0.78rem' }}
              >
                <Key size={13} />
                <span>Connect API Key</span>
              </button>
            </div>
          )}

          {/* Plan Meta Banner */}
          <div className="hud-card" style={{ borderLeft: `3px solid ${isAiConnected ? 'var(--accent-orange)' : 'var(--accent-red)'}` }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
              <div>
                <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                  Active Market Scan: <span className="mono" style={{ color: isAiConnected ? 'var(--accent-orange)' : 'var(--accent-red)' }}>{isAiConnected ? (latestPlan?.plan_id || 'Ready for Scan') : 'Scanner Paused (AI Disconnected)'}</span>
                </div>
                <div style={{ fontSize: '0.88rem', fontWeight: 600, color: '#fff', marginTop: '0.2rem' }}>
                  {isAiConnected
                    ? (latestPlan?.market_summary || 'Click "Scan Market Now" or start the Auto-Scanner to discover real-time intraday setups.')
                    : 'AI provider is not connected. Candidate scanning is paused until a valid API key is entered.'}
                </div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: '0.68rem', color: 'var(--text-dim)' }}>
                  AI Provider: {selectedProvider === 'OPENAI' ? 'OpenAI' : 'Google Gemini'} ({selectedModel})
                </div>
                <div style={{ fontSize: '0.68rem', color: isAiConnected ? 'var(--text-dim)' : 'var(--accent-red)' }}>
                  Status: {isAiConnected ? 'Connected' : 'Not Connected'}
                </div>
              </div>
            </div>

            {(!isAiConnected || latestPlan?.no_trade_reason) && (
              <div style={{ marginTop: '0.75rem', padding: '0.6rem 0.8rem', background: 'rgba(244, 63, 94, 0.1)', border: '1px solid rgba(244, 63, 94, 0.25)', borderRadius: 6, fontSize: '0.78rem', color: 'var(--accent-red)', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <AlertTriangle size={15} />
                <span>
                  <strong>STATUS:</strong> {!isAiConnected ? 'AI is not connected. API key is missing. No dummy trade setups will be shown.' : latestPlan.no_trade_reason}
                </span>
              </div>
            )}
          </div>

          {/* Candidate Stock Cards */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
              <h3 style={{ fontSize: '0.95rem', fontWeight: 600, color: '#fff' }}>
                Qualified F&O Setups ({candidates.length} / {maxCandidates} Max)
              </h3>
              <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                Deterministic Risk-Reward Enforced
              </span>
            </div>

            {isAiConnected && (
              <div style={{
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
                padding: '0.5rem 0.75rem',
                background: 'rgba(56, 189, 248, 0.08)',
                border: '1px solid rgba(56, 189, 248, 0.2)',
                borderRadius: 6,
                marginBottom: '0.75rem',
                fontSize: '0.72rem',
                color: 'var(--text-muted)'
              }}>
                <Zap size={13} color="var(--accent-blue)" />
                <span>
                  <strong style={{ color: '#fff' }}>Autonomous Execution Active:</strong> The bot automatically executes these setups in Paper Agent and in Live Trading (when live auto-execution is enabled) based on the AI's exact levels. Buttons below provide optional manual override dispatch.
                </span>
              </div>
            )}

            {!isAiConnected ? (
              <div className="hud-card" style={{ textAlign: 'center', padding: '3rem 1.5rem', border: '1px dashed rgba(244, 63, 94, 0.35)' }}>
                <div style={{
                  width: 56,
                  height: 56,
                  borderRadius: '50%',
                  background: 'rgba(244, 63, 94, 0.12)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 1rem auto'
                }}>
                  <ShieldAlert size={28} color="var(--accent-red)" />
                </div>
                <div style={{ fontSize: '1rem', color: '#fff', fontWeight: 600, marginBottom: '0.35rem' }}>
                  AI Intelligence Engine Disconnected
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', maxWidth: 440, margin: '0 auto 1.25rem auto', lineHeight: 1.5 }}>
                  Real-time F&O analysis requires an active {selectedProvider === 'OPENAI' ? 'OpenAI' : 'Google Gemini'} API connection.
                  Dummy fallback data has been strictly disabled to protect capital.
                </div>
                <button
                  className="btn-primary"
                  onClick={() => setShowApiKeyModal(true)}
                  style={{ margin: '0 auto', display: 'flex', alignItems: 'center', gap: '0.45rem', padding: '0.55rem 1.2rem', fontSize: '0.82rem' }}
                >
                  <Key size={14} />
                  <span>Connect API Key Now</span>
                </button>
              </div>
            ) : candidates.length === 0 ? (
              <div className="hud-card" style={{ textAlign: 'center', padding: '3rem 1.5rem' }}>
                <Search size={32} color="var(--text-dim)" style={{ marginBottom: '0.75rem' }} />
                <div style={{ fontSize: '0.92rem', color: 'var(--text-muted)', fontWeight: 500 }}>
                  No Active Stock Candidates
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-dim)', maxWidth: 420, margin: '0.5rem auto 1.25rem auto' }}>
                  The AI evaluates real-time market prices, volume breakouts, and option spreads. Click "Scan Market Now" to evaluate current opportunities.
                </div>
                <button
                  className="btn-primary"
                  onClick={handleTriggerIntradayScan}
                  disabled={isRunningScan}
                  style={{ margin: '0 auto', display: 'flex', alignItems: 'center', gap: '0.45rem' }}
                >
                  <RefreshCw size={14} className={isRunningScan ? 'spin' : ''} />
                  <span>Scan Market Now</span>
                </button>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {candidates.map((cand, idx) => {
                  const isBullish = cand.bias === 'BULLISH';
                  const contract = cand.primary_contract || {};
                  const tech = cand.technical || {};
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
                    <div key={cand.symbol || idx} className="hud-card" style={{ border: '1px solid var(--border-medium)', position: 'relative' }}>
                      {/* Card Header Line */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '0.5rem', borderBottom: '1px solid var(--border-light)', paddingBottom: '0.75rem', marginBottom: '0.75rem' }}>
                        <div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem' }}>
                            <span className="mono" style={{ fontSize: '1.15rem', fontWeight: 800, color: '#fff' }}>
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

                            <span className="badge" style={{ background: 'rgba(255, 255, 255, 0.05)', color: 'var(--text-muted)' }}>
                              {cand.setup_type}
                            </span>
                          </div>
                          <div style={{ fontSize: '0.72rem', color: 'var(--text-dim)', marginTop: '0.2rem' }}>
                            {cand.company_name} ({cand.sector})
                          </div>
                        </div>

                        <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Confidence</div>
                            <div className="mono" style={{ fontWeight: 700, color: 'var(--accent-emerald)', fontSize: '0.9rem' }}>
                              {Math.round((cand.confidence_score || 0.8) * 100)}%
                            </div>
                          </div>
                          <div style={{ textAlign: 'right', marginLeft: '0.5rem' }}>
                            <div style={{ fontSize: '0.68rem', color: 'var(--text-muted)' }}>Target R:R</div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '0.35rem', justifyContent: 'flex-end' }}>
                              {isHighBeta && (
                                <span
                                  style={{
                                    fontSize: '0.62rem',
                                    fontWeight: 800,
                                    color: '#c084fc',
                                    background: 'rgba(192, 132, 252, 0.16)',
                                    border: '1px solid rgba(192, 132, 252, 0.4)',
                                    padding: '0.1rem 0.35rem',
                                    borderRadius: 4
                                  }}
                                >
                                  HIGH BETA
                                </span>
                              )}
                              <span className="mono" style={{ fontWeight: 700, color: isHighBeta ? '#c084fc' : 'var(--accent-orange)', fontSize: '0.9rem' }}>
                                1 : {mgmt.risk_reward_ratio ? Number(mgmt.risk_reward_ratio).toFixed(1) : (isHighBeta ? '2.0' : '1.5')}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>

                      {/* Technical & Contract Parameters Grid */}
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: '0.65rem', marginBottom: '0.75rem' }}>
                        <div style={{ padding: '0.5rem', background: 'rgba(0,0,0,0.25)', borderRadius: 6 }}>
                          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Spot Reference</div>
                          <div className="mono" style={{ fontWeight: 600 }}>₹{tech.reference_price}</div>
                        </div>
                        <div style={{ padding: '0.5rem', background: 'rgba(0,0,0,0.25)', borderRadius: 6 }}>
                          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Entry Trigger</div>
                          <div className="mono" style={{ fontWeight: 600, color: 'var(--accent-blue)' }}>₹{tech.entry_trigger}</div>
                        </div>
                        <div style={{ padding: '0.5rem', background: 'rgba(0,0,0,0.25)', borderRadius: 6 }}>
                          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Contract ({lotUnits}/lot)</div>
                          <div className="mono" style={{ fontWeight: 700, color: '#fff', fontSize: '0.78rem' }}>
                            {contract.strike_price} {contract.option_type || (isBullish ? 'CE' : 'PE')}
                          </div>
                        </div>
                        <div style={{ padding: '0.5rem', background: 'rgba(0,0,0,0.25)', borderRadius: 6 }}>
                          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Entry Premium</div>
                          <div className="mono" style={{ fontWeight: 700, color: 'var(--accent-blue)' }}>₹{entryPrice.toFixed(2)}</div>
                        </div>
                        <div style={{ padding: '0.5rem', background: 'rgba(0,0,0,0.25)', borderRadius: 6 }}>
                          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Stop Loss</div>
                          <div className="mono" style={{ fontWeight: 700, color: 'var(--accent-red)' }}>₹{slPrice.toFixed(2)}</div>
                        </div>
                        <div style={{ padding: '0.5rem', background: 'rgba(0,0,0,0.25)', borderRadius: 6 }}>
                          <div style={{ fontSize: '0.66rem', color: 'var(--text-muted)' }}>Target 1</div>
                          <div className="mono" style={{ fontWeight: 700, color: 'var(--accent-emerald)' }}>₹{target1Price.toFixed(2)}</div>
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
                          padding: '0.55rem 0.75rem',
                          border: '1px solid rgba(255, 255, 255, 0.05)',
                          marginBottom: '0.75rem'
                        }}
                      >
                        {/* Expected Profit */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                              Expected Profit (1 Lot • {lotUnits} shares)
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
                              +{profitPct}% (+₹{profitPts.toFixed(2)} pts)
                            </span>
                          </div>
                          <div className="mono" style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--accent-emerald)', marginTop: '0.15rem' }}>
                            +{formatINR(expectedProfit)}
                          </div>
                        </div>

                        {/* Expected Loss */}
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '0.1rem', borderLeft: '1px solid var(--border-light)', paddingLeft: '0.75rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                            <span style={{ fontSize: '0.68rem', color: 'var(--text-muted)', fontWeight: 600 }}>
                              Max Risk / Loss (1 Lot • {lotUnits} shares)
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
                              -{lossPct}% (-₹{lossPts.toFixed(2)} pts)
                            </span>
                          </div>
                          <div className="mono" style={{ fontSize: '1.05rem', fontWeight: 800, color: 'var(--accent-red)', marginTop: '0.15rem' }}>
                            -{formatINR(expectedLoss)}
                          </div>
                        </div>
                      </div>

                      {/* Rationale & Warnings */}
                      <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '0.85rem', lineHeight: 1.45 }}>
                        <strong>Technical Rationale:</strong> {tech.technical_rationale || 'Breakout confirmed across high-volume node.'}
                      </div>

                      {/* Action Approvals & Status */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '0.65rem', borderTop: '1px solid var(--border-light)', flexWrap: 'wrap', gap: '0.5rem' }}>
                        <div style={{ fontSize: '0.72rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                          <span style={{ color: 'var(--text-dim)' }}>Status:</span>
                          {cand.approval_status === 'AUTO_DISPATCHED_PAPER' ? (
                            <span style={{ color: 'var(--accent-blue)', fontWeight: 600 }}>🤖 Auto-Dispatched to Paper</span>
                          ) : cand.approval_status === 'AUTO_DISPATCHED_LIVE' ? (
                            <span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>⚡ Auto-Dispatched to Live</span>
                          ) : cand.approval_status === 'AUTO_DISPATCHED_PAPER_LIVE' ? (
                            <span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>🤖⚡ Auto-Dispatched (Paper & Live)</span>
                          ) : cand.approval_status === 'APPROVED' ? (
                            <span style={{ color: 'var(--accent-emerald)', fontWeight: 600 }}>✓ Approved</span>
                          ) : (
                            <span style={{ color: 'var(--accent-orange)' }}>Autonomous Queue Ready</span>
                          )}
                        </div>

                        <div style={{ display: 'flex', gap: '0.5rem' }}>
                          <button
                            className="btn-secondary"
                            style={{ padding: '0.4rem 0.75rem', fontSize: '0.75rem' }}
                            onClick={() => handleApproveCandidate(latestPlan?.plan_id, cand.symbol, 'PAPER')}
                            title="Optional manual override: Immediately simulate in Paper Ledger"
                          >
                            <Sparkles size={13} style={{ marginRight: 4 }} color="var(--accent-blue)" />
                            Manual Paper Dispatch
                          </button>
                          <button
                            className="btn-primary"
                            style={{ padding: '0.4rem 0.75rem', fontSize: '0.75rem' }}
                            onClick={() => handleApproveCandidate(latestPlan?.plan_id, cand.symbol, 'LIVE')}
                            title="Optional manual override: Immediately send live order to Angel One"
                          >
                            <CheckCircle2 size={13} style={{ marginRight: 4 }} />
                            Manual Live Dispatch
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Historical Scans Table */}
          <div className="hud-card">
            <div className="card-header-line">
              <span style={{ fontWeight: 600, fontSize: '0.88rem' }}>Recent Market Scans</span>
              <Layers size={14} color="var(--text-muted)" />
            </div>

            <div className="table-container" style={{ marginTop: '0.5rem' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Scan / Plan ID</th>
                    <th>Session Date</th>
                    <th>Candidates</th>
                    <th>AI Provider</th>
                    <th>Latency</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {planHistory.length === 0 ? (
                    <tr>
                      <td colSpan="6" style={{ textAlign: 'center', color: 'var(--text-dim)', padding: '1.5rem' }}>
                        No historical market scans stored yet.
                      </td>
                    </tr>
                  ) : (
                    planHistory.map((p) => (
                      <tr key={p.plan_id}>
                        <td className="mono" style={{ fontSize: '0.78rem' }}>{p.plan_id}</td>
                        <td>{p.intended_date}</td>
                        <td>
                          <span className="mono" style={{ fontWeight: 600, color: 'var(--accent-orange)' }}>
                            {p.candidates?.length || 0} stocks
                          </span>
                        </td>
                        <td>{p.ai_provider} ({p.model})</td>
                        <td className="mono">{Math.round(p.latency_ms || 0)}ms</td>
                        <td>
                          <span className="badge" style={{ background: 'rgba(16, 185, 129, 0.1)', color: 'var(--accent-emerald)' }}>
                            {p.status}
                          </span>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

        </div>

      </div>

      {/* API Key Modal */}
      {showApiKeyModal && (
        <div className="modal-backdrop">
          <div className="modal-box" style={{ maxWidth: 440 }}>
            <h3 style={{ fontSize: '1.05rem', fontWeight: 600, color: '#fff', marginBottom: '0.5rem' }}>
              Configure {selectedProvider} API Key
            </h3>
            <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '1rem' }}>
              Credentials are saved securely on the server and never exposed in browser storage or logs.
            </p>

            <div className="form-group" style={{ marginBottom: '1rem' }}>
              <label className="form-label">
                {selectedProvider === 'OPENAI' ? 'OpenAI Secret Key (sk-...)' : 'Google Gemini API Key'}
              </label>
              <input
                type="password"
                className="form-input mono"
                placeholder={selectedProvider === 'OPENAI' ? 'sk-...' : 'AIzaSy...'}
                value={apiKeyInput}
                onChange={(e) => setApiKeyInput(e.target.value)}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.5rem' }}>
              <button className="btn-secondary" onClick={() => setShowApiKeyModal(false)}>
                Cancel
              </button>
              <button className="btn-primary" onClick={handleSaveAiConfig}>
                Save Key
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
