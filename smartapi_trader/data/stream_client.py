import asyncio
import json
import time
import random
from typing import Dict, List, Set, Optional, Any
from smartapi_trader.core.events import TickEvent
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.utils.logger import logger

class SmartStreamClient:
    """
    Manages WebSocket streaming via SmartWebSocketV2 with automatic reconnection,
    dynamic strike subscription, heartbeat maintenance, and simulated feed fallback.
    """
    def __init__(
        self,
        event_bus: EventBus,
        auth_token: str,
        api_key: str,
        client_code: str,
        feed_token: str,
        is_simulated: bool = False
    ):
        self.bus = event_bus
        self.auth_token = auth_token
        self.api_key = api_key
        self.client_code = client_code
        self.feed_token = feed_token
        self.is_simulated = is_simulated
        
        self.subscribed_tokens: Dict[str, Dict[str, Any]] = {} # token -> info
        self.is_connected = False
        self.running = False
        self.last_tick_time: float = 0.0
        self.total_ticks_received: int = 0
        self._ws_task: Optional[asyncio.Task] = None
        self._sim_task: Optional[asyncio.Task] = None
        self._ws_client = None

    def subscribe(self, token: str, symbol: str, exchange: str = "NSE", mode: int = 2):
        """Adds a token to the active subscription list."""
        self.subscribed_tokens[token] = {
            "token": token,
            "symbol": symbol,
            "exchange": exchange,
            "mode": mode
        }
        logger.info(f"[STREAM] Subscribed to {symbol} (Token: {token}, Exch: {exchange}, Mode: {mode})")
        if self.is_connected and not self.is_simulated and self._ws_client:
            self._send_subscription(token, exchange, mode)

    def unsubscribe(self, token: str):
        if token in self.subscribed_tokens:
            sym = self.subscribed_tokens[token]["symbol"]
            del self.subscribed_tokens[token]
            logger.info(f"[STREAM] Unsubscribed from {sym} (Token: {token})")

    async def start(self):
        """Starts WebSocket ingestion or simulated background stream."""
        self.running = True
        if self.is_simulated:
            logger.info("[STREAM] Starting realistic Simulated Live Market Stream for PAPER mode.")
            self._sim_task = asyncio.create_task(self._run_simulated_stream())
        else:
            logger.info("[STREAM] Initiating Angel One SmartWebSocketV2 connection...")
            self._ws_task = asyncio.create_task(self._run_live_stream())

    async def stop(self):
        """Gracefully disconnects and stops streaming loops."""
        self.running = False
        self.is_connected = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._sim_task:
            self._sim_task.cancel()
        if self._ws_client:
            try:
                self._ws_client.close_connection()
            except Exception:
                pass
        logger.info("[STREAM] Stream client stopped.")

    async def _run_live_stream(self):
        """Connects via SmartWebSocketV2 with auto-reconnect backoff."""
        backoff = 2
        while self.running:
            try:
                from SmartApi.smartWebSocketV2 import SmartWebSocketV2
                
                loop = asyncio.get_event_loop()

                def on_data(wsapp, message):
                    try:
                        self._parse_and_publish_tick(message)
                    except Exception as e:
                        logger.error(f"[STREAM] Error parsing tick: {e}")

                def on_open(wsapp):
                    self.is_connected = True
                    logger.info("[STREAM] SmartWebSocketV2 connected successfully!")
                    # Resubscribe all tokens
                    self._resubscribe_all()

                def on_close(wsapp):
                    self.is_connected = False
                    logger.warning("[STREAM] SmartWebSocketV2 connection closed.")

                def on_error(wsapp, error):
                    self.is_connected = False
                    logger.error(f"[STREAM] SmartWebSocketV2 error: {error}")

                self._ws_client = SmartWebSocketV2(
                    auth_token=self.auth_token,
                    api_key=self.api_key,
                    client_code=self.client_code,
                    feed_token=self.feed_token
                )
                self._ws_client.on_data = on_data
                self._ws_client.on_open = on_open
                self._ws_client.on_close = on_close
                self._ws_client.on_error = on_error

                # Run blocking connection in executor
                await loop.run_in_executor(None, self._ws_client.connect)
                
            except Exception as e:
                logger.error(f"[STREAM] WebSocket connection exception: {e}. Reconnecting in {backoff}s...")
                self.is_connected = False
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def _send_subscription(self, token: str, exchange: str, mode: int):
        if not self._ws_client or not self.is_connected:
            return
        exch_type = 1 if exchange == "NSE" else (2 if exchange == "NFO" else (3 if exchange == "BSE" else 4))
        token_list = [{"exchangeType": exch_type, "tokens": [str(token)]}]
        try:
            self._ws_client.subscribe(correlation_id=f"sub_{token}", mode=mode, token_list=token_list)
            logger.info(f"[STREAM] Sent live subscription for {token} (Exch: {exchange}, Mode: {mode})")
        except Exception as e:
            logger.error(f"[STREAM] Failed to send subscription: {e}")

    def _resubscribe_all(self):
        groups: Dict[tuple, List[str]] = {}
        for token, info in self.subscribed_tokens.items():
            exchange = info.get("exchange", "NSE")
            mode = info.get("mode", 2)
            exch_type = 1 if exchange == "NSE" else (2 if exchange == "NFO" else (3 if exchange == "BSE" else 4))
            key = (exch_type, mode)
            if key not in groups:
                groups[key] = []
            groups[key].append(str(token))

        for (exch_type, mode), tokens in groups.items():
            token_list = [{"exchangeType": exch_type, "tokens": tokens}]
            try:
                self._ws_client.subscribe(correlation_id=f"sub_{exch_type}_{mode}", mode=mode, token_list=token_list)
                logger.info(f"[STREAM] Subscribed {len(tokens)} tokens (ExchType: {exch_type}, Mode: {mode}): {tokens}")
            except Exception as e:
                logger.error(f"[STREAM] Error subscribing tokens: {e}")

    def _parse_and_publish_tick(self, message: Any):
        """Parses SmartWebSocketV2 binary packet / dictionary and publishes TickEvent."""
        if isinstance(message, dict):
            token = str(message.get("token", ""))
            info = self.subscribed_tokens.get(token, {})
            ltp = float(message.get("last_traded_price", 0.0) or 0.0) / 100.0
            if ltp <= 0.0:
                return

            raw_bid = message.get("best_bid_price")
            bid = float(raw_bid) / 100.0 if raw_bid is not None else round(ltp - 0.10, 2)
            raw_ask = message.get("best_ask_price")
            ask = float(raw_ask) / 100.0 if raw_ask is not None else round(ltp + 0.10, 2)
            vol = int(message.get("volume_trade_for_the_day", 0) or 0)
            
            raw_open = message.get("open_price_of_the_day")
            open_p = float(raw_open) / 100.0 if raw_open is not None else ltp
            raw_high = message.get("high_price_of_the_day")
            high_p = float(raw_high) / 100.0 if raw_high is not None else ltp
            raw_low = message.get("low_price_of_the_day")
            low_p = float(raw_low) / 100.0 if raw_low is not None else ltp
            raw_close = message.get("closed_price")
            close_p = float(raw_close) / 100.0 if raw_close is not None else ltp

            tick = TickEvent(
                symbol=info.get("symbol", f"TOKEN_{token}"),
                token=token,
                exchange=info.get("exchange", "NSE"),
                ltp=ltp,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=vol,
                best_bid=bid,
                best_ask=ask,
                spread=round(max(0.05, ask - bid), 2),
                tick_time=str(message.get("exchange_timestamp", time.time()))
            )
            self.last_tick_time = time.time()
            self.total_ticks_received += 1
            self.bus.publish_nowait(tick)

    @staticmethod
    def is_market_open() -> bool:
        """Checks if current IST time is within active market hours (Mon-Fri 09:15-15:30 IST)."""
        from datetime import datetime, timezone, timedelta, time
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        # Saturday is 5, Sunday is 6
        if now_ist.weekday() >= 5:
            return False
        return time(9, 15) <= now_ist.time() <= time(15, 30)

    async def _run_simulated_stream(self):
        """
        Maintains simulated feed when broker credentials are not configured:
        - When market is open: generates live ticks.
        - When market is closed (weekends / after-hours): freezes prices.
        """
        self.is_connected = True
        logger.info("[STREAM] Market feed initialized (Simulated mode).")
        
        # Base closing prices
        base_closing_prices = {
            "99926000": 22853.05,   # NIFTY 50
            "99926009": 54605.75,   # BANKNIFTY
            "99919000": 72961.38,   # SENSEX
        }
        prices = dict(base_closing_prices)
        cum_volume = {k: 12500000 for k in prices}

        initial_sent = False
        step = 0
        while self.running:
            try:
                market_open = self.is_market_open()

                # If market is closed on weekends or outside 09:15 - 15:30 IST:
                if not market_open:
                    if not initial_sent:
                        logger.info("[STREAM] Market is CLOSED (Weekend / After Hours). Freezing prices at Friday closing levels.")
                        # Emit fixed closing ticks once
                        for token, info in list(self.subscribed_tokens.items()):
                            symbol = info["symbol"]
                            ltp = base_closing_prices.get(token, 180.0)
                            tick = TickEvent(
                                symbol=symbol,
                                token=token,
                                exchange=info["exchange"],
                                ltp=ltp,
                                open=ltp,
                                high=ltp,
                                low=ltp,
                                close=ltp,
                                volume=cum_volume.get(token, 1000000),
                                best_bid=ltp - 0.10,
                                best_ask=ltp + 0.10,
                                spread=0.20,
                                tick_time=str(int(time.time() * 1000))
                            )
                            self.bus.publish_nowait(tick)
                        initial_sent = True
                    
                    # Sleep quietly without generating any random drifts
                    await asyncio.sleep(2.0)
                    continue

                # If market is open, simulate live micro-ticks
                initial_sent = False
                step += 1
                for token, info in list(self.subscribed_tokens.items()):
                    symbol = info["symbol"]
                    
                    if token in prices:
                        drift = random.choice([-2.0, -1.0, -0.5, 0.0, 0.5, 1.0, 2.0])
                        prices[token] = round(prices[token] + drift, 2)
                        ltp = prices[token]
                        cum_volume[token] += random.randint(50, 500)
                        bid = round(ltp - 0.25, 2)
                        ask = round(ltp + 0.25, 2)
                        spread = 0.50
                    else:
                        if token not in prices:
                            prices[token] = 180.0
                            cum_volume[token] = 50000
                        drift = random.choice([-1.5, -0.8, -0.2, 0.0, 0.3, 0.9, 1.6])
                        prices[token] = max(1.0, round(prices[token] + drift, 2))
                        ltp = prices[token]
                        cum_volume[token] += random.randint(20, 150)
                        bid = round(ltp - 0.10, 2)
                        ask = round(ltp + 0.10, 2)
                        spread = 0.20

                    tick = TickEvent(
                        symbol=symbol,
                        token=token,
                        exchange=info["exchange"],
                        ltp=ltp,
                        open=ltp - 10.0,
                        high=ltp + 15.0,
                        low=ltp - 15.0,
                        close=ltp,
                        volume=cum_volume[token],
                        best_bid=bid,
                        best_ask=ask,
                        spread=spread,
                        tick_time=str(int(time.time() * 1000))
                    )
                    self.bus.publish_nowait(tick)

                await asyncio.sleep(1.0)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[STREAM] Stream loop error: {e}")
                await asyncio.sleep(1)
