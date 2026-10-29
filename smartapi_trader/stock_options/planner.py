"""
Overnight AI Planner and Research Scheduler for NSE Stock Options.
Runs post-market close, computes intended next trading date,
analyzes price action, volume, option contracts, calls AI,
and persists conditional trade plans with a strict maximum of 3 candidates.
"""

import asyncio
from datetime import datetime, timedelta, time
from typing import Dict, Any, List, Optional
from smartapi_trader.ai.ai_service import AIService
from smartapi_trader.stock_options.universe import StockUniverseManager, NSE_FO_STOCKS
from smartapi_trader.stock_options.market_data_service import StockMarketDataService
from smartapi_trader.stock_options.storage import StockOptionsStorage
from smartapi_trader.utils.tz import now_ist, is_trading_day
from smartapi_trader.utils.logger import logger


class OvernightAIPlanner:
    """
    Researches the NSE market after closing and prepares conditional trading plans
    for the next session. Strict hard limit: at most 3 distinct stock candidates.
    NEVER places real or simulated orders directly.
    """

    def __init__(
        self,
        ai_service: AIService,
        market_data: StockMarketDataService,
        storage: StockOptionsStorage,
        notifier: Optional[Any] = None
    ):
        self.ai = ai_service
        self.market_data = market_data
        self.storage = storage
        self.notifier = notifier
        self._lock = asyncio.Lock()
        self.is_running = False
        self.dispatch_callback: Optional[Any] = None

    @staticmethod
    def get_next_trading_date(start_dt: Optional[datetime] = None) -> datetime:
        """Computes next official NSE trading day, skipping weekends and exchange holidays."""
        cur = (start_dt or now_ist()) + timedelta(days=1)
        # Advance until we hit a trading day (Monday-Friday, not a holiday)
        while not is_trading_day(cur):
            cur += timedelta(days=1)
        return cur

    async def execute_plan(
        self,
        stock_universe: Optional[List[str]] = None,
        max_candidates: int = 3,
        force_manual: bool = False,
        ai_provider: Optional[str] = None,
        ai_model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes an overnight research run with strict concurrency control
        and backend enforcement of max 3 candidates.
        """
        if self._lock.locked():
            logger.warning("[OVERNIGHT_PLANNER] Research run already in progress. Rejecting duplicate trigger.")
            return {"status": "error", "message": "An overnight research run is already executing."}

        async with self._lock:
            self.is_running = True
            try:
                clamped_max = min(3, max(1, int(max_candidates)))
                now = now_ist()
                next_trading_dt = self.get_next_trading_date(now)
                intended_date_str = next_trading_dt.strftime("%Y-%m-%d")

                logger.info(
                    f"[OVERNIGHT_PLANNER] Starting overnight research run for session {intended_date_str}. "
                    f"Max candidate cap: {clamped_max}"
                )

                # 1. Filter and quantitatively rank eligible stocks
                if not stock_universe or (len(stock_universe) == 1 and stock_universe[0].upper() in ("ALL_FO", "ALL", "AUTO_DISCOVER")):
                    candidate_universe = list(NSE_FO_STOCKS.keys())
                else:
                    candidate_universe = stock_universe

                shortlisted_data = self.market_data.rank_and_shortlist_stocks(
                    candidate_symbols=candidate_universe,
                    max_shortlist=6  # Pre-screen to top 6 pools for the AI to select max 3
                )

                # 2. Market Context Summary
                market_context = {
                    "current_timestamp": now.isoformat(),
                    "intended_session_date": intended_date_str,
                    "market_session_regime": "Post-Market EOD Close",
                    "nifty_sentiment": "Mild Bullish Consolidation above 24,800",
                    "india_vix_estimate": 13.8,
                    "max_candidate_limit": clamped_max
                }

                # 3. Call AI Service with strict backend cap
                ai_response = await self.ai.analyze(
                    run_type="OVERNIGHT_PLAN",
                    intended_date=intended_date_str,
                    stock_data=shortlisted_data,
                    market_context=market_context,
                    max_candidates=clamped_max,
                    provider=ai_provider,
                    model=ai_model
                )

                # 4. Enforce backend maximum candidate constraints & validate stock tickers
                final_candidates = [
                    c for c in ai_response.candidates
                    if c.symbol.upper() in NSE_FO_STOCKS and c.symbol.upper() not in ("ALL_FO", "ALL", "AUTO_DISCOVER")
                ][:clamped_max]
                plan_data = {
                    "plan_id": f"PLAN_{next_trading_dt.strftime('%Y%m%d')}_{int(now.timestamp())}",
                    "created_at": now.isoformat(),
                    "intended_date": intended_date_str,
                    "status": "PENDING_APPROVAL",
                    "market_summary": ai_response.market_summary,
                    "candidates": [c.model_dump() for c in final_candidates],
                    "ai_provider": ai_response.provider,
                    "model": ai_response.model,
                    "no_trade_reason": ai_response.no_trade_reason if not final_candidates else None,
                    "latency_ms": ai_response.latency_ms,
                    "validation_warnings": ai_response.validation_warnings
                }

                # 5. Persist to SQLite
                self.storage.save_overnight_plan(plan_data)
                logger.info(
                    f"[OVERNIGHT_PLANNER] Successfully generated plan {plan_data['plan_id']} "
                    f"with {len(final_candidates)} candidates."
                )

                # 6. Auto-dispatch to active Paper / Live Agents
                if self.dispatch_callback and final_candidates:
                    try:
                        await self.dispatch_callback(plan_data["candidates"], plan_data["plan_id"])
                    except Exception as e:
                        logger.error(f"[OVERNIGHT_PLANNER] Error during auto-dispatch: {e}")

                # 7. Notify via Telegram if configured
                if self.notifier:
                    try:
                        self.notifier.send_message(
                            f"🌙 <b>Overnight AI Stock Options Plan Generated</b>\n"
                            f"Session Date: <code>{intended_date_str}</code>\n"
                            f"Candidates: <b>{len(final_candidates)} / {clamped_max}</b>\n"
                            f"Provider: {ai_response.provider} ({ai_response.model})\n"
                            f"Status: Auto-dispatched / In Queue."
                        )
                    except Exception as e:
                        logger.warning(f"[OVERNIGHT_PLANNER] Telegram notification error: {e}")

                return {
                    "status": "success",
                    "plan": plan_data,
                    "message": f"Generated overnight plan with {len(final_candidates)} candidates."
                }

            except Exception as e:
                logger.error(f"[OVERNIGHT_PLANNER] Error during overnight plan generation: {e}")
                return {"status": "error", "message": str(e)}
            finally:
                self.is_running = False
