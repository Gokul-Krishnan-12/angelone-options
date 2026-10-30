"""
Stock Options Persistence & Audit Trail Storage.
Stores overnight plans, intraday scans, live & paper orders,
positions, settings, and performance journal in SQLite.
"""

import os
import sqlite3
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from smartapi_trader.utils.logger import logger


class StockOptionsStorage:
    """
    Dedicated persistent database layer for AI-Powered Stock Options.
    Enforces atomic transactions and audit history.
    """

    def __init__(self, db_path: str = "data/stock_options.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def _init_db(self):
        with self._get_connection() as conn:
            # 1. Overnight Plans Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS overnight_plans (
                    plan_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    intended_date TEXT,
                    status TEXT DEFAULT 'PENDING_APPROVAL',
                    market_summary TEXT,
                    candidates_json TEXT,
                    ai_provider TEXT,
                    model TEXT,
                    no_trade_reason TEXT,
                    latency_ms REAL,
                    validation_warnings_json TEXT
                );
            """)

            # 2. Intraday Scans Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS intraday_scans (
                    scan_id TEXT PRIMARY KEY,
                    created_at TEXT,
                    interval_mins INTEGER,
                    stocks_evaluated INTEGER,
                    stocks_shortlisted INTEGER,
                    candidates_count INTEGER,
                    candidates_json TEXT,
                    ai_provider TEXT,
                    model TEXT,
                    market_summary TEXT,
                    no_trade_reason TEXT,
                    latency_ms REAL,
                    validation_warnings_json TEXT
                );
            """)

            # 3. Stock Options Orders Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_options_orders (
                    order_id TEXT PRIMARY KEY,
                    plan_id TEXT,
                    symbol TEXT,
                    underlying TEXT,
                    option_type TEXT,
                    strike REAL,
                    expiry TEXT,
                    transaction_type TEXT,
                    order_type TEXT,
                    quantity INTEGER,
                    price REAL,
                    trigger_price REAL,
                    status TEXT,
                    filled_qty INTEGER DEFAULT 0,
                    average_price REAL DEFAULT 0.0,
                    is_paper INTEGER DEFAULT 0,
                    execution_mode TEXT DEFAULT 'PAPER',
                    rejection_reason TEXT,
                    created_at TEXT,
                    updated_at TEXT
                );
            """)

            # 4. Stock Options Positions Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_options_positions (
                    symbol TEXT PRIMARY KEY,
                    underlying TEXT,
                    option_type TEXT,
                    strike REAL,
                    expiry TEXT,
                    quantity INTEGER,
                    lot_size INTEGER,
                    lots INTEGER,
                    entry_price REAL,
                    current_ltp REAL,
                    unrealized_pnl REAL DEFAULT 0.0,
                    realized_pnl REAL DEFAULT 0.0,
                    stop_loss REAL,
                    target_1 REAL,
                    token TEXT DEFAULT '',
                    is_open INTEGER DEFAULT 1,
                    is_paper INTEGER DEFAULT 0,
                    execution_mode TEXT DEFAULT 'PAPER',
                    created_at TEXT,
                    updated_at TEXT
                );
            """)

            # Ensure token column exists in existing DBs
            try:
                conn.execute("ALTER TABLE stock_options_positions ADD COLUMN token TEXT DEFAULT ''")
            except Exception:
                pass

            # 5. Persistent Settings Table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_options_settings (
                    key TEXT PRIMARY KEY,
                    value TEXT,
                    updated_at TEXT
                );
            """)

            # 6. Completed Trades Performance Journal
            conn.execute("""
                CREATE TABLE IF NOT EXISTS stock_options_trades (
                    trade_id TEXT PRIMARY KEY,
                    symbol TEXT,
                    underlying TEXT,
                    option_type TEXT,
                    strike REAL,
                    quantity INTEGER,
                    entry_price REAL,
                    exit_price REAL,
                    gross_pnl REAL,
                    charges REAL DEFAULT 0.0,
                    net_pnl REAL,
                    entry_time TEXT,
                    exit_time TEXT,
                    exit_reason TEXT,
                    is_paper INTEGER DEFAULT 0,
                    created_at TEXT
                );
            """)

    # ---------------- Overnight Plans ---------------- #

    def save_overnight_plan(self, plan_data: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO overnight_plans
                (plan_id, created_at, intended_date, status, market_summary, candidates_json, ai_provider, model, no_trade_reason, latency_ms, validation_warnings_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                plan_data["plan_id"],
                plan_data.get("created_at", datetime.now().isoformat()),
                plan_data.get("intended_date", ""),
                plan_data.get("status", "PENDING_APPROVAL"),
                plan_data.get("market_summary", ""),
                json.dumps(plan_data.get("candidates", [])),
                plan_data.get("ai_provider", ""),
                plan_data.get("model", ""),
                plan_data.get("no_trade_reason"),
                float(plan_data.get("latency_ms", 0.0)),
                json.dumps(plan_data.get("validation_warnings", []))
            ))

    def get_latest_overnight_plan(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM overnight_plans ORDER BY created_at DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["candidates"] = json.loads(d.get("candidates_json") or "[]")
            d["validation_warnings"] = json.loads(d.get("validation_warnings_json") or "[]")
            return d

    def get_all_overnight_plans(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM overnight_plans ORDER BY created_at DESC LIMIT ?", (limit,))
            plans = []
            for row in cursor.fetchall():
                d = dict(row)
                d["candidates"] = json.loads(d.get("candidates_json") or "[]")
                d["validation_warnings"] = json.loads(d.get("validation_warnings_json") or "[]")
                plans.append(d)
            return plans

    def update_plan_status(self, plan_id: str, new_status: str, candidate_symbol: Optional[str] = None):
        with self._get_connection() as conn:
            if candidate_symbol:
                # Update status within candidates JSON
                cursor = conn.cursor()
                cursor.execute("SELECT candidates_json FROM overnight_plans WHERE plan_id = ?", (plan_id,))
                row = cursor.fetchone()
                if row:
                    candidates = json.loads(row["candidates_json"] or "[]")
                    for c in candidates:
                        if c.get("symbol") == candidate_symbol:
                            c["approval_status"] = new_status
                    conn.execute("UPDATE overnight_plans SET candidates_json = ? WHERE plan_id = ?", (json.dumps(candidates), plan_id))
            else:
                conn.execute("UPDATE overnight_plans SET status = ? WHERE plan_id = ?", (new_status, plan_id))

    # ---------------- Intraday Scans ---------------- #

    def save_intraday_scan(self, scan_data: Dict[str, Any]):
        with self._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO intraday_scans
                (scan_id, created_at, interval_mins, stocks_evaluated, stocks_shortlisted, candidates_count, candidates_json, ai_provider, model, market_summary, no_trade_reason, latency_ms, validation_warnings_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                scan_data["scan_id"],
                scan_data.get("created_at", datetime.now().isoformat()),
                int(scan_data.get("interval_mins", 5)),
                int(scan_data.get("stocks_evaluated", 0)),
                int(scan_data.get("stocks_shortlisted", 0)),
                int(scan_data.get("candidates_count", 0)),
                json.dumps(scan_data.get("candidates", [])),
                scan_data.get("ai_provider", ""),
                scan_data.get("model", ""),
                scan_data.get("market_summary", ""),
                scan_data.get("no_trade_reason"),
                float(scan_data.get("latency_ms", 0.0)),
                json.dumps(scan_data.get("validation_warnings", []))
            ))

    def get_latest_intraday_scan(self) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM intraday_scans ORDER BY created_at DESC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                return None
            d = dict(row)
            d["candidates"] = json.loads(d.get("candidates_json") or "[]")
            d["validation_warnings"] = json.loads(d.get("validation_warnings_json") or "[]")
            return d

    def get_recent_intraday_scans(self, limit: int = 15) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM intraday_scans ORDER BY created_at DESC LIMIT ?", (limit,))
            scans = []
            for row in cursor.fetchall():
                d = dict(row)
                d["candidates"] = json.loads(d.get("candidates_json") or "[]")
                d["validation_warnings"] = json.loads(d.get("validation_warnings_json") or "[]")
                scans.append(d)
            return scans

    # ---------------- Positions & Orders ---------------- #

    def save_position(self, pos: Dict[str, Any]):
        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute("""
                INSERT OR REPLACE INTO stock_options_positions
                (symbol, underlying, option_type, strike, expiry, quantity, lot_size, lots, entry_price, current_ltp, unrealized_pnl, realized_pnl, stop_loss, target_1, token, is_open, is_paper, execution_mode, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                pos["symbol"],
                pos.get("underlying", ""),
                pos.get("option_type", "CE"),
                float(pos.get("strike", 0.0)),
                pos.get("expiry", ""),
                int(pos.get("quantity", 0)),
                int(pos.get("lot_size", 1)),
                int(pos.get("lots", 1)),
                float(pos.get("entry_price", 0.0)),
                float(pos.get("current_ltp", 0.0)),
                float(pos.get("unrealized_pnl", 0.0)),
                float(pos.get("realized_pnl", 0.0)),
                float(pos.get("stop_loss", 0.0)),
                float(pos.get("target_1", 0.0)),
                str(pos.get("token", "")),
                1 if pos.get("is_open", True) else 0,
                1 if pos.get("is_paper", False) else 0,
                pos.get("execution_mode", "PAPER"),
                pos.get("created_at", now),
                now
            ))

    def update_position_ltp(self, symbol: str, is_paper: bool, current_ltp: float, unrealized_pnl: float):
        """Updates live LTP and floating unrealized PnL for an open stock options position."""
        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute("""
                UPDATE stock_options_positions
                SET current_ltp = ?, unrealized_pnl = ?, updated_at = ?
                WHERE symbol = ? AND is_paper = ? AND is_open = 1
            """, (float(current_ltp), float(unrealized_pnl), now, symbol, 1 if is_paper else 0))

    def get_positions(self, is_paper: bool, open_only: bool = True) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            paper_flag = 1 if is_paper else 0
            if open_only:
                cursor.execute("SELECT * FROM stock_options_positions WHERE is_paper = ? AND is_open = 1 ORDER BY updated_at DESC", (paper_flag,))
            else:
                cursor.execute("SELECT * FROM stock_options_positions WHERE is_paper = ? ORDER BY updated_at DESC", (paper_flag,))
            return [dict(r) for r in cursor.fetchall()]

    def close_position(self, symbol: str, is_paper: bool, exit_price: float, exit_reason: str = "Target Reached"):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stock_options_positions WHERE symbol = ? AND is_paper = ? AND is_open = 1", (symbol, 1 if is_paper else 0))
            row = cursor.fetchone()
            if not row:
                return
            pos = dict(row)
            entry_p = float(pos["entry_price"])
            qty = int(pos["quantity"])
            gross_pnl = round((exit_price - entry_p) * qty, 2)
            charges = round(40.0 + (exit_price * qty * 0.0006), 2)  # Brokerage + STT estimate
            net_pnl = round(gross_pnl - charges, 2)
            now = datetime.now().isoformat()

            # 1. Update position status
            conn.execute("""
                UPDATE stock_options_positions
                SET is_open = 0, current_ltp = ?, realized_pnl = ?, unrealized_pnl = 0.0, updated_at = ?
                WHERE symbol = ? AND is_paper = ?
            """, (exit_price, gross_pnl, now, symbol, 1 if is_paper else 0))

            # 2. Record completed trade
            trade_id = f"TR_STK_{int(datetime.now().timestamp() * 1000)}"
            conn.execute("""
                INSERT INTO stock_options_trades
                (trade_id, symbol, underlying, option_type, strike, quantity, entry_price, exit_price, gross_pnl, charges, net_pnl, entry_time, exit_time, exit_reason, is_paper, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                trade_id,
                pos["symbol"],
                pos["underlying"],
                pos["option_type"],
                pos["strike"],
                qty,
                entry_p,
                exit_price,
                gross_pnl,
                charges,
                net_pnl,
                pos["created_at"],
                now,
                exit_reason,
                1 if is_paper else 0,
                now
            ))

    def save_order(self, order: Dict[str, Any]):
        with self._get_connection() as conn:
            now = datetime.now().isoformat()
            conn.execute("""
                INSERT OR REPLACE INTO stock_options_orders
                (order_id, plan_id, symbol, underlying, option_type, strike, expiry, transaction_type, order_type, quantity, price, trigger_price, status, filled_qty, average_price, is_paper, execution_mode, rejection_reason, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                order["order_id"],
                order.get("plan_id", ""),
                order["symbol"],
                order.get("underlying", ""),
                order.get("option_type", "CE"),
                float(order.get("strike", 0.0)),
                order.get("expiry", ""),
                order.get("transaction_type", "BUY"),
                order.get("order_type", "LIMIT"),
                int(order.get("quantity", 0)),
                float(order.get("price", 0.0)),
                float(order.get("trigger_price", 0.0)),
                order.get("status", "PENDING"),
                int(order.get("filled_qty", 0)),
                float(order.get("average_price", 0.0)),
                1 if order.get("is_paper", False) else 0,
                order.get("execution_mode", "PAPER"),
                order.get("rejection_reason"),
                order.get("created_at", now),
                now
            ))

    def get_orders(self, is_paper: bool, limit: int = 30) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stock_options_orders WHERE is_paper = ? ORDER BY created_at DESC LIMIT ?", (1 if is_paper else 0, limit))
            return [dict(r) for r in cursor.fetchall()]

    def get_trades(self, is_paper: bool, limit: int = 50) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM stock_options_trades WHERE is_paper = ? ORDER BY exit_time DESC LIMIT ?", (1 if is_paper else 0, limit))
            return [dict(r) for r in cursor.fetchall()]

    def get_performance_summary(self, is_paper: bool) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            paper_flag = 1 if is_paper else 0
            cursor.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN net_pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN net_pnl <= 0 THEN 1 ELSE 0 END) as losses,
                    COALESCE(SUM(net_pnl), 0.0) as total_net_pnl,
                    COALESCE(SUM(gross_pnl), 0.0) as total_gross_pnl,
                    COALESCE(SUM(charges), 0.0) as total_charges,
                    COALESCE(AVG(CASE WHEN net_pnl > 0 THEN net_pnl END), 0.0) as avg_win,
                    COALESCE(AVG(CASE WHEN net_pnl <= 0 THEN net_pnl END), 0.0) as avg_loss
                FROM stock_options_trades WHERE is_paper = ?
            """, (paper_flag,))
            row = dict(cursor.fetchone())
            total = row["total_trades"] or 0
            wins = row["wins"] or 0
            losses = row["losses"] or 0
            win_rate = round((wins / total) * 100, 1) if total > 0 else 0.0

            # Profit Factor = sum of positive PnL / abs(sum of negative PnL)
            cursor.execute("SELECT COALESCE(SUM(net_pnl), 0.0) as pos FROM stock_options_trades WHERE is_paper = ? AND net_pnl > 0", (paper_flag,))
            pos_sum = cursor.fetchone()["pos"]
            cursor.execute("SELECT COALESCE(SUM(net_pnl), 0.0) as neg FROM stock_options_trades WHERE is_paper = ? AND net_pnl < 0", (paper_flag,))
            neg_sum = abs(cursor.fetchone()["neg"])
            profit_factor = round(pos_sum / neg_sum, 2) if neg_sum > 0 else (round(pos_sum, 2) if pos_sum > 0 else 1.0)

            row["win_rate_pct"] = win_rate
            row["profit_factor"] = profit_factor
            return row

    def reset_paper_history(self):
        """Resets only simulated paper trades, orders, and positions."""
        with self._get_connection() as conn:
            conn.execute("DELETE FROM stock_options_positions WHERE is_paper = 1")
            conn.execute("DELETE FROM stock_options_orders WHERE is_paper = 1")
            conn.execute("DELETE FROM stock_options_trades WHERE is_paper = 1")
            logger.info("[STORAGE] Reset paper trading history in stock_options.db.")

    def get_calendar_pnl(self, is_paper: bool = True, month: Optional[str] = None) -> Dict[str, Any]:
        """Loads and groups all stock options trades by date for calendar display."""
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
                    query = """
                        SELECT * FROM stock_options_trades 
                        WHERE is_paper = ? AND (exit_time LIKE ? OR created_at LIKE ? OR entry_time LIKE ?) 
                        ORDER BY exit_time ASC
                    """
                    rows = conn.execute(query, (paper_val, f"{month}%", f"{month}%", f"{month}%")).fetchall()
                else:
                    query = "SELECT * FROM stock_options_trades WHERE is_paper = ? ORDER BY exit_time ASC"
                    rows = conn.execute(query, (paper_val,)).fetchall()

                for r in rows:
                    t = dict(r)
                    raw_time = str(t.get("exit_time") or t.get("created_at") or t.get("entry_time") or "")
                    d = raw_time.split("T")[0].split(" ")[0] if raw_time else ""
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
                    charges = float(t.get("charges") or 0.0)

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

                    calendar_trade = {
                        "id": t.get("trade_id", ""),
                        "trade_id": t.get("trade_id", ""),
                        "timestamp": t.get("exit_time") or t.get("created_at") or "",
                        "date": d,
                        "symbol": t.get("symbol", ""),
                        "underlying": t.get("underlying", ""),
                        "option_type": t.get("option_type", ""),
                        "strike_price": float(t.get("strike") or 0.0),
                        "strike": float(t.get("strike") or 0.0),
                        "quantity": int(t.get("quantity") or 0),
                        "entry_price": float(t.get("entry_price") or 0.0),
                        "exit_price": float(t.get("exit_price") or 0.0),
                        "gross_pnl": gross,
                        "charges": charges,
                        "total_charges": charges,
                        "net_pnl": net,
                        "exit_reason": t.get("exit_reason", "Completed"),
                        "execution_strategy": "STOCK_OPTIONS",
                        "is_paper": bool(t.get("is_paper", 1))
                    }
                    days[d]["trades"].append(calendar_trade)

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
            logger.error(f"[STORAGE] Error getting stock options calendar pnl: {e}")

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

    # ---------------- Settings ---------------- #

    def save_setting(self, key: str, value: Any):
        with self._get_connection() as conn:
            val_str = json.dumps(value) if isinstance(value, (dict, list, bool, int, float)) else str(value)
            conn.execute("""
                INSERT OR REPLACE INTO stock_options_settings (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, val_str, datetime.now().isoformat()))

    def get_setting(self, key: str, default: Any = None) -> Any:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT value FROM stock_options_settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            if not row:
                return default
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
