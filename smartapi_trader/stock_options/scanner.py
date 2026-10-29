"""
Scheduled Intraday AI Scanner for NSE Stock Options.
Runs periodically during active market hours (09:15 - 15:15 IST),
prevents overlapping runs, implements event-driven reanalysis gating,
and enforces a strict maximum of 3 candidates per scan run.
"""

import asyncio
import time
from datetime import datetime, time as dt_time
from typing import Dict, Any, List, Optional
from smartapi_trader.ai.ai_service import AIService
from smartapi_trader.stock_options.universe import StockUniverseManager, NSE_FO_STOCKS
from smartapi_trader.stock_options.market_data_service import StockMarketDataService
from smartapi_trader.stock_options.storage import StockOptionsStorage
from smartapi_trader.utils.tz import now_ist, is_market_hours, is_trading_day
from smartapi_trader.utils.logger import logger


class IntradayAIScanner:
    """
    Intraday scanning engine evaluating opportunities at intervals (1m, 3m, 5m, 10m, 15m).
    Independent of overnight planner, strictly capped at 3 candidates.
    """

    def __init__(
        self,
        ai_service: AIService,
        market_data: StockMarketDataService,
        storage: StockOptionsStorage,
        default_interval_mins: int = 5,
        notifier: Optional[Any] = None
    ):
        self.ai = ai_service
        self.market_data = market_data
        self.storage = storage
        self.notifier = notifier

        # Load persisted settings from SQLite storage
        persisted_interval = self.storage.get_setting("scanner_interval_mins")
        try:
            self.interval_mins = int(persisted_interval) if persisted_interval else default_interval_mins
        except Exception:
            self.interval_mins = default_interval_mins

        persisted_max = self.storage.get_setting("scanner_max_candidates")
        try:
            self.max_candidates = int(persisted_max) if persisted_max else 3
        except Exception:
            self.max_candidates = 3

        persisted_universe = self.storage.get_setting("scanner_stock_universe")
        self.selected_universe: List[str] = persisted_universe if persisted_universe else list(NSE_FO_STOCKS.keys())[:8]

        self.is_active = False
        self.is_scanning = False
        self._lock = asyncio.Lock()
        self._task: Optional[asyncio.Task] = None
        self._last_scan_time = 0.0
        self._last_spot_snapshots: Dict[str, float] = {}

        # Default session boundaries (09:00 - 15:00 IST / 9 AM to 3 PM)
        self.session_start = dt_time(9, 0)
        self.session_end = dt_time(15, 0)
        saved_start = self.storage.get_setting("scanner_session_start")
        saved_end = self.storage.get_setting("scanner_session_end")
        if saved_start:
            try:
                p = saved_start.split(":")
                self.session_start = dt_time(int(p[0]), int(p[1]))
            except Exception:
                pass
        if saved_end:
            try:
                p = saved_end.split(":")
                self.session_end = dt_time(int(p[0]), int(p[1]))
            except Exception:
                pass
        self.dispatch_callback: Optional[Any] = None

    def configure(
        self,
        interval_mins: Optional[int] = None,
        max_candidates: Optional[int] = None,
        session_start_str: Optional[str] = None,
        session_end_str: Optional[str] = None,
        stock_universe: Optional[List[str]] = None
    ):
        if interval_mins and interval_mins in (1, 3, 5, 10, 15, 30, 60, 120):
            self.interval_mins = interval_mins
            self.storage.save_setting("scanner_interval_mins", self.interval_mins)
        elif interval_mins and interval_mins > 0:
            self.interval_mins = interval_mins
            self.storage.save_setting("scanner_interval_mins", self.interval_mins)

        if max_candidates is not None:
            self.max_candidates = min(3, max(1, int(max_candidates)))
            self.storage.save_setting("scanner_max_candidates", self.max_candidates)

        if stock_universe is not None:
            clean = [s.upper() for s in stock_universe if s.upper() in NSE_FO_STOCKS]
            self.selected_universe = clean if clean else list(NSE_FO_STOCKS.keys())
            self.storage.save_setting("scanner_stock_universe", self.selected_universe)

        if session_start_str:
            try:
                parts = session_start_str.split(":")
                self.session_start = dt_time(int(parts[0]), int(parts[1]))
                self.storage.save_setting("scanner_session_start", session_start_str)
            except Exception:
                pass

        if session_end_str:
            try:
                parts = session_end_str.split(":")
                self.session_end = dt_time(int(parts[0]), int(parts[1]))
                self.storage.save_setting("scanner_session_end", session_end_str)
            except Exception:
                pass

        logger.info(
            f"[INTRADAY_SCANNER] Configured & Persisted: Interval={self.interval_mins}m, "
            f"MaxCandidates={self.max_candidates}, Session={self.session_start}-{self.session_end}"
        )

    async def start(self):
        """Starts the periodic background scanning loop."""
        if self.is_active:
            return
        self.is_active = True
        self.storage.save_setting("scanner_is_active", True)
        self._task = asyncio.create_task(self._scanner_loop())
        logger.info(f"[INTRADAY_SCANNER] Started background scanner (Interval: {self.interval_mins}m).")

    async def stop(self):
        """Stops the periodic scanning loop."""
        self.is_active = False
        self.storage.save_setting("scanner_is_active", False)
        if self._task and not self._task.done():
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        self._task = None
        logger.info("[INTRADAY_SCANNER] Stopped background scanner.")

    async def _scanner_loop(self):
        """Continuous scheduled loop running at configured intervals."""
        while self.is_active:
            try:
                now = now_ist()
                in_session = (
                    is_trading_day(now) and
                    self.session_start <= now.time() <= self.session_end
                )

                if in_session:
                    # Check if enough time elapsed since last scan
                    elapsed_secs = time.time() - self._last_scan_time
                    target_interval_secs = self.interval_mins * 60

                    if elapsed_secs >= target_interval_secs:
                        await self.execute_scan(is_manual=False)

                # Sleep in short increments to allow rapid stop/pause response
                await asyncio.sleep(10)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[INTRADAY_SCANNER] Exception in scanner loop: {e}")
                await asyncio.sleep(15)

    def _has_material_market_change(self, current_stocks: List[Dict[str, Any]]) -> bool:
        """
        Event-driven reanalysis gate:
        Checks if spot price moved > 0.35% or volume ratio changed significantly
        to avoid redundant AI calls when prices are stagnant.
        """
        if not self._last_spot_snapshots:
            return True

        for stock in current_stocks:
            sym = stock["symbol"]
            curr_spot = stock["spot"]
            prev_spot = self._last_spot_snapshots.get(sym)
            if prev_spot is None:
                return True
            pct_diff = abs(curr_spot - prev_spot) / prev_spot
            if pct_diff >= 0.0035:  # 0.35% move
                return True

        return False

    async def execute_scan(
        self,
        is_manual: bool = False,
        ai_provider: Optional[str] = None,
        ai_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Performs a single market scan run with overlap protection
        and strict backend candidate limit of at most 3.
        """
        if self._lock.locked():
            logger.warning("[INTRADAY_SCANNER] Previous scan still executing. Coalescing/skipping overlapping run.")
            return {"status": "skipped", "message": "Previous scan in progress."}

        async with self._lock:
            self.is_scanning = True
            start_ts = time.time()
            now = now_ist()
            scan_id = f"SCAN_{int(now.timestamp() * 1000)}"

            try:
                clamped_max = min(3, max(1, self.max_candidates))
                intended_date_str = now.strftime("%Y-%m-%d")

                # 0. Session Window Enforcement (09:00 - 15:00 IST / 9 AM to 3 PM)
                in_session = (
                    is_trading_day(now) and
                    self.session_start <= now.time() <= self.session_end
                )
                if not is_manual and not in_session:
                    logger.info("[INTRADAY_SCANNER] Gated: AI automatic scan skipped outside active session (09:00 - 15:00 IST).")
                    return {
                        "status": "outside_session",
                        "message": "AI scanning is only active from 9:00 AM to 3:00 PM IST on trading days."
                    }

                logger.info(f"[INTRADAY_SCANNER] Executing scan {scan_id} (Manual: {is_manual}, Max Cap: {clamped_max}, InSession: {in_session})...")

                # 1. Retrieve fresh data and rank candidate universe
                shortlisted = self.market_data.rank_and_shortlist_stocks(
                    candidate_symbols=self.selected_universe,
                    max_shortlist=6
                )

                # 2. Check event-driven reanalysis gate (unless manual trigger)
                if not is_manual and not self._has_material_market_change(shortlisted):
                    logger.info("[INTRADAY_SCANNER] Gated: Market prices consolidated without material displacement. Skipping redundant AI call.")
                    self._last_scan_time = time.time()
                    return {"status": "gated", "message": "Market stable; AI call skipped to conserve API costs."}

                # Update snapshots
                for s in shortlisted:
                    self._last_spot_snapshots[s["symbol"]] = s["spot"]

                # 3. Formulate context
                market_context = {
                    "scan_id": scan_id,
                    "timestamp": now.isoformat(),
                    "session_time_ist": now.strftime("%H:%M:%S"),
                    "market_regime": "Active Intraday Session",
                    "interval_mins": self.interval_mins,
                    "max_candidate_limit": clamped_max
                }

                # 4. Dispatch to AI Service
                ai_response = await self.ai.analyze(
                    run_type="INTRADAY_SCAN",
                    intended_date=intended_date_str,
                    stock_data=shortlisted,
                    market_context=market_context,
                    max_candidates=clamped_max,
                    provider=ai_provider,
                    model=ai_model
                )

                final_candidates = [
                    c for c in ai_response.candidates
                    if c.symbol.upper() in NSE_FO_STOCKS and c.symbol.upper() not in ("ALL_FO", "ALL", "AUTO_DISCOVER")
                ][:clamped_max]

                scan_record = {
                    "scan_id": scan_id,
                    "created_at": now.isoformat(),
                    "interval_mins": self.interval_mins,
                    "stocks_evaluated": len(self.selected_universe),
                    "stocks_shortlisted": len(shortlisted),
                    "candidates_count": len(final_candidates),
                    "candidates": [c.model_dump() for c in final_candidates],
                    "ai_provider": ai_response.provider,
                    "model": ai_response.model,
                    "market_summary": ai_response.market_summary,
                    "no_trade_reason": ai_response.no_trade_reason if not final_candidates else None,
                    "latency_ms": ai_response.latency_ms,
                    "validation_warnings": ai_response.validation_warnings
                }

                # 5. Persist scan result and track session
                session_key = f"SESSION_{now.strftime('%Y%m%d')}"
                session_state = self.storage.get_setting("scanner_session_state") or {}
                if session_state.get("session_id") != session_key:
                    session_state = {
                        "session_id": session_key,
                        "session_date": intended_date_str,
                        "scans_count": 0,
                        "traded_symbols": [],
                        "started_at": now.isoformat()
                    }
                session_state["scans_count"] = session_state.get("scans_count", 0) + 1
                session_state["last_scan_at"] = now.isoformat()
                self.storage.save_setting("scanner_session_state", session_state)

                scan_record["session"] = session_state
                self.storage.save_intraday_scan(scan_record)

                # Consolidate with unified plan record so all pages stay perfectly synchronized
                plan_sync_data = {
                    "plan_id": scan_id,
                    "created_at": now.isoformat(),
                    "intended_date": intended_date_str,
                    "status": "ACTIVE_INTRADAY",
                    "market_summary": ai_response.market_summary,
                    "candidates": [c.model_dump() for c in final_candidates],
                    "ai_provider": ai_response.provider,
                    "model": ai_response.model,
                    "no_trade_reason": ai_response.no_trade_reason if not final_candidates else None,
                    "latency_ms": ai_response.latency_ms,
                    "validation_warnings": ai_response.validation_warnings
                }
                self.storage.save_overnight_plan(plan_sync_data)
                self._last_scan_time = time.time()

                logger.info(
                    f"[INTRADAY_SCANNER] Scan {scan_id} finished: {len(final_candidates)} candidates returned "
                    f"in {ai_response.latency_ms}ms. Session {session_key} (Scan #{session_state['scans_count']})."
                )

                # 6. Auto-dispatch to active Paper / Live Agents
                if self.dispatch_callback and final_candidates:
                    try:
                        await self.dispatch_callback(scan_record["candidates"], scan_id)
                        # Record traded symbols in session state
                        for fc in final_candidates:
                            if fc.symbol not in session_state["traded_symbols"]:
                                session_state["traded_symbols"].append(fc.symbol)
                        self.storage.save_setting("scanner_session_state", session_state)
                    except Exception as e:
                        logger.error(f"[INTRADAY_SCANNER] Error during auto-dispatch: {e}")

                # 7. Notify via Telegram if configured
                if self.notifier and final_candidates:
                    try:
                        cand_lines = []
                        for c in final_candidates:
                            contract = c.primary_contract
                            tech = c.technical
                            mgmt = c.trade_management
                            cand_lines.append(
                                f"• <b>{c.symbol}</b> ({c.bias} • {contract.option_type} {contract.strike_price})\n"
                                f"   Entry: ₹{tech.entry_trigger} | SL: ₹{mgmt.stop_loss} | T1: ₹{mgmt.target_1} (R:R 1:{mgmt.risk_reward_ratio})"
                            )
                        cand_txt = "\n".join(cand_lines)
                        self.notifier.send_message(
                            f"🎯 <b>AI INTRADAY F&O SCAN REPORT</b>\n\n"
                            f"Session: <code>{session_key}</code> (Scan #{session_state.get('scans_count', 1)})\n"
                            f"Interval: {self.interval_mins}m | Provider: {ai_response.provider} ({ai_response.model})\n\n"
                            f"<b>Top High-Probability Setups:</b>\n{cand_txt}\n\n"
                            f"🤖 <i>Auto-routed to Stock Options Paper & Live Trading Engines.</i>"
                        )
                    except Exception as e:
                        logger.warning(f"[INTRADAY_SCANNER] Telegram dispatch error: {e}")

                return {
                    "status": "success",
                    "scan": scan_record,
                    "plan": plan_sync_data,
                    "session": session_state,
                    "message": f"Scan completed with {len(final_candidates)} candidates."
                }

            except Exception as e:
                logger.error(f"[INTRADAY_SCANNER] Scan error: {e}")
                return {"status": "error", "message": str(e)}
            finally:
                self.is_scanning = False
