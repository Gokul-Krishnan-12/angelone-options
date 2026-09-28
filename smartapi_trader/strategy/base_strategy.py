from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from smartapi_trader.core.events import BarEvent, TickEvent, SignalEvent
from smartapi_trader.core.event_bus import EventBus

class BaseStrategy(ABC):
    """
    Abstract base strategy interface.
    Consumes market data events and emits validated trading signals.
    """
    def __init__(self, name: str, event_bus: EventBus):
        self.name = name
        self.bus = event_bus
        self.is_active = True

    @abstractmethod
    async def on_bar(self, event: BarEvent):
        """Processes incoming closed or live OHLCV bars."""
        pass

    @abstractmethod
    async def on_tick(self, event: TickEvent):
        """Processes incoming raw market quotes."""
        pass

    @abstractmethod
    def reset_daily_state(self):
        """Resets intraday buffers, swing levels, and sweep markers."""
        pass
