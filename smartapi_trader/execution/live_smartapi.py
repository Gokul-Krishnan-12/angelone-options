import asyncio
import time
import aiohttp
from typing import Dict, Any, Optional
from smartapi_trader.execution.base_engine import ExecutionEngine
from smartapi_trader.core.events import OrderEvent, FillEvent, EventType
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.core.state_manager import StateManager
from smartapi_trader.utils.logger import logger

class TokenBucketRateLimiter:
    """Async token-bucket rate limiter enforcing <= 10 requests per second."""
    def __init__(self, rate: int = 10, capacity: int = 10):
        self.rate = rate
        self.capacity = capacity
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = asyncio.Lock()

    async def acquire(self):
        async with self._lock:
            while True:
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.capacity, self.tokens + (elapsed * self.rate))
                self.last_update = now
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
                # Wait for next token
                await asyncio.sleep(1.0 / self.rate)

class LiveSmartAPIExecutionEngine(ExecutionEngine):
    """
    Production Angel One REST API integration.
    Handles JWT authentication headers, token-bucket rate limiting (<= 10 req/s),
    native broker exchange order IDs, and maps broker responses into internal events.
    """
    def __init__(
        self,
        event_bus: EventBus,
        state_manager: StateManager,
        config: Dict[str, Any],
        smart_connect_instance: Any = None,
        jwt_token: str = "",
        api_key: str = ""
    ):
        self.bus = event_bus
        self.state_mgr = state_manager
        self.cfg = config.get("broker", {})
        self.smart_connect = smart_connect_instance
        self.jwt_token = jwt_token
        self.api_key = api_key or self.cfg.get("api_key", "")
        self.base_url = self.cfg.get("base_url", "https://apiconnect.angelbroking.com")
        
        self.rate_limiter = TokenBucketRateLimiter(rate=10, capacity=10)
        self.session: Optional[aiohttp.ClientSession] = None

        # Subscribe to order submission events
        self.bus.subscribe(EventType.ORDER_UPDATE, self._on_order_event)

    def update_jwt_token(self, jwt_token: str):
        self.jwt_token = jwt_token

    async def _get_session(self) -> aiohttp.ClientSession:
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-UserType": "USER",
            "X-SourceID": "WEB",
            "X-ClientLocalIP": "127.0.0.1",
            "X-ClientPublicIP": "106.193.147.98",
            "X-MACAddress": "fe80::216e:6507:4bfe:379",
            "X-PrivateKey": self.api_key,
            "Authorization": f"Bearer {self.jwt_token}"
        }

    async def _on_order_event(self, event: OrderEvent):
        """Processes incoming order from event bus if in LIVE execution mode."""
        if self.state_mgr.execution_mode != "LIVE":
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
                "trigger_price": event.trigger_price,
                "variety": event.variety
            })

    async def submit_order(self, order_params: Dict[str, Any]) -> Dict[str, Any]:
        """Routes order to Angel One /rest/secure/angelbroking/order/v1/placeOrder."""
        await self.rate_limiter.acquire()
        session = await self._get_session()
        
        url = f"{self.base_url}/rest/secure/angelbroking/order/v1/placeOrder"
        payload = {
            "variety": order_params.get("variety", "NORMAL"),
            "tradingsymbol": order_params.get("symbol"),
            "symboltoken": order_params.get("token"),
            "transactiontype": order_params.get("transaction_type", "BUY"),
            "exchange": order_params.get("exchange", "NFO"),
            "ordertype": order_params.get("order_type", "LIMIT"),
            "producttype": "INTRADAY",
            "duration": "DAY",
            "price": str(order_params.get("price")),
            "quantity": str(order_params.get("quantity"))
        }
        if order_params.get("trigger_price", 0) > 0:
            payload["triggerprice"] = str(order_params.get("trigger_price"))

        order_id = order_params.get("order_id", f"LIVE_{int(time.time()*1000)}")
        logger.info(f"[LIVE_SMARTAPI] Placing LIVE order to Angel One: {payload}")

        try:
            async with session.post(url, json=payload, headers=self._get_headers(), timeout=10) as resp:
                data = await resp.json()
                if resp.status == 200 and data.get("status"):
                    broker_order_id = data.get("data", {}).get("orderid", order_id)
                    logger.info(f"[LIVE_SMARTAPI] Order placed successfully! Broker OrderID: {broker_order_id}")
                    
                    submitted = OrderEvent(
                        order_id=broker_order_id,
                        client_order_id=order_id,
                        symbol=order_params.get("symbol", ""),
                        token=order_params.get("token", ""),
                        exchange=order_params.get("exchange", "NFO"),
                        transaction_type=order_params.get("transaction_type", "BUY"),
                        quantity=int(order_params.get("quantity", 0)),
                        price=float(order_params.get("price", 0.0)),
                        status="OPEN"
                    )
                    await self.bus.publish(submitted)
                    return {"status": True, "orderid": broker_order_id, "data": data}
                else:
                    msg = data.get("message", f"HTTP {resp.status}")
                    logger.error(f"[LIVE_SMARTAPI] Order placement REJECTED: {msg}")
                    rejected = OrderEvent(
                        order_id=order_id,
                        symbol=order_params.get("symbol", ""),
                        status="REJECTED",
                        rejection_reason=msg
                    )
                    await self.bus.publish(rejected)
                    return {"status": False, "message": msg}

        except Exception as e:
            logger.error(f"[LIVE_SMARTAPI] Network exception during order placement: {e}")
            return {"status": False, "message": str(e)}

    async def modify_order(self, order_id: str, modify_params: Dict[str, Any]) -> Dict[str, Any]:
        await self.rate_limiter.acquire()
        session = await self._get_session()
        url = f"{self.base_url}/rest/secure/angelbroking/order/v1/modifyOrder"
        payload = {
            "orderid": order_id,
            "variety": modify_params.get("variety", "NORMAL"),
            "ordertype": modify_params.get("order_type", "LIMIT"),
            "price": str(modify_params.get("price")),
            "quantity": str(modify_params.get("quantity"))
        }
        if modify_params.get("trigger_price", 0) > 0:
            payload["triggerprice"] = str(modify_params.get("trigger_price"))

        logger.info(f"[LIVE_SMARTAPI] Modifying order {order_id}: {payload}")
        try:
            async with session.post(url, json=payload, headers=self._get_headers(), timeout=10) as resp:
                data = await resp.json()
                logger.info(f"[LIVE_SMARTAPI] Order modify response: {data}")
                return data
        except Exception as e:
            logger.error(f"[LIVE_SMARTAPI] Exception modifying order: {e}")
            return {"status": False, "message": str(e)}

    async def cancel_order(self, order_id: str, variety: str = "NORMAL") -> Dict[str, Any]:
        await self.rate_limiter.acquire()
        session = await self._get_session()
        url = f"{self.base_url}/rest/secure/angelbroking/order/v1/cancelOrder"
        payload = {"variety": variety, "orderid": order_id}
        logger.info(f"[LIVE_SMARTAPI] Cancelling order {order_id} (variety={variety})")
        try:
            async with session.post(url, json=payload, headers=self._get_headers(), timeout=10) as resp:
                data = await resp.json()
                logger.info(f"[LIVE_SMARTAPI] Cancel order response: {data}")
                return data
        except Exception as e:
            logger.error(f"[LIVE_SMARTAPI] Exception cancelling order: {e}")
            return {"status": False, "message": str(e)}

    async def get_positions(self) -> Dict[str, Any]:
        await self.rate_limiter.acquire()
        session = await self._get_session()
        url = f"{self.base_url}/rest/secure/angelbroking/order/v1/getPosition"
        try:
            async with session.get(url, headers=self._get_headers(), timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"[LIVE_SMARTAPI] Exception getting positions: {e}")
            return {"status": False, "message": str(e)}

    async def get_account_balance(self) -> Dict[str, Any]:
        await self.rate_limiter.acquire()
        session = await self._get_session()
        url = f"{self.base_url}/rest/secure/angelbroking/user/v1/getRMS"
        try:
            async with session.get(url, headers=self._get_headers(), timeout=10) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"[LIVE_SMARTAPI] Exception getting RMS balance: {e}")
            return {"status": False, "message": str(e)}
