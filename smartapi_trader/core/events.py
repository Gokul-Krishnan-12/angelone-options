from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Dict, Any, Optional
from datetime import datetime

class EventType(str, Enum):
    TICK = "TICK"
    BAR = "BAR"
    SIGNAL = "SIGNAL"
    ORDER_SUBMIT = "ORDER_SUBMIT"
    ORDER_UPDATE = "ORDER_UPDATE"
    FILL = "FILL"
    POSITION_UPDATE = "POSITION_UPDATE"
    RISK_ALERT = "RISK_ALERT"
    SYSTEM_STATE = "SYSTEM_STATE"
    LOG = "LOG"

@dataclass
class BaseEvent:
    event_type: EventType
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d

@dataclass
class TickEvent(BaseEvent):
    event_type: EventType = field(default=EventType.TICK, init=False)
    symbol: str = ""
    token: str = ""
    exchange: str = "NSE"
    ltp: float = 0.0
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    best_bid: float = 0.0
    best_ask: float = 0.0
    spread: float = 0.0
    tick_time: str = ""

@dataclass
class BarEvent(BaseEvent):
    event_type: EventType = field(default=EventType.BAR, init=False)
    symbol: str = ""
    token: str = ""
    exchange: str = "NSE"
    timeframe: str = "3m"  # "3m" or "15m"
    open: float = 0.0
    high: float = 0.0
    low: float = 0.0
    close: float = 0.0
    volume: int = 0
    vwap: float = 0.0
    is_closed: bool = False
    bar_start_time: str = ""

@dataclass
class SignalEvent(BaseEvent):
    event_type: EventType = field(default=EventType.SIGNAL, init=False)
    signal_id: str = ""
    underlying: str = ""            # "NIFTY", "BANKNIFTY", "SENSEX"
    signal_type: str = ""           # "BUY_CE" or "BUY_PE"
    strike: float = 0.0
    option_type: str = ""           # "CE" or "PE"
    expiry: str = ""
    symboltoken: str = ""
    tradingsymbol: str = ""
    exchange: str = "NFO"
    lot_size: int = 0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0           # +2.0R (60% partial exit)
    fvg_top: float = 0.0
    fvg_bottom: float = 0.0
    sweep_level: float = 0.0
    swing_invalidation_level: float = 0.0  # 3m swing break level for structural breakeven confirmation
    reason: str = ""

@dataclass
class OrderEvent(BaseEvent):
    event_type: EventType = field(default=EventType.ORDER_UPDATE, init=False)
    order_id: str = ""
    client_order_id: str = ""
    symbol: str = ""
    token: str = ""
    exchange: str = "NFO"
    transaction_type: str = "BUY"   # "BUY" or "SELL"
    order_type: str = "LIMIT"       # "LIMIT", "MARKET", "STOPLOSS_LIMIT"
    product_type: str = "INTRADAY"
    quantity: int = 0
    price: float = 0.0
    trigger_price: float = 0.0
    status: str = "PENDING"         # "PENDING", "OPEN", "FILLED", "CANCELLED", "REJECTED"
    variety: str = "NORMAL"         # "NORMAL" or "STOPLOSS"
    filled_quantity: int = 0
    average_price: float = 0.0
    rejection_reason: str = ""
    is_paper: bool = True

@dataclass
class FillEvent(BaseEvent):
    event_type: EventType = field(default=EventType.FILL, init=False)
    fill_id: str = ""
    order_id: str = ""
    symbol: str = ""
    token: str = ""
    transaction_type: str = "BUY"
    quantity: int = 0
    price: float = 0.0
    slippage: float = 0.0
    execution_venue: str = "PAPER"  # "PAPER" or "SMARTAPI"

@dataclass
class PositionEvent(BaseEvent):
    event_type: EventType = field(default=EventType.POSITION_UPDATE, init=False)
    symbol: str = ""
    token: str = ""
    underlying: str = ""
    option_type: str = "CE"
    strike_price: float = 0.0
    quantity: int = 0
    lot_size: int = 0
    lots: int = 0
    entry_price: float = 0.0
    current_ltp: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0
    stop_loss: float = 0.0
    target_1: float = 0.0
    exchange: str = "NFO"
    sl_order_id: str = ""           # Broker Order ID of resting STOPLOSS_LIMIT order
    sl_trigger_price: float = 0.0
    sl_limit_price: float = 0.0
    be_moved: bool = False
    structural_be_confirmed: bool = False
    swing_invalidation_level: float = 0.0 # 3m structural level to confirm breakeven
    partial_taken: bool = False
    is_open: bool = True
    is_paper: bool = True
    execution_mode: str = "PAPER"

@dataclass
class RiskAlertEvent(BaseEvent):
    event_type: EventType = field(default=EventType.RISK_ALERT, init=False)
    level: str = "INFO"             # "INFO", "WARNING", "CRITICAL"
    rule_name: str = ""
    message: str = ""
    action_taken: str = ""

@dataclass
class SystemStateEvent(BaseEvent):
    event_type: EventType = field(default=EventType.SYSTEM_STATE, init=False)
    execution_mode: str = "PAPER"
    equity: float = 100000.0
    available_margin: float = 100000.0
    daily_pnl: float = 0.0
    daily_drawdown_pct: float = 0.0
    trades_taken_today: int = 0
    max_trades_allowed: int = 2
    consecutive_losses: int = 0
    is_panic_active: bool = False
    strategy_status: str = "SCANNING"
    active_positions_count: int = 0
