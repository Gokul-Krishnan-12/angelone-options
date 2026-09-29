import asyncio
from datetime import datetime
from typing import Dict, Any, List, Optional
from smartapi_trader.core.events import (
    BaseEvent, EventType, TickEvent, OrderEvent, FillEvent, PositionEvent, SystemStateEvent
)
from smartapi_trader.core.event_bus import EventBus
from smartapi_trader.utils.logger import logger
from smartapi_trader.utils.charges import calculate_option_charges

class StateManager:
    """
    Centralized in-memory operational state store with SQLite persistence.
    Maintains real-time portfolio, order book, positions, and strategy telemetry.
    """
    def __init__(self, event_bus: EventBus, execution_mode: str = "PAPER", initial_capital: float = 100000.0, storage: Optional[Any] = None, max_trades_allowed: int = 2):
        self.bus = event_bus
        self.execution_mode = execution_mode
        self.storage = storage
        self.starting_equity = initial_capital
        self.equity = initial_capital
        self.available_margin = initial_capital
        self.realized_pnl = 0.0
        self.total_brokerage = 0.0
        self.net_pnl = 0.0
        self.unrealized_pnl = 0.0
        self.daily_pnl = 0.0
        self.peak_equity = initial_capital
        self.daily_drawdown_pct = 0.0
        self.completed_trades: List[Dict[str, Any]] = []
        
        self.trades_taken_today = 0
        self.max_trades_allowed = int(max_trades_allowed)
        self.consecutive_losses = 0
        
        # Dual Agent Control States
        self.paper_agent_status = "RUNNING" if execution_mode == "PAPER" else "IDLE"
        self.real_agent_status = "RUNNING" if execution_mode == "LIVE" else "IDLE"
        
        # Real Broker RMS (Live Angel One Ledger)
        self.broker_rms: Dict[str, Any] = {
            "net": 0.0,
            "availablecash": 0.0,
            "collateral": 0.0,
            "utiliseddebits": 0.0,
            "m2munrealized": 0.0,
            "m2mrealized": 0.0,
            "is_live_synced": False
        }

        # Enclosed Paper Trading Ledger (Completely Isolated from Live Broker)
        self.paper_capital = float(initial_capital)
        self.paper_starting_capital = float(initial_capital)
        self.paper_available_margin = float(initial_capital)
        self.paper_realized_pnl = 0.0
        self.paper_total_brokerage = 0.0
        self.paper_net_pnl = 0.0
        self.paper_unrealized_pnl = 0.0
        self.paper_daily_pnl = 0.0
        self.paper_drawdown_pct = 0.0
        self.paper_trades_taken = 0
        self.paper_completed_trades: List[Dict[str, Any]] = []
        
        self.is_panic_active = False
        self.is_halted = False
        self.strategy_status = "Scanning for Liquidity Sweep"
        
        # State collections
        self.positions: Dict[str, PositionEvent] = {} # Keyed by symbol
        self.orders: Dict[str, OrderEvent] = {}       # Keyed by order_id
        self.ticks: Dict[str, TickEvent] = {}         # Keyed by token
        self.trade_history: List[Dict[str, Any]] = []
        self.spot_levels: Dict[str, Dict[str, float]] = {
            "NIFTY": {"spot": 23140.5, "vwap": 23063.1, "pdh": 23162.7, "pdl": 23020.95, "high": 23162.7, "low": 23020.95},
            "BANKNIFTY": {"spot": 55580.4, "vwap": 55438.5, "pdh": 55762.6, "pdl": 55373.75, "high": 55762.6, "low": 55373.75},
            "SENSEX": {"spot": 73895.74, "vwap": 73580.54, "pdh": 73968.05, "pdl": 73477.77, "high": 73968.05, "low": 73477.77},
        }

        # Wire up event subscriptions
        self._register_subscribers()

        # Restore persistent state from SQLite storage if configured
        if self.storage:
            self._restore_from_storage()

    def _reconcile_unrecorded_trades(self):
        """
        Self-healing reconciliation: Scans filled exit orders against the trades table.
        If a position was exited (sell order filled) but no trade was recorded in SQLite,
        reconstructs the completed trade, cancels lingering trigger-pending SL orders,
        and saves the trade to storage.
        """
        if not self.storage:
            return
        try:
            with self.storage._get_connection() as conn:
                # Find filled SELL orders that represent completed position exits
                sell_orders = conn.execute("""
                    SELECT * FROM orders 
                    WHERE transaction_type = 'SELL' 
                      AND status = 'FILLED' 
                      AND order_id NOT LIKE 'ORD_SL_%'
                    ORDER BY created_at ASC
                """).fetchall()

                for s_row in sell_orders:
                    s_ord = dict(s_row)
                    symbol = s_ord.get("symbol", "")
                    s_qty = int(s_ord.get("filled_quantity") or s_ord.get("quantity") or 0)
                    s_price = float(s_ord.get("average_price") or s_ord.get("price") or 0.0)
                    s_time = s_ord.get("created_at", "")
                    s_date = s_time[:10] if s_time else datetime.now().strftime("%Y-%m-%d")
                    is_paper = bool(s_ord.get("is_paper", 1))

                    if not symbol or s_qty <= 0:
                        continue

                    # Check if a trade already exists for this symbol and date
                    existing = conn.execute("""
                        SELECT COUNT(*) as cnt FROM trades 
                        WHERE symbol = ? AND (date = ? OR timestamp LIKE ?)
                    """, (symbol, s_date, f"{s_date}%")).fetchone()

                    if existing and existing["cnt"] > 0:
                        continue  # Already recorded

                    # Find corresponding filled BUY order
                    b_row = conn.execute("""
                        SELECT * FROM orders 
                        WHERE symbol = ? AND transaction_type = 'BUY' AND status = 'FILLED'
                        ORDER BY created_at ASC LIMIT 1
                    """, (symbol,)).fetchone()

                    b_price = 0.0
                    b_exchange = "NSE"
                    if b_row:
                        b_ord = dict(b_row)
                        b_price = float(b_ord.get("average_price") or b_ord.get("price") or 0.0)
                        b_exchange = b_ord.get("exchange") or "NSE"

                    # If no buy order found, look in positions table
                    if b_price == 0.0:
                        pos_row = conn.execute("SELECT * FROM positions WHERE symbol = ?", (symbol,)).fetchone()
                        if pos_row:
                            p_dict = dict(pos_row)
                            b_price = float(p_dict.get("entry_price") or 0.0)
                            b_exchange = p_dict.get("exchange") or "NSE"

                    if b_price == 0.0:
                        b_price = s_price

                    gross_pnl = round((s_price - b_price) * s_qty, 2)
                    charges = calculate_option_charges(b_price, s_price, s_qty, b_exchange)
                    total_fee = charges.get("total_charges", 61.79)
                    net_pnl = round(gross_pnl - total_fee, 2)

                    import re
                    strike_val = 0.0
                    opt_val = ""
                    # Indian index strikes are 5 digits (e.g. 72200, 53900, 22600) or 4 digits (<10000)
                    m = re.search(r'(\d{5})\s*(CE|PE)$', symbol, re.IGNORECASE)
                    if m:
                        strike_val = float(m.group(1))
                        opt_val = m.group(2).upper()
                    else:
                        m4 = re.search(r'(\d{4})\s*(CE|PE)$', symbol, re.IGNORECASE)
                        if m4:
                            strike_val = float(m4.group(1))
                            opt_val = m4.group(2).upper()
                    if strike_val > 100000:
                        strike_val = strike_val % 100000

                    exit_reason = "Target 1 (+2.0R) Hit" if gross_pnl > 0 else "Stop Loss Hit"
                    trade_id = f"TR_{s_date.replace('-', '')[4:]}_001"

                    trade_record = {
                        "id": trade_id,
                        "timestamp": s_time.replace("T", " ")[:19] if s_time else datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "date": s_date,
                        "symbol": symbol,
                        "strike_price": strike_val,
                        "option_type": opt_val,
                        "quantity": s_qty,
                        "entry_price": b_price,
                        "exit_price": s_price,
                        "gross_pnl": gross_pnl,
                        "brokerage": charges.get("brokerage", 40.0),
                        "total_charges": total_fee,
                        "net_pnl": net_pnl,
                        "is_paper": 1 if is_paper else 0,
                        "exit_reason": exit_reason
                    }

                    self.storage.save_trade(trade_record)
                    self.storage.mark_position_closed(symbol, realized_pnl=gross_pnl)
                    logger.info(f"[STATE] 🛠️ Reconciled unrecorded completed trade for {symbol}: Gross=₹{gross_pnl:+.2f}, Net=₹{net_pnl:+.2f}")

                    # Cancel lingering resting SL orders for this symbol
                    conn.execute("""
                        UPDATE orders 
                        SET status = 'CANCELLED', updated_at = ? 
                        WHERE symbol = ? AND order_id LIKE 'ORD_SL_%' AND status = 'TRIGGER_PENDING'
                    """, (datetime.now().isoformat(), symbol))
                    conn.commit()

        except Exception as e:
            logger.error(f"[STATE] Error in _reconcile_unrecorded_trades: {e}")

    def _restore_from_storage(self):
        """Restores ledger, active positions, and trade history from SQLite storage."""
        if not self.storage:
            return
        try:
            # First reconcile any unrecorded exit executions
            self._reconcile_unrecorded_trades()

            today_str = datetime.now().strftime("%Y-%m-%d")
            ledger = self.storage.load_daily_ledger(today_str)
            if ledger:
                self.trades_taken_today = int(ledger.get("trades_taken_today") or 0)
                self.consecutive_losses = int(ledger.get("consecutive_losses") or 0)
                self.realized_pnl = float(ledger.get("realized_pnl") or 0.0)
                self.total_brokerage = float(ledger.get("total_brokerage") or 0.0)
                self.net_pnl = float(ledger.get("net_pnl") or 0.0)
                self.daily_pnl = self.net_pnl
                self.paper_capital = float(ledger.get("paper_capital") or self.paper_capital)
                self.paper_starting_capital = float(ledger.get("paper_starting_capital") or self.paper_starting_capital)
                self.paper_available_margin = self.paper_capital
                self.paper_realized_pnl = float(ledger.get("paper_realized_pnl") or 0.0)
                self.paper_total_brokerage = float(ledger.get("paper_total_brokerage") or 0.0)
                self.paper_net_pnl = float(ledger.get("paper_net_pnl") or 0.0)
                self.paper_daily_pnl = self.paper_net_pnl
                self.paper_trades_taken = int(ledger.get("paper_trades_taken") or 0)
                logger.info(f"[STATE] Restored today's ledger checkpoint ({today_str}): Paper Capital=₹{self.paper_capital:.2f}, Paper Trades={self.paper_trades_taken}, Live Trades={self.trades_taken_today}")
            else:
                # Carry forward yesterday's closing paper capital if available
                if hasattr(self.storage, "load_latest_daily_ledger"):
                    latest_prev = self.storage.load_latest_daily_ledger()
                    if latest_prev and latest_prev.get("paper_capital"):
                        prev_cap = float(latest_prev.get("paper_capital"))
                        self.paper_capital = prev_cap
                        self.paper_starting_capital = prev_cap
                        self.paper_available_margin = prev_cap
                        logger.info(f"[STATE] Rolled over previous day's paper capital: ₹{self.paper_capital:.2f}")

            # Crash recovery: load open positions so SL/TP monitoring immediately resumes
            open_pos_list = self.storage.load_open_positions()
            for pos in open_pos_list:
                self.positions[pos.symbol] = pos
            if open_pos_list:
                logger.warning(f"[STATE] 🛡️ CRASH RECOVERY: Restored {len(open_pos_list)} OPEN POSITIONS for active SL/TP monitoring: {[p.symbol for p in open_pos_list]}")

            # Load today's orders
            orders_list = self.storage.load_todays_orders(limit=50)
            for ord_obj in orders_list:
                self.orders[ord_obj.order_id] = ord_obj

            # Load completed trades
            self.completed_trades = self.storage.load_todays_trades(is_paper=False)
            self.paper_completed_trades = self.storage.load_todays_trades(is_paper=True)
            # Sanitize any legacy strike prices with expiry prefix (e.g. 172200 -> 72200)
            for tr_list in (self.completed_trades, self.paper_completed_trades, self.trade_history):
                for tr in tr_list:
                    sp = float(tr.get("strike_price") or 0.0)
                    if sp > 100000:
                        tr["strike_price"] = sp % 100000

            logger.info(f"[STATE] Restored trades: {len(self.completed_trades)} live, {len(self.paper_completed_trades)} paper, {len(self.trade_history)} total history.")

            # Self-healing ledger recalculation from completed trades
            if self.paper_completed_trades:
                self._recalculate_paper_ledger()
                self._sync_ledger_to_storage()

            if self.completed_trades:
                self.realized_pnl = round(sum(float(t.get("gross_pnl", 0.0)) for t in self.completed_trades), 2)
                self.total_brokerage = round(sum(float(t.get("total_charges", 0.0)) for t in self.completed_trades), 2)
                self.net_pnl = round(sum(float(t.get("net_pnl", 0.0)) for t in self.completed_trades), 2)
                self.daily_pnl = self.net_pnl
                self.trades_taken_today = len(self.completed_trades)
                self._sync_ledger_to_storage()

            self._recalculate_portfolio()
        except Exception as e:
            logger.error(f"[STATE] Error restoring state from storage: {e}")

    def _sync_ledger_to_storage(self):
        """Flushes current daily metrics to SQLite daily_ledger."""
        if not self.storage:
            return
        today_str = datetime.now().strftime("%Y-%m-%d")
        ledger_data = {
            "date": today_str,
            "execution_mode": self.execution_mode,
            "starting_equity": self.starting_equity,
            "realized_pnl": self.realized_pnl,
            "total_brokerage": self.total_brokerage,
            "net_pnl": self.net_pnl,
            "trades_taken_today": self.trades_taken_today,
            "consecutive_losses": self.consecutive_losses,
            "paper_capital": self.paper_capital,
            "paper_starting_capital": self.paper_starting_capital,
            "paper_realized_pnl": self.paper_realized_pnl,
            "paper_total_brokerage": self.paper_total_brokerage,
            "paper_net_pnl": self.paper_net_pnl,
            "paper_trades_taken": self.paper_trades_taken
        }
        self.storage.save_daily_ledger(ledger_data)

    def persist_position(self, pos: PositionEvent):
        """Persists current state of a position (e.g. SL moved to breakeven, partial exit)."""
        if self.storage:
            is_paper = (self.execution_mode == "PAPER") or getattr(pos, "is_paper", False)
            self.storage.save_position(pos, is_paper=is_paper)

    def _register_subscribers(self):
        self.bus.subscribe(EventType.TICK, self._on_tick)
        self.bus.subscribe(EventType.ORDER_UPDATE, self._on_order_update)
        self.bus.subscribe(EventType.FILL, self._on_fill)
        self.bus.subscribe(EventType.POSITION_UPDATE, self._on_position_update)

    def set_execution_mode(self, mode: str, min_capital: float = 50000.0, force: bool = False) -> tuple:
        if mode in ["PAPER", "LIVE"]:
            if mode == "PAPER":
                self.start_paper_agent()
                return True, "Execution mode switched to PAPER."
            else:
                return self.start_real_agent(min_capital=min_capital, force=force)
        return False, f"Invalid mode: {mode}"

    def start_paper_agent(self):
        self.execution_mode = "PAPER"
        self.paper_agent_status = "RUNNING"
        self.real_agent_status = "PAUSED"
        self.is_halted = False
        self.strategy_status = "Paper Agent: Scanning for Liquidity Sweep"
        logger.info("[AGENT] Paper Trading Agent STARTED.")
        self._sync_ledger_to_storage()
        self.broadcast_state()

    def pause_paper_agent(self):
        self.paper_agent_status = "PAUSED"
        logger.info("[AGENT] Paper Trading Agent PAUSED.")
        self.broadcast_state()

    def start_real_agent(self, min_capital: float = 50000.0, force: bool = False) -> tuple:
        """
        Arms Real Live Trading Agent.
        Enforces capital adequacy against live Angel One RMS balance.
        Returns (success: bool, message: str).
        """
        if not self.broker_rms.get("is_live_synced", False) and not force:
            logger.warning("[AGENT] Cannot start Real Agent: Live broker RMS not synced.")
            return False, "Live broker RMS is not synchronized with Angel One."

        avail_cash = float(self.broker_rms.get("availablecash", 0.0) or self.broker_rms.get("net", 0.0) or 0.0)
        if not force and avail_cash < min_capital:
            logger.warning(
                f"[AGENT] Cannot start Real Agent: Insufficient capital. "
                f"Available: ₹{avail_cash:.2f}, Required: ₹{min_capital:.2f}"
            )
            return False, (
                f"Insufficient capital: Available Angel One balance ₹{avail_cash:,.2f} is below minimum "
                f"required ₹{min_capital:,.2f} (1.5% risk rule for 1 lot)."
            )

        self.execution_mode = "LIVE"
        self.real_agent_status = "RUNNING"
        self.paper_agent_status = "PAUSED"
        self.is_halted = False
        self.strategy_status = "Real Agent: Active RMS Live Execution Armed"
        logger.warning("[AGENT] REAL TRADING AGENT STARTED - Live Angel One Orders Armed.")
        self._sync_ledger_to_storage()
        self.broadcast_state()
        return True, "Real Live Trading Agent started successfully."

    def pause_real_agent(self):
        self.real_agent_status = "PAUSED"
        logger.warning("[AGENT] REAL TRADING AGENT PAUSED.")
        self.broadcast_state()

    def set_paper_capital(self, capital: float):
        """Sets dummy capital for paper trading inside its own enclosed ledger."""
        self.paper_capital = float(capital)
        self.paper_starting_capital = float(capital)
        self.paper_available_margin = float(capital)
        # NEVER touches self.broker_rms or live equity!
        logger.info(f"[STATE] Dummy Paper Capital set to ₹{capital:.2f} (enclosed paper ledger).")
        self._sync_ledger_to_storage()
        self.broadcast_state()

    def update_broker_rms(self, rms_data: Dict[str, Any], min_capital: float = 50000.0):
        """Updates live Angel One RMS balance."""
        try:
            if rms_data.get("is_simulated"):
                # Simulated placeholder should never overwrite live broker RMS
                self.broker_rms["is_live_synced"] = False
                self.broadcast_state()
                return

            net = float(rms_data.get("net", 0.0) or 0.0)
            avail = float(rms_data.get("availablecash", 0.0) or 0.0)
            collateral = float(rms_data.get("collateral", 0.0) or 0.0)
            debits = float(rms_data.get("utiliseddebits", 0.0) or 0.0)

            self.broker_rms = {
                "net": net,
                "availablecash": avail,
                "collateral": collateral,
                "utiliseddebits": debits,
                "m2munrealized": float(rms_data.get("m2munrealized", 0.0) or 0.0),
                "m2mrealized": float(rms_data.get("m2mrealized", 0.0) or 0.0),
                "is_live_synced": True
            }
            self.available_margin = avail
            self.equity = net
            self.starting_equity = net
            logger.info(f"[STATE] Angel One RMS updated: Net=₹{net:.2f}, Cash=₹{avail:.2f}, Collateral=₹{collateral:.2f}")

            # Safety Governor: Auto-pause Real Agent if running and live cash is below min_capital
            if self.real_agent_status == "RUNNING" and avail < min_capital:
                logger.warning(
                    f"[AGENT] Auto-pausing Real Agent: Available cash (₹{avail:.2f}) is below minimum "
                    f"required capital ₹{min_capital:.2f}."
                )
                self.real_agent_status = "PAUSED"
                self.execution_mode = "PAPER"
                self.strategy_status = f"Real Agent Paused: Capital (₹{avail:.2f}) Below ₹{min_capital:.2f} Minimum"

            self.broadcast_state()
        except Exception as e:
            logger.error(f"[STATE] Error parsing RMS data: {e}")

    def set_strategy_status(self, status: str):
        self.strategy_status = status
        self.broadcast_state()

    def trigger_panic(self):
        self.is_panic_active = True
        self.is_halted = True
        self.strategy_status = "EMERGENCY PANIC TRIGGERED - HALTED"
        logger.warning("[STATE] EMERGENCY PANIC TRIGGERED! Halting all strategy activity.")
        self.broadcast_state()

    def reset_panic(self):
        self.is_panic_active = False
        self.is_halted = False
        self.strategy_status = "Scanning for Liquidity Sweep"
        logger.info("[STATE] Emergency Panic cleared. Engine resumed.")
        self.broadcast_state()

    def update_spot_telemetry(self, underlying: str, spot: float, vwap: float, pdh: float = 0.0, pdl: float = 0.0, high: float = 0.0, low: float = 0.0):
        if underlying in self.spot_levels:
            current = self.spot_levels[underlying]
            current["spot"] = spot
            current["vwap"] = vwap
            if pdh > 0: current["pdh"] = pdh
            if pdl > 0: current["pdl"] = pdl
            if high > 0: current["high"] = max(current["high"], high)
            if low > 0: current["low"] = min(current["low"], low) if current["low"] > 0 else low

    async def _on_tick(self, event: TickEvent):
        self.ticks[event.token] = event
        # If tick matches any active open position, update unrealized P&L
        updated = False
        for symbol, pos in list(self.positions.items()):
            if pos.token == event.token and pos.is_open:
                pos.current_ltp = event.ltp
                price_diff = event.ltp - pos.entry_price
                pos.unrealized_pnl = round(price_diff * pos.quantity, 2)
                pos.unrealized_pnl_pct = round((price_diff / pos.entry_price) * 100, 2) if pos.entry_price > 0 else 0.0
                updated = True
        
        if updated:
            self._recalculate_portfolio()

    async def _on_order_update(self, event: OrderEvent):
        self.orders[event.order_id] = event
        if self.storage:
            is_paper = getattr(event, "is_paper", None)
            if is_paper is None:
                is_paper = (self.execution_mode == "PAPER") or ("PAPER" in event.order_id or "ORD_NIFTY_" in event.order_id or "ORD_BANKNIFTY_" in event.order_id or "ORD_SENSEX_" in event.order_id or "MANUAL_EXIT_" in event.order_id)
            self.storage.save_order(event, is_paper=bool(is_paper))
        self.broadcast_state()

    async def _on_fill(self, event: FillEvent):
        logger.info(f"[STATE] Order filled: {event.symbol} Qty={event.quantity} Price={event.price} Slip={event.slippage:.2f}")
        self.broadcast_state()

    async def _on_position_update(self, event: PositionEvent):
        self.positions[event.symbol] = event
        if self.storage:
            is_paper = (self.execution_mode == "PAPER") or getattr(event, "is_paper", False)
            self.storage.save_position(event, is_paper=is_paper)
        self._recalculate_portfolio()

    def _recalculate_portfolio(self):
        """Recalculates equity, unrealized P&L, daily drawdown %."""
        # Auto-retire any positions where quantity is zero
        for p in list(self.positions.values()):
            if p.is_open and p.quantity <= 0:
                p.is_open = False
                if self.storage:
                    self.storage.mark_position_closed(p.symbol, realized_pnl=p.realized_pnl)

        total_unrealized = sum(p.unrealized_pnl for p in self.positions.values() if p.is_open and p.quantity > 0)
        self.unrealized_pnl = round(total_unrealized, 2)
        self.daily_pnl = round(self.realized_pnl + self.unrealized_pnl, 2)
        self.equity = round(self.starting_equity + self.daily_pnl, 2)
        
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity

        drawdown = (self.starting_equity - self.equity) / self.starting_equity
        self.daily_drawdown_pct = max(0.0, round(drawdown * 100, 2))

    def record_completed_trade(
        self,
        pnl: float,
        entry_price: float = 0.0,
        exit_price: float = 0.0,
        quantity: int = 0,
        symbol: str = "",
        exchange: str = "NSE",
        is_paper: bool = False,
        strike_price: float = 0.0,
        option_type: str = "",
        exit_reason: str = ""
    ):
        """Called when a position is closed. Computes brokerage and updates net ledger."""
        charges = {"brokerage": 40.0, "total_charges": 65.0}
        if entry_price > 0 and exit_price > 0 and quantity > 0:
            charges = calculate_option_charges(entry_price, exit_price, quantity, exchange)

        total_fee = charges.get("total_charges", 65.0)
        net = round(pnl - total_fee, 2)

        # Resolve strike price and option type
        # Resolve strike price and option type
        resolved_strike = float(strike_price or 0.0)
        resolved_opt = option_type or ""
        if symbol:
            import re
            m = re.search(r'(\d{5})\s*(CE|PE)$', symbol, re.IGNORECASE)
            if not m:
                m = re.search(r'(\d{4})\s*(CE|PE)$', symbol, re.IGNORECASE)
            if m:
                if resolved_strike == 0.0 or resolved_strike > 100000:
                    try:
                        resolved_strike = float(m.group(1))
                    except Exception:
                        pass
                if not resolved_opt:
                    resolved_opt = m.group(2).upper()

        if resolved_strike > 100000:
            resolved_strike = resolved_strike % 100000

        trade_num = len(self.completed_trades) + len(self.paper_completed_trades) + 1
        is_paper_trade = bool(is_paper or self.execution_mode == "PAPER")
        today_date_str = datetime.now().strftime("%Y-%m-%d")
        trade_record = {
            "id": f"TR_{datetime.now().strftime('%m%d')}_{trade_num:03d}",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "date": today_date_str,
            "symbol": symbol or "OPTIDX",
            "strike_price": resolved_strike,
            "option_type": resolved_opt,
            "quantity": quantity,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "gross_pnl": round(pnl, 2),
            "brokerage": charges.get("brokerage", 40.0),
            "total_charges": total_fee,
            "net_pnl": net,
            "is_paper": 1 if is_paper_trade else 0,
            "exit_reason": exit_reason
        }

        if is_paper_trade:
            self.paper_realized_pnl += round(pnl, 2)
            self.paper_total_brokerage += total_fee
            self.paper_net_pnl += net
            self.paper_capital += net
            self.paper_trades_taken += 1
            self.paper_completed_trades.append(trade_record)
        else:
            self.realized_pnl += round(pnl, 2)
            self.total_brokerage += total_fee
            self.net_pnl += net
            self.trades_taken_today += 1
            self.completed_trades.append(trade_record)
            if pnl < 0:
                self.consecutive_losses += 1
            else:
                self.consecutive_losses = 0

        self.trade_history.insert(0, trade_record)

        if self.storage:
            self.storage.save_trade(trade_record)
            self.storage.mark_position_closed(symbol, realized_pnl=pnl)
            self._sync_ledger_to_storage()

        self._recalculate_portfolio()
        self.broadcast_state()

    def remove_paper_trade(self, trade_id: str = ""):
        """Removes a paper trade by ID or removes the latest if empty."""
        if not self.paper_completed_trades:
            return
        
        target = None
        if not trade_id or trade_id.upper() == "LATEST":
            target = self.paper_completed_trades.pop()
        else:
            for i, tr in enumerate(self.paper_completed_trades):
                if tr.get("id") == trade_id:
                    target = self.paper_completed_trades.pop(i)
                    break
        
        if target:
            logger.info(f"[STATE] Removed paper trade {target.get('id')}: {target.get('symbol')}")
            if self.storage:
                self.storage.delete_paper_trade(target.get("id"))
            self._recalculate_paper_ledger()
            if self.storage:
                self._sync_ledger_to_storage()
            self.broadcast_state()

    def reset_paper_trades(self):
        """Clears all paper trades and resets paper quotas and ledger."""
        self.paper_completed_trades.clear()
        self.paper_trades_taken = 0
        self.paper_realized_pnl = 0.0
        self.paper_total_brokerage = 0.0
        self.paper_net_pnl = 0.0
        self.paper_daily_pnl = 0.0
        self.paper_capital = float(self.paper_starting_capital)
        self.paper_available_margin = float(self.paper_starting_capital)
        paper_order_ids = [oid for oid, ord_obj in self.orders.items() if getattr(ord_obj, "order_id", "").startswith(("ORD_NIFTY_", "ORD_BANKNIFTY_", "MANUAL_EXIT_"))]
        for oid in paper_order_ids:
            self.orders.pop(oid, None)
        logger.info("[STATE] Reset all paper trades and quota back to 0.")
        if self.storage:
            self.storage.clear_paper_trades(today_only=True)
            self._sync_ledger_to_storage()
        self.broadcast_state()

    def _recalculate_paper_ledger(self):
        """Recalculates paper trading ledger based on remaining completed trades."""
        gross = 0.0
        brokerage = 0.0
        net = 0.0
        for tr in self.paper_completed_trades:
            gross += float(tr.get("gross_pnl", 0.0))
            brokerage += float(tr.get("total_charges", 0.0))
            net += float(tr.get("net_pnl", 0.0))
        
        self.paper_realized_pnl = round(gross, 2)
        self.paper_total_brokerage = round(brokerage, 2)
        self.paper_net_pnl = round(net, 2)
        self.paper_daily_pnl = round(net, 2)
        self.paper_capital = round(self.paper_starting_capital + net, 2)
        self.paper_available_margin = self.paper_capital
        self.paper_trades_taken = len(self.paper_completed_trades)


    def get_snapshot(self) -> Dict[str, Any]:
        """Provides full serializable system snapshot for dashboard."""
        live_net = float(self.broker_rms.get("net", 0.0) or 0.0)
        live_cash = float(self.broker_rms.get("availablecash", 0.0) or 0.0)

        return {
            "execution_mode": self.execution_mode,
            # Live Angel One Ledger (for Overview, Navbar, Sidebar, Real Agent)
            "broker_rms": self.broker_rms,
            "starting_equity": live_net,
            "equity": live_net,
            "available_margin": live_cash,
            "realized_pnl": self.realized_pnl,
            "total_brokerage": round(self.total_brokerage, 2),
            "net_pnl": round(self.net_pnl, 2),
            "unrealized_pnl": self.unrealized_pnl,
            "daily_pnl": self.daily_pnl,
            "daily_drawdown_pct": self.daily_drawdown_pct,
            "trades_taken_today": self.trades_taken_today,
            "max_trades_allowed": self.max_trades_allowed,
            "consecutive_losses": self.consecutive_losses,
            "paper_agent_status": self.paper_agent_status,
            "real_agent_status": self.real_agent_status,
            "is_panic_active": self.is_panic_active,
            "is_halted": self.is_halted,
            "strategy_status": self.strategy_status,
            "positions": [pos.to_dict() for pos in self.positions.values() if pos.is_open and pos.quantity > 0],
            "real_positions": [pos.to_dict() for pos in self.positions.values() if pos.is_open and pos.quantity > 0 and not getattr(pos, 'is_paper', False) and getattr(pos, 'execution_mode', '') == 'LIVE'],
            "paper_positions": [pos.to_dict() for pos in self.positions.values() if pos.is_open and pos.quantity > 0 and (getattr(pos, 'is_paper', False) or getattr(pos, 'execution_mode', '') == 'PAPER')],
            "orders": [ord.to_dict() for ord in list(self.orders.values())[-20:]], # recent 20
            "completed_trades": self.completed_trades[-20:],
            "trade_history": self.trade_history[:50],
            "spot_levels": self.spot_levels,
            "is_market_open": StateManager.is_market_open(),

            # Completely Enclosed Paper Trading Ledger (ONLY for Paper Trade page)
            "paper_state": {
                "capital": round(self.paper_capital, 2),
                "starting_capital": round(self.paper_starting_capital, 2),
                "available_margin": round(self.paper_available_margin, 2),
                "realized_pnl": round(self.paper_realized_pnl, 2),
                "total_brokerage": round(self.paper_total_brokerage, 2),
                "net_pnl": round(self.paper_net_pnl, 2),
                "unrealized_pnl": round(self.paper_unrealized_pnl, 2),
                "daily_pnl": round(self.paper_daily_pnl, 2),
                "drawdown_pct": self.paper_drawdown_pct,
                "trades_taken": self.paper_trades_taken,
                "max_trades_allowed": self.max_trades_allowed,
                "status": self.paper_agent_status,
                "completed_trades": self.paper_completed_trades[-20:]
            },
            "timestamp": datetime.now().isoformat()
        }

    @staticmethod
    def is_market_open() -> bool:
        """Checks if current IST time is within active market hours (Mon-Fri 09:15-15:30 IST)."""
        from datetime import timezone, timedelta, time
        ist = timezone(timedelta(hours=5, minutes=30))
        now_ist = datetime.now(ist)
        if now_ist.weekday() >= 5:
            return False
        return time(9, 15) <= now_ist.time() <= time(15, 30)

    def broadcast_state(self):
        """Enqueues a SystemStateEvent onto the event bus."""
        event = SystemStateEvent(
            execution_mode=self.execution_mode,
            equity=self.equity,
            available_margin=self.available_margin,
            daily_pnl=self.daily_pnl,
            daily_drawdown_pct=self.daily_drawdown_pct,
            trades_taken_today=self.trades_taken_today,
            max_trades_allowed=self.max_trades_allowed,
            consecutive_losses=self.consecutive_losses,
            is_panic_active=self.is_panic_active,
            strategy_status=self.strategy_status,
            active_positions_count=len([p for p in self.positions.values() if p.is_open])
        )
        self.bus.publish_nowait(event)
