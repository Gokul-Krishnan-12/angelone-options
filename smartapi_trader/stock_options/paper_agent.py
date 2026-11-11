"""
Stock Options Paper Trading Agent & Isolated Simulation Engine.
Strictly isolated from live broker execution. Can NEVER place real orders.
Maintains independent virtual capital, simulated fills, slippage, and P&L ledger.
NOT blocked by live risk manager limits.
"""

import os
import sys
import time
import asyncio
from datetime import datetime, time as dt_time
from typing import Dict, Any, List, Optional
from smartapi_trader.stock_options.storage import StockOptionsStorage
from smartapi_trader.stock_options.validator import StockOptionsValidator, check_trigger_status
from smartapi_trader.stock_options.universe import NSE_FO_STOCKS
from smartapi_trader.utils.tz import is_market_hours
from smartapi_trader.utils.logger import logger



class StockOptionsPaperEngine:
    """
    Dedicated simulation engine for Stock Options.
    Contains ZERO broker connectivity and ZERO ability to submit live orders.
    Enforces realistic fills with slippage, bid-ask spread penalty, and statutory tax modeling.
    """

    def __init__(self, initial_capital: float = 500000.0, slippage_pct: float = 0.35):
        self.initial_capital = initial_capital
        self.virtual_balance = initial_capital
        self.slippage_pct = slippage_pct
        self.brokerage_per_order = 20.0  # ₹20 per executed leg

    def simulate_order_fill(
        self,
        symbol: str,
        transaction_type: str,
        quantity: int,
        nominal_price: float
    ) -> Dict[str, Any]:
        """Simulates realistic fill accounting for slippage and brokerage."""
        # For BUY: Fill at nominal_price + slippage (Ask fill)
        # For SELL: Fill at nominal_price - slippage (Bid fill)
        slip_mult = (1.0 + (self.slippage_pct / 100.0)) if transaction_type == "BUY" else (1.0 - (self.slippage_pct / 100.0))
        exec_price = round(max(0.05, nominal_price * slip_mult), 2)
        total_trade_value = round(exec_price * quantity, 2)
        statutory_taxes = round(total_trade_value * 0.000625, 2)  # STT + GST + Stamp duty
        total_charges = round(self.brokerage_per_order + statutory_taxes, 2)

        return {
            "symbol": symbol,
            "transaction_type": transaction_type,
            "quantity": quantity,
            "nominal_price": nominal_price,
            "executed_price": exec_price,
            "trade_value": total_trade_value,
            "slippage_points": round(abs(exec_price - nominal_price), 2),
            "charges": total_charges,
            "timestamp": datetime.now().isoformat()
        }


class StockOptionsPaperAgent:
    """
    Simulated Stock Options Agent operating independently with its own
    virtual capital, custom risk parameters, and isolated simulation engine.
    """

    def __init__(
        self,
        storage: StockOptionsStorage,
        validator: Optional[StockOptionsValidator] = None,
        initial_capital: float = 500000.0,
        notifier: Optional[Any] = None,
        market_data: Optional[Any] = None,
        event_bus: Optional[Any] = None
    ):
        self.storage = storage
        self.validator = validator or StockOptionsValidator()
        self.simulation_engine = StockOptionsPaperEngine(initial_capital=initial_capital)
        self.notifier = notifier
        self.market_data = market_data
        self.event_bus = event_bus

        self.status = "RUNNING"  # "RUNNING", "PAUSED", "STOPPED"
        self.auto_execute = True
        self._lock = asyncio.Lock()
        self._monitor_task: Optional[asyncio.Task] = None

        # Load persisted settings or initialize defaults
        self.virtual_capital = float(self.storage.get_setting("paper_stock_opt_capital", initial_capital))
        self.slippage_pct = float(self.storage.get_setting("paper_stock_opt_slippage_pct", 0.35))
        self.risk_per_trade_pct = float(self.storage.get_setting("paper_stock_opt_risk_pct", 2.0))
        self.simulation_engine.virtual_balance = self.virtual_capital
        self.simulation_engine.slippage_pct = self.slippage_pct

        # Armed candidate queue waiting for entry price / trigger confirmation
        self.armed_candidates: Dict[str, Dict[str, Any]] = {}
        self._load_persisted_armed_candidates()

    def _load_persisted_armed_candidates(self):
        """Loads any resting armed triggers from persistent SQLite settings."""
        try:
            persisted = self.storage.get_setting("paper_armed_candidates")
            if isinstance(persisted, dict):
                self.armed_candidates = persisted
            elif isinstance(persisted, list):
                self.armed_candidates = {str(item.get("symbol")): item for item in persisted if item.get("symbol")}
        except Exception as e:
            logger.debug(f"[PAPER_AGENT] Could not load persisted armed candidates: {e}")

    def _persist_armed_candidates(self):
        """Persists resting armed triggers into storage."""
        try:
            if self.storage:
                self.storage.save_setting("paper_armed_candidates", self.armed_candidates)
        except Exception as e:
            logger.debug(f"[PAPER_AGENT] Could not persist armed candidates: {e}")

    def get_armed_candidates(self) -> List[Dict[str, Any]]:
        """Returns list of currently armed stock setups waiting for entry."""
        return list(self.armed_candidates.values())

    def cancel_armed_candidate(self, symbol: str) -> Dict[str, Any]:
        """Cancels an armed setup before it triggers."""
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
            logger.info(f"[PAPER_AGENT] Armed setup for {sym} cancelled by user.")
            return {"status": "success", "message": f"Armed setup for {sym} cancelled."}
        return {"status": "not_found", "message": f"No armed setup found for {sym}."}

    def start(self):
        self.status = "RUNNING"
        self._ensure_monitor_task()
        logger.info("[PAPER_AGENT] Stock Options Paper Agent STARTED. Autonomous live bracket & PnL monitoring active.")

    def pause(self):
        self.status = "PAUSED"
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None
        logger.info("[PAPER_AGENT] Stock Options Paper Agent PAUSED.")

    def stop(self):
        self.status = "STOPPED"
        if self._monitor_task and not self._monitor_task.done():
            self._monitor_task.cancel()
            self._monitor_task = None
        logger.info("[PAPER_AGENT] Stock Options Paper Agent STOPPED.")

    def _ensure_monitor_task(self):
        """Ensures the background position monitor task is running."""
        if self.status == "RUNNING" and (self._monitor_task is None or self._monitor_task.done()):
            try:
                loop = asyncio.get_running_loop()
                self._monitor_task = loop.create_task(self._position_monitor_loop())
            except RuntimeError:
                pass

    async def _position_monitor_loop(self):
        """
        Autonomous Position Monitor:
        Runs in background every 3 seconds to poll live market prices, update
        unrealized P&L in real time, evaluate armed setups waiting for trigger,
        and automatically execute Stop-Loss, Target 1 take-profit, or 15:15 IST EOD square-offs.
        """
        logger.info("[PAPER_AGENT] 🚀 Autonomous real-time position & bracket monitor loop started.")
        while self.status == "RUNNING":
            try:
                await self._evaluate_armed_candidates()
                await self.update_open_positions_ltp()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PAPER_AGENT] Error in position monitor loop: {e}")
            await asyncio.sleep(3.0)

    async def _evaluate_armed_candidates(self):
        """
        Monitors armed stock option setups every tick.
        When spot crosses the entry trigger, executes the simulated trade fill.
        If spot breaches invalidation level, drops the setup.
        """
        if not self.armed_candidates:
            return

        cur_ist = datetime.now()
        is_testing = ("unittest" in sys.modules or "pytest" in sys.modules or os.environ.get("TESTING") == "1")
        is_past_cutoff = (not is_testing and is_market_hours(cur_ist) and cur_ist.time() >= dt_time(14, 30))

        symbols_to_remove = []
        for sym, item in list(self.armed_candidates.items()):
            candidate = item.get("candidate", {})
            plan_id = item.get("plan_id", "")

            # Strict 14:30 IST Cutoff during live market hours: expire un-triggered setups to prevent late-session theta burn
            if is_past_cutoff:
                logger.info(f"[PAPER_AGENT] ⏰ Armed candidate {sym} expired at 14:30 IST (Entry cutoff to prevent late-session theta decay).")
                symbols_to_remove.append(sym)
                if self.storage and plan_id:
                    try:
                        self.storage.update_plan_status(plan_id, "EXPIRED_ENTRY_CUTOFF", sym)
                    except Exception:
                        pass
                continue

            current_spot = 0.0
            if self.market_data:
                try:
                    if hasattr(self.market_data, "_get_active_stream_client"):
                        stream = self.market_data._get_active_stream_client()
                        stk_meta = NSE_FO_STOCKS.get(sym, {})
                        stk_tok = str(stk_meta.get("token_nse") or "").strip()
                        if stream and stk_tok and stk_tok not in stream.subscribed_tokens:
                            stream.subscribe(token=stk_tok, symbol=f"{sym}-EQ", exchange="NSE", mode=2)
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
                logger.warning(f"[PAPER_AGENT] 🛑 Armed setup {sym} INVALIDATED: {trig_reason}")
                symbols_to_remove.append(sym)
                if self.storage and plan_id:
                    try:
                        self.storage.update_plan_status(plan_id, "INVALIDATED", sym)
                    except Exception:
                        pass
                if self.notifier:
                    try:
                        self.notifier.send_message(f"⚠️ <b>Stock Option Setup Invalidated</b>\n{sym}: {trig_reason}")
                    except Exception:
                        pass
                continue

            if is_trig:
                logger.info(f"[PAPER_AGENT] 🎯 ENTRY TRIGGER CONFIRMED: {sym} -> {trig_reason}! Executing simulated fill...")
                symbols_to_remove.append(sym)
                try:
                    res = await self.execute_simulated_trade(candidate, plan_id=plan_id, force_immediate=True)
                    if self.storage and plan_id:
                        target_status = "AUTO_DISPATCHED_PAPER_FILLED" if res.get("status") == "success" else "EXECUTION_FAILED"
                        try:
                            self.storage.update_plan_status(plan_id, target_status, sym)
                        except Exception:
                            pass
                except Exception as ex:
                    logger.error(f"[PAPER_AGENT] Error executing triggered trade for {sym}: {ex}")
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
            "target_mode": "PAPER",
            "armed_at": datetime.now().isoformat(),
            "last_checked_at": datetime.now().isoformat()
        }

        self.armed_candidates[sym] = armed_item
        self._persist_armed_candidates()
        self._ensure_monitor_task()

        logger.info(
            f"[PAPER_AGENT] ⏳ ARMED CANDIDATE: {sym} ({armed_item['contract']}) | "
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
                    f"⏳ <b>Stock Option Setup Armed</b>\n"
                    f"Underlying: <b>{sym}</b>\n"
                    f"Contract: <code>{armed_item['contract']}</code>\n"
                    f"Current Spot: ₹{current_spot:.2f}\n"
                    f"Entry Trigger: <b>₹{entry_trigger:.2f}</b>\n"
                    f"Mode: <b>PAPER (Simulation)</b>\n"
                    f"Waiting for breakout confirmation before placing simulated order."
                )
            except Exception:
                pass

        return {
            "status": "armed",
            "message": f"Setup for {sym} armed. Monitoring exchange spot (Current: ₹{current_spot:.2f}, Trigger: ₹{entry_trigger:.2f}).",
            "armed_item": armed_item
        }

    async def update_open_positions_ltp(self) -> List[Dict[str, Any]]:
        """
        Fetches live option prices from exchange for all open simulated positions,
        updates floating PnL, and autonomously triggers bracket exits (SL, TP, EOD).
        Returns the updated positions list.
        """
        positions = self.storage.get_positions(is_paper=True, open_only=True)
        if not positions:
            return []

        from datetime import time as dt_time
        cur_ist = datetime.now()
        is_eod_time = (dt_time(15, 15) <= cur_ist.time() <= dt_time(15, 30))

        updated_list = []
        for pos in positions:
            sym = pos["symbol"]
            qty = int(pos.get("quantity") or 0)
            entry_p = float(pos.get("entry_price") or 0.0)
            sl = float(pos.get("stop_loss") or 0.0)
            t1 = float(pos.get("target_1") or 0.0)
            underlying = pos.get("underlying") or ""
            tok = pos.get("token") or pos.get("symboltoken") or pos.get("instrument_token") or ""
            opt_type = pos.get("option_type") or ("CE" if "CE" in sym else "PE")
            strike = float(pos.get("strike") or pos.get("strike_price") or 0.0)

            # 1. Fetch current live option LTP
            current_ltp = 0.0
            if self.market_data:
                try:
                    # Auto-subscribe open position contract to WebSocket stream
                    if tok and hasattr(self.market_data, "_get_active_stream_client"):
                        stream = self.market_data._get_active_stream_client()
                        if stream and str(tok).isdigit() and str(tok) not in stream.subscribed_tokens:
                            try:
                                stream.subscribe(token=str(tok), symbol=sym, exchange="NFO", mode=2)
                            except Exception:
                                pass

                    current_ltp = self.market_data.get_option_ltp(
                        symbol=sym,
                        underlying=underlying,
                        token=tok,
                        strike=strike,
                        option_type=opt_type,
                        allow_modeled=False
                    )
                except Exception as e:
                    logger.debug(f"[PAPER_AGENT] Failed to fetch LTP for {sym}: {e}")

            if current_ltp <= 0:
                current_ltp = float(pos.get("current_ltp") or entry_p)

            # 2. Compute Floating Real-time PnL
            unrealized_pnl = round((current_ltp - entry_p) * qty, 2)
            unrealized_pnl_pct = round(((current_ltp - entry_p) / entry_p) * 100.0, 2) if entry_p > 0 else 0.0

            # 3. Persist updated live price and PnL
            self.storage.update_position_ltp(
                symbol=sym,
                is_paper=True,
                current_ltp=current_ltp,
                unrealized_pnl=unrealized_pnl
            )

            pos["current_ltp"] = current_ltp
            pos["unrealized_pnl"] = unrealized_pnl
            pos["unrealized_pnl_pct"] = unrealized_pnl_pct

            # 4. Autonomous Institutional Bracket Triggers
            # 4a. Institutional Breakeven Protection Shift (Risk Elimination at +0.85R)
            be_threshold = entry_p + (entry_p - sl) * 0.85 if sl < entry_p else entry_p * 1.12
            if current_ltp >= be_threshold and sl < entry_p:
                new_sl = round(entry_p * 1.005, 2)
                pos["stop_loss"] = new_sl
                sl = new_sl
                self.storage.update_position_brackets(sym, is_paper=True, stop_loss=new_sl, target_1=t1)
                logger.info(f"[PAPER_AGENT] 🛡️ BREAKEVEN ENGAGED for {sym}: LTP ₹{current_ltp} >= Threshold ₹{be_threshold:.2f}. Stop-Loss raised to ₹{new_sl} (Capital Protected).")

            # 4b. Stop Loss (LTP <= Stop Loss for option buyers)
            if sl > 0 and current_ltp <= sl:
                logger.warning(f"[PAPER_AGENT] 🛑 AUTO STOP-LOSS TRIGGERED: {sym} LTP ₹{current_ltp} <= SL ₹{sl}. Auto-liquidating virtual position.")
                self.close_simulated_position(
                    symbol=sym,
                    exit_nominal_price=current_ltp,
                    reason=f"Auto Stop-Loss Hit (SL: ₹{sl}, Exit: ₹{current_ltp})"
                )
                continue

            # Multi-Tranche Exits: Partial Profit Booking at Target 1 (1:2.0 R:R)
            if t1 > 0 and current_ltp >= t1:
                lots = int(pos.get("lots") or 1)
                tranche = int(pos.get("tranche_stage") or 0)
                if lots >= 2 and tranche == 0:
                    # Book 50% lots at Target 1, shift SL to Breakeven, trail remaining to Target 2
                    close_lots = lots // 2
                    lot_size = int(pos.get("lot_size") or 1)
                    close_qty = close_lots * lot_size
                    entry_p = float(pos.get("entry_price") or current_ltp)
                    breakeven_sl = round(entry_p + 0.05, 2)
                    runner_target = float(pos.get("target_2") or 0.0)
                    if runner_target <= current_ltp:
                        unit_risk = max(0.5, entry_p - float(pos.get("stop_loss") or entry_p * 0.88))
                        runner_target = round(entry_p + (unit_risk * 3.0), 2)

                    logger.info(
                        f"[PAPER_AGENT] 🎯 PARTIAL TARGET 1 HIT: {sym} LTP ₹{current_ltp} >= Target ₹{t1}. "
                        f"Booking 50% ({close_lots} lot(s)), raising SL to Breakeven ₹{breakeven_sl}, trailing remainder to T2 ₹{runner_target}."
                    )
                    self.partially_close_simulated_position(
                        symbol=sym,
                        closed_qty=close_qty,
                        exit_nominal_price=current_ltp,
                        new_sl=breakeven_sl,
                        new_target=runner_target,
                        reason=f"Partial Target 1 Hit (T1: ₹{t1}, Booked {close_lots} lot(s))"
                    )
                    continue
                else:
                    reason_txt = f"Auto Target 2 Hit (T2: ₹{t1}, Exit: ₹{current_ltp})" if tranche >= 1 else f"Auto Target 1 Hit (T1: ₹{t1}, Exit: ₹{current_ltp})"
                    logger.info(f"[PAPER_AGENT] 🎯 AUTO TARGET TRIGGERED: {sym} LTP ₹{current_ltp} >= Target ₹{t1}. Auto-liquidating virtual position for profit.")
                    self.close_simulated_position(
                        symbol=sym,
                        exit_nominal_price=current_ltp,
                        reason=reason_txt
                    )
                    continue

            # EOD Auto Square-off at 15:15 IST
            if is_eod_time:
                logger.info(f"[PAPER_AGENT] ⏰ AUTO EOD SQUARE-OFF (15:15 IST): Liquidating {sym} @ ₹{current_ltp}.")
                self.close_simulated_position(
                    symbol=sym,
                    exit_nominal_price=current_ltp,
                    reason="EOD Auto Square-off (15:15 IST)"
                )
                continue

            updated_list.append(pos)

        return updated_list


    def update_settings(
        self,
        virtual_capital: Optional[float] = None,
        slippage_pct: Optional[float] = None,
        risk_per_trade_pct: Optional[float] = None
    ):
        """Updates paper simulation parameters independently of live settings."""
        if virtual_capital is not None and virtual_capital > 0:
            self.virtual_capital = virtual_capital
            self.simulation_engine.virtual_balance = virtual_capital
            self.storage.save_setting("paper_stock_opt_capital", virtual_capital)

        if slippage_pct is not None and slippage_pct >= 0:
            self.slippage_pct = slippage_pct
            self.simulation_engine.slippage_pct = slippage_pct
            self.storage.save_setting("paper_stock_opt_slippage_pct", slippage_pct)

        if risk_per_trade_pct is not None and risk_per_trade_pct > 0:
            self.risk_per_trade_pct = risk_per_trade_pct
            self.storage.save_setting("paper_stock_opt_risk_pct", risk_per_trade_pct)

        logger.info(
            f"[PAPER_AGENT] Updated independent paper settings: Capital=₹{self.virtual_capital}, "
            f"Slippage={self.slippage_pct}%, RiskPerTrade={self.risk_per_trade_pct}%"
        )

    def reset_paper_ledger(self, reset_capital: Optional[float] = None):
        """Resets virtual paper capital and trade logs after confirmation."""
        new_cap = reset_capital if (reset_capital and reset_capital > 0) else 500000.0
        self.virtual_capital = new_cap
        self.simulation_engine.virtual_balance = new_cap
        self.storage.save_setting("paper_stock_opt_capital", new_cap)
        self.storage.reset_paper_history()
        logger.info(f"[PAPER_AGENT] Virtual paper ledger reset with ₹{new_cap:.2f} capital.")

    async def execute_simulated_trade(
        self,
        candidate: Dict[str, Any],
        plan_id: str = "",
        force_immediate: bool = False
    ) -> Dict[str, Any]:
        """
        Simulates execution with independent paper rules.
        NEVER contacts the broker or places real orders.
        If force_immediate is False and entry trigger has not been breached,
        arms the candidate in the pending watchlist to wait for entry price.
        """
        if self.status != "RUNNING":
            return {"status": "error", "message": f"Paper Agent is in {self.status} mode."}

        async with self._lock:
            # 1. Validation (Independent of live market hours so paper testing can be simulated anytime)
            sym = candidate.get("symbol", "").upper()
            contract = candidate.get("primary_contract", {})
            indicative_prem = float(contract.get("indicative_premium", 10.0))
            tech = candidate.get("technical", {})

            # Query real live market spot price
            spot = 0.0
            if self.market_data:
                try:
                    spot = self.market_data.get_spot_ltp(sym)
                except Exception:
                    pass
            default_spot = NSE_FO_STOCKS.get(sym, {}).get("base_price", 1000.0)
            ref_p = float(tech.get("reference_price") or tech.get("entry_trigger") or 0.0)
            if (spot <= 0 or (spot == default_spot and ref_p > 0 and abs(ref_p - default_spot) / max(1.0, ref_p) > 0.01)):
                spot = ref_p or default_spot
            elif spot <= 0:
                spot = ref_p or default_spot

            # 2. Check conditional trigger confirmation unless force_immediate is True
            if not force_immediate:
                # 14:30 IST Entry Cutoff Guard: Block late afternoon entries during live market hours
                now_dt = datetime.now()
                is_testing = ("unittest" in sys.modules or "pytest" in sys.modules or os.environ.get("TESTING") == "1")
                if not is_testing and is_market_hours(now_dt) and now_dt.time() >= dt_time(14, 30):
                    logger.warning(f"[PAPER_AGENT] Rejected {sym}: Entry cutoff reached (14:30 IST). Intraday option buying is closed to prevent late-session theta decay.")
                    return {"status": "rejected", "reason": "Entry cutoff reached (14:30 IST). Intraday option buying is closed."}

                # Concurrent open positions cap (default 3)
                max_sim_positions = int(self.storage.get_setting("max_concurrent_paper_positions") or 3)
                current_open = self.storage.get_positions(is_paper=True, open_only=True)
                if len(current_open) >= max_sim_positions:
                    logger.warning(f"[PAPER_AGENT] Rejected {sym}: Maximum open paper positions limit reached ({len(current_open)}/{max_sim_positions}).")
                    return {"status": "rejected", "reason": f"Maximum open paper positions limit reached ({len(current_open)}/{max_sim_positions})."}

                # Prevent duplicate active positions in the same underlying
                if any(p.get("underlying") == sym for p in current_open):
                    logger.warning(f"[PAPER_AGENT] Rejected {sym}: Position in {sym} is already active.")
                    return {"status": "rejected", "reason": f"Position in {sym} is already active."}

                is_trig, is_inval, trig_reason = check_trigger_status(candidate, spot)
                if is_inval:
                    logger.warning(f"[PAPER_AGENT] Candidate {sym} rejected at submission: {trig_reason}")
                    return {"status": "rejected", "reason": trig_reason}

                if not is_trig:
                    # Stock has not reached entry trigger yet -> Arm it and wait for entry price!
                    return self.arm_candidate(candidate, plan_id=plan_id, current_spot=spot, reason=trig_reason)

            # 3. If triggered or force_immediate: remove from armed candidates if present
            self.armed_candidates.pop(sym, None)
            self._persist_armed_candidates()

            # Query real live market LTP if market_data service is available
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
                    logger.debug(f"[PAPER_AGENT] Live option LTP query failed for {sym}: {ex}")

            is_valid, reason, params = self.validator.validate_candidate_for_execution(
                candidate=candidate,
                current_spot=spot,
                current_option_ltp=indicative_prem,
                bid_price=indicative_prem * 0.99,
                ask_price=indicative_prem * 1.01,
                is_paper=True
            )

            if not is_valid:
                return {"status": "rejected", "reason": reason}

            # 2. Simulated Sizing & Fill via Simulation Engine
            lot_sz = params["lot_size"]
            configured_lots = int(self.storage.get_setting("stock_options_default_lots") or 1)
            lots = int(candidate.get("lots") or configured_lots or 1)
            qty = lot_sz * lots
            cost_estimate = qty * params["entry_price"]
            if lots > 1 and cost_estimate > (self.simulation_engine.virtual_balance * 0.45):
                lots = 1
                qty = lot_sz

            fill_result = self.simulation_engine.simulate_order_fill(
                symbol=params["symbol"],
                transaction_type="BUY",
                quantity=qty,
                nominal_price=params["entry_price"]
            )

            executed_entry = fill_result["executed_price"]
            cost = fill_result["trade_value"] + fill_result["charges"]

            if cost > self.simulation_engine.virtual_balance:
                return {
                    "status": "rejected",
                    "reason": f"Insufficient virtual paper capital (Required: ₹{cost:.2f}, Available: ₹{self.simulation_engine.virtual_balance:.2f})."
                }

            # Deduct virtual capital
            self.simulation_engine.virtual_balance -= cost

            # 3. Record simulated order
            order_id = f"SIM_ORD_{int(time.time() * 1000)}"
            order_record = {
                "order_id": order_id,
                "plan_id": plan_id,
                "symbol": params["symbol"],
                "underlying": params["underlying"],
                "option_type": params["option_type"],
                "strike": params["strike"],
                "expiry": params["expiry"],
                "transaction_type": "BUY",
                "order_type": "LIMIT",
                "quantity": qty,
                "price": params["entry_price"],
                "trigger_price": 0.0,
                "status": "FILLED",
                "filled_qty": qty,
                "average_price": executed_entry,
                "is_paper": True,
                "execution_mode": "PAPER"
            }
            self.storage.save_order(order_record)

            # 4. Record simulated position with brackets anchored to actual executed fill
            exec_sl = params["stop_loss"] if params["stop_loss"] < executed_entry else round(executed_entry * 0.88, 2)
            exec_t1 = params["target_1"] if params["target_1"] > executed_entry else round(executed_entry + ((executed_entry - exec_sl) * 2.0), 2)
            exec_t2 = params.get("target_2") or round(executed_entry + ((executed_entry - exec_sl) * 3.0), 2)

            pos_record = {
                "symbol": params["symbol"],
                "underlying": params["underlying"],
                "token": params.get("token", ""),
                "option_type": params["option_type"],
                "strike": params["strike"],
                "expiry": params["expiry"],
                "quantity": qty,
                "lot_size": lot_sz,
                "lots": lots,
                "entry_price": executed_entry,
                "current_ltp": executed_entry,
                "stop_loss": exec_sl,
                "target_1": exec_t1,
                "target_2": exec_t2,
                "tranche_stage": 0,
                "is_open": True,
                "is_paper": True,
                "execution_mode": "PAPER",
                "entry_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            self.storage.save_position(pos_record)
            self._ensure_monitor_task()

            # Subscribe to real-time WebSocket ticks for position
            try:
                if hasattr(self.market_data, "_get_active_stream_client"):
                    stream = self.market_data._get_active_stream_client()
                    c_tok = str(params.get("token") or "").strip()
                    if stream and c_tok and c_tok.isdigit():
                        stream.subscribe(token=c_tok, symbol=params["symbol"], exchange="NFO", mode=2)
            except Exception as e:
                logger.debug(f"[PAPER_AGENT] Auto-subscribe for executed position failed: {e}")

            logger.info(
                f"[PAPER_AGENT] ✅ Virtual trade executed: {params['symbol']} Qty={qty} "
                f"Fill=₹{executed_entry} (Slippage: {fill_result['slippage_points']} pts)."
            )

            if self.notifier:
                try:
                    self.notifier.notify_trade_entry({
                        "symbol": params["symbol"],
                        "strategy_name": f"StockOpt_{candidate.get('setup_type', 'Momentum')}",
                        "lots": 1,
                        "quantity": qty,
                        "entry_price": executed_entry,
                        "slippage_points": fill_result.get("slippage_points", 0.0),
                        "stop_loss": params["stop_loss"],
                        "target_1": params["target_1"],
                        "mode": "PAPER"
                    })
                except Exception as e:
                    logger.warning(f"[PAPER_AGENT] Telegram notification error: {e}")

            return {
                "status": "success",
                "message": f"Simulated fill for {params['symbol']} @ ₹{executed_entry}",
                "order": order_record,
                "fill": fill_result,
                "remaining_virtual_capital": self.simulation_engine.virtual_balance
            }

    def close_simulated_position(self, symbol: str, exit_nominal_price: float, reason: str = "Manual Exit"):
        """Simulates exit with slippage and records completed paper trade."""
        positions = self.storage.get_positions(is_paper=True, open_only=True)
        target = next((p for p in positions if p["symbol"] == symbol), None)
        if not target:
            return {"status": "error", "message": f"No open paper position found for {symbol}."}

        qty = target["quantity"]
        fill_result = self.simulation_engine.simulate_order_fill(
            symbol=symbol,
            transaction_type="SELL",
            quantity=qty,
            nominal_price=exit_nominal_price
        )

        exec_exit = fill_result["executed_price"]
        proceeds = fill_result["trade_value"] - fill_result["charges"]
        self.simulation_engine.virtual_balance += proceeds

        self.storage.close_position(
            symbol=symbol,
            is_paper=True,
            exit_price=exec_exit,
            exit_reason=reason
        )

        entry_p = float(target.get("entry_price") or 0.0)
        gross_pnl = round((exec_exit - entry_p) * qty, 2)
        charges = float(fill_result.get("charges") or 20.0)
        net_pnl = round(gross_pnl - charges, 2)
        if self.notifier:
            try:
                self.notifier.notify_trade_exit({
                    "symbol": symbol,
                    "entry_price": entry_p,
                    "exit_price": exec_exit,
                    "quantity": qty,
                    "gross_pnl": gross_pnl,
                    "total_charges": charges,
                    "net_pnl": net_pnl,
                    "reason": reason,
                    "mode": "PAPER",
                    "strategy_name": "StockOptions_Paper"
                })
            except Exception as e:
                logger.warning(f"[PAPER_AGENT] Telegram exit alert error: {e}")

        logger.info(f"[PAPER_AGENT] Closed virtual position {symbol} @ ₹{exec_exit} ({reason}).")
        return {"status": "success", "exit_price": exec_exit, "proceeds": proceeds}

    def partially_close_simulated_position(
        self,
        symbol: str,
        closed_qty: int,
        exit_nominal_price: float,
        new_sl: float,
        new_target: float,
        reason: str = "Partial Target 1 Hit"
    ) -> Dict[str, Any]:
        """Executes a partial simulated exit (e.g. 50% lots), moves SL to Breakeven, and trails remainder to T2."""
        positions = self.storage.get_positions(is_paper=True, open_only=True)
        target = next((p for p in positions if p["symbol"] == symbol), None)
        if not target:
            return {"status": "error", "message": f"No open paper position found for {symbol}."}

        fill_result = self.simulation_engine.simulate_order_fill(
            symbol=symbol,
            transaction_type="SELL",
            quantity=closed_qty,
            nominal_price=exit_nominal_price
        )

        exec_exit = fill_result["executed_price"]
        proceeds = fill_result["trade_value"] - fill_result["charges"]
        self.simulation_engine.virtual_balance += proceeds

        res = self.storage.partially_close_position(
            symbol=symbol,
            is_paper=True,
            closed_qty=closed_qty,
            exit_price=exec_exit,
            new_sl=new_sl,
            new_target=new_target,
            exit_reason=reason
        )

        entry_p = float(target.get("entry_price") or 0.0)
        gross_pnl = round((exec_exit - entry_p) * closed_qty, 2)
        charges = float(fill_result.get("charges") or 20.0)
        net_pnl = round(gross_pnl - charges, 2)

        if self.notifier:
            try:
                self.notifier.send_message(
                    f"🎯 <b>PARTIAL TARGET 1 HIT (+1:2.0 R:R)</b>\n\n"
                    f"Symbol: <b>{symbol}</b>\n"
                    f"Booked 50%: <b>{closed_qty} Qty @ ₹{exec_exit:.2f}</b>\n"
                    f"Realized PnL: <b>+₹{net_pnl:,.2f}</b> (Charges: ₹{charges:.2f})\n\n"
                    f"🛡️ <b>Risk Lock:</b> Stop-Loss moved to Breakeven <b>₹{new_sl:.2f}</b> (Zero Risk)\n"
                    f"🚀 <b>Runner Mode:</b> Remaining {res.get('remaining_qty', 0)} Qty trailing to Target 2 <b>₹{new_target:.2f}</b>"
                )
            except Exception as e:
                logger.warning(f"[PAPER_AGENT] Telegram partial exit alert error: {e}")

        logger.info(f"[PAPER_AGENT] Partially closed virtual position {symbol}: {closed_qty} qty @ ₹{exec_exit} ({reason}).")
        return {"status": "success", "exit_price": exec_exit, "proceeds": proceeds, "pnl": net_pnl}
