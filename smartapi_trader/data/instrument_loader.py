import os
import sqlite3
import json
import time
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from smartapi_trader.utils.logger import logger

class InstrumentLoader:
    """
    Downloads, parses, and indexes Angel One OpenAPIScripMaster into a high-speed
    local SQLite database with sub-millisecond strike lookup capabilities.
    """
    SCRIP_MASTER_URL = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
    
    def __init__(self, db_path: str = "data/instruments.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path) if os.path.dirname(self.db_path) else ".", exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self):
        """Initializes tables and indexes for high-speed option chain querying."""
        with self.conn:
            self.conn.execute("""
                CREATE TABLE IF NOT EXISTS instruments (
                    token TEXT PRIMARY KEY,
                    symbol TEXT,
                    name TEXT,
                    expiry TEXT,
                    strike REAL,
                    lotsize INTEGER,
                    instrumenttype TEXT,
                    exch_seg TEXT,
                    tick_size REAL,
                    updated_at TEXT
                )
            """)
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_lookup ON instruments(name, exch_seg, instrumenttype)")
            self.conn.execute("CREATE INDEX IF NOT EXISTS idx_inst_strike ON instruments(name, strike, expiry)")
            self.conn.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")

    def is_cache_valid_for_today(self) -> bool:
        """Checks if today's master scrip file has already been indexed."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM meta WHERE key = 'last_download_date'")
        row = cursor.fetchone()
        if row and row["value"] == today_str:
            cursor.execute("SELECT COUNT(*) as count FROM instruments")
            cnt = cursor.fetchone()["count"]
            if cnt > 100:
                logger.info(f"[INSTRUMENTS] Local cache is valid for today ({today_str}) with {cnt} instruments indexed.")
                return True
        return False

    def load_instruments(self, force_refresh: bool = False):
        """Loads scrip master, either from local cache or streaming CDN download."""
        if not force_refresh and self.is_cache_valid_for_today():
            return

        logger.info(f"[INSTRUMENTS] Initiating scrip master download from {self.SCRIP_MASTER_URL}...")
        success = self._download_and_index()
        if not success:
            logger.warning("[INSTRUMENTS] Live scrip master download failed. Checking if database has fallback/synthetic records...")
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM instruments")
            if cursor.fetchone()["cnt"] == 0:
                logger.warning("[INSTRUMENTS] Populating synthetic option master for NIFTY, BANKNIFTY, SENSEX...")
                self._seed_synthetic_contracts()

    def _download_and_index(self, max_retries: int = 3) -> bool:
        """Stream downloads the JSON master file with retry backoff."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)"
        }
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"[INSTRUMENTS] Downloading master file (Attempt {attempt}/{max_retries})...")
                response = requests.get(self.SCRIP_MASTER_URL, headers=headers, timeout=30, stream=True)
                if response.status_code != 200:
                    logger.warning(f"[INSTRUMENTS] HTTP status {response.status_code}. Retrying in {attempt * 2}s...")
                    time.sleep(attempt * 2)
                    continue

                raw_data = response.json()
                if not isinstance(raw_data, list) or len(raw_data) == 0:
                    logger.warning("[INSTRUMENTS] Received empty or invalid master payload.")
                    continue

                logger.info(f"[INSTRUMENTS] Download complete ({len(raw_data)} total instruments). Filtering and indexing index derivatives...")
                self._index_records(raw_data)
                return True

            except Exception as e:
                logger.error(f"[INSTRUMENTS] Download attempt {attempt} failed: {e}")
                time.sleep(attempt * 2)

        return False

    def _index_records(self, records: List[Dict[str, Any]]):
        """Filters and inserts index spot and derivative records into SQLite."""
        target_names = {"NIFTY", "BANKNIFTY", "SENSEX", "MIDCPNIFTY"}
        target_segments = {"NSE", "BSE", "NFO", "BFO"}
        today_str = datetime.now().strftime("%Y-%m-%d")

        filtered = []
        for r in records:
            name = (r.get("name") or "").upper()
            seg = (r.get("exch_seg") or "").upper()
            inst_type = (r.get("instrumenttype") or "").upper()
            
            # Keep target indices or options/futures on target indices
            if name in target_names and seg in target_segments:
                try:
                    strike = float(r.get("strike", 0.0) or 0.0)
                    # Strike in Angel One file is often multiplied by 100 for NFO
                    if strike > 500000:
                        strike = strike / 100.0
                    
                    lotsize = int(r.get("lotsize", 1) or 1)
                    tick_size = float(r.get("tick_size", 0.05) or 0.05)
                    
                    filtered.append((
                        str(r.get("token")),
                        str(r.get("symbol")),
                        name,
                        str(r.get("expiry", "")),
                        strike,
                        lotsize,
                        inst_type,
                        seg,
                        tick_size,
                        today_str
                    ))
                except Exception:
                    continue

        logger.info(f"[INSTRUMENTS] Indexing {len(filtered)} filtered index derivatives into SQLite...")
        with self.conn:
            self.conn.execute("DELETE FROM instruments")
            self.conn.executemany("""
                INSERT OR REPLACE INTO instruments 
                (token, symbol, name, expiry, strike, lotsize, instrumenttype, exch_seg, tick_size, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, filtered)
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_download_date', ?)", (today_str,))
        
        logger.info(f"[INSTRUMENTS] Successfully indexed {len(filtered)} contracts.")

    def _seed_synthetic_contracts(self):
        """
        Seeds deterministic synthetic contracts for NIFTY, BANKNIFTY, and SENSEX
        if broker CDN is unavailable, ensuring 100% testability and zero crashes.
        """
        today = datetime.now()
        # SEBI standardized: Nifty weekly on Tuesday (weekday 1), Sensex weekly on Thursday (weekday 3)
        nifty_days = (1 - today.weekday()) % 7
        sensex_days = (3 - today.weekday()) % 7
        nifty_expiry = (today + timedelta(days=nifty_days)).strftime("%d%b%Y").upper()
        sensex_expiry = (today + timedelta(days=sensex_days)).strftime("%d%b%Y").upper()
        # Monthly Bank Nifty expiry on last Tuesday
        banknifty_monthly = (today + timedelta(days=(1 - today.weekday() + 28) % 7 + 21)).strftime("%d%b%Y").upper()
        today_str = today.strftime("%Y-%m-%d")

        synthetic = []
        # 1. Nifty contracts (Weekly Tuesday)
        for strike in range(22000, 26000, 50):
            # CE
            sym_ce = f"NIFTY{nifty_expiry}{strike}CE"
            tok_ce = f"NFO_NIF_{strike}_CE"
            synthetic.append((tok_ce, sym_ce, "NIFTY", nifty_expiry, float(strike), 65, "OPTIDX", "NFO", 0.05, today_str))
            # PE
            sym_pe = f"NIFTY{nifty_expiry}{strike}PE"
            tok_pe = f"NFO_NIF_{strike}_PE"
            synthetic.append((tok_pe, sym_pe, "NIFTY", nifty_expiry, float(strike), 65, "OPTIDX", "NFO", 0.05, today_str))

        # 2. Bank Nifty contracts (Monthly Tuesday only under SEBI rules)
        for strike in range(48000, 55000, 100):
            sym_ce = f"BANKNIFTY{banknifty_monthly}{strike}CE"
            tok_ce = f"NFO_BNF_{strike}_CE"
            synthetic.append((tok_ce, sym_ce, "BANKNIFTY", banknifty_monthly, float(strike), 30, "OPTIDX", "NFO", 0.05, today_str))
            sym_pe = f"BANKNIFTY{banknifty_monthly}{strike}PE"
            tok_pe = f"NFO_BNF_{strike}_PE"
            synthetic.append((tok_pe, sym_pe, "BANKNIFTY", banknifty_monthly, float(strike), 30, "OPTIDX", "NFO", 0.05, today_str))

        # 3. Sensex contracts (Weekly Thursday)
        for strike in range(75000, 85000, 100):
            sym_ce = f"SENSEX{sensex_expiry}{strike}CE"
            tok_ce = f"BFO_SEN_{strike}_CE"
            synthetic.append((tok_ce, sym_ce, "SENSEX", sensex_expiry, float(strike), 20, "OPTIDX", "BFO", 0.05, today_str))
            sym_pe = f"SENSEX{sensex_expiry}{strike}PE"
            tok_pe = f"BFO_SEN_{strike}_PE"
            synthetic.append((tok_pe, sym_pe, "SENSEX", sensex_expiry, float(strike), 20, "OPTIDX", "BFO", 0.05, today_str))

        with self.conn:
            self.conn.executemany("""
                INSERT OR REPLACE INTO instruments 
                (token, symbol, name, expiry, strike, lotsize, instrumenttype, exch_seg, tick_size, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, synthetic)
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_download_date', ?)", (today_str,))
        
        logger.info(f"[INSTRUMENTS] Seeded {len(synthetic)} synthetic contracts.")

    def get_atm_option(self, underlying: str, spot_price: float, option_type: str, expiry_index: int = 0) -> Optional[Dict[str, Any]]:
        """
        Fast lookup: returns exact contract parameters for ATM / immediate ITM option.
        Sub-millisecond retrieval via SQLite indexes.
        """
        underlying = underlying.upper()
        option_type = option_type.upper() # "CE" or "PE"
        exch_seg = "BFO" if underlying == "SENSEX" else "NFO"

        cursor = self.conn.cursor()
        
        # 1. Get distinct upcoming expiries
        cursor.execute("""
            SELECT DISTINCT expiry FROM instruments 
            WHERE name = ? AND exch_seg = ? AND instrumenttype = 'OPTIDX' AND expiry != ''
        """, (underlying, exch_seg))
        
        raw_expiries = [row["expiry"] for row in cursor.fetchall()]
        if not raw_expiries:
            # Try without exch_seg restriction
            cursor.execute("""
                SELECT DISTINCT expiry FROM instruments 
                WHERE name = ? AND expiry != ''
            """, (underlying,))
            raw_expiries = [row["expiry"] for row in cursor.fetchall()]

        if not raw_expiries:
            logger.error(f"[INSTRUMENTS] No active expiries found for {underlying}")
            return None

        # Parse expiry dates and sort chronologically, ignoring past dates
        today_date = datetime.now().date()
        valid_expiries = []
        for exp in raw_expiries:
            try:
                exp_dt = datetime.strptime(exp.strip(), "%d%b%Y").date()
                if exp_dt >= today_date:
                    valid_expiries.append((exp_dt, exp.strip()))
            except Exception:
                continue

        if not valid_expiries:
            # Fallback in case date formatting fails or testing with older dates
            valid_expiries = [(datetime.min.date(), exp.strip()) for exp in raw_expiries]

        valid_expiries.sort(key=lambda x: x[0])
        expiries = [exp_str for _, exp_str in valid_expiries]

        target_expiry = expiries[min(expiry_index, len(expiries) - 1)]

        # 2. Find option strikes for this expiry
        # Match symbol suffix 'CE' or 'PE'
        cursor.execute("""
            SELECT * FROM instruments 
            WHERE name = ? AND expiry = ? AND symbol LIKE ?
            ORDER BY ABS(strike - ?) ASC
            LIMIT 5
        """, (underlying, target_expiry, f"%{option_type}", spot_price))

        rows = cursor.fetchall()
        if not rows:
            # Fallback query
            cursor.execute("""
                SELECT * FROM instruments 
                WHERE name = ? AND symbol LIKE ?
                ORDER BY ABS(strike - ?) ASC
                LIMIT 1
            """, (underlying, f"%{option_type}", spot_price))
            rows = cursor.fetchall()

        if rows:
            best = rows[0]
            return {
                "symboltoken": str(best["token"]),
                "tradingsymbol": str(best["symbol"]),
                "name": str(best["name"]),
                "strike": float(best["strike"]),
                "expiry": str(best["expiry"]),
                "lotsize": int(best["lotsize"]),
                "exchange": str(best["exch_seg"]),
                "tick_size": float(best["tick_size"]),
            }
        
        logger.warning(f"[INSTRUMENTS] Could not resolve ATM option for {underlying} @ {spot_price}")
        return None
