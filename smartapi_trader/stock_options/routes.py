"""
FastAPI REST & Control API Endpoints for AI-Powered Stock Options.
Exposes endpoints for Overnight Planner, Intraday Scanner,
Live Trading Agent, and Paper Trading Agent.
"""

from datetime import datetime
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from typing import Dict, Any, List, Optional
from smartapi_trader.utils.logger import logger

router = APIRouter(prefix="/api/stock-options", tags=["stock-options"])

# References injected during initialization
class StockOptionsContext:
    ai_service: Optional[Any] = None
    market_data: Optional[Any] = None
    storage: Optional[Any] = None
    planner: Optional[Any] = None
    scanner: Optional[Any] = None
    live_agent: Optional[Any] = None
    paper_agent: Optional[Any] = None
    universe_mgr: Optional[Any] = None

so_ctx = StockOptionsContext()

def ensure_stock_options_initialized():
    """Initializes standalone components if not already injected by orchestrator."""
    if so_ctx.storage is None:
        from smartapi_trader.stock_options.storage import StockOptionsStorage
        so_ctx.storage = StockOptionsStorage()
    if so_ctx.universe_mgr is None:
        from smartapi_trader.stock_options.universe import StockUniverseManager
        so_ctx.universe_mgr = StockUniverseManager()
    if so_ctx.market_data is None:
        from smartapi_trader.stock_options.market_data_service import StockMarketDataService
        so_ctx.market_data = StockMarketDataService(so_ctx.universe_mgr)
    if so_ctx.ai_service is None:
        from smartapi_trader.ai.ai_service import AIService
        ai_cfg = {}
        if so_ctx.storage:
            saved_prov = so_ctx.storage.get_setting("ai_provider")
            saved_model = so_ctx.storage.get_setting("ai_model")
            saved_oai = so_ctx.storage.get_setting("openai_api_key")
            saved_gem = so_ctx.storage.get_setting("gemini_api_key")
            if saved_prov:
                ai_cfg["provider"] = saved_prov
            if saved_model:
                ai_cfg["model"] = saved_model
            if saved_oai:
                ai_cfg["openai_api_key"] = saved_oai
            if saved_gem:
                ai_cfg["gemini_api_key"] = saved_gem
        so_ctx.ai_service = AIService(ai_cfg)

    if so_ctx.planner is None:
        from smartapi_trader.stock_options.planner import OvernightAIPlanner
        so_ctx.planner = OvernightAIPlanner(so_ctx.ai_service, so_ctx.market_data, so_ctx.storage)
    if so_ctx.scanner is None:
        from smartapi_trader.stock_options.scanner import IntradayAIScanner
        so_ctx.scanner = IntradayAIScanner(so_ctx.ai_service, so_ctx.market_data, so_ctx.storage)
    if so_ctx.paper_agent is None:
        from smartapi_trader.stock_options.paper_agent import StockOptionsPaperAgent
        from smartapi_trader.stock_options.validator import StockOptionsValidator
        so_ctx.paper_agent = StockOptionsPaperAgent(so_ctx.storage, StockOptionsValidator(so_ctx.universe_mgr))

    bind_dispatch_callbacks()


async def auto_dispatch_candidates(candidates: List[Dict[str, Any]], plan_or_scan_id: str):
    """
    Autonomous Trading Pipeline:
    When the AI generates or discovers qualified candidates:
    1. If Paper Agent is RUNNING, automatically opens simulated positions without manual clicking.
    2. If Live Agent is RUNNING and auto_execute is True, validates against RMS and executes live orders.
    """
    logger.info(f"[AUTO_BOT] 🤖 Autonomous pipeline evaluating {len(candidates)} candidates from {plan_or_scan_id}...")
    for cand in candidates:
        sym = str(cand.get("symbol", "")).upper().strip()
        if not sym or sym in ("ALL_FO", "ALL", "AUTO_DISCOVER"):
            continue

        dispatched_targets = []

        # 1. Paper Agent Auto-Execution
        if so_ctx.paper_agent and so_ctx.paper_agent.status == "RUNNING":
            try:
                res = await so_ctx.paper_agent.execute_simulated_trade(cand, plan_id=plan_or_scan_id)
                if res.get("status") == "success":
                    dispatched_targets.append("PAPER")
                    logger.info(f"[AUTO_BOT] ✅ Simulated trade executed for {sym} in virtual ledger.")
                else:
                    logger.info(f"[AUTO_BOT] Paper trade for {sym} status: {res.get('reason') or res.get('message')}")
            except Exception as e:
                logger.error(f"[AUTO_BOT] Error in paper auto-execution for {sym}: {e}")

        # 2. Live Agent Auto-Execution
        if so_ctx.live_agent and so_ctx.live_agent.status == "RUNNING" and getattr(so_ctx.live_agent, "auto_execute", False):
            try:
                res = await so_ctx.live_agent.execute_approved_candidate(cand, plan_id=plan_or_scan_id)
                if res.get("status") == "success":
                    dispatched_targets.append("LIVE")
                    logger.info(f"[AUTO_BOT] 🚀 Real trade dispatched to Angel One for {sym}.")
                else:
                    logger.info(f"[AUTO_BOT] Live trade for {sym} status: {res.get('reason') or res.get('message')}")
            except Exception as e:
                logger.error(f"[AUTO_BOT] Error in live auto-execution for {sym}: {e}")

        # Update persistent candidate status in SQLite
        if dispatched_targets and so_ctx.storage:
            target_status = "AUTO_DISPATCHED_" + "_".join(dispatched_targets)
            try:
                so_ctx.storage.update_plan_status(plan_or_scan_id, target_status, sym)
            except Exception:
                pass


def bind_dispatch_callbacks():
    if so_ctx.planner:
        so_ctx.planner.dispatch_callback = auto_dispatch_candidates
    if so_ctx.scanner:
        so_ctx.scanner.dispatch_callback = auto_dispatch_candidates


ensure_stock_options_initialized()



# Request Models
class AIConfigRequest(BaseModel):
    provider: str
    model: Optional[str] = None
    openai_key: Optional[str] = None
    gemini_key: Optional[str] = None

class PlannerRunRequest(BaseModel):
    stock_universe: Optional[List[str]] = None
    max_candidates: int = Field(default=3, ge=1, le=3)
    provider: Optional[str] = None
    model: Optional[str] = None

class PlanApprovalRequest(BaseModel):
    plan_id: str
    status: str  # "APPROVED" or "REJECTED"
    candidate_symbol: Optional[str] = None

class ScannerConfigRequest(BaseModel):
    interval_mins: int = Field(default=5)
    max_candidates: int = Field(default=3, ge=1, le=3)
    session_start: Optional[str] = "09:00"
    session_end: Optional[str] = "15:00"
    stock_universe: Optional[List[str]] = None

class ScannerRunRequest(BaseModel):
    provider: Optional[str] = None
    model: Optional[str] = None
    stock_universe: Optional[List[str]] = None
    max_candidates: Optional[int] = None

class PaperConfigRequest(BaseModel):
    virtual_capital: Optional[float] = None
    slippage_pct: Optional[float] = None
    risk_per_trade_pct: Optional[float] = None

class CandidateExecuteRequest(BaseModel):
    candidate: Dict[str, Any]
    plan_id: Optional[str] = ""

class ClosePositionRequest(BaseModel):
    symbol: str
    exit_price: float
    reason: Optional[str] = "Manual Exit"


# ---------------- AI Provider Endpoints ---------------- #

@router.get("/ai/config")
async def get_ai_config():
    if not so_ctx.ai_service:
        raise HTTPException(status_code=503, detail="AI Service not initialized.")
    return so_ctx.ai_service.get_masked_config()

@router.post("/ai/config")
async def save_ai_config(req: AIConfigRequest):
    if not so_ctx.ai_service:
        raise HTTPException(status_code=503, detail="AI Service not initialized.")
    so_ctx.ai_service.update_credentials(
        provider=req.provider,
        model=req.model,
        openai_key=req.openai_key,
        gemini_key=req.gemini_key
    )
    # Persist in storage
    if so_ctx.storage:
        so_ctx.storage.save_setting("ai_provider", req.provider)
        if req.model:
            so_ctx.storage.save_setting("ai_model", req.model)
        if req.openai_key:
            so_ctx.storage.save_setting("openai_api_key", req.openai_key)
        if req.gemini_key:
            so_ctx.storage.save_setting("gemini_api_key", req.gemini_key)
    return {"status": "success", "message": f"AI provider updated to {req.provider}."}

@router.post("/ai/test")
async def test_ai_connection():
    if not so_ctx.ai_service or not so_ctx.market_data:
        raise HTTPException(status_code=503, detail="AI Service or Market Data not initialized.")
    if not so_ctx.ai_service.is_configured:
        return {
            "status": "not_configured",
            "message": "AI is not connected. API key is not configured.",
            "candidates_returned": 0,
            "latency_ms": 0.0,
            "validation_warnings": ["AI provider is not configured. Connect your API key to test live market analysis."],
            "market_summary": "AI Provider is not configured."
        }
    # Run test analysis on 2 stocks
    shortlist = so_ctx.market_data.rank_and_shortlist_stocks(candidate_symbols=["RELIANCE", "TCS"], max_shortlist=2)
    res = await so_ctx.ai_service.analyze(
        run_type="INTRADAY_SCAN",
        intended_date="2026-10-30",
        stock_data=shortlist,
        market_context={"test": True},
        max_candidates=2
    )
    return {
        "status": "success",
        "provider": res.provider,
        "model": res.model,
        "latency_ms": res.latency_ms,
        "candidates_returned": len(res.candidates),
        "validation_warnings": res.validation_warnings,
        "market_summary": res.market_summary
    }


# ---------------- Overnight Planner Endpoints ---------------- #

@router.get("/planner/latest")
async def get_latest_overnight_plan():
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    if so_ctx.ai_service and not so_ctx.ai_service.is_configured:
        return {
            "status": "not_configured",
            "message": "AI Research Provider is not connected. Connect your API key to generate trade setups.",
            "candidates": [],
            "market_summary": "AI is not connected. API key is required to discover and analyze F&O setups.",
            "no_trade_reason": "AI is not connected. API key is missing or not configured. No dummy setups are shown."
        }
    plan = so_ctx.storage.get_latest_overnight_plan()
    return plan or {"status": "none", "message": "No overnight plans generated yet."}

@router.get("/planner/history")
async def get_overnight_plan_history(limit: int = 15):
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    return so_ctx.storage.get_all_overnight_plans(limit=limit)

@router.post("/planner/run")
async def run_overnight_planner(req: PlannerRunRequest):
    if not so_ctx.planner:
        raise HTTPException(status_code=503, detail="Planner not initialized.")
    if so_ctx.ai_service and not so_ctx.ai_service.is_configured:
        return {
            "status": "not_configured",
            "message": "AI is not connected. Please enter a valid OpenAI or Google Gemini API key to run market scanning.",
            "candidates": []
        }
    res = await so_ctx.planner.execute_plan(
        stock_universe=req.stock_universe,
        max_candidates=req.max_candidates,
        force_manual=True,
        ai_provider=req.provider,
        ai_model=req.model
    )
    return res

@router.post("/planner/approve")
async def approve_overnight_plan(req: PlanApprovalRequest):
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    so_ctx.storage.update_plan_status(
        plan_id=req.plan_id,
        new_status=req.status,
        candidate_symbol=req.candidate_symbol
    )
    return {"status": "success", "message": f"Updated status to {req.status} for plan {req.plan_id}."}


# ---------------- Intraday Scanner Endpoints ---------------- #

@router.get("/scanner/status")
async def get_scanner_status():
    if not so_ctx.scanner:
        raise HTTPException(status_code=503, detail="Scanner not initialized.")
    session_state = so_ctx.storage.get_setting("scanner_session_state") if so_ctx.storage else {}
    if not isinstance(session_state, dict):
        session_state = {}
    return {
        "is_active": so_ctx.scanner.is_active,
        "is_scanning": so_ctx.scanner.is_scanning,
        "interval_mins": so_ctx.scanner.interval_mins,
        "max_candidates": so_ctx.scanner.max_candidates,
        "session_start": so_ctx.scanner.session_start.strftime("%H:%M"),
        "session_end": so_ctx.scanner.session_end.strftime("%H:%M"),
        "selected_universe": so_ctx.scanner.selected_universe,
        "last_scan_time": so_ctx.scanner._last_scan_time,
        "session": session_state,
        "session_id": session_state.get("session_id"),
        "session_date": session_state.get("session_date"),
        "scans_count": session_state.get("scans_count", 0),
        "traded_symbols": session_state.get("traded_symbols", []),
        "last_scan_at": session_state.get("last_scan_at")
    }

@router.post("/scanner/start")
async def start_scanner():
    if not so_ctx.scanner:
        raise HTTPException(status_code=503, detail="Scanner not initialized.")
    if so_ctx.ai_service and not so_ctx.ai_service.is_configured:
        raise HTTPException(
            status_code=400,
            detail="Cannot start AI Radar: AI Provider API key is not connected. Please enter your API key first."
        )
    await so_ctx.scanner.start()
    return {"status": "success", "message": "Intraday AI Scanner started."}

@router.post("/scanner/stop")
async def stop_scanner():
    if not so_ctx.scanner:
        raise HTTPException(status_code=503, detail="Scanner not initialized.")
    await so_ctx.scanner.stop()
    return {"status": "success", "message": "Intraday AI Scanner stopped."}

@router.post("/scanner/config")
async def update_scanner_config(req: ScannerConfigRequest):
    if not so_ctx.scanner:
        raise HTTPException(status_code=503, detail="Scanner not initialized.")
    so_ctx.scanner.configure(
        interval_mins=req.interval_mins,
        max_candidates=req.max_candidates,
        session_start_str=req.session_start,
        session_end_str=req.session_end,
        stock_universe=req.stock_universe
    )
    return {
        "status": "success",
        "message": "Scanner configuration updated.",
        "interval_mins": so_ctx.scanner.interval_mins,
        "max_candidates": so_ctx.scanner.max_candidates,
        "selected_universe": so_ctx.scanner.selected_universe,
    }

@router.post("/scanner/run")
async def trigger_manual_scan(req: Optional[ScannerRunRequest] = None):
    if not so_ctx.scanner:
        raise HTTPException(status_code=503, detail="Scanner not initialized.")

    target_provider = (req.provider if req and req.provider else (so_ctx.ai_service.active_provider_name if so_ctx.ai_service else "GEMINI")).upper()
    target_model = req.model if req and req.model else (so_ctx.ai_service.active_model if so_ctx.ai_service else None)

    if so_ctx.ai_service:
        so_ctx.ai_service.active_provider_name = target_provider
        if target_model:
            so_ctx.ai_service.active_model = target_model
        if not so_ctx.ai_service.is_provider_configured(target_provider):
            return {
                "status": "not_configured",
                "message": f"AI provider {target_provider} is not connected. Please enter your API key to run market scanning.",
                "candidates": []
            }

    return await so_ctx.scanner.execute_scan(
        is_manual=True,
        ai_provider=target_provider,
        ai_model=target_model
    )

@router.get("/scanner/latest")
async def get_latest_scan():
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    if so_ctx.ai_service and not so_ctx.ai_service.is_configured:
        return {
            "status": "not_configured",
            "message": "AI Research Provider is not connected. Connect your API key to scan live market.",
            "candidates": [],
            "market_summary": "AI is not connected. API key is required to discover and analyze F&O setups.",
            "no_trade_reason": "AI is not connected. API key is missing or not configured. No dummy setups are shown."
        }
    scan = so_ctx.storage.get_latest_intraday_scan()
    return scan or {"status": "none", "message": "No scans recorded yet."}

@router.get("/scanner/history")
async def get_scan_history(limit: int = 15):
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    return so_ctx.storage.get_recent_intraday_scans(limit=limit)


# ---------------- Live Agent Endpoints ---------------- #

@router.get("/live/status")
async def get_live_agent_status():
    if not so_ctx.live_agent:
        raise HTTPException(status_code=503, detail="Live Agent not initialized.")
    positions = so_ctx.storage.get_positions(is_paper=False, open_only=True)
    orders = so_ctx.storage.get_orders(is_paper=False, limit=10)
    unrealized = sum(float(p.get("unrealized_pnl", 0.0)) for p in positions)
    realized = sum(float(p.get("realized_pnl", 0.0)) for p in positions)

    return {
        "status": so_ctx.live_agent.status,
        "auto_execute": so_ctx.live_agent.auto_execute,
        "open_positions_count": len(positions),
        "unrealized_pnl": round(unrealized, 2),
        "realized_pnl": round(realized, 2),
        "recent_orders_count": len(orders)
    }

@router.post("/live/start")
async def start_live_agent():
    if not so_ctx.live_agent:
        raise HTTPException(status_code=503, detail="Live Agent not initialized.")
    so_ctx.live_agent.start()
    return {"status": "success", "agent_status": so_ctx.live_agent.status}

@router.post("/live/pause")
async def pause_live_agent():
    if not so_ctx.live_agent:
        raise HTTPException(status_code=503, detail="Live Agent not initialized.")
    so_ctx.live_agent.pause()
    return {"status": "success", "agent_status": so_ctx.live_agent.status}

@router.post("/live/stop")
async def stop_live_agent():
    if not so_ctx.live_agent:
        raise HTTPException(status_code=503, detail="Live Agent not initialized.")
    so_ctx.live_agent.stop()
    return {"status": "success", "agent_status": so_ctx.live_agent.status}

@router.post("/live/auto-execute")
async def toggle_live_auto_execute(enabled: bool):
    if not so_ctx.live_agent:
        raise HTTPException(status_code=503, detail="Live Agent not initialized.")
    so_ctx.live_agent.set_auto_execute(enabled)
    return {"status": "success", "auto_execute": so_ctx.live_agent.auto_execute}

@router.get("/live/positions")
async def get_live_positions():
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    return so_ctx.storage.get_positions(is_paper=False, open_only=True)

@router.get("/live/orders")
async def get_live_orders(limit: int = 30):
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    return so_ctx.storage.get_orders(is_paper=False, limit=limit)

@router.post("/live/execute-candidate")
async def execute_live_candidate(req: CandidateExecuteRequest):
    if not so_ctx.live_agent:
        raise HTTPException(status_code=503, detail="Live Agent not initialized.")
    return await so_ctx.live_agent.execute_approved_candidate(req.candidate, plan_id=req.plan_id or "")

@router.post("/live/kill-switch")
async def trigger_live_kill_switch():
    if not so_ctx.live_agent:
        raise HTTPException(status_code=503, detail="Live Agent not initialized.")
    return await so_ctx.live_agent.emergency_kill_switch()


# ---------------- Paper Agent Endpoints ---------------- #

@router.get("/paper/status")
async def get_paper_agent_status():
    if not so_ctx.paper_agent:
        raise HTTPException(status_code=503, detail="Paper Agent not initialized.")
    perf = so_ctx.storage.get_performance_summary(is_paper=True)
    positions = so_ctx.storage.get_positions(is_paper=True, open_only=True)

    return {
        "status": so_ctx.paper_agent.status,
        "virtual_capital": so_ctx.paper_agent.virtual_capital,
        "available_virtual_balance": round(so_ctx.paper_agent.simulation_engine.virtual_balance, 2),
        "slippage_pct": so_ctx.paper_agent.slippage_pct,
        "risk_per_trade_pct": so_ctx.paper_agent.risk_per_trade_pct,
        "open_positions_count": len(positions),
        "performance": perf
    }

@router.post("/paper/start")
async def start_paper_agent():
    if not so_ctx.paper_agent:
        raise HTTPException(status_code=503, detail="Paper Agent not initialized.")
    so_ctx.paper_agent.start()
    return {"status": "success", "agent_status": so_ctx.paper_agent.status}

@router.post("/paper/pause")
async def pause_paper_agent():
    if not so_ctx.paper_agent:
        raise HTTPException(status_code=503, detail="Paper Agent not initialized.")
    so_ctx.paper_agent.pause()
    return {"status": "success", "agent_status": so_ctx.paper_agent.status}

@router.post("/paper/config")
async def update_paper_config(req: PaperConfigRequest):
    if not so_ctx.paper_agent:
        raise HTTPException(status_code=503, detail="Paper Agent not initialized.")
    so_ctx.paper_agent.update_settings(
        virtual_capital=req.virtual_capital,
        slippage_pct=req.slippage_pct,
        risk_per_trade_pct=req.risk_per_trade_pct
    )
    return {"status": "success", "message": "Paper settings updated."}

@router.post("/paper/reset")
async def reset_paper_agent(capital: Optional[float] = 500000.0):
    if not so_ctx.paper_agent:
        raise HTTPException(status_code=503, detail="Paper Agent not initialized.")
    so_ctx.paper_agent.reset_paper_ledger(reset_capital=capital)
    return {"status": "success", "message": f"Virtual paper ledger reset to ₹{capital:.2f}."}

@router.get("/paper/positions")
async def get_paper_positions():
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    return so_ctx.storage.get_positions(is_paper=True, open_only=True)

@router.get("/paper/orders")
async def get_paper_orders(limit: int = 100):
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    return so_ctx.storage.get_orders(is_paper=True, limit=min(500, max(1, limit)))

@router.get("/paper/trades")
async def get_paper_trades(limit: int = 100):
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    return so_ctx.storage.get_trades(is_paper=True, limit=min(500, max(1, limit)))

@router.post("/paper/execute-candidate")
async def execute_paper_candidate(req: CandidateExecuteRequest):
    if not so_ctx.paper_agent:
        raise HTTPException(status_code=503, detail="Paper Agent not initialized.")
    return await so_ctx.paper_agent.execute_simulated_trade(req.candidate, plan_id=req.plan_id or "")

@router.post("/paper/close-position")
async def close_paper_position(req: ClosePositionRequest):
    if not so_ctx.paper_agent:
        raise HTTPException(status_code=503, detail="Paper Agent not initialized.")
    return so_ctx.paper_agent.close_simulated_position(
        symbol=req.symbol,
        exit_nominal_price=req.exit_price,
        reason=req.reason or "Manual Exit"
    )

@router.get("/paper/calendar")
async def get_paper_calendar(month: Optional[str] = None):
    """Returns aggregated daily PnL and trade lists for stock options paper calendar display."""
    if not so_ctx.storage:
        raise HTTPException(status_code=503, detail="Storage not initialized.")
    data = so_ctx.storage.get_calendar_pnl(is_paper=True, month=month)
    return {"status": "success", **data}


# ---------------- Universe & Quotes Endpoints ---------------- #

@router.get("/universe")
async def get_stock_universe():
    if not so_ctx.universe_mgr:
        raise HTTPException(status_code=503, detail="Universe manager not initialized.")
    return so_ctx.universe_mgr.get_eligible_stocks()

@router.get("/universe/day-start-movers")
async def get_day_start_movers():
    """
    Day-Start Screener:
    Fetches the top high-beta, high-ATR momentum F&O stocks at day start (09:15 AM)
    suitable for aggressive intraday options momentum trading.
    """
    if not so_ctx.market_data:
        raise HTTPException(status_code=503, detail="Market data service not initialized.")

    high_beta_candidates = [
        "COFORGE", "PERSISTENT", "DIXON", "POLYCAB", "INDUSINDBK",
        "CANBK", "DLF", "ADANIENT", "SBIN", "TRENT", "HAL", "BHEL"
    ]

    shortlisted = so_ctx.market_data.rank_and_shortlist_stocks(
        candidate_symbols=high_beta_candidates,
        max_shortlist=8
    )

    symbols = [s["symbol"] for s in shortlisted] if shortlisted else high_beta_candidates[:8]

    return {
        "status": "success",
        "description": "Day-Start High-Beta F&O Momentum Stocks",
        "timestamp": datetime.now().isoformat(),
        "symbols": symbols,
        "stocks": shortlisted
    }

@router.get("/quote/{symbol}")
async def get_stock_quote(symbol: str):
    if not so_ctx.market_data:
        raise HTTPException(status_code=503, detail="Market data service not initialized.")
    return so_ctx.market_data.get_stock_technical_summary(symbol)
