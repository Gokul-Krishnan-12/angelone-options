import os
import sqlite3
import json
import time
import yaml
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
    
    def __init__(self, db_path: str = "data/instruments.db", symbols_yaml_path: Optional[str] = None):
        self.db_path = db_path
        self.symbols_yaml_path = symbols_yaml_path or "smartapi_trader/config/symbols.yaml"
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
        """Checks if today's master scrip file has already been indexed with index and stock options."""
        today_str = datetime.now().strftime("%Y-%m-%d")
        cursor = self.conn.cursor()
        cursor.execute("SELECT value FROM meta WHERE key = 'last_download_date'")
        row = cursor.fetchone()
        if row and row["value"] == today_str:
            cursor.execute("SELECT COUNT(*) as count FROM instruments")
            cnt = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) as count FROM instruments WHERE instrumenttype = 'OPTSTK'")
            optstk_cnt = cursor.fetchone()["count"]
            if cnt > 100 and optstk_cnt > 100:
                logger.info(f"[INSTRUMENTS] Local cache is valid for today ({today_str}) with {cnt} instruments indexed (including {optstk_cnt} real stock options).")
                return True
        return False

    def load_instruments(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Loads scrip master, either from local cache or streaming CDN download, and syncs regulatory lot sizes."""
        regulatory_changes = {}
        if not force_refresh and self.is_cache_valid_for_today():
            regulatory_changes = self.sync_regulatory_lot_sizes()
            return regulatory_changes

        logger.info(f"[INSTRUMENTS] Initiating scrip master download from {self.SCRIP_MASTER_URL}...")
        success = self._download_and_index()
        if not success:
            logger.warning("[INSTRUMENTS] Live scrip master download failed. Checking if database has fallback/synthetic records...")
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) as cnt FROM instruments")
            if cursor.fetchone()["cnt"] == 0:
                logger.warning("[INSTRUMENTS] Populating synthetic option master for NIFTY, BANKNIFTY, SENSEX...")
                self._seed_synthetic_contracts()

        regulatory_changes = self.sync_regulatory_lot_sizes()
        return regulatory_changes

    def sync_regulatory_lot_sizes(self) -> Dict[str, Any]:
        """
        Synchronizes index lot sizes from exchange instruments to symbols.yaml.
        When SEBI revises index lot sizes (e.g. NIFTY, BANKNIFTY, SENSEX), this detects
        the active nearest contract lot size and updates symbols.yaml on disk.
        Returns a dict of changes detected: {index_symbol: {"old": old_lot, "new": new_lot, "expiry": exp}}
        """
        changes: Dict[str, Any] = {}
        if not os.path.exists(self.symbols_yaml_path):
            logger.warning(f"[REGULATORY] symbols.yaml not found at {self.symbols_yaml_path}")
            return changes

        try:
            with open(self.symbols_yaml_path, "r", encoding="utf-8") as f:
                content = f.read()

            symbols_data = yaml.safe_load(content) or {}
            indices_cfg = symbols_data.get("indices", {})
            today_date = datetime.now().date()
            cursor = self.conn.cursor()

            for key, idx_info in indices_cfg.items():
                name = idx_info.get("token_prefix") or key
                exch_seg = idx_info.get("deriv_exchange", "NFO")
                configured_lot = idx_info.get("lot_size")

                cursor.execute("""
                    SELECT DISTINCT expiry FROM instruments
                    WHERE name = ? AND exch_seg = ? AND instrumenttype = 'OPTIDX' AND expiry != ''
                """, (name, exch_seg))
                rows = cursor.fetchall()
                if not rows:
                    continue

                valid_expiries = []
                for r in rows:
                    exp_str = r["expiry"].strip()
                    try:
                        exp_dt = datetime.strptime(exp_str, "%d%b%Y").date()
                        if exp_dt >= today_date:
                            valid_expiries.append((exp_dt, exp_str))
                    except Exception:
                        continue

                if not valid_expiries:
                    continue

                valid_expiries.sort(key=lambda x: x[0])
                nearest_expiry = valid_expiries[0][1]

                cursor.execute("""
                    SELECT lotsize FROM instruments
                    WHERE name = ? AND exch_seg = ? AND expiry = ? AND instrumenttype = 'OPTIDX' AND lotsize > 0
                    LIMIT 1
                """, (name, exch_seg, nearest_expiry))
                lot_row = cursor.fetchone()
                if lot_row:
                    exchange_lot = int(lot_row["lotsize"])
                    if configured_lot != exchange_lot:
                        logger.warning(
                            f"[REGULATORY] SEBI Index Lot Size Revision detected for {key}: "
                            f"{configured_lot} -> {exchange_lot} (expiry {nearest_expiry})"
                        )
                        changes[key] = {
                            "old": configured_lot,
                            "new": exchange_lot,
                            "expiry": nearest_expiry
                        }

            if changes:
                # Update symbols.yaml line-by-line to preserve comments and structure
                lines = content.splitlines(keepends=True)
                new_lines = []
                current_section: Optional[str] = None
                for line in lines:
                    stripped = line.strip()
                    for idx_name in indices_cfg.keys():
                        if stripped.startswith(f"{idx_name}:"):
                            current_section = idx_name
                            break
                    else:
                        if current_section and stripped and not line.startswith(" ") and not line.startswith("\t"):
                            current_section = None

                    if current_section in changes and stripped.startswith("lot_size:"):
                        indent = line[:line.find("lot_size:")]
                        new_lot = changes[current_section]["new"]
                        new_lines.append(f"{indent}lot_size: {new_lot}\n")
                    else:
                        new_lines.append(line)

                with open(self.symbols_yaml_path, "w", encoding="utf-8") as f:
                    f.writelines(new_lines)
                logger.info(f"[REGULATORY] Updated {self.symbols_yaml_path} with new regulatory lot sizes: {changes}")

        except Exception as e:
            logger.error(f"[REGULATORY] Failed to sync regulatory lot sizes: {e}")

        return changes

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

                logger.info(f"[INSTRUMENTS] Download complete ({len(raw_data)} total instruments). Filtering and indexing index and stock derivatives...")
                self._index_records(raw_data)
                return True

            except Exception as e:
                logger.error(f"[INSTRUMENTS] Download attempt {attempt} failed: {e}")
                time.sleep(attempt * 2)

        return False

    def _index_records(self, records: List[Dict[str, Any]]):
        """Filters and inserts index spot, index derivatives, stock derivatives, and stock cash spot tokens into SQLite."""
        target_indices = {"NIFTY", "BANKNIFTY", "SENSEX", "MIDCPNIFTY"}
        target_segments = {"NSE", "BSE", "NFO", "BFO"}
        today_str = datetime.now().strftime("%Y-%m-%d")

        # Discover all F&O stock underlyings present in the exchange file
        fo_stock_names = {
            (r.get("name") or "").upper()
            for r in records
            if (r.get("exch_seg") or "").upper() == "NFO" and (r.get("instrumenttype") or "").upper() in ("OPTSTK", "FUTSTK")
        }

        filtered = []
        for r in records:
            name = (r.get("name") or "").upper()
            seg = (r.get("exch_seg") or "").upper()
            inst_type = (r.get("instrumenttype") or "").upper()
            sym = str(r.get("symbol") or "")
            
            is_index = name in target_indices and seg in target_segments
            is_stock_fo = seg == "NFO" and inst_type in ("OPTSTK", "FUTSTK")
            is_stock_cash = seg == "NSE" and sym.endswith("-EQ") and name in fo_stock_names

            if is_index or is_stock_fo or is_stock_cash:
                try:
                    strike = float(r.get("strike", 0.0) or 0.0)
                    # Strike in Angel One file is multiplied by 100 for NFO/BFO derivatives
                    if seg in ("NFO", "BFO") and strike > 0:
                        strike = strike / 100.0
                    
                    lotsize = int(r.get("lotsize", 1) or 1)
                    tick_size = float(r.get("tick_size", 0.05) or 0.05)
                    
                    filtered.append((
                        str(r.get("token")),
                        sym,
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

        logger.info(f"[INSTRUMENTS] Indexing {len(filtered)} filtered index, stock derivatives, and cash spot records into SQLite...")
        with self.conn:
            self.conn.execute("DELETE FROM instruments")
            self.conn.executemany("""
                INSERT OR REPLACE INTO instruments 
                (token, symbol, name, expiry, strike, lotsize, instrumenttype, exch_seg, tick_size, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, filtered)
            self.conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('last_download_date', ?)", (today_str,))
        logger.info(f"[INSTRUMENTS] Successfully indexed {len(filtered)} records (Indices & {len(fo_stock_names)} F&O stocks).")

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

    def get_otm_option(
        self,
        underlying: str,
        spot_price: float,
        option_type: str,
        strikes_otm: int = 1,
        expiry_index: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Resolves the Out-Of-The-Money (OTM) hedge option strike for Debit Spreads.
        - For CE (Bull Call): Higher strike than ATM (strike > atm_strike)
        - For PE (Bear Put): Lower strike than ATM (strike < atm_strike)
        """
        atm = self.get_atm_option(underlying, spot_price, option_type, expiry_index)
        if not atm:
            return None

        atm_strike = float(atm["strike"])
        target_expiry = str(atm["expiry"])
        cursor = self.conn.cursor()

        if option_type == "CE":
            cursor.execute("""
                SELECT * FROM instruments
                WHERE name = ? AND expiry = ? AND symbol LIKE '%CE' AND strike > ?
                ORDER BY strike ASC
                LIMIT ?
            """, (underlying, target_expiry, atm_strike, max(1, strikes_otm)))
        else:
            cursor.execute("""
                SELECT * FROM instruments
                WHERE name = ? AND expiry = ? AND symbol LIKE '%PE' AND strike < ?
                ORDER BY strike DESC
                LIMIT ?
            """, (underlying, target_expiry, atm_strike, max(1, strikes_otm)))

        rows = cursor.fetchall()
        if rows:
            best_otm = rows[-1]  # Take the Nth strike OTM
            return {
                "symboltoken": str(best_otm["token"]),
                "tradingsymbol": str(best_otm["symbol"]),
                "name": str(best_otm["name"]),
                "strike": float(best_otm["strike"]),
                "expiry": str(best_otm["expiry"]),
                "lotsize": int(best_otm["lotsize"]),
                "exchange": str(best_otm["exch_seg"]),
                "tick_size": float(best_otm["tick_size"]),
            }

        logger.warning(f"[INSTRUMENTS] Could not resolve {strikes_otm}-strike OTM {option_type} option for {underlying} @ {spot_price}")
        return None
