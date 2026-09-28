import asyncio
import random
import time
from typing import Dict, Any, Optional
from smartapi_trader.execution.base_engine import ExecutionEngine
from smartapi_trader.core.events import OrderEvent, FillEvent, EventType
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.state_manager import StateManager
from smartapi_trader.utils.logger import logger

class PaperExecutionEngine(ExecutionEngine):
    """
    In-memory simulated execution venue.
    Models realistic exchange matching:
    - Adverse bid-ask slippage: Ask + (Spread * kappa) for BUY, Bid - (Spread * kappa) for SELL
    - Network and matching engine latency: 150 - 300 milliseconds artificial delay
    - Virtual cash balance and margin validation
    """
    def __init__(self, event_bus: EventBus, state_manager: StateManager, config: Dict[str, Any]):
        self.bus = event_bus
        self.state_mgr = state_manager
        self.cfg = config.get("execution", {})
        
        self.kappa = self.cfg.get("slippage_factor", 0.20)
        self.latency_ms = self.cfg.get("simulated_latency_ms", 200)
        
        self.virtual_cash = self.cfg.get("paper_initial_capital", 100000.0)
        self.virtual_margin = self.virtual_cash
        self.open_orders: Dict[str, Dict[str, Any]] = {}

        # Subscribe to order submission events
        self.bus.subscribe(EventType.ORDER_UPDATE, self._on_order_event)

    async def _on_order_event(self, event: OrderEvent):
        """Processes incoming order from event bus if in PAPER execution mode."""
        if self.state_mgr.execution_mode != "PAPER":
            return
        if event.status == "PENDING":
            await self.submit_order({
                "order_id": event.order_id,
                "symbol": event.symbol,
                "token": event.token,
                "exchange": event.exchange,
                "transaction_type": event.transaction_type,
                "order_type": event.order_type,
                "quantity": event.quantity,
                "price": event.price,
                "variety": event.variety
            })

    async def submit_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """Simulates latency, validates margin, models slippage, and executes fill."""
        order_id = order_params.get("order_id", f"PAPER_{int(time.time()*1000)}")
        symbol = order_params.get("symbol", "")
        token = order_params.get("token", "")
        tx_type = order_params.get("transaction_type", "BUY")
        qty = int(order_params.get("quantity", 0))
        limit_price = float(order_params.get("price", 0.0))

        logger.info(f"[PAPER_EXEC] Submitting order {order_id}: {tx_type} {qty}x {symbol} @ limit {limit_price}")

        # If resting STOPLOSS order, place into order book as TRIGGER_PENDING
        if order_params.get("variety") == "STOPLOSS":
            trigger_p = float(order_params.get("trigger_price", 0.0))
            self.open_orders[order_id] = dict(order_params)
            logger.info(f"[PAPER_EXEC] 🛡️ Resting STOPLOSS-L order placed: ID={order_id} Trigger={trigger_p} Limit={limit_price}")
            
            pending_order = OrderEvent(
                order_id=order_id,
                symbol=symbol,
                token=token,
                exchange=order_params.get("exchange", "NFO"),
                transaction_type="SELL",
                order_type="STOPLOSS_LIMIT",
                quantity=qty,
                price=limit_price,
                trigger_price=trigger_p,
                status="TRIGGER_PENDING",
                variety="STOPLOSS"
            )
            await self.bus.publish(pending_order)
            return {"status": True, "orderid": order_id}

        # 1. Simulate Latency (150ms - 300ms)
        delay = random.uniform(0.15, 0.30)
        await asyncio.sleep(delay)

        # 2. Retrieve live quote for adverse spread slippage modeling
        tick = self.state_mgr.ticks.get(token)
        if tick:
            best_bid = tick.best_bid or (tick.ltp - 0.10)
            best_ask = tick.best_ask or (tick.ltp + 0.10)
            spread = max(0.05, best_ask - best_bid)
        else:
            best_bid = limit_price - 0.10
            best_ask = limit_price + 0.10
            spread = 0.20

        # Fill Price Model: Fill = Ask + (Spread * kappa) for BUY
        #                   Fill = Bid - (Spread * kappa) for SELL
        if tx_type == "BUY":
            fill_price = round(best_ask + (spread * self.kappa), 2)
            slippage = round(fill_price - limit_price, 2)
        else:
            fill_price = round(best_bid - (spread * self.kappa), 2)
            slippage = round(limit_price - fill_price, 2)

        total_value = fill_price * qty

        # 3. Virtual Margin Validation
        if tx_type == "BUY" and total_value > self.virtual_margin:
            logger.warning(f"[PAPER_EXEC] Order {order_id} REJECTED: Insufficient virtual margin (Req: ₹{total_value:.2f}, Avail: ₹{self.virtual_margin:.2f})")
            rejected_event = OrderEvent(
                order_id=order_id,
                symbol=symbol,
                token=token,
                transaction_type=tx_type,
                quantity=qty,
                price=limit_price,
                status="REJECTED",
                rejection_reason="Insufficient virtual margin"
            )
            await self.bus.publish(rejected_event)
            return {"status": False, "orderid": order_id, "message": "Insufficient virtual margin"}

        # 4. Execute Fill
        if tx_type == "BUY":
            self.virtual_margin -= total_value
        else:
            self.virtual_margin += total_value

        self.state_mgr.available_margin = round(self.virtual_margin, 2)

        fill_id = f"FILL_{int(time.time() * 1000)}"
        fill_event = FillEvent(
            fill_id=fill_id,
            order_id=order_id,
            symbol=symbol,
            token=token,
            transaction_type=tx_type,
            quantity=qty,
            price=fill_price,
            slippage=slippage,
            execution_venue="PAPER"
        )

        completed_order = OrderEvent(
            order_id=order_id,
            symbol=symbol,
            token=token,
            exchange=order_params.get("exchange", "NFO"),
            transaction_type=tx_type,
            order_type=order_params.get("order_type", "LIMIT"),
            quantity=qty,
            price=limit_price,
            status="FILLED",
            filled_quantity=qty,
            average_price=fill_price
        )

        logger.info(f"[PAPER_EXEC] ORDER FILLED! ID={order_id} {tx_type} {qty}x {symbol} @ ₹{fill_price} (Slip: ₹{slippage:+.2f}, Latency: {int(delay*1000)}ms)")
        
        await self.bus.publish(fill_event)
        await self.bus.publish(completed_order)

        return {
            "status": True,
            "orderid": order_id,
            "fill_price": fill_price,
            "slippage": slippage,
            "latency_ms": int(delay * 1000)
        }

    async def modify_order(self, order_id: str, modify_params: Dict[str, Any]) -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        if order_id in self.open_orders:
            ord_data = self.open_orders[order_id]
            if "price" in modify_params:
                ord_data["price"] = modify_params["price"]
            if "trigger_price" in modify_params:
                ord_data["trigger_price"] = modify_params["trigger_price"]
            if "quantity" in modify_params:
                ord_data["quantity"] = modify_params["quantity"]
            logger.info(f"[PAPER_EXEC] Order {order_id} modified: Trigger={ord_data.get('trigger_price')} Qty={ord_data.get('quantity')}")
        return {"status": True, "orderid": order_id}

    async def cancel_order(self, order_id: str, variety: str = "NORMAL") -> Dict[str, Any]:
        await asyncio.sleep(0.05)
        self.open_orders.pop(order_id, None)
        logger.info(f"[PAPER_EXEC] Order {order_id} cancelled (variety={variety}).")
        cancelled_order = OrderEvent(
            order_id=order_id,
            status="CANCELLED"
        )
        await self.bus.publish(cancelled_order)
        return {"status": True, "orderid": order_id}

    async def get_positions(self) -> Dict[str, Any]:
        return {
            "status": True,
            "data": [p.to_dict() for p in self.state_mgr.positions.values() if p.is_open]
        }

    async def get_account_balance(self) -> Dict[str, Any]:
        return {
            "status": True,
            "data": {
                "net": self.virtual_margin,
                "availablecash": self.virtual_cash,
                "unrealized_pnl": self.state_mgr.unrealized_pnl
            }
        }
