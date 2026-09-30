import math
from datetime import datetime, time
from typing import Dict, Any, Optional, Tuple
from smartapi_trader.core.events import (
    SignalEvent, OrderEvent, PositionEvent, TickEvent, RiskAlertEvent, EventType
)
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.state_manager import StateManager
from smartapi_trader.utils.logger import logger
from smartapi_trader.utils.tz import ist_time

class RiskManager:
    """
    Mathematical Capital Preservation & Multi-Stage Bracket Engine.
    
    Enforces:
    - Fixed fractional 1.5% risk per trade sizing: Lots = floor( (Equity * 0.015) / (UnitRisk * LotSize) )
    - Max 2 trades per day limit
    - Max 3.0% daily drawdown circuit breaker
    - Consecutive loss circuit breaker (2 losses)
    - Midday chop filter (11:15 - 13:30 IST)
    - Mandatory 15:12 IST square-off
    - Dynamic trailing: Breakeven at +1.0R, partial 60% exit at +2.0R, trail 40% remainder
    """
    def __init__(
        self,
        event_bus: EventBus,
        state_manager: StateManager,
        config: Dict[str, Any],
        notifier: Optional[Any] = None,
        live_engine: Optional[Any] = None,
        paper_engine: Optional[Any] = None
    ):
        self.bus = event_bus
        self.state_mgr = state_manager
        self.cfg = config.get("risk", {})
        self.notifier = notifier
        self.live_engine = live_engine
        self.paper_engine = paper_engine
        
        self.risk_pct = self.cfg.get("risk_per_trade_pct", 0.015)       # 1.5%
        self.max_drawdown_pct = self.cfg.get("max_daily_drawdown_pct", 0.03) # 3.0%
        self.max_trades = self.cfg.get("max_trades_per_day", 2)
        self.consecutive_loss_limit = self.cfg.get("consecutive_loss_limit", 2)
        self.be_trigger_r = self.cfg.get("breakeven_trigger_r", 1.0)
        self.tp1_r = self.cfg.get("partial_exit_r", 2.0)
        self.tp1_qty_pct = self.cfg.get("partial_exit_qty_pct", 0.60)
        self.max_slippage_pct = config.get("execution", {}).get("max_slippage_pct", 2.0)

        # Wire up listeners
        self.bus.subscribe(EventType.SIGNAL, self._on_signal)
        self.bus.subscribe(EventType.TICK, self._on_tick)

    def set_engines(self, live_engine: Any, paper_engine: Any):
        self.live_engine = live_engine
        self.paper_engine = paper_engine

    def _get_active_engine(self):
        if self.state_mgr.execution_mode == "LIVE":
            return self.live_engine
        return self.paper_engine

    @staticmethod
    def _round_to_tick(price: float, tick_size: float = 0.05) -> float:
        return round(round(float(price) / tick_size) * tick_size, 2)

    async def _on_signal(self, signal: SignalEvent):
        """Validates incoming signal against risk constraints and calculates lot sizing."""
        logger.info(f"[RISK] Validating signal {signal.signal_id} for {signal.tradingsymbol}...")

        # 1. System Halt or Emergency Panic
        if self.state_mgr.is_panic_active or self.state_mgr.is_halted:
            self._raise_alert("WARNING", "Panic/Halted", "Order rejected: System is in PANIC or HALT mode.")
            return

        # 2. Daily Trade Budget Check
        is_paper = (self.state_mgr.execution_mode == "PAPER") or getattr(signal, "is_paper", False)
        trades_count = self.state_mgr.paper_trades_taken if is_paper else self.state_mgr.trades_taken_today
        if trades_count >= self.max_trades:
            self._raise_alert("WARNING", "MaxTradesLimit", f"Daily trade quota reached ({trades_count}/{self.max_trades}).")
            return

        # 3. Consecutive Loss Circuit Breaker
        if self.state_mgr.consecutive_losses >= self.consecutive_loss_limit:
            self._raise_alert("CRITICAL", "ConsecutiveLossLock", f"Consecutive loss circuit tripped ({self.state_mgr.consecutive_losses} losses). System locked for the day.")
            return

        # 4. Daily Drawdown Circuit Breaker (3.0%)
        current_drawdown = self.state_mgr.daily_drawdown_pct / 100.0
        if current_drawdown >= self.max_drawdown_pct:
            self._raise_alert("CRITICAL", "MaxDrawdownBreach", f"Drawdown ({current_drawdown:.1%}) exceeds 3.0% hard threshold! System halted.")
            self.state_mgr.trigger_panic()
            return

        # 5. Time Constraints (Strict 15:00 Entry Cut-off & Midday Chop)
        now_time = ist_time()
        # Midday chop filter
        if time(11, 15) <= now_time <= time(13, 30):
            self._raise_alert("WARNING", "MiddayChopFilter", "Order rejected: Midday consolidation window (11:15-13:30 IST).")
            return

        # Strict entry cut-off (15:00 IST) - No new positions entered within 30 min of close
        if now_time >= time(15, 0):
            self._raise_alert("WARNING", "EODCutoff", "Order rejected: Past entry cut-off time (15:00 IST). Taking trades after 3:00 PM is restricted due to close risk.")
            return

        # 6. Sizing Formulation
        equity = self.state_mgr.paper_capital if is_paper else self.state_mgr.equity
        available_margin = self.state_mgr.paper_available_margin if is_paper else self.state_mgr.available_margin
        capital_at_risk = equity * self.risk_pct
        unit_risk = signal.entry_price - signal.stop_loss

        if unit_risk <= 0:
            self._raise_alert("WARNING", "InvalidUnitRisk", f"Invalid unit risk ({unit_risk}). Stop loss must be below entry price.")
            return

        lot_size = signal.lot_size
        risk_per_lot = unit_risk * lot_size
        lots = math.floor(capital_at_risk / risk_per_lot)

        if lots < 1:
            # Allow minimum 1 lot for both REAL and PAPER if available margin covers the contract
            # and single-lot risk does not exceed the maximum daily drawdown limit (3.0% of equity)
            margin_req = signal.entry_price * lot_size
            max_tolerable_risk = equity * self.max_drawdown_pct
            if margin_req <= available_margin and risk_per_lot <= max_tolerable_risk:
                lots = 1
                logger.info(f"[RISK] Minimum 1 lot permitted for {signal.underlying} (Margin: ₹{margin_req:.2f} <= ₹{available_margin:.2f}, Risk: ₹{risk_per_lot:.2f} <= ₹{max_tolerable_risk:.2f}).")
            else:
                reason = "Margin insufficient" if margin_req > available_margin else f"Single lot risk (₹{risk_per_lot:.2f}) exceeds max daily risk (₹{max_tolerable_risk:.2f})"
                self._raise_alert("WARNING", "InsufficientRiskCapital", f"Order rejected: {reason}. Required: ₹{margin_req:.2f}, Available: ₹{available_margin:.2f}.")
                return

        total_quantity = lots * lot_size
        margin_required = signal.entry_price * total_quantity

        if margin_required > available_margin:
            self._raise_alert("WARNING", "MarginExhaustion", f"Required margin (₹{margin_required:.2f}) exceeds available (₹{available_margin:.2f}).")
            return

        logger.info(f"[RISK] Order APPROVED: {signal.tradingsymbol} Lots={lots} (Qty={total_quantity}) Risk=₹{capital_at_risk:.2f} Margin=₹{margin_required:.2f}")

        # Construct and submit validated order
        order_event = OrderEvent(
            order_id=f"ORD_{signal.underlying}_{int(datetime.now().timestamp() * 1000)}",
            symbol=signal.tradingsymbol,
            token=signal.symboltoken,
            exchange=signal.exchange,
            transaction_type="BUY",
            order_type="LIMIT",
            product_type="INTRADAY",
            quantity=total_quantity,
            price=signal.entry_price,
            trigger_price=0.0,
            status="PENDING",
            variety="NORMAL"
        )
        
        # Save position expectation metadata for multi-stage bracket tracking
        pos_event = PositionEvent(
            symbol=signal.tradingsymbol,
            token=signal.symboltoken,
            underlying=signal.underlying,
            option_type=signal.option_type,
            strike_price=getattr(signal, 'strike', 0.0),
            quantity=total_quantity,
            lot_size=signal.lot_size,
            lots=lots,
            entry_price=signal.entry_price,
            current_ltp=signal.entry_price,
            stop_loss=signal.stop_loss,
            target_1=signal.target_1,
            exchange=signal.exchange,
            swing_invalidation_level=getattr(signal, "swing_invalidation_level", 0.0),
            is_open=True,
            is_paper=(self.state_mgr.execution_mode == "PAPER"),
            execution_mode=self.state_mgr.execution_mode
        )
        await self.bus.publish(pos_event)
        await self.bus.publish(order_event)

        # Immediately place protective Native Exchange Stop-Loss Limit order on broker
        await self._place_exchange_stop_loss(pos_event)

        if self.notifier:
            self.notifier.notify_trade_entry({
                "symbol": signal.tradingsymbol,
                "underlying": signal.underlying,
                "option_type": signal.option_type,
                "strike": signal.strike,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "target_1": signal.target_1,
                "quantity": total_quantity,
                "lots": lots,
                "mode": self.state_mgr.execution_mode
            })

    def _get_sl_limit_buffer(self, trigger_price: float) -> float:
        """Computes dynamic volatility-adjusted buffer for SEBI-compliant STOPLOSS_LIMIT orders."""
        if self.cfg.get("dynamic_sl_buffer", True):
            # Dynamic 4.0% - 5.5% buffer for fast gap-down and high IV regimes
            buffer_pct = max(self.cfg.get("min_sl_buffer_pct", 0.035), min(self.cfg.get("max_sl_buffer_pct", 0.055), 0.045))
        else:
            buffer_pct = 0.02
        return max(0.50, round(trigger_price * buffer_pct, 2))

    async def _place_exchange_stop_loss(self, pos: PositionEvent):
        """Places a resting STOPLOSS_LIMIT order on Angel One / paper engine with dynamic volatility buffer."""
        engine = self._get_active_engine()
        if not engine:
            return

        trigger_price = self._round_to_tick(pos.stop_loss)
        buffer = self._get_sl_limit_buffer(trigger_price)
        limit_price = self._round_to_tick(max(0.05, trigger_price - buffer))

        pos.sl_trigger_price = trigger_price
        pos.sl_limit_price = limit_price

        order_params = {
            "order_id": f"ORD_SL_{pos.symbol}_{int(datetime.now().timestamp() * 1000)}",
            "symbol": pos.symbol,
            "token": pos.token,
            "exchange": getattr(pos, "exchange", "NFO"),
            "transaction_type": "SELL",
            "order_type": "STOPLOSS_LIMIT",
            "variety": "STOPLOSS",
            "quantity": pos.quantity,
            "price": limit_price,
            "trigger_price": trigger_price
        }

        logger.info(f"[RISK] 🛡️ Placing Native Exchange STOPLOSS-L: {pos.symbol} Qty={pos.quantity} Trigger=₹{trigger_price} Limit=₹{limit_price} (Dynamic Buffer: ₹{buffer})")
        try:
            res = await engine.submit_order(order_params)
            if res and res.get("status"):
                sl_id = res.get("orderid", "")
                pos.sl_order_id = sl_id
                logger.info(f"[RISK] ✅ Native Exchange SL successfully active on broker! OrderID: {sl_id}")
                self.state_mgr.persist_position(pos)
                self.state_mgr.broadcast_state()
            else:
                logger.error(f"[RISK] ⚠️ Failed to place exchange stop loss: {res.get('message', 'Unknown error')}")
        except Exception as e:
            logger.error(f"[RISK] Exception placing exchange stop loss: {e}")

    async def _on_tick(self, tick: TickEvent):
        """Monitors active positions against stop-loss, breakeven, and partial take-profit triggers."""
        # 1. EOD Square-Off Monitor (15:12 IST)
        now_time = ist_time()
        if now_time >= time(15, 12) and not self.state_mgr.is_halted:
            open_positions = [p for p in self.state_mgr.positions.values() if p.is_open]
            if open_positions:
                logger.warning("[RISK] MANDATORY 15:12 IST SQUARE-OFF TRIGGERED! Closing all open positions at market.")
                await self._square_off_all("Mandatory 15:12 IST EOD liquidation")
                return

        # 2. Hard Daily Drawdown Monitor
        if self.state_mgr.daily_drawdown_pct >= (self.max_drawdown_pct * 100):
            logger.critical(f"[RISK] Daily Drawdown limit ({self.state_mgr.daily_drawdown_pct}%) breached! Triggering immediate circuit breaker liquidation.")
            await self._square_off_all("Hard 3.0% daily drawdown circuit breaker breach")
            self.state_mgr.trigger_panic()
            if self.notifier:
                self.notifier.notify_panic_triggered("Hard 3.0% daily drawdown circuit breaker breach")
            return

        # 3. Position-level Trailing & Bracket Management
        for symbol, pos in list(self.state_mgr.positions.items()):
            if not pos.is_open or pos.token != tick.token:
                continue

            ltp = tick.ltp
            pos.current_ltp = ltp
            unit_risk = pos.entry_price - pos.stop_loss if pos.stop_loss > 0 else (pos.entry_price * 0.12)
            profit_points = ltp - pos.entry_price

            # Stop Loss Trigger (Hard SL)
            if ltp <= pos.stop_loss:
                logger.warning(f"[RISK] STOP-LOSS HIT for {symbol} @ {ltp} (SL was {pos.stop_loss}). Exiting position.")
                await self._exit_position(pos, ltp, "Stop-Loss Hit")
                continue

            # Stage 1: Refined Breakeven Shift (Structural Invalidation Confirmation)
            is_structural_mode = (self.cfg.get("breakeven_mode") == "STRUCTURAL_SWING_BREAK")
            structural_confirmed = True
            swing_level = getattr(pos, "swing_invalidation_level", 0.0)
            if is_structural_mode and swing_level > 0:
                spot = self.state_mgr.spot_levels.get(pos.underlying, {}).get("spot", 0.0)
                if spot > 0:
                    if pos.option_type == "CE":
                        structural_confirmed = (spot >= swing_level)
                    else:
                        structural_confirmed = (spot <= swing_level)

            if profit_points >= (unit_risk * self.be_trigger_r) and structural_confirmed and not pos.be_moved:
                pos.stop_loss = pos.entry_price
                pos.be_moved = True
                pos.structural_be_confirmed = True

                # Modify Native Exchange SL to Breakeven with dynamic buffer
                new_trigger = self._round_to_tick(pos.entry_price)
                buffer = self._get_sl_limit_buffer(new_trigger)
                new_limit = self._round_to_tick(max(0.05, new_trigger - buffer))
                pos.sl_trigger_price = new_trigger
                pos.sl_limit_price = new_limit

                if getattr(pos, "sl_order_id", "") and (engine := self._get_active_engine()):
                    try:
                        await engine.modify_order(pos.sl_order_id, {
                            "variety": "STOPLOSS",
                            "order_type": "STOPLOSS_LIMIT",
                            "price": new_limit,
                            "trigger_price": new_trigger,
                            "quantity": pos.quantity
                        })
                        logger.info(f"[RISK] 🛡️ Modified Exchange Stop-Loss to BREAKEVEN: OrderID={pos.sl_order_id} Trigger={new_trigger} (Structural Swing Level Confirmed: {swing_level})")
                    except Exception as e:
                        logger.error(f"[RISK] Error modifying exchange SL to breakeven: {e}")

                self.state_mgr.persist_position(pos)
                logger.info(f"[RISK] Profit reached +{self.be_trigger_r}R with Structural Break for {symbol}! Stop-Loss moved to BREAKEVEN ({pos.entry_price}). Risk eliminated.")
                self.state_mgr.broadcast_state()
                if self.notifier:
                    self.notifier.notify_breakeven_moved({
                        "symbol": symbol,
                        "entry_price": pos.entry_price,
                        "current_ltp": ltp,
                        "mode": self.state_mgr.execution_mode
                    })

            # Stage 2: Partial Profit Locking (60% quantity) at +2.0R
            if profit_points >= (unit_risk * self.tp1_r) and not pos.partial_taken:
                lots_to_close = max(1, math.floor(pos.lots * self.tp1_qty_pct))
                qty_to_close = lots_to_close * pos.lot_size
                remaining_qty = max(0, pos.quantity - qty_to_close)

                if remaining_qty == 0:
                    # 1-lot position: TP1 fully closes the position and locks in 100% of realized gains
                    logger.info(f"[RISK] Target 1 (+2.0R) HIT for single-lot {symbol}! Fully booking gains @ ₹{ltp:.2f}")
                    await self._exit_position(pos, ltp, "Target 1 (+2.0R) Hit")
                    return

                pos.partial_taken = True
                pos.quantity = remaining_qty
                pos.lots = max(0, pos.lots - lots_to_close)

                # Reduce native exchange SL quantity to match remaining position
                if getattr(pos, "sl_order_id", "") and remaining_qty > 0 and (engine := self._get_active_engine()):
                    try:
                        await engine.modify_order(pos.sl_order_id, {
                            "variety": "STOPLOSS",
                            "order_type": "STOPLOSS_LIMIT",
                            "price": getattr(pos, "sl_limit_price", self._round_to_tick(pos.stop_loss * 0.98)),
                            "trigger_price": getattr(pos, "sl_trigger_price", self._round_to_tick(pos.stop_loss)),
                            "quantity": remaining_qty
                        })
                        logger.info(f"[RISK] 🛡️ Modified Exchange Stop-Loss quantity to remaining {remaining_qty}: OrderID={pos.sl_order_id}")
                    except Exception as e:
                        logger.error(f"[RISK] Error modifying exchange SL quantity: {e}")

                self.state_mgr.persist_position(pos)
                logger.info(f"[RISK] Target 1 (+2.0R) HIT for {symbol}! Locking gains on 60% position ({qty_to_close} units).")
                
                # Execute partial sell
                await self._execute_partial_exit(pos, qty_to_close, ltp)

                # Record completed trade for the closed partial quantity
                partial_pnl = round((ltp - pos.entry_price) * qty_to_close, 2)
                self.state_mgr.record_completed_trade(
                    pnl=partial_pnl,
                    entry_price=pos.entry_price,
                    exit_price=ltp,
                    quantity=qty_to_close,
                    symbol=pos.symbol,
                    exchange=getattr(pos, 'exchange', 'NFO'),
                    is_paper=(self.state_mgr.execution_mode == "PAPER"),
                    strike_price=getattr(pos, 'strike_price', 0.0),
                    option_type=getattr(pos, 'option_type', ''),
                    exit_reason="Target 1 (+2.0R) Partial (60%)"
                )

                if self.notifier:
                    self.notifier.notify_partial_tp1({
                        "symbol": symbol,
                        "booked_qty": qty_to_close,
                        "price": ltp,
                        "gain_pts": profit_points,
                        "pnl": partial_pnl,
                        "mode": self.state_mgr.execution_mode
                    })

    async def _execute_partial_exit(self, pos: PositionEvent, qty: int, price: float):
        """Sends order to book partial profits."""
        exit_order = OrderEvent(
            order_id=f"ORD_EXIT_PARTIAL_{int(datetime.now().timestamp() * 1000)}",
            symbol=pos.symbol,
            token=pos.token,
            exchange=getattr(pos, 'exchange', 'NFO'),
            transaction_type="SELL",
            order_type="LIMIT",
            quantity=qty,
            price=price,
            status="PENDING",
            variety="NORMAL",
            is_paper=(self.state_mgr.execution_mode == "PAPER")
        )
        await self.bus.publish(exit_order)

    async def _exit_position(self, pos: PositionEvent, price: float, reason: str):
        """Liquidates remaining open position and cancels resting exchange stop loss."""
        # Cancel resting exchange stop loss order first so no duplicate execution occurs
        if getattr(pos, "sl_order_id", "") and (engine := self._get_active_engine()):
            try:
                await engine.cancel_order(pos.sl_order_id, variety="STOPLOSS")
                logger.info(f"[RISK] 🛡️ Cancelled resting Exchange Stop-Loss order: {pos.sl_order_id}")
            except Exception as e:
                logger.error(f"[RISK] Error cancelling resting SL {pos.sl_order_id}: {e}")
            pos.sl_order_id = ""

        pos.is_open = False
        pnl = round((price - pos.entry_price) * pos.quantity, 2)
        pos.realized_pnl = pnl
        
        exit_order = OrderEvent(
            order_id=f"ORD_EXIT_FULL_{int(datetime.now().timestamp() * 1000)}",
            symbol=pos.symbol,
            token=pos.token,
            exchange=getattr(pos, 'exchange', 'NFO'),
            transaction_type="SELL",
            order_type="MARKET",
            quantity=pos.quantity,
            price=price,
            status="PENDING",
            variety="NORMAL",
            is_paper=(self.state_mgr.execution_mode == "PAPER")
        )
        self.state_mgr.record_completed_trade(
            pnl=pnl,
            entry_price=pos.entry_price,
            exit_price=price,
            quantity=pos.quantity,
            symbol=pos.symbol,
            exchange=getattr(pos, 'exchange', 'NFO'),
            is_paper=(self.state_mgr.execution_mode == "PAPER"),
            strike_price=getattr(pos, 'strike_price', 0.0),
            option_type=getattr(pos, 'option_type', ''),
            exit_reason=reason
        )

        if self.notifier:
            from smartapi_trader.utils.charges import calculate_option_charges
            charges = calculate_option_charges(pos.entry_price, price, pos.quantity)
            total_charges = charges.get("total_charges", 65.0)
            self.notifier.notify_trade_exit({
                "symbol": pos.symbol,
                "entry_price": pos.entry_price,
                "exit_price": price,
                "quantity": pos.quantity,
                "gross_pnl": pnl,
                "total_charges": total_charges,
                "net_pnl": pnl - total_charges,
                "reason": reason,
                "mode": self.state_mgr.execution_mode
            })

    async def _square_off_all(self, reason: str):
        """Liquidates all open positions and cancels open orders."""
        for pos in list(self.state_mgr.positions.values()):
            if pos.is_open:
                await self._exit_position(pos, pos.current_ltp, reason)

    def _raise_alert(self, level: str, rule: str, msg: str):
        logger.warning(f"[RISK_ALERT] [{level}] {rule}: {msg}")
        alert = RiskAlertEvent(level=level, rule_name=rule, message=msg, action_taken="REJECT")
        self.bus.publish_nowait(alert)
