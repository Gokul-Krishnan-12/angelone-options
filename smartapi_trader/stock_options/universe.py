"""
NSE Stock Options Universe & Contract Discovery.
Maintains the eligible NSE F&O stock universe, sector categorization,
lot sizes, strike intervals, and contract resolvers for stock options.
"""

import os
import sqlite3
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from smartapi_trader.utils.logger import logger

# Top liquid NSE F&O underlying stocks
NSE_FO_STOCKS: Dict[str, Dict[str, Any]] = {
    "RELIANCE": {
        "name": "Reliance Industries Ltd",
        "sector": "Energy / Conglomerate",
        "lot_size": 250,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 1280.0,
        "token_nse": "2885"
    },
    "TCS": {
        "name": "Tata Consultancy Services Ltd",
        "sector": "Information Technology",
        "lot_size": 175,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 4120.0,
        "token_nse": "11536"
    },
    "INFY": {
        "name": "Infosys Ltd",
        "sector": "Information Technology",
        "lot_size": 400,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1880.0,
        "token_nse": "1594"
    },
    "HDFCBANK": {
        "name": "HDFC Bank Ltd",
        "sector": "Banking & Financials",
        "lot_size": 550,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1740.0,
        "token_nse": "1333"
    },
    "ICICIBANK": {
        "name": "ICICI Bank Ltd",
        "sector": "Banking & Financials",
        "lot_size": 700,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1260.0,
        "token_nse": "4963"
    },
    "SBIN": {
        "name": "State Bank of India",
        "sector": "Banking (PSU)",
        "lot_size": 750,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 970.0,
        "token_nse": "3045"
    },
    "BHARTIARTL": {
        "name": "Bharti Airtel Ltd",
        "sector": "Telecom",
        "lot_size": 475,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1690.0,
        "token_nse": "10604"
    },
    "TATAMOTORS": {
        "name": "Tata Motors Ltd",
        "sector": "Automobile",
        "lot_size": 550,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 930.0,
        "token_nse": "3456"
    },
    "LT": {
        "name": "Larsen & Toubro Ltd",
        "sector": "Infrastructure & Capital Goods",
        "lot_size": 150,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 3650.0,
        "token_nse": "11483"
    },
    "AXISBANK": {
        "name": "Axis Bank Ltd",
        "sector": "Banking & Financials",
        "lot_size": 625,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1180.0,
        "token_nse": "5900"
    },
    "KOTAKBANK": {
        "name": "Kotak Mahindra Bank Ltd",
        "sector": "Banking & Financials",
        "lot_size": 400,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1780.0,
        "token_nse": "1922"
    },
    "BAJFINANCE": {
        "name": "Bajaj Finance Ltd",
        "sector": "NBFC / Financial Services",
        "lot_size": 125,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 7150.0,
        "token_nse": "317"
    },
    "MARUTI": {
        "name": "Maruti Suzuki India Ltd",
        "sector": "Automobile",
        "lot_size": 50,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 12400.0,
        "token_nse": "10999"
    },
    "SUNPHARMA": {
        "name": "Sun Pharmaceutical Industries Ltd",
        "sector": "Pharma & Healthcare",
        "lot_size": 350,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1820.0,
        "token_nse": "3351"
    },
    "TITAN": {
        "name": "Titan Company Ltd",
        "sector": "Consumer Discretionary",
        "lot_size": 175,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 3480.0,
        "token_nse": "3506"
    },
    "ITC": {
        "name": "ITC Ltd",
        "sector": "FMCG",
        "lot_size": 1600,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 485.0,
        "token_nse": "1660"
    },
    "TATASTEEL": {
        "name": "Tata Steel Ltd",
        "sector": "Metals & Mining",
        "lot_size": 5500,
        "strike_step": 2.5,
        "tick_size": 0.05,
        "base_price": 150.0,
        "token_nse": "3499"
    },
    "WIPRO": {
        "name": "Wipro Ltd",
        "sector": "Information Technology",
        "lot_size": 1500,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 540.0,
        "token_nse": "3787"
    },
    "HINDUNILVR": {
        "name": "Hindustan Unilever Ltd",
        "sector": "FMCG",
        "lot_size": 300,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 2520.0,
        "token_nse": "1330"
    },
    "COALINDIA": {
        "name": "Coal India Ltd",
        "sector": "Mining & Energy",
        "lot_size": 2100,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 460.0,
        "token_nse": "20374"
    },
    "JSWSTEEL": {
        "name": "JSW Steel Ltd",
        "sector": "Metals & Mining",
        "lot_size": 675,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 980.0,
        "token_nse": "11723"
    },
    "ADANIENT": {
        "name": "Adani Enterprises Ltd",
        "sector": "Conglomerate & Metals",
        "lot_size": 300,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 2950.0,
        "token_nse": "25"
    },
    "ADANIPORTS": {
        "name": "Adani Ports and SEZ Ltd",
        "sector": "Infrastructure & Logistics",
        "lot_size": 400,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1380.0,
        "token_nse": "15083"
    },
    "M&M": {
        "name": "Mahindra & Mahindra Ltd",
        "sector": "Automobile",
        "lot_size": 350,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 2820.0,
        "token_nse": "2031"
    },
    "HCLTECH": {
        "name": "HCL Technologies Ltd",
        "sector": "Information Technology",
        "lot_size": 350,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1820.0,
        "token_nse": "7229"
    },
    "GRASIM": {
        "name": "Grasim Industries Ltd",
        "sector": "Diversified & Chemicals",
        "lot_size": 250,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 2650.0,
        "token_nse": "1232"
    },
    "HEROMOTOCO": {
        "name": "Hero MotoCorp Ltd",
        "sector": "Automobile",
        "lot_size": 150,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 5100.0,
        "token_nse": "1348"
    },
    "CIPLA": {
        "name": "Cipla Ltd",
        "sector": "Pharma & Healthcare",
        "lot_size": 650,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1540.0,
        "token_nse": "694"
    },
    "DRREDDY": {
        "name": "Dr. Reddy's Laboratories Ltd",
        "sector": "Pharma & Healthcare",
        "lot_size": 125,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 6650.0,
        "token_nse": "881"
    },
    "EICHERMOT": {
        "name": "Eicher Motors Ltd",
        "sector": "Automobile",
        "lot_size": 175,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 4900.0,
        "token_nse": "910"
    },
    "TECHM": {
        "name": "Tech Mahindra Ltd",
        "sector": "Information Technology",
        "lot_size": 600,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1650.0,
        "token_nse": "13538"
    },
    "DIVISLAB": {
        "name": "Divi's Laboratories Ltd",
        "sector": "Pharma & Healthcare",
        "lot_size": 200,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 5900.0,
        "token_nse": "10940"
    },
    "BPCL": {
        "name": "Bharat Petroleum Corp Ltd",
        "sector": "Oil & Gas / Energy",
        "lot_size": 1800,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 315.0,
        "token_nse": "526"
    },
    "HDFCLIFE": {
        "name": "HDFC Life Insurance Co Ltd",
        "sector": "Insurance & Financials",
        "lot_size": 1100,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 725.0,
        "token_nse": "467"
    },
    "SBILIFE": {
        "name": "SBI Life Insurance Co Ltd",
        "sector": "Insurance & Financials",
        "lot_size": 750,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1680.0,
        "token_nse": "21808"
    },
    "APOLLOHOSP": {
        "name": "Apollo Hospitals Enterprise Ltd",
        "sector": "Healthcare Services",
        "lot_size": 125,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 7150.0,
        "token_nse": "157"
    },
    "SHRIRAMFIN": {
        "name": "Shriram Finance Ltd",
        "sector": "NBFC / Financial Services",
        "lot_size": 150,
        "strike_step": 25.0,
        "tick_size": 0.05,
        "base_price": 3280.0,
        "token_nse": "4306"
    },
    "BEL": {
        "name": "Bharat Electronics Ltd",
        "sector": "Defense & Capital Goods",
        "lot_size": 2850,
        "strike_step": 2.5,
        "tick_size": 0.05,
        "base_price": 295.0,
        "token_nse": "383"
    },
    "HAL": {
        "name": "Hindustan Aeronautics Ltd",
        "sector": "Defense & Aerospace",
        "lot_size": 150,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 4450.0,
        "token_nse": "2303"
    },
    "TRENT": {
        "name": "Trent Ltd",
        "sector": "Retail / Consumer",
        "lot_size": 100,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 7450.0,
        "token_nse": "1964"
    },
    "NTPC": {
        "name": "NTPC Ltd",
        "sector": "Power & Energy",
        "lot_size": 1500,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 410.0,
        "token_nse": "11630"
    },
    "POWERGRID": {
        "name": "Power Grid Corporation of India",
        "sector": "Power & Energy",
        "lot_size": 1800,
        "strike_step": 2.5,
        "tick_size": 0.05,
        "base_price": 325.0,
        "token_nse": "14977"
    },
    "ONGC": {
        "name": "Oil & Natural Gas Corp Ltd",
        "sector": "Oil & Gas / Energy",
        "lot_size": 2250,
        "strike_step": 2.5,
        "tick_size": 0.05,
        "base_price": 272.0,
        "token_nse": "2475"
    },
    "TATACONSUM": {
        "name": "Tata Consumer Products Ltd",
        "sector": "FMCG",
        "lot_size": 900,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1090.0,
        "token_nse": "3432"
    },
    "ULTRACEMCO": {
        "name": "UltraTech Cement Ltd",
        "sector": "Cement & Building Materials",
        "lot_size": 100,
        "strike_step": 100.0,
        "tick_size": 0.05,
        "base_price": 11200.0,
        "token_nse": "11532"
    },
    "NESTLEIND": {
        "name": "Nestle India Ltd",
        "sector": "FMCG",
        "lot_size": 200,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 2280.0,
        "token_nse": "17963"
    },
    "ASIANPAINT": {
        "name": "Asian Paints Ltd",
        "sector": "Consumer / Paints",
        "lot_size": 200,
        "strike_step": 20.0,
        "tick_size": 0.05,
        "base_price": 2980.0,
        "token_nse": "236"
    },
    "INDUSINDBK": {
        "name": "IndusInd Bank Ltd",
        "sector": "Banking & Financials",
        "lot_size": 500,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 1150.0,
        "token_nse": "5258"
    },
    "HINDALCO": {
        "name": "Hindalco Industries Ltd",
        "sector": "Metals & Mining",
        "lot_size": 1400,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 710.0,
        "token_nse": "1363"
    },
    "BAJAJ-AUTO": {
        "name": "Bajaj Auto Ltd",
        "sector": "Automobile",
        "lot_size": 75,
        "strike_step": 100.0,
        "tick_size": 0.05,
        "base_price": 10100.0,
        "token_nse": "16669"
    },
    "POLYCAB": {
        "name": "Polycab India Ltd",
        "sector": "Cables & Capital Goods",
        "lot_size": 125,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 6600.0,
        "token_nse": "9590"
    },
    "PERSISTENT": {
        "name": "Persistent Systems Ltd",
        "sector": "Information Technology",
        "lot_size": 100,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 5400.0,
        "token_nse": "18365"
    },
    "COFORGE": {
        "name": "Coforge Ltd",
        "sector": "Information Technology",
        "lot_size": 150,
        "strike_step": 50.0,
        "tick_size": 0.05,
        "base_price": 7800.0,
        "token_nse": "11543"
    },
    "DIXON": {
        "name": "Dixon Technologies Ltd",
        "sector": "Consumer Electronics / EMS",
        "lot_size": 100,
        "strike_step": 100.0,
        "tick_size": 0.05,
        "base_price": 13500.0,
        "token_nse": "21690"
    },
    "CANBK": {
        "name": "Canara Bank",
        "sector": "Banking (PSU)",
        "lot_size": 6750,
        "strike_step": 1.0,
        "tick_size": 0.05,
        "base_price": 108.0,
        "token_nse": "583"
    },
    "PFC": {
        "name": "Power Finance Corporation",
        "sector": "NBFC / Financial Services",
        "lot_size": 1300,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 450.0,
        "token_nse": "14299"
    },
    "RECLTD": {
        "name": "REC Ltd",
        "sector": "NBFC / Financial Services",
        "lot_size": 1400,
        "strike_step": 5.0,
        "tick_size": 0.05,
        "base_price": 530.0,
        "token_nse": "15355"
    },
    "BHEL": {
        "name": "Bharat Heavy Electricals Ltd",
        "sector": "Power & Capital Goods",
        "lot_size": 2625,
        "strike_step": 2.5,
        "tick_size": 0.05,
        "base_price": 235.0,
        "token_nse": "438"
    },
    "DLF": {
        "name": "DLF Ltd",
        "sector": "Real Estate",
        "lot_size": 825,
        "strike_step": 10.0,
        "tick_size": 0.05,
        "base_price": 840.0,
        "token_nse": "14732"
    },
    "FEDERALBNK": {
        "name": "The Federal Bank Ltd",
        "sector": "Banking & Financials",
        "lot_size": 5000,
        "strike_step": 1.0,
        "tick_size": 0.05,
        "base_price": 195.0,
        "token_nse": "1023"
    }
}

HIGH_BETA_SYMBOLS = {
    "COFORGE", "PERSISTENT", "DIXON", "POLYCAB", "INDUSINDBK",
    "BHEL", "DLF", "ADANIENT", "ADANIPORTS", "TRENT", "HAL",
    "BEL", "CANBK", "FEDERALBNK", "PFC", "RECLTD", "TATASTEEL",
    "HINDALCO", "TATAMOTORS", "SBIN"
}

def is_high_beta_stock(symbol: str) -> bool:
    """Returns True if the symbol is categorized as a High-Beta / High-ATR momentum F&O stock."""
    return str(symbol).upper().strip() in HIGH_BETA_SYMBOLS


class StockUniverseManager:
    """
    Manages NSE F&O stock candidate discovery, option chain lookups,
    and contract strike/expiry resolution.
    """

    def __init__(self, db_path: str = "data/instruments.db"):
        self.db_path = db_path
        self._ensure_stock_options_indexed()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_stock_options_indexed(self):
        """Ensures the instruments database contains stock options contracts."""
        try:
            with self._get_connection() as conn:
                conn.execute("""
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
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) as count FROM instruments WHERE instrumenttype = 'OPTSTK'")
                count = cursor.fetchone()["count"]
                if count == 0:
                    logger.info("[STOCK_UNIVERSE] Seeding initial NSE stock options contracts...")
                    self._seed_stock_contracts(conn)
        except Exception as e:
            logger.error(f"[STOCK_UNIVERSE] Error checking stock options contracts: {e}")


    def _seed_stock_contracts(self, conn: sqlite3.Connection):
        """Seeds realistic stock option contracts for the curated NSE F&O universe."""
        now = datetime.now()
        # Monthly stock option expiry: Last Thursday of the current and next month
        def get_last_thursday(year: int, month: int) -> datetime:
            import calendar
            last_day = calendar.monthrange(year, month)[1]
            dt = datetime(year, month, last_day)
            offset = (dt.weekday() - 3) % 7
            return dt - timedelta(days=offset)

        cur_exp_dt = get_last_thursday(now.year, now.month)
        if cur_exp_dt < now:
            # Current month expired, move to next month
            next_m = now.month + 1 if now.month < 12 else 1
            next_y = now.year if now.month < 12 else now.year + 1
            cur_exp_dt = get_last_thursday(next_y, next_m)

        next_m2 = cur_exp_dt.month + 1 if cur_exp_dt.month < 12 else 1
        next_y2 = cur_exp_dt.year if cur_exp_dt.month < 12 else cur_exp_dt.year + 1
        next_exp_dt = get_last_thursday(next_y2, next_m2)

        expiries = [
            cur_exp_dt.strftime("%d%b%Y").upper(),
            next_exp_dt.strftime("%d%b%Y").upper()
        ]
        today_str = now.strftime("%Y-%m-%d")

        records = []
        for symbol, info in NSE_FO_STOCKS.items():
            base_p = info["base_price"]
            step = info["strike_step"]
            lot = info["lot_size"]
            tick = info["tick_size"]
            token_base = int(info["token_nse"])

            for exp in expiries:
                # Generate strikes: -8 to +8 steps around base price
                for i in range(-8, 9):
                    strike = round(base_p + (i * step), 2)
                    strike_str = int(strike) if strike.is_integer() else f"{strike:.1f}"

                    # CE
                    sym_ce = f"{symbol}{exp}{strike_str}CE"
                    tok_ce = f"NFO_{symbol}_{strike_str}_CE_{exp}"
                    records.append((
                        tok_ce, sym_ce, symbol, exp, strike, lot, "OPTSTK", "NFO", tick, today_str
                    ))

                    # PE
                    sym_pe = f"{symbol}{exp}{strike_str}PE"
                    tok_pe = f"NFO_{symbol}_{strike_str}_PE_{exp}"
                    records.append((
                        tok_pe, sym_pe, symbol, exp, strike, lot, "OPTSTK", "NFO", tick, today_str
                    ))

        conn.executemany("""
            INSERT OR REPLACE INTO instruments
            (token, symbol, name, expiry, strike, lotsize, instrumenttype, exch_seg, tick_size, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, records)
        logger.info(f"[STOCK_UNIVERSE] Seeded {len(records)} stock option contracts across {len(NSE_FO_STOCKS)} stocks.")

    def get_eligible_stocks(self, selected_symbols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Returns metadata for all or shortlisted eligible NSE stocks."""
        stocks = []
        if selected_symbols and len(selected_symbols) == 1 and selected_symbols[0].upper() in ("ALL_FO", "ALL", "AUTO_DISCOVER"):
            target_keys = list(NSE_FO_STOCKS.keys())
        elif selected_symbols:
            target_keys = [s.upper().strip() for s in selected_symbols if s.strip()]
        else:
            target_keys = list(NSE_FO_STOCKS.keys())

        for sym in target_keys:
            if sym in NSE_FO_STOCKS:
                meta = dict(NSE_FO_STOCKS[sym])
                meta["symbol"] = sym
                stocks.append(meta)
            else:
                stocks.append({
                    "symbol": sym,
                    "name": f"{sym} Ltd",
                    "sector": "NSE F&O Equity",
                    "lot_size": 250,
                    "strike_step": 10.0,
                    "tick_size": 0.05,
                    "base_price": 1000.0,
                    "token_nse": ""
                })
        return stocks

    def resolve_stock_option_contract(
        self,
        symbol: str,
        spot_price: float,
        option_type: str,
        strike_offset: int = 0,
        expiry_index: int = 0
    ) -> Optional[Dict[str, Any]]:
        """
        Resolves an option contract for an NSE stock.
        strike_offset: 0 = ATM, +1 = 1 strike higher, -1 = 1 strike lower
        """
        symbol = symbol.upper()
        option_type = option_type.upper()
        stock_meta = NSE_FO_STOCKS.get(symbol)
        if not stock_meta:
            # Dynamically infer step and lot size from price
            step = 50.0 if spot_price > 4000 else (20.0 if spot_price > 2000 else (10.0 if spot_price > 800 else (5.0 if spot_price > 250 else 2.5)))
            stock_meta = {
                "name": f"{symbol} Ltd",
                "sector": "NSE F&O Equity",
                "lot_size": 250,
                "strike_step": step,
                "tick_size": 0.05,
                "base_price": spot_price,
                "token_nse": ""
            }

        step = stock_meta["strike_step"]
        atm_strike = round(round(spot_price / step) * step, 2)
        target_strike = round(atm_strike + (strike_offset * step), 2)

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                # 1. Fetch available expiries for this stock
                cursor.execute("""
                    SELECT DISTINCT expiry FROM instruments
                    WHERE name = ? AND instrumenttype = 'OPTSTK' AND expiry != ''
                """, (symbol,))
                raw_expiries = [r["expiry"] for r in cursor.fetchall()]

                if not raw_expiries:
                    # Fallback seed if missing
                    self._seed_stock_contracts(conn)
                    cursor.execute("""
                        SELECT DISTINCT expiry FROM instruments
                        WHERE name = ? AND instrumenttype = 'OPTSTK' AND expiry != ''
                    """, (symbol,))
                    raw_expiries = [r["expiry"] for r in cursor.fetchall()]

                # Parse and sort chronologically
                valid_expiries = []
                today_date = datetime.now().date()
                for exp in raw_expiries:
                    try:
                        exp_dt = datetime.strptime(exp.strip(), "%d%b%Y").date()
                        if exp_dt >= today_date:
                            valid_expiries.append((exp_dt, exp.strip()))
                    except Exception:
                        continue

                valid_expiries.sort(key=lambda x: x[0])
                if not valid_expiries:
                    valid_expiries = [(datetime.max.date(), exp) for exp in raw_expiries]

                if not valid_expiries:
                    return None

                target_expiry = valid_expiries[min(expiry_index, len(valid_expiries) - 1)][1]

                # 2. Query contract nearest to target_strike
                cursor.execute("""
                    SELECT * FROM instruments
                    WHERE name = ? AND expiry = ? AND symbol LIKE ?
                    ORDER BY ABS(strike - ?) ASC
                    LIMIT 1
                """, (symbol, target_expiry, f"%{option_type}", target_strike))
                row = cursor.fetchone()

                if row:
                    return {
                        "symboltoken": str(row["token"]),
                        "tradingsymbol": str(row["symbol"]),
                        "underlying": symbol,
                        "strike": float(row["strike"]),
                        "option_type": option_type,
                        "expiry": str(row["expiry"]),
                        "lotsize": int(row["lotsize"]),
                        "exchange": str(row["exch_seg"]),
                        "tick_size": float(row["tick_size"]),
                        "sector": stock_meta["sector"]
                    }

        except Exception as e:
            logger.error(f"[STOCK_UNIVERSE] Error resolving stock option for {symbol}: {e}")

        # Fallback synthetic contract representation if DB query failed
        now = datetime.now()
        exp_str = (now + timedelta(days=25)).strftime("%d%b%Y").upper()
        strike_str = int(target_strike) if target_strike.is_integer() else f"{target_strike:.1f}"
        return {
            "symboltoken": f"SYN_{symbol}_{strike_str}_{option_type}",
            "tradingsymbol": f"{symbol}{exp_str}{strike_str}{option_type}",
            "underlying": symbol,
            "strike": target_strike,
            "option_type": option_type,
            "expiry": exp_str,
            "lotsize": stock_meta["lot_size"],
            "exchange": "NFO",
            "tick_size": stock_meta["tick_size"],
            "sector": stock_meta["sector"]
        }

    def get_contract_by_symbol(self, tradingsymbol: str) -> Optional[Dict[str, Any]]:
        """Finds instrument metadata from local SQLite index by tradingsymbol."""
        if not tradingsymbol:
            return None
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM instruments WHERE symbol = ? LIMIT 1", (tradingsymbol.strip(),))
                row = cursor.fetchone()
                if row:
                    return dict(row)
        except Exception as e:
            logger.debug(f"[STOCK_UNIVERSE] Error looking up contract by symbol {tradingsymbol}: {e}")
        return None
