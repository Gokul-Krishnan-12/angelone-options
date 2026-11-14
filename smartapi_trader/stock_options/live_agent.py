"""
Stock Options Live Trading Agent.
Executes real-money stock-options trades using the existing broker integration
(Angel One SmartAPI) and mandatory existing RiskManager.
"""

import time
import asyncio
from datetime import datetime, time as dt_time
from typing import Dict, Any, List, Optional
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.events import SignalEvent, OrderEvent, PositionEvent
from smartapi_trader.risk.risk_manager import RiskManager
from smartapi_trader.execution.live_smartapi import LiveSmartAPIExecutionEngine
from smartapi_trader.stock_options.storage import StockOptionsStorage
from smartapi_trader.stock_options.validator import StockOptionsValidator, check_trigger_status
from smartapi_trader.stock_options.universe import NSE_FO_STOCKS
from smartapi_trader.utils.tz import is_market_hours
from smartapi_trader.utils.logger import logger


class StockOptionsLiveAgent:
    """
    Real-money Stock Options Trading Agent.
    Submits trades strictly through the mandatory RiskManager and LiveSmartAPIExecutionEngine.
    Includes autonomous trigger monitoring: arms setups and waits for spot entry price before execution.
    """

    def __init__(
        self,
        event_bus: EventBus,
        risk_manager: RiskManager,
        live_engine: LiveSmartAPIExecutionEngine,
        storage: StockOptionsStorage,
        validator: Optional[StockOptionsValidator] = None,
        notifier: Optional[Any] = None,
        market_data: Optional[Any] = None
    ):
        self.bus = event_bus
        self.risk_manager = risk_manager
        self.live_engine = live_engine
        self.storage = storage
        self.market_data = market_data
        self.validator = validator or StockOptionsValidator(storage=self.storage, market_data=self.market_data)
        if self.validator.storage is None:
            self.validator.storage = self.storage
        if self.validator.market_data is None:
            self.validator.market_data = self.market_data
        self.notifier = notifier

        self.status = "IDLE"  # "IDLE", "RUNNING", "PAUSED", "STOPPED"
        self.auto_execute = False
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None

        # Armed candidate queue waiting for live entry trigger confirmation
        self.armed_candidates: Dict[str, Dict[str, Any]] = {}
        self._load_persisted_armed_candidates()

    def _load_persisted_armed_candidates(self):
        """Loads resting live armed triggers from persistent SQLite settings."""
        try:
            persisted = self.storage.get_setting("live_armed_candidates")
            if isinstance(persisted, dict):
                self.armed_candidates = persisted
            elif isinstance(persisted, list):
                self.armed_candidates = {str(item.get("symbol")): item for item in persisted if item.get("symbol")}
        except Exception as e:
            logger.debug(f"[LIVE_AGENT] Could not load persisted armed candidates: {e}")

    def _persist_armed_candidates(self):
        """Persists resting live armed triggers into storage."""
        try:
            if self.storage:
                self.storage.save_setting("live_armed_candidates", self.armed_candidates)
        except Exception as e:
            logger.debug(f"[LIVE_AGENT] Could not persist armed candidates: {e}")

    def get_armed_candidates(self) -> List[Dict[str, Any]]:
        """Returns list of currently armed stock setups waiting for entry in live agent."""
        return list(self.armed_candidates.values())

    def cancel_armed_candidate(self, symbol: str) -> Dict[str, Any]:
        """Cancels an armed live setup before it triggers."""
        sym = symbol.upper().strip()
        if sym in self.armed_candidates:
            item = self.armed_candidates.pop(sym)
            self._persist_armed_candidates()
            plan_id = item.get("plan_id", "")
            if self.storage and plan_id:
                try:
                    self.storage.update_plan_status(plan_id, "CANCELLED_BY_USER", sym)
                except Exception:
                    pass
            logger.info(f"[LIVE_AGENT] Armed setup for {sym} cancelled by user.")
            return {"status": "success", "message": f"Armed live setup for {sym} cancelled."}
        return {"status": "not_found", "message": f"No armed live setup found for {sym}."}

    def start(self):
        self.status = "RUNNING"
        self._ensure_monitor_task()
        logger.info("[LIVE_AGENT] Stock Options Live Agent STARTED. RMS enforcement and autonomous trigger monitor active.")

    def pause(self):
        self.status = "PAUSED"
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None
        logger.info("[LIVE_AGENT] Stock Options Live Agent PAUSED. New entries blocked.")

    def stop(self):
        self.status = "STOPPED"
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None
        logger.info("[LIVE_AGENT] Stock Options Live Agent STOPPED.")

    def _ensure_monitor_task(self):
        """Ensures the background live trigger monitor task is running."""
        if self.status == "RUNNING" and (self._monitor_task is None or self._monitor_task.done()):
            try:
                loop = asyncio.get_running_loop()
                self._monitor_task = loop.create_task(self._live_monitor_loop())
            except RuntimeError:
                pass

    async def _live_monitor_loop(self):
        """
        Background monitor loop evaluating armed candidates against live market quotes every 3 seconds.
        When spot crosses the entry trigger, submits the order to RiskManager for execution.
        """
        logger.info("[LIVE_AGENT] 🚀 Live autonomous trigger monitor loop started.")
        while self.status == "RUNNING":
            try:
                await self._evaluate_armed_candidates()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[LIVE_AGENT] Error in live monitor loop: {e}")
            await asyncio.sleep(3.0)

    async def _evaluate_armed_candidates(self):
        """Monitors armed stock option setups for spot trigger crosses or invalidation."""
        if not self.armed_candidates:
            return

        cur_ist = datetime.now()
        is_past_cutoff = (is_market_hours(cur_ist) and cur_ist.time() >= dt_time(13, 45))

        # Strict 09:15 - 09:20 IST Opening Bell Stabilization Lock: Avoid opening gap noise & whip traps
        if is_market_hours(cur_ist) and dt_time(9, 15) <= cur_ist.time() < dt_time(9, 20):
            return

        symbols_to_remove = []
        for sym, item in list(self.armed_candidates.items()):
            candidate = item.get("candidate", {})
            plan_id = item.get("plan_id", "")

            # Strict 13:45 IST Cutoff during live market hours: expire un-triggered setups to prevent late-session theta burn
            if is_past_cutoff:
                logger.info(f"[LIVE_AGENT] ⏰ Armed candidate {sym} expired at 13:45 IST (Entry cutoff to prevent late-session theta decay).")
                symbols_to_remove.append(sym)
                if self.storage and plan_id:
                    try:
                        self.storage.update_plan_status(plan_id, "EXPIRED_ENTRY_CUTOFF", sym)
                    except Exception:
                        pass
                continue

            # Same-day Stop-Loss Cooldown Guard: Discard armed setup if stock was stopped out earlier today
            if self.storage:
                try:
                    stopped_symbols = self.storage.get_stopped_out_underlyings_today()
                    if sym in stopped_symbols:
                        logger.warning(f"[LIVE_AGENT] 🛑 Armed setup {sym} INVALIDATED: Daily Cooldown active (stopped out earlier today).")
                        symbols_to_remove.append(sym)
                        if plan_id:
                            self.storage.update_plan_status(plan_id, "DAILY_COOLDOWN_STOPPED_OUT", sym)
                        continue
                except Exception:
                    pass

            current_spot = 0.0
            if self.market_data:
                try:
                    current_spot = self.market_data.get_spot_ltp(sym)
                except Exception:
                    pass
            if current_spot <= 0:
                continue

            item["last_spot"] = current_spot
            item["last_checked_at"] = cur_ist.isoformat()

            is_trig, is_inval, trig_reason = check_trigger_status(candidate, current_spot)
            item["status_reason"] = trig_reason

            if is_inval:
                logger.warning(f"[LIVE_AGENT] 🛑 Live setup {sym} INVALIDATED: {trig_reason}")
                symbols_to_remove.append(sym)
                if self.storage and plan_id:
                    try:
                        self.storage.update_plan_status(plan_id, "INVALIDATED", sym)
                    except Exception:
                        pass
                if self.notifier:
                    try:
                        self.notifier.send_message(f"⚠️ <b>LIVE Stock Option Setup Invalidated</b>\n{sym}: {trig_reason}")
                    except Exception:
                        pass
                continue

            if is_trig:
                logger.info(f"[LIVE_AGENT] 🎯 ENTRY TRIGGER CONFIRMED: {sym} -> {trig_reason}! Submitting to RMS...")
                symbols_to_remove.append(sym)
                try:
                    res = await self.execute_approved_candidate(candidate, plan_id=plan_id, force_immediate=True)
                    if self.storage and plan_id:
                        target_status = "AUTO_DISPATCHED_LIVE_FILLED" if res.get("status") == "success" else "EXECUTION_REJECTED"
                        try:
                            self.storage.update_plan_status(plan_id, target_status, sym)
                        except Exception:
                            pass
                except Exception as ex:
                    logger.error(f"[LIVE_AGENT] Error executing triggered live trade for {sym}: {ex}")
                continue

        if symbols_to_remove:
            for s in symbols_to_remove:
                self.armed_candidates.pop(s, None)
            self._persist_armed_candidates()

    def arm_candidate(
        self,
        candidate: Dict[str, Any],
        plan_id: str = "",
        current_spot: float = 0.0,
        reason: str = ""
    ) -> Dict[str, Any]:
        """
        Arms a conditional stock option trade setup to wait for entry price/trigger.
        Does NOT execute order immediately.
        """
        sym = candidate.get("symbol", "").upper().strip()
        contract = candidate.get("primary_contract", {})
        tech = candidate.get("technical", {})
        mgmt = candidate.get("trade_management", {})
        bias = candidate.get("bias", "BULLISH").upper()
        entry_trigger = float(tech.get("entry_trigger", 0.0))
        inval_level = float(tech.get("invalidation_level", 0.0))

        armed_item = {
            "symbol": sym,
            "plan_id": plan_id,
            "bias": bias,
            "candidate": candidate,
            "entry_trigger": entry_trigger,
            "invalidation_level": inval_level,
            "indicative_premium": float(contract.get("indicative_premium", 0.0)),
            "contract": contract.get("tradingsymbol", f"{sym} {contract.get('strike_price')} {contract.get('option_type')}"),
            "lot_size": int(contract.get("lot_size", 1)),
            "stop_loss": float(mgmt.get("stop_loss", 0.0)),
            "target_1": float(mgmt.get("target_1", 0.0)),
            "initial_spot": current_spot,
            "last_spot": current_spot,
            "status": "ARMED_WAITING_FOR_TRIGGER",
            "status_reason": reason or f"Waiting for spot ₹{entry_trigger}",
            "target_mode": "LIVE",
            "armed_at": datetime.now().isoformat(),
            "last_checked_at": datetime.now().isoformat()
        }

        self.armed_candidates[sym] = armed_item
        self._persist_armed_candidates()
        self._ensure_monitor_task()

        logger.info(
            f"[LIVE_AGENT] ⏳ ARMED LIVE CANDIDATE: {sym} ({armed_item['contract']}) | "
            f"Spot: ₹{current_spot:.2f} | Entry Trigger: ₹{entry_trigger:.2f} | "
            f"SL: ₹{armed_item['stop_loss']} | T1: ₹{armed_item['target_1']}"
        )

        if self.storage and plan_id:
            try:
                self.storage.update_plan_status(plan_id, "ARMED_WAITING_FOR_TRIGGER", sym)
            except Exception:
                pass

        if self.notifier:
            try:
                self.notifier.send_message(
                    f"⏳ <b>LIVE Stock Option Setup Armed</b>\n"
                    f"Underlying: <b>{sym}</b>\n"
                    f"Contract: <code>{armed_item['contract']}</code>\n"
                    f"Current Spot: ₹{current_spot:.2f}\n"
                    f"Entry Trigger: <b>₹{entry_trigger:.2f}</b>\n"
                    f"Mode: <b>LIVE (Angel One RMS)</b>\n"
                    f"Waiting for breakout confirmation before routing order to Angel One."
                )
            except Exception:
                pass

        return {
            "status": "armed",
            "message": f"Setup for {sym} armed. Monitoring exchange spot (Current: ₹{current_spot:.2f}, Trigger: ₹{entry_trigger:.2f}).",
            "armed_item": armed_item
        }

    def set_auto_execute(self, enabled: bool):
        self.auto_execute = bool(enabled)
        logger.info(f"[LIVE_AGENT] Auto execution set to {self.auto_execute}")

    async def emergency_kill_switch(self) -> Dict[str, Any]:
        """
        Immediately pauses agent, cancels all resting orders, and closes
        open real stock options positions at market.
        """
        self.status = "STOPPED"
        self.auto_execute = False
        self.armed_candidates.clear()
        self._persist_armed_candidates()
        logger.critical("[LIVE_AGENT] 🚨 EMERGENCY KILL SWITCH TRIGGERED FOR STOCK OPTIONS!")

        open_positions = self.storage.get_positions(is_paper=False, open_only=True)
        closed_count = 0

        for pos in open_positions:
            try:
                sym = pos["symbol"]
                tok = pos["token"] if "token" in pos else ""
                qty = pos["quantity"]
                ltp = pos.get("current_ltp", pos.get("entry_price", 0.0))

                exit_order = {
                    "order_id": f"ORD_KILL_{int(time.time() * 1000)}",
                    "symbol": sym,
                    "token": tok,
                    "exchange": "NFO",
                    "transaction_type": "SELL",
                    "order_type": "MARKET",
                    "variety": "NORMAL",
                    "quantity": qty,
                    "price": ltp
                }

                if self.live_engine:
                    await self.live_engine.submit_order(exit_order)

                self.storage.close_position(sym, is_paper=False, exit_price=ltp, exit_reason="Emergency Kill Switch Liquidation")
                closed_count += 1
            except Exception as e:
                logger.error(f"[LIVE_AGENT] Error liquidating position {pos.get('symbol')}: {e}")

        if self.notifier:
            try:
                self.notifier.send_message(f"🚨 <b>LIVE STOCK OPTIONS EMERGENCY KILL SWITCH ACTIVATED</b>\nClosed {closed_count} open positions.")
            except Exception:
                pass

        return {"status": "success", "closed_positions": closed_count, "message": "Emergency kill switch executed."}

    async def execute_approved_candidate(
        self,
        candidate: Dict[str, Any],
        plan_id: str = "",
        force_immediate: bool = False
    ) -> Dict[str, Any]:
        """
        Validates candidate deterministically, checks against mandatory RiskManager,
        and submits real order to Angel One.
        If force_immediate is False and entry trigger has not been breached,
        arms the candidate in the pending watchlist to wait for entry price.
        """
        if self.status != "RUNNING":
            return {"status": "error", "message": f"Agent is in {self.status} mode. Must be RUNNING to execute trades."}

        async with self._lock:
            # 1. Deterministic Pre-Flight Validation
            sym = candidate.get("symbol", "").upper()
            contract = candidate.get("primary_contract", {})
            tech = candidate.get("technical", {})

            # Query real live market spot price
            spot = 0.0
            if self.market_data:
                try:
                    spot = self.market_data.get_spot_ltp(sym)
                except Exception:
                    pass
            if spot <= 0:
                default_spot = NSE_FO_STOCKS.get(sym, {}).get("base_price", 1000.0)
                spot = float(tech.get("reference_price") or tech.get("entry_trigger") or default_spot)

            # 2. Check conditional trigger confirmation unless force_immediate is True
            if not force_immediate:
                now_dt = datetime.now()

                # 09:15 - 09:20 IST Opening Bell Stabilization Lock: Hold in armed state to avoid opening gap whipsaws
                if is_market_hours(now_dt) and dt_time(9, 15) <= now_dt.time() < dt_time(9, 20):
                    logger.info(f"[LIVE_AGENT] ⏳ Setup for {sym} held in armed state: Opening bell stabilization lock active (09:15-09:20 IST). Awaiting 09:20 range settlement.")
                    return self.arm_candidate(candidate, plan_id=plan_id, current_spot=spot, reason="Opening bell stabilization (09:15-09:20 IST)")

                # 13:45 IST Entry Cutoff Guard: Block late afternoon entries during live market hours
                if is_market_hours(now_dt) and now_dt.time() >= dt_time(13, 45):
                    logger.warning(f"[LIVE_AGENT] Rejected {sym}: Entry cutoff reached (13:45 IST). Intraday option buying is closed to prevent late-session theta decay.")
                    return {"status": "rejected", "reason": "Entry cutoff reached (13:45 IST). Intraday option buying is closed."}

                # Same-day Stop-Loss Cooldown Guard: Block re-entry if stock was stopped out earlier today
                if self.storage:
                    try:
                        stopped_symbols = self.storage.get_stopped_out_underlyings_today()
                        if sym in stopped_symbols:
                            logger.warning(f"[LIVE_AGENT] Rejected {sym}: Daily Cooldown active. Stock stopped out earlier today.")
                            return {"status": "rejected", "reason": f"Daily Cooldown Active: {sym} was stopped out earlier today. Same-day re-entry blocked."}
                    except Exception:
                        pass

                is_trig, is_inval, trig_reason = check_trigger_status(candidate, spot)
                if is_inval:
                    logger.warning(f"[LIVE_AGENT] Pre-trade validation rejected candidate {sym}: {trig_reason}")
                    return {"status": "rejected", "reason": trig_reason}

                if not is_trig:
                    # Stock has not reached entry trigger yet -> Arm it and wait for entry price!
                    return self.arm_candidate(candidate, plan_id=plan_id, current_spot=spot, reason=trig_reason)

            # 3. If triggered or force_immediate: remove from armed candidates if present
            self.armed_candidates.pop(sym, None)
            self._persist_armed_candidates()

            # Query real live market option LTP if available
            indicative_prem = float(contract.get("indicative_premium", 10.0))
            if self.market_data:
                try:
                    c_token = contract.get("instrument_token") or contract.get("symboltoken") or contract.get("token")
                    c_strike = float(contract.get("strike_price") or contract.get("strike") or 0.0)
                    c_symbol = contract.get("tradingsymbol") or contract.get("symbol", "")
                    c_opt_type = contract.get("option_type") or ("CE" if "CE" in c_symbol else "PE")
                    live_opt_ltp = self.market_data.get_option_ltp(
                        symbol=c_symbol,
                        underlying=sym,
                        token=c_token,
                        strike=c_strike,
                        option_type=c_opt_type
                    )
                    if live_opt_ltp > 0:
                        indicative_prem = live_opt_ltp
                except Exception as ex:
                    logger.debug(f"[LIVE_AGENT] Live option LTP query failed for {sym}: {ex}")

            is_valid, reason, params = self.validator.validate_candidate_for_execution(
                candidate=candidate,
                current_spot=spot,
                current_option_ltp=indicative_prem,
                bid_price=indicative_prem * 0.99,
                ask_price=indicative_prem * 1.01,
                is_paper=False
            )

            if not is_valid:
                logger.warning(f"[LIVE_AGENT] Pre-trade validation rejected candidate {candidate.get('symbol')}: {reason}")
                return {"status": "rejected", "reason": reason}

            # 2. Construct SignalEvent for existing RiskManager validation
            strat_name = f"StockOpt_{candidate.get('setup_type', 'Momentum')}"
            sig = SignalEvent(
                signal_id=f"SIG_STK_{candidate.get('symbol')}_{int(time.time())}",
                underlying=params["underlying"],
                signal_type="BUY_CE" if params["option_type"] == "CE" else "BUY_PE",
                strike=params["strike"],
                option_type=params["option_type"],
                expiry=params["expiry"],
                symboltoken=params["token"],
                tradingsymbol=params["symbol"],
                exchange="NFO",
                lot_size=params["lot_size"],
                entry_price=params["entry_price"],
                stop_loss=params["stop_loss"],
                target_1=params["target_1"],
                strategy_name=strat_name,
                reason=candidate.get("technical", {}).get("technical_rationale", "AI Approved Setup"),
                is_paper=False,
                execution_venue="SMARTAPI"
            )

            # 3. Publish to EventBus so existing RiskManager validates risk budget & sizing
            logger.info(f"[LIVE_AGENT] Submitting {sig.tradingsymbol} to mandatory RiskManager...")
            await self.bus.publish(sig)

            # Record pending order into storage
            order_record = {
                "order_id": f"ORD_STK_LIVE_{int(time.time() * 1000)}",
                "plan_id": plan_id,
                "symbol": params["symbol"],
                "underlying": params["underlying"],
                "option_type": params["option_type"],
                "strike": params["strike"],
                "expiry": params["expiry"],
                "transaction_type": "BUY",
                "order_type": "LIMIT",
                "quantity": params["lot_size"],
                "price": params["entry_price"],
                "trigger_price": 0.0,
                "status": "SUBMITTED_TO_RMS",
                "is_paper": False,
                "execution_mode": "LIVE"
            }
            self.storage.save_order(order_record)

            # Record position expectation
            pos_record = {
                "symbol": params["symbol"],
                "underlying": params["underlying"],
                "option_type": params["option_type"],
                "strike": params["strike"],
                "expiry": params["expiry"],
                "quantity": params["lot_size"],
                "lot_size": params["lot_size"],
                "lots": 1,
                "entry_price": params["entry_price"],
                "current_ltp": params["entry_price"],
                "stop_loss": params["stop_loss"],
                "target_1": params["target_1"],
                "is_open": True,
                "is_paper": False,
                "execution_mode": "LIVE",
                "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.storage.save_position(pos_record)

            if self.notifier:
                try:
                    self.notifier.send_message(
                        f"⚡ <b>LIVE Stock Option Order Dispatched</b>\n"
                        f"Contract: <code>{params['symbol']}</code>\n"
                        f"Entry: ₹{params['entry_price']} | SL: ₹{params['stop_loss']} | T1: ₹{params['target_1']}\n"
                        f"Underlying: {params['underlying']}"
                    )
                except Exception:
                    pass

            return {
                "status": "success",
                "message": f"Submitted {params['symbol']} to RMS and broker live execution.",
                "order": order_record
            }
