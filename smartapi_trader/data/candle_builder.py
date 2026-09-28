import math
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from smartapi_trader.core.events import TickEvent, BarEvent
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.utils.logger import logger

class Candle:
    """Represents an OHLCV candle with VWAP calculations."""
    def __init__(self, symbol: str, token: str, exchange: str, timeframe: str, start_time: datetime):
        self.symbol = symbol
        self.token = token
        self.exchange = exchange
        self.timeframe = timeframe
        self.start_time = start_time
        
        self.open: float = 0.0
        self.high: float = 0.0
        self.low: float = float("inf")
        self.close: float = 0.0
        self.volume: int = 0
        self.vwap: float = 0.0
        self.ticks_count: int = 0
        self.is_closed: bool = False

    def update(self, price: float, volume_delta: int, session_pv_sum: float, session_vol_sum: float):
        if self.ticks_count == 0:
            self.open = price
            self.high = price
            self.low = price
            self.close = price
        else:
            if price > self.high:
                self.high = price
            if price < self.low:
                self.low = price
            self.close = price

        self.volume += max(0, volume_delta)
        self.ticks_count += 1
        
        if session_vol_sum > 0:
            self.vwap = round(session_pv_sum / session_vol_sum, 2)
        else:
            self.vwap = self.close

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def body_size(self) -> float:
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        return max(0.0001, self.high - self.low)

    @property
    def upper_wick_ratio(self) -> float:
        return self.upper_wick / self.total_range

    @property
    def lower_wick_ratio(self) -> float:
        return self.lower_wick / self.total_range

    def to_bar_event(self, is_closed: bool = False) -> BarEvent:
        return BarEvent(
            symbol=self.symbol,
            token=self.token,
            exchange=self.exchange,
            timeframe=self.timeframe,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            vwap=self.vwap,
            is_closed=is_closed,
            bar_start_time=self.start_time.isoformat()
        )

class CandleAggregator:
    """
    Assembles multi-timeframe OHLCV bars (3m and 15m) from real-time tick events.
    Computes rolling VWAP and enforces strict bar boundary dispatching.
    """
    def __init__(self, event_bus: EventBus, timeframes: List[int] = None):
        self.bus = event_bus
        self.timeframes = timeframes or [3, 15]  # minutes
        
        # State: token -> timeframe_str -> current Candle
        self.current_candles: Dict[str, Dict[str, Candle]] = {}
        # History: token -> timeframe_str -> List[Candle]
        self.history: Dict[str, Dict[str, List[Candle]]] = {}
        
        # Session Cumulative Volume & Price*Volume for VWAP
        # token -> {"pv_sum": float, "vol_sum": float, "last_vol": int}
        self.session_data: Dict[str, Dict[str, float]] = {}

    def _get_candle_start(self, dt: datetime, tf_minutes: int) -> datetime:
        """Rounds datetime down to current timeframe boundary."""
        minute = (dt.minute // tf_minutes) * tf_minutes
        return dt.replace(minute=minute, second=0, microsecond=0)

    async def on_tick(self, tick: TickEvent):
        """Processes tick, updates active candle or rolls over to new candle."""
        token = tick.token
        now = datetime.now()

        # Track session volume for VWAP
        if token not in self.session_data:
            self.session_data[token] = {
                "pv_sum": 0.0,
                "vol_sum": 0.0,
                "last_cum_volume": tick.volume
            }

        s_data = self.session_data[token]
        # Calculate tick volume increment
        vol_delta = 1
        if tick.volume > s_data["last_cum_volume"]:
            vol_delta = tick.volume - int(s_data["last_cum_volume"])
            s_data["last_cum_volume"] = tick.volume
        
        s_data["pv_sum"] += (tick.ltp * vol_delta)
        s_data["vol_sum"] += vol_delta

        if token not in self.current_candles:
            self.current_candles[token] = {}
            self.history[token] = {}

        for tf in self.timeframes:
            tf_key = f"{tf}m"
            if tf_key not in self.history[token]:
                self.history[token][tf_key] = []

            candle_start = self._get_candle_start(now, tf)
            curr = self.current_candles[token].get(tf_key)

            if curr is None:
                # First candle
                curr = Candle(tick.symbol, tick.token, tick.exchange, tf_key, candle_start)
                self.current_candles[token][tf_key] = curr
            elif candle_start > curr.start_time:
                # Current candle has closed!
                curr.is_closed = True
                self.history[token][tf_key].append(curr)
                # Keep max 100 historical bars
                if len(self.history[token][tf_key]) > 100:
                    self.history[token][tf_key].pop(0)

                # Publish closed bar event
                closed_event = curr.to_bar_event(is_closed=True)
                await self.bus.publish(closed_event)
                logger.debug(f"[CANDLE] {tick.symbol} {tf_key} closed: O={curr.open} H={curr.high} L={curr.low} C={curr.close} V={curr.volume}")

                # Start new candle
                curr = Candle(tick.symbol, tick.token, tick.exchange, tf_key, candle_start)
                self.current_candles[token][tf_key] = curr

            # Update candle values
            curr.update(tick.ltp, vol_delta, s_data["pv_sum"], s_data["vol_sum"])

            # Publish real-time bar update
            live_event = curr.to_bar_event(is_closed=False)
            await self.bus.publish(live_event)

    def get_closed_bars(self, token: str, timeframe: str) -> List[Candle]:
        """Retrieves list of closed candles for a given instrument and timeframe."""
        if token in self.history and timeframe in self.history[token]:
            return self.history[token][timeframe]
        return []
