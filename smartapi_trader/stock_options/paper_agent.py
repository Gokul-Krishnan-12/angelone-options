"""
Stock Options Paper Trading Agent & Isolated Simulation Engine.
Strictly isolated from live broker execution. Can NEVER place real orders.
Maintains independent virtual capital, simulated fills, slippage, and P&L ledger.
NOT blocked by live risk manager limits.
"""

import time
import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from smartapi_trader.stock_options.storage import StockOptionsStorage
from smartapi_trader.stock_options.validator import StockOptionsValidator
from smartapi_trader.stock_options.universe import NSE_FO_STOCKS
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
        unrealized P&L in real time, and automatically execute Stop-Loss,
        Target 1 take-profit, or 15:15 IST EOD square-offs.
        """
        logger.info("[PAPER_AGENT] 🚀 Autonomous real-time position & bracket monitor loop started.")
        while self.status == "RUNNING":
            try:
                await self.update_open_positions_ltp()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PAPER_AGENT] Error in position monitor loop: {e}")
            await asyncio.sleep(3.0)

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
        is_eod_time = (cur_ist.time() >= dt_time(15, 15))

        updated_list = []
        for pos in positions:
            sym = pos["symbol"]
            qty = int(pos.get("quantity") or 0)
            entry_p = float(pos.get("entry_price") or 0.0)
            sl = float(pos.get("stop_loss") or 0.0)
            t1 = float(pos.get("target_1") or 0.0)
            underlying = pos.get("underlying") or ""
            tok = pos.get("token") or ""
            opt_type = pos.get("option_type") or ("CE" if "CE" in sym else "PE")
            strike = float(pos.get("strike") or 0.0)

            # 1. Fetch current live option LTP
            current_ltp = 0.0
            if self.market_data:
                try:
                    current_ltp = self.market_data.get_option_ltp(
                        symbol=sym,
                        underlying=underlying,
                        token=tok,
                        strike=strike,
                        option_type=opt_type
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

            # 4. Autonomous Bracket Triggers
            # Stop Loss (LTP <= Stop Loss for option buyers)
            if sl > 0 and current_ltp <= sl:
                logger.warning(f"[PAPER_AGENT] 🛑 AUTO STOP-LOSS TRIGGERED: {sym} LTP ₹{current_ltp} <= SL ₹{sl}. Auto-liquidating virtual position.")
                self.close_simulated_position(
                    symbol=sym,
                    exit_nominal_price=current_ltp,
                    reason=f"Auto Stop-Loss Hit (SL: ₹{sl}, Exit: ₹{current_ltp})"
                )
                continue

            # Target 1 (LTP >= Target 1 for option buyers)
            if t1 > 0 and current_ltp >= t1:
                logger.info(f"[PAPER_AGENT] 🎯 AUTO TARGET TRIGGERED: {sym} LTP ₹{current_ltp} >= Target ₹{t1}. Auto-liquidating virtual position for profit.")
                self.close_simulated_position(
                    symbol=sym,
                    exit_nominal_price=current_ltp,
                    reason=f"Auto Target 1 Hit (T1: ₹{t1}, Exit: ₹{current_ltp})"
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

    async def execute_simulated_trade(self, candidate: Dict[str, Any], plan_id: str = "") -> Dict[str, Any]:
        """
        Simulates execution with independent paper rules.
        NEVER contacts the broker or places real orders.
        """
        if self.status != "RUNNING":
            return {"status": "error", "message": f"Paper Agent is in {self.status} mode."}

        async with self._lock:
            # 1. Validation (Independent of live market hours so paper testing can be simulated anytime)
            sym = candidate.get("symbol", "").upper()
            contract = candidate.get("primary_contract", {})
            indicative_prem = float(contract.get("indicative_premium", 10.0))
            tech = candidate.get("technical", {})
            default_spot = NSE_FO_STOCKS.get(sym, {}).get("base_price", 1000.0)
            spot = float(tech.get("reference_price") or tech.get("entry_trigger") or default_spot)

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
            qty = params["lot_size"]
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

            # 4. Record simulated position
            pos_record = {
                "symbol": params["symbol"],
                "underlying": params["underlying"],
                "token": params.get("token", ""),
                "option_type": params["option_type"],
                "strike": params["strike"],
                "expiry": params["expiry"],
                "quantity": qty,
                "lot_size": qty,
                "lots": 1,
                "entry_price": executed_entry,
                "current_ltp": executed_entry,
                "stop_loss": params["stop_loss"],
                "target_1": params["target_1"],
                "is_open": True,
                "is_paper": True,
                "execution_mode": "PAPER"
            }
            self.storage.save_position(pos_record)
            self._ensure_monitor_task()

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
