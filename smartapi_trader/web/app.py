import os
import json
import time
import secrets
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.state_manager import StateManager
from smartapi_trader.core.events import EventType, BaseEvent
from smartapi_trader.utils.logger import logger, add_log_listener, remove_log_listener

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
STATIC_DIR = os.path.join(BASE_DIR, "static")
REACT_DIST = os.path.abspath(os.path.join(BASE_DIR, "../../frontend/dist"))
REACT_ASSETS = os.path.join(REACT_DIST, "assets")

app = FastAPI(title="Angel One SmartAPI Options Sniper Control Plane", version="2.0.0")

# Enable CORS for React Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
os.makedirs(REACT_ASSETS, exist_ok=True)
app.mount("/assets", StaticFiles(directory=REACT_ASSETS), name="react_assets")

templates = Jinja2Templates(directory=TEMPLATES_DIR)

# Global references injected on startup
class WebContext:
    event_bus: Optional[EventBus] = None
    state_manager: Optional[StateManager] = None
    strategy: Optional[Any] = None
    execution_engine: Optional[Any] = None
    auth_manager: Optional[Any] = None
    orchestrator: Optional[Any] = None
    risk_manager: Optional[Any] = None
    notifier: Optional[Any] = None
    telegram_bot: Optional[Any] = None

ctx = WebContext()

# Active WebSocket connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Forward logs to WebSocket clients
def _on_log_entry(record: Dict[str, Any]):
    try:
        loop = asyncio.get_running_loop()
        if loop.is_running() and ws_manager.active_connections:
            loop.create_task(ws_manager.broadcast({
                "type": "LOG_ENTRY",
                "data": record
            }))
    except RuntimeError:
        pass

add_log_listener(_on_log_entry)

@app.on_event("startup")
async def startup_event():
    logger.info("[WEB] FastAPI Control Plane initialized.")

    # Forward event bus events to connected UI clients
    async def _forward_bus_events(event: BaseEvent):
        try:
            await ws_manager.broadcast({
                "type": event.event_type.value,
                "data": event.to_dict()
            })
        except Exception:
            pass

    if ctx.event_bus:
        ctx.event_bus.subscribe("*", _forward_bus_events)

@app.get("/", response_class=HTMLResponse)
async def serve_dashboard(request: Request):
    """Renders the React trading control plane (or fallback template)."""
    react_index = os.path.join(REACT_DIST, "index.html")
    if os.path.exists(react_index):
        return FileResponse(react_index)
    snapshot = ctx.state_manager.get_snapshot() if ctx.state_manager else {}
    return templates.TemplateResponse(request=request, name="index.html", context={"snapshot": snapshot})

# ==========================================
# 2FA TELEGRAM AUTHENTICATION & SESSIONS
# ==========================================
AUTH_TOKEN_COOKIE = "sniper_session_token"
valid_sessions: Dict[str, float] = {}  # token -> expires_at
otp_store: Dict[str, Any] = {
    "code": None,
    "expires_at": 0.0,
    "last_sent_at": 0.0,
    "attempts": 0,
}

def verify_authenticated_request(request: Request) -> bool:
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get(AUTH_TOKEN_COOKIE)
    if not token:
        return False
    exp = valid_sessions.get(token)
    if not exp or time.time() > exp:
        valid_sessions.pop(token, None)
        return False
    return True

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    # Allow non-API routes (frontend SPA, static assets, templates) and auth routes
    if not path.startswith("/api/") or path.startswith("/api/auth/"):
        return await call_next(request)
    
    if not verify_authenticated_request(request):
        return JSONResponse(
            status_code=401,
            content={"detail": "Authentication required. Please verify via Telegram OTP."}
        )
    return await call_next(request)

class VerifyOTPRequest(BaseModel):
    otp: str

@app.get("/api/auth/status")
async def auth_status(request: Request):
    """Checks whether the current user is authenticated."""
    is_auth = verify_authenticated_request(request)
    return {"authenticated": is_auth}

@app.post("/api/auth/send_otp")
async def send_login_otp(request: Request):
    """Generates a secure 6-digit OTP and delivers it via Telegram."""
    now = time.time()
    # Rate limit: 25 seconds cooldown between resends
    if now - otp_store.get("last_sent_at", 0) < 25:
        remaining = int(25 - (now - otp_store.get("last_sent_at", 0)))
        raise HTTPException(
            status_code=429,
            detail=f"Please wait {remaining} seconds before requesting a new code."
        )

    code = f"{secrets.randbelow(900000) + 100000}"
    otp_store["code"] = code
    otp_store["expires_at"] = now + 300  # 5 minutes
    otp_store["last_sent_at"] = now
    otp_store["attempts"] = 0

    client_ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")).split(",")[0].strip()
    time_str = datetime.now().strftime("%I:%M:%S %p")

    msg = (
        f"🔐 <b>Angel One Sniper Web Access</b>\n\n"
        f"Your One-Time Passcode (OTP):\n"
        f"👉 <code>{code}</code> 👈\n\n"
        f"⏱ Valid for: <b>5 minutes</b>\n"
        f"🌐 IP: <code>{client_ip}</code>\n"
        f"⏰ Time: <code>{time_str}</code>\n\n"
        f"<i>Enter this code in your browser to access the control plane.</i>"
    )

    notifier = ctx.notifier
    if not notifier:
        cfg_path = os.path.join(BASE_DIR, "../config/settings.yaml")
        if os.path.exists(cfg_path):
            import yaml
            with open(cfg_path, "r") as f:
                cfg = yaml.safe_load(f)
                from smartapi_trader.utils.telegram_notifier import TelegramNotifier
                notifier = TelegramNotifier(cfg.get("telegram", {}))

    if not notifier or not notifier.bot_token or not notifier.chat_id:
        raise HTTPException(
            status_code=500,
            detail="Telegram notifier is not configured. Please check telegram.bot_token and chat_id in settings.yaml."
        )

    ok, err = notifier.send_message_sync(msg)
    if not ok:
        logger.error(f"[AUTH] Failed to send Telegram OTP: {err}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to deliver code to Telegram: {err}"
        )

    cid = notifier.chat_id
    masked_cid = f"...{cid[-4:]}" if len(cid) > 4 else cid
    return {
        "status": "success",
        "message": f"Passcode sent to Telegram (Chat ID ending in {masked_cid})",
        "expires_in": 300,
        "cooldown": 25,
    }

@app.post("/api/auth/verify_otp")
async def verify_login_otp(req: VerifyOTPRequest, request: Request):
    """Validates the 6-digit OTP and issues a persistent session token."""
    now = time.time()
    if not otp_store.get("code") or now > otp_store.get("expires_at", 0):
        raise HTTPException(
            status_code=400,
            detail="Verification code has expired or was not requested. Please click 'Send Code' again."
        )

    if otp_store.get("attempts", 0) >= 5:
        otp_store["code"] = None
        raise HTTPException(
            status_code=400,
            detail="Too many incorrect attempts. Passcode invalidated. Please request a new code."
        )

    user_code = req.otp.strip()
    if user_code != otp_store.get("code"):
        otp_store["attempts"] = otp_store.get("attempts", 0) + 1
        rem = 5 - otp_store["attempts"]
        raise HTTPException(
            status_code=400,
            detail=f"Incorrect verification code. {rem} attempt(s) remaining."
        )

    # Valid! Issue session token
    token = secrets.token_urlsafe(32)
    valid_sessions[token] = now + (86400 * 30)  # 30 days validity
    otp_store["code"] = None  # Consume OTP

    client_ip = (request.headers.get("x-forwarded-for") or (request.client.host if request.client else "unknown")).split(",")[0].strip()
    logger.info(f"[AUTH] Successful operator login from IP {client_ip}.")

    response = JSONResponse(content={
        "status": "success",
        "message": "Authentication successful",
        "token": token
    })
    response.set_cookie(
        key=AUTH_TOKEN_COOKIE,
        value=token,
        max_age=86400 * 30,
        httponly=True,
        samesite="lax",
        path="/"
    )
    return response

@app.post("/api/auth/logout")
async def logout(request: Request):
    """Terminates session and clears credentials."""
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header[7:].strip()
    if not token:
        token = request.cookies.get(AUTH_TOKEN_COOKIE)
    if token:
        valid_sessions.pop(token, None)

    response = JSONResponse(content={"status": "success", "message": "Logged out successfully"})
    response.delete_cookie(key=AUTH_TOKEN_COOKIE, path="/")
    return response

@app.get("/api/state")
async def get_state():
    """Returns current system snapshot."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    return ctx.state_manager.get_snapshot()

class ModeRequest(BaseModel):
    mode: str # "PAPER" or "LIVE"

@app.post("/api/mode")
async def toggle_mode(req: ModeRequest):
    """Switches execution mode between PAPER and LIVE with safety validation."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    if req.mode not in ["PAPER", "LIVE"]:
        raise HTTPException(status_code=400, detail="Invalid mode. Must be 'PAPER' or 'LIVE'")
    
    min_cap = 50000.0
    if ctx.orchestrator and hasattr(ctx.orchestrator, "settings"):
        min_cap = float(ctx.orchestrator.settings.get("risk", {}).get("min_capital_required", 50000.0))

    if req.mode == "LIVE":
        if not ctx.auth_manager or not ctx.auth_manager.is_configured() or ctx.auth_manager.is_simulated:
            raise HTTPException(
                status_code=400,
                detail="Cannot switch to LIVE: Angel One SmartAPI credentials are not configured or invalid."
            )
        rms_res = ctx.auth_manager.fetch_rms_balance()
        if rms_res.get("status") and "data" in rms_res:
            ctx.state_manager.update_broker_rms(rms_res["data"])
        else:
            err = rms_res.get("message", "Unknown error")
            raise HTTPException(
                status_code=400,
                detail=f"Cannot switch to LIVE: Failed to verify RMS balance with Angel One ({err})."
            )

    success, msg = ctx.state_manager.set_execution_mode(req.mode, min_capital=min_cap)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    logger.warning(f"[OPERATOR] Execution mode toggled to {req.mode} via UI control plane.")
    await ws_manager.broadcast({
        "type": "MODE_CHANGED",
        "mode": req.mode
    })
    return {"status": "success", "mode": req.mode}

@app.post("/api/panic")
async def trigger_panic():
    """Global Emergency Panic Switch: cancels all orders, liquidates all positions, halts runner."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    
    ctx.state_manager.trigger_panic()
    # Trigger position liquidation
    for pos in list(ctx.state_manager.positions.values()):
        if pos.is_open:
            # Cancel resting exchange stop-loss order first
            if getattr(pos, "sl_order_id", "") and ctx.execution_engine:
                try:
                    await ctx.execution_engine.cancel_order(pos.sl_order_id, variety="STOPLOSS")
                except Exception as e:
                    logger.error(f"[PANIC] Error cancelling resting SL {pos.sl_order_id}: {e}")
                pos.sl_order_id = ""

            # Emit full exit order
            from smartapi_trader.core.events import OrderEvent
            exit_order = OrderEvent(
                order_id=f"PANIC_EXIT_{pos.symbol}",
                symbol=pos.symbol,
                token=pos.token,
                transaction_type="SELL",
                order_type="MARKET",
                quantity=pos.quantity,
                price=pos.current_ltp,
                status="PENDING"
            )
            await ctx.event_bus.publish(exit_order)
            pos.is_open = False
            ctx.state_manager.record_completed_trade(
                pnl=pos.unrealized_pnl,
                entry_price=pos.entry_price,
                exit_price=pos.current_ltp,
                quantity=pos.quantity,
                symbol=pos.symbol,
                is_paper=(ctx.state_manager.execution_mode == "PAPER"),
                strike_price=getattr(pos, 'strike_price', 0.0),
                option_type=getattr(pos, 'option_type', ''),
                exit_reason="Emergency Panic Liquidation"
            )

    logger.critical("[OPERATOR] GLOBAL PANIC SWITCH ACTIVATED! Liquidating all positions.")
    await ws_manager.broadcast({
        "type": "PANIC_TRIGGERED",
        "message": "Emergency liquidation and engine halt executed."
    })
    return {"status": "panic_activated"}

@app.post("/api/reset_panic")
async def reset_panic():
    """Resets panic state and re-arms strategy scanner."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    ctx.state_manager.reset_panic()
    await ws_manager.broadcast({
        "type": "PANIC_CLEARED",
        "message": "System operational. Scanner re-armed."
    })
    return {"status": "panic_cleared"}

@app.post("/api/exit_position/{symbol}")
async def exit_single_position(symbol: str):
    """Surgical manual override to close a specific open position."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    pos = ctx.state_manager.positions.get(symbol)
    if not pos or not pos.is_open:
        raise HTTPException(status_code=404, detail=f"No open position found for {symbol}")

    # Cancel resting exchange stop-loss order if active
    if getattr(pos, "sl_order_id", "") and ctx.execution_engine:
        try:
            await ctx.execution_engine.cancel_order(pos.sl_order_id, variety="STOPLOSS")
            logger.info(f"[OPERATOR] 🛡️ Cancelled resting Exchange Stop-Loss: {pos.sl_order_id}")
        except Exception as e:
            logger.error(f"[OPERATOR] Error cancelling resting SL {pos.sl_order_id}: {e}")
        pos.sl_order_id = ""

    from smartapi_trader.core.events import OrderEvent
    exit_order = OrderEvent(
        order_id=f"MANUAL_EXIT_{pos.symbol}",
        symbol=pos.symbol,
        token=pos.token,
        transaction_type="SELL",
        order_type="MARKET",
        quantity=pos.quantity,
        price=pos.current_ltp,
        status="PENDING"
    )
    await ctx.event_bus.publish(exit_order)
    pos.is_open = False
    ctx.state_manager.record_completed_trade(
        pnl=pos.unrealized_pnl,
        entry_price=pos.entry_price,
        exit_price=pos.current_ltp,
        quantity=pos.quantity,
        symbol=pos.symbol,
        is_paper=(ctx.state_manager.execution_mode == "PAPER"),
        strike_price=getattr(pos, 'strike_price', 0.0),
        option_type=getattr(pos, 'option_type', ''),
        exit_reason="Manual Surgical Exit"
    )
    logger.info(f"[OPERATOR] Surgical manual exit executed for position: {symbol}")
    return {"status": "success", "symbol": symbol}

@app.post("/api/positions/refresh_ltp")
async def refresh_positions_ltp():
    """Polls real exchange LTP for all active open positions and recalculates unrealized P&L."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    
    updated_count = 0
    for symbol, pos in list(ctx.state_manager.positions.items()):
        if not pos.is_open:
            continue
        ltp = None
        if ctx.auth_manager and not ctx.auth_manager.is_simulated and pos.token:
            exch = pos.exchange or ("BFO" if "SENSEX" in symbol else "NFO")
            ltp = await asyncio.to_thread(ctx.auth_manager.get_token_ltp, exch, symbol, str(pos.token))
        
        if ltp and ltp > 0:
            pos.current_ltp = float(ltp)
            diff = pos.current_ltp - pos.entry_price
            pos.unrealized_pnl = round(diff * pos.quantity, 2)
            pos.unrealized_pnl_pct = round((diff / pos.entry_price) * 100.0, 2) if pos.entry_price > 0 else 0.0
            updated_count += 1
    
    if updated_count > 0:
        ctx.state_manager._recalculate_portfolio()
        ctx.state_manager.broadcast_state()
    
    return {
        "status": "success",
        "updated": updated_count,
        "positions": [p.to_dict() for p in ctx.state_manager.positions.values() if p.is_open]
    }

class TestSignalRequest(BaseModel):
    underlying: str = "NIFTY"
    signal_type: str = "BUY_CE"

@app.post("/api/test_signal")
async def trigger_test_signal(req: TestSignalRequest):
    """Triggers an interactive sniper test signal for UI verification."""
    if ctx.strategy and hasattr(ctx.strategy, "trigger_test_signal"):
        await ctx.strategy.trigger_test_signal(req.underlying, req.signal_type)
        return {"status": "test_signal_dispatched", "underlying": req.underlying, "type": req.signal_type}
    raise HTTPException(status_code=500, detail="Strategy not available")

# =========================================================================
# Enhanced Broker Balance & Dual Agent Controls
# =========================================================================

@app.get("/api/broker/balance")
@app.post("/api/broker/refresh_balance")
async def get_or_refresh_broker_balance():
    """Fetches real-time RMS balance from Angel One SmartAPI."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")

    if ctx.auth_manager:
        rms_res = await asyncio.to_thread(ctx.auth_manager.fetch_rms_balance)
        if rms_res.get("status") and "data" in rms_res:
            ctx.state_manager.update_broker_rms(rms_res["data"])
            return {"status": "success", "data": ctx.state_manager.broker_rms}
    
    # Fallback to in-memory state
    return {"status": "success", "data": ctx.state_manager.broker_rms}

@app.post("/api/agent/paper/start")
async def start_paper_agent():
    """Starts the Paper Trading Agent with realistic adverse slippage simulation."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    ctx.state_manager.start_paper_agent()
    await ws_manager.broadcast({"type": "AGENT_STATE", "agent": "paper", "status": "RUNNING"})
    return {"status": "success", "paper_agent": "RUNNING"}

@app.post("/api/agent/paper/pause")
async def pause_paper_agent():
    """Pauses the Paper Trading Agent."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    ctx.state_manager.pause_paper_agent()
    await ws_manager.broadcast({"type": "AGENT_STATE", "agent": "paper", "status": "PAUSED"})
    return {"status": "success", "paper_agent": "PAUSED"}

class PaperCapitalRequest(BaseModel):
    capital: float

@app.post("/api/paper/capital")
async def update_paper_capital(req: PaperCapitalRequest):
    """Sets custom dummy capital for paper trading."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    if req.capital <= 0:
        raise HTTPException(status_code=400, detail="Capital must be greater than zero")
    ctx.state_manager.set_paper_capital(req.capital)
    try:
        import yaml
        config_path = os.path.join(BASE_DIR, "../config/settings.yaml")
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
        cfg.setdefault("execution", {})["paper_initial_capital"] = float(req.capital)
        with open(config_path, "w") as f:
            yaml.safe_dump(cfg, f, default_flow_style=False)
    except Exception as e:
        logger.error(f"[SETTINGS] Error saving paper_initial_capital to settings.yaml: {e}")

    await ws_manager.broadcast({"type": "SYSTEM_STATE", "data": ctx.state_manager.get_snapshot()})
    return {"status": "success", "capital": req.capital}

@app.post("/api/paper/reset_trades")
async def reset_paper_trades():
    """Removes all paper trades and resets the trade quota to 0."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    ctx.state_manager.reset_paper_trades()
    await ws_manager.broadcast({"type": "SYSTEM_STATE", "data": ctx.state_manager.get_snapshot()})
    logger.info("[OPERATOR] Paper trades ledger and trade quota reset to 0.")
    return {"status": "success", "message": "All paper trades removed and quota reset to 0"}

@app.delete("/api/paper/trade/{trade_id}")
async def delete_paper_trade(trade_id: str):
    """Removes a specific paper trade from the ledger and updates quota."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    ctx.state_manager.remove_paper_trade(trade_id)
    await ws_manager.broadcast({"type": "SYSTEM_STATE", "data": ctx.state_manager.get_snapshot()})
    logger.info(f"[OPERATOR] Paper trade {trade_id} removed.")
    return {"status": "success", "removed": trade_id}


@app.get("/api/paper/calendar")
async def get_paper_calendar(month: Optional[str] = None):
    """Returns aggregated daily PnL and trade lists for paper calendar display."""
    if hasattr(ctx, "trade_storage") and ctx.trade_storage:
        data = ctx.trade_storage.get_calendar_pnl(is_paper=True, month=month)
        return {"status": "success", **data}
    return {
        "status": "success",
        "month": month,
        "days": {},
        "summary": {
            "total_days_traded": 0, "winning_days": 0, "losing_days": 0,
            "scratch_days": 0, "win_rate_pct": 0.0, "total_trades": 0,
            "total_gross_pnl": 0.0, "total_charges": 0.0, "total_net_pnl": 0.0
        }
    }


@app.post("/api/agent/real/start")
async def start_real_agent():
    """Starts the Real Trading Agent routing to Angel One RMS exchange matching."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    
    # 1. Verify broker credentials & session
    if not ctx.auth_manager or not ctx.auth_manager.is_configured() or ctx.auth_manager.is_simulated:
        raise HTTPException(
            status_code=400,
            detail="Cannot start Real Trading Agent: Angel One SmartAPI credentials are not configured or invalid in Settings."
        )
    
    # 2. Refresh live RMS balance directly from Angel One
    rms_res = ctx.auth_manager.fetch_rms_balance()
    if rms_res.get("status") and "data" in rms_res:
        ctx.state_manager.update_broker_rms(rms_res["data"])
    else:
        err = rms_res.get("message", "Unknown RMS failure")
        raise HTTPException(
            status_code=400,
            detail=f"Cannot start Real Trading Agent: Failed to verify live RMS balance with Angel One ({err})."
        )

    # 3. Minimum required capital check
    min_cap = 50000.0
    if ctx.orchestrator and hasattr(ctx.orchestrator, "settings"):
        min_cap = float(ctx.orchestrator.settings.get("risk", {}).get("min_capital_required", 50000.0))

    success, msg = ctx.state_manager.start_real_agent(min_capital=min_cap)
    if not success:
        raise HTTPException(status_code=400, detail=msg)

    await ws_manager.broadcast({"type": "AGENT_STATE", "agent": "real", "status": "RUNNING"})
    return {"status": "success", "real_agent": "RUNNING", "message": msg}

@app.post("/api/agent/real/pause")
async def pause_real_agent():
    """Pauses the Real Trading Agent."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    ctx.state_manager.pause_real_agent()
    await ws_manager.broadcast({"type": "AGENT_STATE", "agent": "real", "status": "PAUSED"})
    return {"status": "success", "real_agent": "PAUSED"}

@app.get("/api/orders")
async def get_all_orders(include_paper: bool = False):
    """Returns active positions, recent orders, and trade history for Orders page."""
    if not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager not initialized")
    
    if include_paper:
        positions = [pos.to_dict() for pos in ctx.state_manager.positions.values() if pos.is_open and pos.quantity > 0]
        orders = [ord.to_dict() for ord in ctx.state_manager.orders.values()]
        trade_history = ctx.state_manager.trade_history
    else:
        # Strictly Live Angel One broker orders & trades
        positions = [
            pos.to_dict() for pos in ctx.state_manager.positions.values() 
            if pos.is_open and pos.quantity > 0 and not getattr(pos, 'is_paper', False) and getattr(pos, 'execution_mode', '') == 'LIVE'
        ]
        
        # Exclude paper simulated order prefixes and orders flagged as paper
        paper_prefixes = ("ORD_NIFTY_", "ORD_BANKNIFTY_", "ORD_SENSEX_", "ORD_EXIT_PARTIAL_", "ORD_SL_", "MANUAL_EXIT_")
        orders = [
            ord.to_dict() for ord in ctx.state_manager.orders.values()
            if not getattr(ord, 'is_paper', False) and not any(ord.order_id.startswith(p) for p in paper_prefixes)
        ]
        
        # Trade history: strictly real broker completed trades
        trade_history = [t for t in ctx.state_manager.trade_history if not t.get('is_paper')]

    return {
        "positions": positions,
        "orders": orders,
        "trade_history": trade_history,
        "realized_pnl": ctx.state_manager.realized_pnl,
        "unrealized_pnl": ctx.state_manager.unrealized_pnl
    }

@app.get("/api/trades/history")
async def get_trades_history(limit: int = 100, is_paper: Optional[bool] = None):
    """Returns persistent historical trades from SQLite storage."""
    if hasattr(ctx, "trade_storage") and ctx.trade_storage:
        return {
            "status": "success",
            "trades": ctx.trade_storage.load_all_trades(limit=limit, is_paper=is_paper)
        }
    if ctx.state_manager:
        trades = ctx.state_manager.trade_history
        if is_paper is not None:
            trades = [t for t in trades if t.get("is_paper") == is_paper]
        return {"status": "success", "trades": trades[:limit]}
    return {"status": "success", "trades": []}

class SettingsUpdateRequest(BaseModel):
    api_key: Optional[str] = None
    client_code: Optional[str] = None
    pin: Optional[str] = None
    totp_secret: Optional[str] = None
    risk_per_trade_pct: Optional[float] = None
    max_daily_drawdown_pct: Optional[float] = None
    max_trades_per_day: Optional[int] = None
    paper_initial_capital: Optional[float] = None
    telegram_enabled: Optional[bool] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    telegram_eod_time: Optional[str] = None
    enable_ilsme_sweep: Optional[bool] = None
    enable_momentum_breakout: Optional[bool] = None

@app.get("/api/settings")
async def get_settings():
    """Fetches current settings with masked credentials."""
    import yaml
    config_path = os.path.join(BASE_DIR, "../config/settings.yaml")
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)
        
        # Mask sensitive keys for safety
        b = cfg.get("broker", {})
        api_k = b.get("api_key", "")
        masked_api = f"{api_k[:4]}****{api_k[-4:]}" if len(api_k) > 8 else ("configured" if api_k and api_k != "YOUR_SMARTAPI_API_KEY" else "")
        
        return {
            "broker": {
                "client_code": b.get("client_code", ""),
                "api_key_masked": masked_api,
                "has_totp": bool(b.get("totp_secret") and b.get("totp_secret") != "YOUR_BASE32_TOTP_SECRET"),
                "is_configured": ctx.auth_manager.is_configured() if ctx.auth_manager else False
            },
            "telegram": cfg.get("telegram", {}),
            "risk": cfg.get("risk", {}),
            "execution": cfg.get("execution", {}),
            "strategy": cfg.get("strategy", {})
        }
    except Exception as e:
        logger.error(f"[SETTINGS] Error loading settings: {e}")
        return {}

@app.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest):
    """Updates settings.yaml and optionally re-authenticates broker session if credentials changed."""
    import yaml
    config_path = os.path.join(BASE_DIR, "../config/settings.yaml")
    try:
        with open(config_path, "r") as f:
            cfg = yaml.safe_load(f)

        old_broker = cfg.get("broker", {})
        credentials_changed = False

        if req.api_key and req.api_key.strip() and req.api_key.strip() != old_broker.get("api_key"):
            cfg.setdefault("broker", {})["api_key"] = req.api_key.strip()
            credentials_changed = True
        if req.client_code and req.client_code.strip() and req.client_code.strip() != old_broker.get("client_code"):
            cfg.setdefault("broker", {})["client_code"] = req.client_code.strip()
            credentials_changed = True
        if req.pin and req.pin.strip() and req.pin.strip() != old_broker.get("pin"):
            cfg.setdefault("broker", {})["pin"] = req.pin.strip()
            credentials_changed = True
        if req.totp_secret and req.totp_secret.strip() and req.totp_secret.strip() != old_broker.get("totp_secret"):
            cfg.setdefault("broker", {})["totp_secret"] = req.totp_secret.strip()
            credentials_changed = True

        if req.risk_per_trade_pct is not None:
            new_risk = float(req.risk_per_trade_pct)
            cfg.setdefault("risk", {})["risk_per_trade_pct"] = new_risk
            rm = ctx.risk_manager or getattr(ctx.orchestrator, "risk_manager", None)
            if rm: rm.risk_per_trade = new_risk

        if req.max_daily_drawdown_pct is not None:
            new_dd = float(req.max_daily_drawdown_pct)
            cfg.setdefault("risk", {})["max_daily_drawdown_pct"] = new_dd
            rm = ctx.risk_manager or getattr(ctx.orchestrator, "risk_manager", None)
            if rm: rm.max_drawdown_pct = new_dd

        if req.max_trades_per_day is not None:
            new_max = int(req.max_trades_per_day)
            cfg.setdefault("risk", {})["max_trades_per_day"] = new_max
            if ctx.state_manager:
                ctx.state_manager.max_trades_allowed = new_max
            rm = ctx.risk_manager or getattr(ctx.orchestrator, "risk_manager", None)
            if rm: rm.max_trades = new_max

        if req.paper_initial_capital is not None: cfg.setdefault("execution", {})["paper_initial_capital"] = req.paper_initial_capital

        if req.telegram_enabled is not None: cfg.setdefault("telegram", {})["enabled"] = req.telegram_enabled
        if req.telegram_bot_token: cfg.setdefault("telegram", {})["bot_token"] = req.telegram_bot_token.strip()
        if req.telegram_chat_id: cfg.setdefault("telegram", {})["chat_id"] = req.telegram_chat_id.strip()
        if req.telegram_eod_time: cfg.setdefault("telegram", {})["eod_report_time"] = req.telegram_eod_time.strip()

        if req.enable_ilsme_sweep is not None:
            cfg.setdefault("strategy", {})["enable_ilsme_sweep"] = req.enable_ilsme_sweep
            if ctx.strategy and hasattr(ctx.strategy, "cfg"):
                ctx.strategy.cfg["enable_ilsme_sweep"] = req.enable_ilsme_sweep

        if req.enable_momentum_breakout is not None:
            cfg.setdefault("strategy", {})["enable_momentum_breakout"] = req.enable_momentum_breakout
            if ctx.strategy and hasattr(ctx.strategy, "cfg"):
                ctx.strategy.cfg["enable_momentum_breakout"] = req.enable_momentum_breakout

        with open(config_path, "w") as f:
            yaml.safe_dump(cfg, f, default_flow_style=False)

        if ctx.notifier:
            ctx.notifier.update_config(cfg.get("telegram", {}))

        # Real-time state push to WebSockets and UI
        if ctx.state_manager:
            ctx.state_manager.broadcast_state()
            if ws_manager.active_connections:
                await ws_manager.broadcast({
                    "type": "STATE_UPDATE",
                    "data": ctx.state_manager.get_snapshot()
                })

        auth_warning = None
        # Only re-initialize session if credentials actually changed
        if ctx.auth_manager and credentials_changed:
            b = cfg.get("broker", {})
            ctx.auth_manager.api_key = b.get("api_key", "")
            ctx.auth_manager.client_code = b.get("client_code", "")
            ctx.auth_manager.pin = b.get("pin", "")
            ctx.auth_manager.totp_secret = b.get("totp_secret", "")
            
            try:
                smart_api, jwt, feed = await asyncio.to_thread(ctx.auth_manager.initialize_session)
                if ctx.execution_engine and hasattr(ctx.execution_engine, "update_jwt_token"):
                    ctx.execution_engine.update_jwt_token(jwt)
                
                # Fetch live RMS
                rms = await asyncio.to_thread(ctx.auth_manager.fetch_rms_balance)
                if rms.get("status") and "data" in rms and ctx.state_manager:
                    ctx.state_manager.update_broker_rms(rms["data"])
            except Exception as auth_err:
                logger.warning(f"[SETTINGS] Broker authentication warning: {auth_err}")
                auth_warning = f"Settings saved, but broker authentication failed: {auth_err}"

        logger.info("[SETTINGS] Successfully updated and saved settings.yaml")
        if auth_warning:
            return {"status": "warning", "message": auth_warning}
        return {"status": "success", "message": "Settings updated and saved successfully"}
    except Exception as e:
        logger.error(f"[SETTINGS] Failed to save settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class BacktestRunRequest(BaseModel):
    capital: Optional[float] = 50000.0
    risk_pct: Optional[float] = 0.03
    sl_pct: Optional[float] = 0.10
    dynamic_compounding: Optional[bool] = True
    start_date: Optional[str] = None
    end_date: Optional[str] = None

@app.get("/api/backtest/results")
async def get_backtest_results():
    """Returns cached backtest performance and trade-by-trade ledger."""
    results_path = "data/backtest_results.json"
    if os.path.exists(results_path):
        try:
            with open(results_path) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"[BACKTEST] Error reading cache: {e}")
    
    from smartapi_trader.strategy.backtest_engine import BacktestEngine
    engine = BacktestEngine(starting_capital=50000.0, dynamic_compounding=True)
    results = engine.run()
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    return results

@app.post("/api/backtest/run")
async def run_backtest_endpoint(req: BacktestRunRequest):
    """Executes a backtest simulation with user parameters."""
    try:
        from smartapi_trader.strategy.backtest_engine import BacktestEngine
        engine = BacktestEngine(
            starting_capital=req.capital or 50000.0,
            risk_per_trade_pct=req.risk_pct or 0.03,
            initial_sl_pct=req.sl_pct or 0.10,
            dynamic_compounding=req.dynamic_compounding if req.dynamic_compounding is not None else True,
            start_date=req.start_date,
            end_date=req.end_date
        )
        results = engine.run()
        results_path = "data/backtest_results.json"
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        return {"status": "success", "results": results}
    except Exception as e:
        logger.error(f"[BACKTEST] Run failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================================
# Telegram Integration Endpoints
# =========================================================================

@app.get("/api/telegram/status")
async def get_telegram_status():
    """Returns Telegram configuration and bot daemon status."""
    if not ctx.notifier:
        return {"enabled": False, "status": "Not initialized"}
    is_bot_running = ctx.telegram_bot.is_running() if ctx.telegram_bot else False
    return {
        "status": "success",
        "enabled": ctx.notifier.enabled,
        "chat_id": ctx.notifier.chat_id,
        "bot_active": is_bot_running,
        "target_chat": "Configured (@Trade_info_for_you_bot)"
    }

@app.post("/api/telegram/test")
async def send_telegram_test():
    """Sends a live test notification to verify Telegram Bot connectivity."""
    if not ctx.notifier:
        raise HTTPException(status_code=503, detail="Telegram notifier not initialized")
    now_str = datetime.now().strftime("%H:%M:%S")
    test_msg = (
        f"🔔 <b>TELEGRAM NOTIFICATION TEST SUCCESSFUL</b>\n\n"
        f"🚀 <b>Service:</b> Angel One Options Sniper Engine\n"
        f"🤖 <b>Bot:</b> Active & Listening for Commands\n"
        f"💬 <b>Chat ID:</b> <code>{ctx.notifier.chat_id}</code>\n"
        f"⏱ <b>Timestamp:</b> {now_str} IST\n\n"
        f"<i>Ready to send real-time trade alerts and automated 15:15 EOD summaries.</i>"
    )
    success, detail = ctx.notifier.send_message_sync(test_msg)
    if success:
        return {"status": "success", "message": "Test notification sent successfully to Telegram."}
    else:
        raise HTTPException(status_code=500, detail=f"Telegram API delivery failed: {detail}")

@app.post("/api/telegram/send_eod")
async def send_telegram_eod():
    """Immediately compiles and delivers the End of Day (EOD) Performance Report to Telegram."""
    if not ctx.notifier or not ctx.state_manager:
        raise HTTPException(status_code=503, detail="State manager or notifier not initialized")
    
    success, detail = ctx.notifier.notify_eod_summary(ctx.state_manager)
    if success:
        return {"status": "success", "message": "End of Day (EOD) performance report dispatched to Telegram."}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to dispatch EOD report: {detail}")

@app.websocket("/ws/telemetry")
async def websocket_telemetry_endpoint(websocket: WebSocket):
    """High-frequency WebSocket channel streaming live telemetry and tick updates to UI."""
    token = websocket.query_params.get("token") or websocket.cookies.get(AUTH_TOKEN_COOKIE)
    if not token or token not in valid_sessions or time.time() > valid_sessions[token]:
        await websocket.close(code=4401)
        return

    await ws_manager.connect(websocket)
    try:
        # Send initial full snapshot on connection
        if ctx.state_manager:
            await websocket.send_json({
                "type": "INITIAL_STATE",
                "data": ctx.state_manager.get_snapshot()
            })
        
        # Keepalive loop
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
    except Exception:
        ws_manager.disconnect(websocket)

# SPA Client-Side Routing Fallback
@app.get("/{full_path:path}")
async def serve_spa_fallback(full_path: str, request: Request):
    """Fallback route serving React SPA for client-side routing, or static assets from dist."""
    target_file = os.path.join(REACT_DIST, full_path)
    if os.path.isfile(target_file):
        return FileResponse(target_file)
    
    react_index = os.path.join(REACT_DIST, "index.html")
    if os.path.exists(react_index):
        return FileResponse(react_index)
    snapshot = ctx.state_manager.get_snapshot() if ctx.state_manager else {}
    return templates.TemplateResponse(request=request, name="index.html", context={"snapshot": snapshot})
