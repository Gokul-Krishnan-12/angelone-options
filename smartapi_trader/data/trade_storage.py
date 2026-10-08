import sqlite3
import os
from datetime import datetime
from typing import Dict, Any, List, Optional
from smartapi_trader.core.events import PositionEvent, OrderEvent
from smartapi_trader.utils.logger import logger

class TradeStorage:
    """
    SQLite persistent storage for:
    - Open & closed positions (crash recovery for SL/Target management)
    - Orders audit book
    - Completed trades journal (both live & paper)
    - Daily ledger snapshots (capital, daily P&L, quotas)
    """

    def __init__(self, db_path: str = "data/trading_storage.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable Write-Ahead Logging for high concurrency & resilience
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        """Initializes tables and indices if they do not exist."""
        with self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS positions (
                    symbol TEXT PRIMARY KEY,
                    token TEXT,
                    underlying TEXT,
                    option_type TEXT,
                    strike_price REAL,
                    quantity INTEGER,
                    lot_size INTEGER,
                    lots INTEGER,
                    entry_price REAL,
                    current_ltp REAL,
                    unrealized_pnl REAL,
                    unrealized_pnl_pct REAL,
                    realized_pnl REAL,
                    stop_loss REAL,
                    target_1 REAL,
                    exchange TEXT DEFAULT 'NFO',
                    sl_order_id TEXT DEFAULT '',
                    sl_trigger_price REAL DEFAULT 0.0,
                    sl_limit_price REAL DEFAULT 0.0,
                    be_moved INTEGER DEFAULT 0,
                    partial_taken INTEGER DEFAULT 0,
                    is_open INTEGER DEFAULT 1,
                    is_paper INTEGER DEFAULT 0,
                    created_at TEXT,
                    updated_at TEXT
                );
            """)

            # Ensure columns exist if table was already initialized
            for col, col_def in [
                ("exchange", "TEXT DEFAULT 'NFO'"),
                ("sl_order_id", "TEXT DEFAULT ''"),
                ("sl_trigger_price", "REAL DEFAULT 0.0"),
                ("sl_limit_price", "REAL DEFAULT 0.0"),
                ("strategy_name", "TEXT DEFAULT 'ILSME_Sniper'")
            ]:
                try:
                    conn.execute(f"ALTER TABLE positions ADD COLUMN {col} {col_def};")
                except sqlite3.OperationalError:
                    pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    client_order_id TEXT,
                    symbol TEXT,
                    token TEXT,
                    exchange TEXT,
                    transaction_type TEXT,
                    order_type TEXT,
                    product_type TEXT,
                    quantity INTEGER,
                    price REAL,
                    trigger_price REAL,
                    status TEXT,
                    variety TEXT,
                    filled_quantity INTEGER,
                    average_price REAL,
                    rejection_reason TEXT,
                    is_paper INTEGER DEFAULT 0,
                    strategy_name TEXT DEFAULT 'ILSME_Sniper',
                    created_at TEXT,
                    updated_at TEXT
                );
            """)
            try:
                conn.execute("ALTER TABLE orders ADD COLUMN strategy_name TEXT DEFAULT 'ILSME_Sniper';")
            except sqlite3.OperationalError:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS trades (
                    id TEXT PRIMARY KEY,
                    timestamp TEXT,
                    date TEXT,
                    symbol TEXT,
                    strike_price REAL,
                    option_type TEXT,
                    quantity INTEGER,
                    entry_price REAL,
                    exit_price REAL,
                    gross_pnl REAL,
                    brokerage REAL,
                    total_charges REAL,
                    net_pnl REAL,
                    is_paper INTEGER DEFAULT 0,
                    exit_reason TEXT,
                    strategy_name TEXT DEFAULT 'ILSME_Sniper'
                );
            """)
            try:
                conn.execute("ALTER TABLE trades ADD COLUMN strategy_name TEXT DEFAULT 'ILSME_Sniper';")
            except sqlite3.OperationalError:
                pass

            conn.execute("""
                CREATE TABLE IF NOT EXISTS daily_ledger (
                    date TEXT PRIMARY KEY,
                    execution_mode TEXT,
                    starting_equity REAL,
                    realized_pnl REAL,
                    total_brokerage REAL,
                    net_pnl REAL,
                    trades_taken_today INTEGER DEFAULT 0,
                    consecutive_losses INTEGER DEFAULT 0,
                    paper_capital REAL,
                    paper_starting_capital REAL,
                    paper_realized_pnl REAL,
                    paper_total_brokerage REAL,
                    paper_net_pnl REAL,
                    paper_trades_taken INTEGER DEFAULT 0,
                    updated_at TEXT
                );
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_date ON trades(date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trades_is_paper ON trades(is_paper);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_positions_is_open ON positions(is_open);")
            conn.commit()

        logger.info(f"[STORAGE] Initialized SQLite trading storage at {self.db_path}")

    # ==================== POSITIONS ====================

    def save_position(self, pos: PositionEvent, is_paper: bool = False):
        """Upserts position into database."""
        now_str = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO positions (
                        symbol, token, underlying, option_type, strike_price,
                        quantity, lot_size, lots, entry_price, current_ltp,
                        unrealized_pnl, unrealized_pnl_pct, realized_pnl,
                        stop_loss, target_1, exchange, sl_order_id, sl_trigger_price, sl_limit_price,
                        be_moved, partial_taken, is_open, is_paper, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        token=excluded.token,
                        quantity=excluded.quantity,
                        entry_price=excluded.entry_price,
                        current_ltp=excluded.current_ltp,
                        unrealized_pnl=excluded.unrealized_pnl,
                        unrealized_pnl_pct=excluded.unrealized_pnl_pct,
                        realized_pnl=excluded.realized_pnl,
                        stop_loss=excluded.stop_loss,
                        target_1=excluded.target_1,
                        exchange=excluded.exchange,
                        sl_order_id=excluded.sl_order_id,
                        sl_trigger_price=excluded.sl_trigger_price,
                        sl_limit_price=excluded.sl_limit_price,
                        be_moved=excluded.be_moved,
                        partial_taken=excluded.partial_taken,
                        is_open=excluded.is_open,
                        updated_at=excluded.updated_at;
                """, (
                    pos.symbol, pos.token, pos.underlying, pos.option_type, pos.strike_price,
                    pos.quantity, pos.lot_size, pos.lots, pos.entry_price, pos.current_ltp,
                    pos.unrealized_pnl, pos.unrealized_pnl_pct, pos.realized_pnl,
                    pos.stop_loss, pos.target_1, getattr(pos, "exchange", "NFO"),
                    getattr(pos, "sl_order_id", ""), getattr(pos, "sl_trigger_price", 0.0),
                    getattr(pos, "sl_limit_price", 0.0),
                    1 if pos.be_moved else 0,
                    1 if pos.partial_taken else 0, 1 if pos.is_open else 0,
                    1 if is_paper else 0, now_str, now_str
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"[STORAGE] Error saving position {pos.symbol}: {e}")

    def load_open_positions(self) -> List[PositionEvent]:
        """Loads all open positions from database for crash recovery."""
        positions = []
        try:
            with self._get_connection() as conn:
                rows = conn.execute("SELECT * FROM positions WHERE is_open = 1").fetchall()
                for r in rows:
                    pos = PositionEvent(
                        symbol=r["symbol"],
                        token=r["token"],
                        underlying=r["underlying"],
                        option_type=r["option_type"],
                        strike_price=float(r["strike_price"] or 0.0),
                        quantity=int(r["quantity"] or 0),
                        lot_size=int(r["lot_size"] or 0),
                        lots=int(r["lots"] or 0),
                        entry_price=float(r["entry_price"] or 0.0),
                        current_ltp=float(r["current_ltp"] or 0.0),
                        unrealized_pnl=float(r["unrealized_pnl"] or 0.0),
                        unrealized_pnl_pct=float(r["unrealized_pnl_pct"] or 0.0),
                        realized_pnl=float(r["realized_pnl"] or 0.0),
                        stop_loss=float(r["stop_loss"] or 0.0),
                        target_1=float(r["target_1"] or 0.0),
                        exchange=r["exchange"] if "exchange" in r.keys() else "NFO",
                        sl_order_id=r["sl_order_id"] if "sl_order_id" in r.keys() else "",
                        sl_trigger_price=float(r["sl_trigger_price"] or 0.0) if "sl_trigger_price" in r.keys() else 0.0,
                        sl_limit_price=float(r["sl_limit_price"] or 0.0) if "sl_limit_price" in r.keys() else 0.0,
                        be_moved=bool(r["be_moved"]),
                        partial_taken=bool(r["partial_taken"]),
                        is_open=True
                    )
                    positions.append(pos)
        except Exception as e:
            logger.error(f"[STORAGE] Error loading open positions: {e}")
        return positions

    def mark_position_closed(self, symbol: str, realized_pnl: float = 0.0):
        """Marks a position as closed in database."""
        now_str = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE positions
                    SET is_open = 0, realized_pnl = ?, updated_at = ?
                    WHERE symbol = ?
                """, (realized_pnl, now_str, symbol))
                conn.commit()
        except Exception as e:
            logger.error(f"[STORAGE] Error marking position closed {symbol}: {e}")

    # ==================== ORDERS ====================

    def save_order(self, order: OrderEvent, is_paper: bool = False):
        """Upserts order record into database."""
        now_str = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO orders (
                        order_id, client_order_id, symbol, token, exchange,
                        transaction_type, order_type, product_type, quantity,
                        price, trigger_price, status, variety, filled_quantity,
                        average_price, rejection_reason, is_paper, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(order_id) DO UPDATE SET
                        status=excluded.status,
                        filled_quantity=excluded.filled_quantity,
                        average_price=excluded.average_price,
                        rejection_reason=excluded.rejection_reason,
                        updated_at=excluded.updated_at;
                """, (
                    order.order_id, order.client_order_id, order.symbol, order.token, order.exchange,
                    order.transaction_type, order.order_type, order.product_type, order.quantity,
                    order.price, order.trigger_price, order.status, order.variety,
                    order.filled_quantity, order.average_price, order.rejection_reason,
                    1 if is_paper else 0, now_str, now_str
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"[STORAGE] Error saving order {order.order_id}: {e}")

    def load_todays_orders(self, limit: int = 50) -> List[OrderEvent]:
        """Loads today's orders."""
        orders = []
        today_prefix = datetime.now().strftime("%Y-%m-%d")
        try:
            with self._get_connection() as conn:
                rows = conn.execute("""
                    SELECT * FROM orders
                    WHERE created_at LIKE ?
                    ORDER BY created_at DESC LIMIT ?
                """, (f"{today_prefix}%", limit)).fetchall()
                for r in reversed(rows):
                    ord_obj = OrderEvent(
                        order_id=r["order_id"],
                        client_order_id=r["client_order_id"] or "",
                        symbol=r["symbol"] or "",
                        token=r["token"] or "",
                        exchange=r["exchange"] or "NFO",
                        transaction_type=r["transaction_type"] or "BUY",
                        order_type=r["order_type"] or "LIMIT",
                        product_type=r["product_type"] or "INTRADAY",
                        quantity=int(r["quantity"] or 0),
                        price=float(r["price"] or 0.0),
                        trigger_price=float(r["trigger_price"] or 0.0),
                        status=r["status"] or "PENDING",
                        variety=r["variety"] or "NORMAL",
                        filled_quantity=int(r["filled_quantity"] or 0),
                        average_price=float(r["average_price"] or 0.0),
                        rejection_reason=r["rejection_reason"] or ""
                    )
                    orders.append(ord_obj)
        except Exception as e:
            logger.error(f"[STORAGE] Error loading orders: {e}")
        return orders

    # ==================== TRADES ====================

    def save_trade(self, trade: Dict[str, Any]):
        """Persists completed trade into trades table."""
        ts = trade.get("timestamp") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        date_str = ts.split(" ")[0] if " " in ts else datetime.now().strftime("%Y-%m-%d")
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO trades (
                        id, timestamp, date, symbol, strike_price, option_type,
                        quantity, entry_price, exit_price, gross_pnl, brokerage,
                        total_charges, net_pnl, is_paper, exit_reason, strategy_name
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        exit_price=excluded.exit_price,
                        gross_pnl=excluded.gross_pnl,
                        net_pnl=excluded.net_pnl,
                        exit_reason=excluded.exit_reason,
                        strategy_name=excluded.strategy_name;
                """, (
                    trade.get("id"),
                    ts,
                    date_str,
                    trade.get("symbol", ""),
                    float(trade.get("strike_price") or 0.0),
                    trade.get("option_type", ""),
                    int(trade.get("quantity") or 0),
                    float(trade.get("entry_price") or 0.0),
                    float(trade.get("exit_price") or 0.0),
                    float(trade.get("gross_pnl") or 0.0),
                    float(trade.get("brokerage") or 40.0),
                    float(trade.get("total_charges") or 65.0),
                    float(trade.get("net_pnl") or 0.0),
                    1 if trade.get("is_paper") else 0,
                    trade.get("exit_reason", ""),
                    trade.get("strategy_name") or "ILSME_Sniper"
                ))
                conn.commit()
                logger.info(f"[STORAGE] Persisted trade {trade.get('id')} to SQLite.")
        except Exception as e:
            logger.error(f"[STORAGE] Error saving trade {trade.get('id')}: {e}")

    def load_todays_trades(self, is_paper: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Loads completed trades for today."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        trades = []
        try:
            with self._get_connection() as conn:
                if is_paper is None:
                    rows = conn.execute("SELECT * FROM trades WHERE date = ? ORDER BY timestamp ASC", (today_str,)).fetchall()
                else:
                    paper_val = 1 if is_paper else 0
                    rows = conn.execute("SELECT * FROM trades WHERE date = ? AND is_paper = ? ORDER BY timestamp ASC", (today_str, paper_val)).fetchall()
                for r in rows:
                    trades.append(dict(r))
        except Exception as e:
            logger.error(f"[STORAGE] Error loading today's trades: {e}")
        return trades

    def load_all_trades(self, limit: int = 100, is_paper: Optional[bool] = None) -> List[Dict[str, Any]]:
        """Loads recent completed trades across all days."""
        trades = []
        try:
            with self._get_connection() as conn:
                if is_paper is None:
                    rows = conn.execute("SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?", (limit,)).fetchall()
                else:
                    paper_val = 1 if is_paper else 0
                    rows = conn.execute("SELECT * FROM trades WHERE is_paper = ? ORDER BY timestamp DESC LIMIT ?", (paper_val, limit)).fetchall()
                for r in rows:
                    trades.append(dict(r))
        except Exception as e:
            logger.error(f"[STORAGE] Error loading all trades: {e}")
        return trades

    def delete_paper_trade(self, trade_id: str):
        """Removes a paper trade by ID."""
        try:
            with self._get_connection() as conn:
                conn.execute("DELETE FROM trades WHERE id = ? AND is_paper = 1", (trade_id,))
                conn.commit()
                logger.info(f"[STORAGE] Deleted paper trade {trade_id} from SQLite.")
        except Exception as e:
            logger.error(f"[STORAGE] Error deleting paper trade {trade_id}: {e}")

    def clear_paper_trades(self, today_only: bool = True):
        """Clears paper trades (for trade reset feature)."""
        try:
            today_str = datetime.now().strftime("%Y-%m-%d")
            with self._get_connection() as conn:
                if today_only:
                    conn.execute("DELETE FROM trades WHERE is_paper = 1 AND date = ?", (today_str,))
                    conn.execute("DELETE FROM orders WHERE is_paper = 1 AND created_at LIKE ?", (f"{today_str}%",))
                    conn.execute("DELETE FROM positions WHERE is_paper = 1")
                else:
                    conn.execute("DELETE FROM trades WHERE is_paper = 1")
                    conn.execute("DELETE FROM orders WHERE is_paper = 1")
                    conn.execute("DELETE FROM positions WHERE is_paper = 1")
                conn.commit()
                logger.info("[STORAGE] Cleared paper trades and positions from SQLite.")
        except Exception as e:
            logger.error(f"[STORAGE] Error clearing paper trades: {e}")

    # ==================== DAILY LEDGER ====================

    def save_daily_ledger(self, ledger: Dict[str, Any]):
        """Upserts daily ledger snapshot."""
        date_str = ledger.get("date") or datetime.now().strftime("%Y-%m-%d")
        now_str = datetime.now().isoformat()
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO daily_ledger (
                        date, execution_mode, starting_equity, realized_pnl,
                        total_brokerage, net_pnl, trades_taken_today, consecutive_losses,
                        paper_capital, paper_starting_capital, paper_realized_pnl,
                        paper_total_brokerage, paper_net_pnl, paper_trades_taken,
                        updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(date) DO UPDATE SET
                        execution_mode=excluded.execution_mode,
                        realized_pnl=excluded.realized_pnl,
                        total_brokerage=excluded.total_brokerage,
                        net_pnl=excluded.net_pnl,
                        trades_taken_today=excluded.trades_taken_today,
                        consecutive_losses=excluded.consecutive_losses,
                        paper_capital=excluded.paper_capital,
                        paper_starting_capital=excluded.paper_starting_capital,
                        paper_realized_pnl=excluded.paper_realized_pnl,
                        paper_total_brokerage=excluded.paper_total_brokerage,
                        paper_net_pnl=excluded.paper_net_pnl,
                        paper_trades_taken=excluded.paper_trades_taken,
                        updated_at=excluded.updated_at;
                """, (
                    date_str,
                    ledger.get("execution_mode", "PAPER"),
                    float(ledger.get("starting_equity") or 0.0),
                    float(ledger.get("realized_pnl") or 0.0),
                    float(ledger.get("total_brokerage") or 0.0),
                    float(ledger.get("net_pnl") or 0.0),
                    int(ledger.get("trades_taken_today") or 0),
                    int(ledger.get("consecutive_losses") or 0),
                    float(ledger.get("paper_capital") or 100000.0),
                    float(ledger.get("paper_starting_capital") or 100000.0),
                    float(ledger.get("paper_realized_pnl") or 0.0),
                    float(ledger.get("paper_total_brokerage") or 0.0),
                    float(ledger.get("paper_net_pnl") or 0.0),
                    int(ledger.get("paper_trades_taken") or 0),
                    now_str
                ))
                conn.commit()
        except Exception as e:
            logger.error(f"[STORAGE] Error saving daily ledger: {e}")

    def load_daily_ledger(self, date_str: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Loads daily ledger snapshot for a given date (defaults to today)."""
        target_date = date_str or datetime.now().strftime("%Y-%m-%d")
        try:
            with self._get_connection() as conn:
                row = conn.execute("SELECT * FROM daily_ledger WHERE date = ?", (target_date,)).fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.error(f"[STORAGE] Error loading daily ledger for {target_date}: {e}")
        return None

    def load_latest_daily_ledger(self) -> Optional[Dict[str, Any]]:
        """Loads the most recent daily ledger row across all history to carry forward paper capital."""
        try:
            with self._get_connection() as conn:
                row = conn.execute("SELECT * FROM daily_ledger ORDER BY date DESC LIMIT 1").fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.error(f"[STORAGE] Error loading latest daily ledger: {e}")
        return None

    # ==================== CALENDAR AGGREGATIONS ====================

    def get_calendar_pnl(self, is_paper: bool = True, month: Optional[str] = None) -> Dict[str, Any]:
        """Loads and groups all trades by date for calendar display."""
        days = {}
        total_gross = 0.0
        total_charges = 0.0
        total_net = 0.0
        total_trades = 0
        winning_days = 0
        losing_days = 0
        scratch_days = 0

        try:
            with self._get_connection() as conn:
                paper_val = 1 if is_paper else 0
                if month:
                    query = "SELECT * FROM trades WHERE is_paper = ? AND (date LIKE ? OR timestamp LIKE ?) ORDER BY timestamp ASC"
                    rows = conn.execute(query, (paper_val, f"{month}%", f"{month}%")).fetchall()
                else:
                    query = "SELECT * FROM trades WHERE is_paper = ? ORDER BY timestamp ASC"
                    rows = conn.execute(query, (paper_val,)).fetchall()

                for r in rows:
                    t = dict(r)
                    d = t.get("date") or (t.get("timestamp", "").split()[0] if " " in str(t.get("timestamp", "")) else "")
                    if not d:
                        continue
                    if d not in days:
                        days[d] = {
                            "date": d,
                            "trade_count": 0,
                            "gross_pnl": 0.0,
                            "total_charges": 0.0,
                            "net_pnl": 0.0,
                            "wins": 0,
                            "losses": 0,
                            "scratches": 0,
                            "trades": []
                        }

                    net = float(t.get("net_pnl") or 0.0)
                    gross = float(t.get("gross_pnl") or 0.0)
                    charges = float(t.get("total_charges") or (t.get("brokerage") or 0.0))

                    days[d]["trade_count"] += 1
                    days[d]["gross_pnl"] = round(days[d]["gross_pnl"] + gross, 2)
                    days[d]["total_charges"] = round(days[d]["total_charges"] + charges, 2)
                    days[d]["net_pnl"] = round(days[d]["net_pnl"] + net, 2)
                    if net > 0:
                        days[d]["wins"] += 1
                    elif net < 0:
                        days[d]["losses"] += 1
                    else:
                        days[d]["scratches"] += 1

                    days[d]["trades"].append(t)

                    total_trades += 1
                    total_gross += gross
                    total_charges += charges
                    total_net += net

                for d, data in days.items():
                    if data["net_pnl"] > 0:
                        winning_days += 1
                    elif data["net_pnl"] < 0:
                        losing_days += 1
                    else:
                        scratch_days += 1

        except Exception as e:
            logger.error(f"[STORAGE] Error getting calendar pnl: {e}")

        total_days = len(days)
        win_rate = round((winning_days / total_days * 100), 1) if total_days > 0 else 0.0

        return {
            "month": month,
            "days": days,
            "summary": {
                "total_days_traded": total_days,
                "winning_days": winning_days,
                "losing_days": losing_days,
                "scratch_days": scratch_days,
                "win_rate_pct": win_rate,
                "total_trades": total_trades,
                "total_gross_pnl": round(total_gross, 2),
                "total_charges": round(total_charges, 2),
                "total_net_pnl": round(total_net, 2)
            }
        }


