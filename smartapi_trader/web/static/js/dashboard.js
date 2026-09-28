// SmartAPI Algorithmic Options Trading Dashboard Client
let ws = null;
let currentMode = "PAPER";
let pendingMode = null;
let lastPingTime = 0;

// Format Currency
function formatINR(val) {
  const num = parseFloat(val) || 0;
  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 2
  }).format(num);
}

// WebSocket Connection & Telemetry Handling
function connectWebSocket() {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/telemetry`;

  ws = new WebSocket(wsUrl);

  ws.onopen = () => {
    console.log("[WS] Connected to SmartAPI Telemetry Feed");
    document.getElementById("heartbeat-dot").classList.remove("offline");
    document.getElementById("ws-status-text").textContent = "FEED CONNECTED";
    sendPing();
  };

  ws.onmessage = (event) => {
    if (event.data === "pong") {
      const latency = Math.round(performance.now() - lastPingTime);
      document.getElementById("latency-text").textContent = `${latency}ms`;
      return;
    }

    try {
      const msg = JSON.parse(event.data);
      handleIncomingEvent(msg);
    } catch (e) {
      console.error("[WS] Parse error:", e);
    }
  };

  ws.onclose = () => {
    console.warn("[WS] Disconnected. Reconnecting in 3s...");
    document.getElementById("heartbeat-dot").classList.add("offline");
    document.getElementById("ws-status-text").textContent = "DISCONNECTED";
    document.getElementById("latency-text").textContent = "--";
    setTimeout(connectWebSocket, 3000);
  };
}

function sendPing() {
  if (ws && ws.readyState === WebSocket.OPEN) {
    lastPingTime = performance.now();
    ws.send("ping");
  }
  setTimeout(sendPing, 10000);
}

function handleIncomingEvent(msg) {
  switch (msg.type) {
    case "INITIAL_STATE":
      updateFullDashboard(msg.data);
      break;
    case "SYSTEM_STATE":
      updateSystemMetrics(msg.data);
      break;
    case "TICK":
      updateTickData(msg.data);
      break;
    case "ORDER_UPDATE":
      appendLog("INFO", `Order Update: ${msg.data.order_id} status=${msg.data.status} ${msg.data.symbol} qty=${msg.data.quantity}`);
      fetchState();
      break;
    case "FILL":
      appendLog("SUCCESS", `Execution Fill: ${msg.data.transaction_type} ${msg.data.quantity}x ${msg.data.symbol} @ ₹${msg.data.price} (Slip: ₹${msg.data.slippage})`);
      fetchState();
      break;
    case "POSITION_UPDATE":
      renderPositions([msg.data]);
      break;
    case "RISK_ALERT":
      appendLog("WARNING", `[RISK ${msg.data.level}] ${msg.data.rule_name}: ${msg.data.message}`);
      break;
    case "LOG_ENTRY":
      appendLog(msg.data.level, `[${msg.data.module}] ${msg.data.message}`, msg.data.timestamp);
      break;
    case "MODE_CHANGED":
      setModeUI(msg.mode);
      break;
    case "PANIC_TRIGGERED":
      appendLog("CRITICAL", "GLOBAL EMERGENCY PANIC TRIGGERED!");
      document.getElementById("panic-indicator").style.display = "block";
      fetchState();
      break;
    case "PANIC_CLEARED":
      appendLog("INFO", "Panic state cleared. Scanner resumed.");
      document.getElementById("panic-indicator").style.display = "none";
      fetchState();
      break;
  }
}

// Fetch Full Snapshot
async function fetchState() {
  try {
    const res = await fetch("/api/state");
    const data = await res.json();
    updateFullDashboard(data);
  } catch (e) {
    console.error("Error fetching state:", e);
  }
}

function updateFullDashboard(state) {
  if (!state) return;
  
  setModeUI(state.execution_mode);
  updateSystemMetrics(state);
  renderPositions(state.positions || []);
  renderOrders(state.orders || []);
  updateRadar(state.spot_levels || {});
  updateStrategyStatus(state.strategy_status || "Scanning for Liquidity Sweep");
  
  if (state.is_panic_active) {
    document.getElementById("panic-indicator").style.display = "block";
  } else {
    document.getElementById("panic-indicator").style.display = "none";
  }
}

function updateSystemMetrics(data) {
  // P&L
  const pnlEl = document.getElementById("hud-pnl");
  const pnlPctEl = document.getElementById("hud-pnl-pct");
  const pnl = data.daily_pnl || 0;
  pnlEl.textContent = (pnl >= 0 ? "+" : "") + formatINR(pnl);
  pnlEl.className = "metric-value " + (pnl >= 0 ? "text-profit" : "text-loss");
  
  const startEq = data.starting_equity || 100000;
  const pnlPct = ((pnl / startEq) * 100).toFixed(2);
  pnlPctEl.textContent = `${pnlPct >= 0 ? "+" : ""}${pnlPct}% Day Gain`;

  // Equity & Margin
  document.getElementById("hud-equity").textContent = formatINR(data.equity || startEq);
  document.getElementById("hud-margin").textContent = formatINR(data.available_margin || startEq);

  // Drawdown Gauge
  const ddPct = data.daily_drawdown_pct || 0;
  document.getElementById("hud-drawdown").textContent = `${ddPct.toFixed(2)}%`;
  const barFill = document.getElementById("drawdown-fill");
  // 3.0% is max, so fill relative to 3.0%
  const fillWidth = Math.min(100, (ddPct / 3.0) * 100);
  barFill.style.width = `${fillWidth}%`;

  // Trade Slots
  const tradesTaken = data.trades_taken_today || 0;
  const maxTrades = data.max_trades_allowed || 2;
  document.getElementById("hud-trades-counter").textContent = `${tradesTaken} of ${maxTrades} Trades Taken`;
  
  const slot1 = document.getElementById("slot-1");
  const slot2 = document.getElementById("slot-2");
  if (tradesTaken >= 1) slot1.classList.add("taken"); else slot1.classList.remove("taken");
  if (tradesTaken >= 2) slot2.classList.add("taken"); else slot2.classList.remove("taken");
}

function updateRadar(spots) {
  for (const [idx, info] of Object.entries(spots)) {
    const priceEl = document.getElementById(`spot-${idx}`);
    const vwapEl = document.getElementById(`vwap-${idx}`);
    const rangeEl = document.getElementById(`range-${idx}`);
    if (priceEl && info.spot > 0) priceEl.textContent = info.spot.toFixed(2);
    if (vwapEl && info.vwap > 0) vwapEl.textContent = `VWAP: ${info.vwap.toFixed(2)}`;
    if (rangeEl && info.pdh > 0) rangeEl.textContent = `PDH: ${info.pdh} | PDL: ${info.pdl}`;
  }
}

function updateTickData(tick) {
  const token = tick.token;
  // Update spot if matches
  if (token === "99926000") {
    const el = document.getElementById("spot-NIFTY");
    if (el) el.textContent = tick.ltp.toFixed(2);
  } else if (token === "99926009") {
    const el = document.getElementById("spot-BANKNIFTY");
    if (el) el.textContent = tick.ltp.toFixed(2);
  } else if (token === "99919000") {
    const el = document.getElementById("spot-SENSEX");
    if (el) el.textContent = tick.ltp.toFixed(2);
  }
}

function updateStrategyStatus(statusText) {
  document.getElementById("strategy-status-text").textContent = statusText;

  const s1 = document.getElementById("step-scan");
  const s2 = document.getElementById("step-sweep");
  const s3 = document.getElementById("step-fvg");
  const s4 = document.getElementById("step-trade");

  [s1, s2, s3, s4].forEach(s => s && s.classList.remove("active"));

  const lower = statusText.toLowerCase();
  if (lower.includes("in trade")) {
    s4 && s4.classList.add("active");
  } else if (lower.includes("fvg") || lower.includes("armed")) {
    s3 && s3.classList.add("active");
  } else if (lower.includes("sweep") || lower.includes("displacement")) {
    s2 && s2.classList.add("active");
  } else {
    s1 && s1.classList.add("active");
  }
}

function renderPositions(positions) {
  const tbody = document.getElementById("positions-body");
  if (!tbody) return;

  if (!positions || positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="9" style="text-align:center; color: var(--text-dim); padding: 2rem;">No active options positions. Waiting for Institutional Sweep setup.</td></tr>`;
    return;
  }

  tbody.innerHTML = positions.map(pos => {
    const pnlClass = pos.unrealized_pnl >= 0 ? "text-profit" : "text-loss";
    return `
      <tr>
        <td class="mono font-bold">${pos.symbol}</td>
        <td><span class="brand-badge">${pos.option_type}</span></td>
        <td>${pos.lots} lots (${pos.quantity})</td>
        <td class="mono">₹${pos.entry_price.toFixed(2)}</td>
        <td class="mono">₹${pos.current_ltp.toFixed(2)}</td>
        <td class="mono font-bold ${pnlClass}">${pos.unrealized_pnl >= 0 ? "+" : ""}${formatINR(pos.unrealized_pnl)} (${pos.unrealized_pnl_pct}%)</td>
        <td class="mono text-loss">₹${pos.stop_loss ? pos.stop_loss.toFixed(2) : "--"}</td>
        <td class="mono text-profit">₹${pos.target_1 ? pos.target_1.toFixed(2) : "--"}</td>
        <td>
          <button class="btn-exit-single" onclick="exitPosition('${pos.symbol}')">Liquidate</button>
        </td>
      </tr>
    `;
  }).join("");
}

function renderOrders(orders) {
  const tbody = document.getElementById("orders-body");
  if (!tbody) return;

  if (!orders || orders.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; color: var(--text-dim); padding: 1.5rem;">No recent orders.</td></tr>`;
    return;
  }

  tbody.innerHTML = orders.slice().reverse().slice(0, 10).map(ord => `
    <tr>
      <td class="mono text-dim">${ord.order_id}</td>
      <td class="mono font-bold">${ord.symbol}</td>
      <td><span class="${ord.transaction_type === 'BUY' ? 'text-profit' : 'text-loss'} font-bold">${ord.transaction_type}</span></td>
      <td>${ord.quantity} @ ₹${ord.price.toFixed(2)}</td>
      <td><span class="brand-badge">${ord.status}</span></td>
      <td class="text-dim mono">${ord.timestamp.slice(11, 19)}</td>
    </tr>
  `).join("");
}

function appendLog(level, message, timeStr) {
  const consoleBox = document.getElementById("console-logs");
  if (!consoleBox) return;

  const timestamp = timeStr || new Date().toTimeString().slice(0, 8);
  const div = document.createElement("div");
  div.className = "log-line mono";
  div.innerHTML = `
    <span class="log-time">[${timestamp}]</span>
    <span class="log-level-${level}">[${level}]</span>
    <span>${message}</span>
  `;
  consoleBox.appendChild(div);
  consoleBox.scrollTop = consoleBox.scrollHeight;
}

// Actions & Modals
function openModeModal() {
  const target = currentMode === "PAPER" ? "LIVE" : "PAPER";
  pendingMode = target;
  document.getElementById("target-mode-name").textContent = target;
  
  const warningText = document.getElementById("mode-warning-text");
  if (target === "LIVE") {
    warningText.textContent = "WARNING: You are about to switch to LIVE PRODUCTION MODE. Real capital will be routed to Angel One exchange matching engines!";
    warningText.style.color = "var(--neon-red)";
  } else {
    warningText.textContent = "Switching to Simulated PAPER Trading mode. Virtual ledger and simulated adverse slippage will be active.";
    warningText.style.color = "var(--neon-cyan)";
  }

  document.getElementById("mode-modal").classList.add("active");
}

function closeModeModal() {
  document.getElementById("mode-modal").classList.remove("active");
  pendingMode = null;
}

async function confirmModeChange() {
  if (!pendingMode) return;
  try {
    const res = await fetch("/api/mode", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: pendingMode })
    });
    const data = await res.json();
    if (data.status === "success") {
      setModeUI(data.mode);
      closeModeModal();
    }
  } catch (e) {
    alert("Error changing execution mode: " + e);
  }
}

function setModeUI(mode) {
  currentMode = mode;
  const btn = document.getElementById("mode-btn");
  if (!btn) return;

  if (mode === "LIVE") {
    btn.className = "mode-toggle-btn mode-live";
    btn.innerHTML = `<span class="pulse-dot" style="background:#ff1744; box-shadow: 0 0 10px #ff1744;"></span> LIVE TRADING [Angel One RMS]`;
  } else {
    btn.className = "mode-toggle-btn mode-paper";
    btn.innerHTML = `<span class="pulse-dot"></span> PAPER TRADING [Simulated]`;
  }
}

function openPanicModal() {
  document.getElementById("panic-modal").classList.add("active");
}

function closePanicModal() {
  document.getElementById("panic-modal").classList.remove("active");
}

async function confirmPanic() {
  try {
    await fetch("/api/panic", { method: "POST" });
    closePanicModal();
    document.getElementById("panic-indicator").style.display = "block";
  } catch (e) {
    alert("Failed to trigger panic: " + e);
  }
}

async function resetPanic() {
  try {
    await fetch("/api/reset_panic", { method: "POST" });
    document.getElementById("panic-indicator").style.display = "none";
  } catch (e) {
    alert("Failed to reset panic: " + e);
  }
}

async function exitPosition(symbol) {
  if (confirm(`Execute immediate surgical market square-off for ${symbol}?`)) {
    try {
      await fetch(`/api/exit_position/${symbol}`, { method: "POST" });
    } catch (e) {
      alert("Failed to exit position: " + e);
    }
  }
}

async function triggerTestSignal(underlying, signalType) {
  try {
    appendLog("INFO", `Manual sniper test triggered: ${underlying} ${signalType}...`);
    const res = await fetch("/api/test_signal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ underlying, signal_type: signalType })
    });
    const d = await res.json();
    console.log("Test signal sent:", d);
  } catch (e) {
    alert("Failed to trigger test signal: " + e);
  }
}

// Initial Boot
window.addEventListener("DOMContentLoaded", () => {
  connectWebSocket();
  fetchState();
});
