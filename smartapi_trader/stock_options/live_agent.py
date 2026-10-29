"""
Stock Options Live Trading Agent.
Executes real-money stock-options trades using the existing broker integration
(Angel One SmartAPI) and mandatory existing RiskManager.
"""

import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.events import SignalEvent, OrderEvent, PositionEvent
from smartapi_trader.risk.risk_manager import RiskManager
from smartapi_trader.execution.live_smartapi import LiveSmartAPIExecutionEngine
from smartapi_trader.stock_options.storage import StockOptionsStorage
from smartapi_trader.stock_options.validator import StockOptionsValidator
from smartapi_trader.utils.logger import logger


class StockOptionsLiveAgent:
    """
    Real-money Stock Options Trading Agent.
    Submits trades strictly through the mandatory RiskManager and LiveSmartAPIExecutionEngine.
    """

    def __init__(
        self,
        event_bus: EventBus,
        risk_manager: RiskManager,
        live_engine: LiveSmartAPIExecutionEngine,
        storage: StockOptionsStorage,
        validator: Optional[StockOptionsValidator] = None,
        notifier: Optional[Any] = None
    ):
        self.bus = event_bus
        self.risk_manager = risk_manager
        self.live_engine = live_engine
        self.storage = storage
        self.validator = validator or StockOptionsValidator()
        self.notifier = notifier

        self.status = "IDLE"  # "IDLE", "RUNNING", "PAUSED", "STOPPED"
        self.auto_execute = False
        self._lock = asyncio.Lock()

    def start(self):
        self.status = "RUNNING"
        logger.info("[LIVE_AGENT] Stock Options Live Agent STARTED. RMS enforcement active.")

    def pause(self):
        self.status = "PAUSED"
        logger.info("[LIVE_AGENT] Stock Options Live Agent PAUSED. New entries blocked.")

    def stop(self):
        self.status = "STOPPED"
        logger.info("[LIVE_AGENT] Stock Options Live Agent STOPPED.")

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

    async def execute_approved_candidate(self, candidate: Dict[str, Any], plan_id: str = "") -> Dict[str, Any]:
        """
        Validates candidate deterministically, checks against mandatory RiskManager,
        and submits real order to Angel One.
        """
        if self.status != "RUNNING":
            return {"status": "error", "message": f"Agent is in {self.status} mode. Must be RUNNING to execute trades."}

        async with self._lock:
            # 1. Deterministic Pre-Flight Validation
            sym = candidate.get("symbol", "").upper()
            contract = candidate.get("primary_contract", {})
            indicative_prem = float(contract.get("indicative_premium", 10.0))
            tech = candidate.get("technical", {})
            from smartapi_trader.stock_options.universe import NSE_FO_STOCKS
            default_spot = NSE_FO_STOCKS.get(sym, {}).get("base_price", 1000.0)
            spot = float(tech.get("reference_price") or tech.get("entry_trigger") or default_spot)


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
                "execution_mode": "LIVE"
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
