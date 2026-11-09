"""
Indian Standard Time (IST, UTC+05:30) and NSE Trading Calendar utilities.
Guarantees consistent market timing and scheduling regardless of host OS timezone.
Provides dynamic synchronization with official NSE holiday calendars and persistent local caching.
"""

import json
from datetime import datetime, timezone, timedelta, time
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from smartapi_trader.utils.logger import logger

# Indian Standard Time (IST) is UTC+05:30 with no daylight saving time
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

# Default official NSE / BSE equity and derivative market trading holidays (YYYY-MM-DD -> Description)
DEFAULT_NSE_HOLIDAYS_MAP: Dict[str, str] = {
    # 2025
    "2025-01-26": "Republic Day",
    "2025-02-26": "Mahashivratri",
    "2025-03-14": "Holi",
    "2025-03-31": "Id-Ul-Fitr (Ramadan Eid)",
    "2025-04-06": "Shri Ram Navami",
    "2025-04-10": "Shri Mahavir Jayanti",
    "2025-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2025-04-18": "Good Friday",
    "2025-05-01": "Maharashtra Day",
    "2025-06-07": "Bakri Id",
    "2025-07-06": "Muharram",
    "2025-08-15": "Independence Day / Parsi New Year",
    "2025-08-27": "Shri Ganesh Chaturthi",
    "2025-10-02": "Mahatma Gandhi Jayanti/Dussehra",
    "2025-10-21": "Diwali Laxmi Pujan",
    "2025-10-22": "Balipratipada",
    "2025-11-05": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2025-12-25": "Christmas",
    # 2026 (Official NSE Trading Calendar)
    "2026-01-15": "Municipal Corporation Election - Maharashtra",
    "2026-01-26": "Republic Day",
    "2026-02-15": "Mahashivratri",
    "2026-03-03": "Holi",
    "2026-03-21": "Id-Ul-Fitr (Ramadan Eid)",
    "2026-03-26": "Shri Ram Navami",
    "2026-03-31": "Shri Mahavir Jayanti",
    "2026-04-03": "Good Friday",
    "2026-04-14": "Dr. Baba Saheb Ambedkar Jayanti",
    "2026-05-01": "Maharashtra Day",
    "2026-05-28": "Bakri Id",
    "2026-06-26": "Muharram",
    "2026-08-15": "Independence Day",
    "2026-09-14": "Ganesh Chaturthi",
    "2026-10-02": "Mahatma Gandhi Jayanti",
    "2026-10-20": "Dussehra",
    "2026-11-08": "Diwali Laxmi Pujan*",
    "2026-11-10": "Diwali-Balipratipada",
    "2026-11-24": "Prakash Gurpurb Sri Guru Nanak Dev",
    "2026-12-25": "Christmas",
}

# In-memory mapping of date string (YYYY-MM-DD) to description
NSE_HOLIDAYS_MAP: Dict[str, str] = dict(DEFAULT_NSE_HOLIDAYS_MAP)

# In-memory set of recognized holiday dates for high-performance O(1) checks
NSE_HOLIDAYS = set(NSE_HOLIDAYS_MAP.keys())

# Persistent local cache location
HOLIDAYS_CACHE_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "nse_holidays.json"


def now_ist() -> datetime:
    """Returns the current datetime in Indian Standard Time (IST)."""
    return datetime.now(IST)


def ist_time() -> time:
    """Returns the current time of day in Indian Standard Time (IST)."""
    return datetime.now(IST).time()


def ist_date_str(fmt: str = "%Y-%m-%d") -> str:
    """Returns today's date formatted in Indian Standard Time (IST)."""
    return datetime.now(IST).strftime(fmt)


def _seed_fixed_national_holidays(year: int):
    """
    Seeds perpetual Indian statutory national market holidays for a given year.
    These dates are legally fixed and do not vary across future years (2027, 2028, 2029+).
    """
    fixed = {
        f"{year}-01-26": "Republic Day",
        f"{year}-05-01": "Maharashtra Day",
        f"{year}-08-15": "Independence Day",
        f"{year}-10-02": "Mahatma Gandhi Jayanti",
        f"{year}-12-25": "Christmas",
    }
    for d, desc in fixed.items():
        if d not in NSE_HOLIDAYS_MAP:
            NSE_HOLIDAYS_MAP[d] = desc
            NSE_HOLIDAYS.add(d)


def _load_cached_holidays():
    """Loads locally cached holidays from disk if available and seeds perpetual national holidays."""
    global NSE_HOLIDAYS_MAP, NSE_HOLIDAYS
    if HOLIDAYS_CACHE_FILE.exists():
        try:
            with open(HOLIDAYS_CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                cached = data.get("holidays", {})
                if isinstance(cached, dict) and cached:
                    for d, info in cached.items():
                        desc = info.get("description", "Exchange Holiday") if isinstance(info, dict) else str(info)
                        NSE_HOLIDAYS_MAP[d] = desc
                    NSE_HOLIDAYS.clear()
                    NSE_HOLIDAYS.update(NSE_HOLIDAYS_MAP.keys())
                    logger.debug(f"[TZ] Loaded {len(NSE_HOLIDAYS_MAP)} trading holidays from local cache.")
        except Exception as e:
            logger.warning(f"[TZ] Failed reading cached holidays: {e}")

    # Ensure current and next calendar years have perpetual national holidays seeded
    cur_yr = now_ist().year
    _seed_fixed_national_holidays(cur_yr)
    _seed_fixed_national_holidays(cur_yr + 1)


def _save_cached_holidays(last_synced: Optional[str] = None):
    """Persists current holiday mapping to disk."""
    try:
        HOLIDAYS_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "last_synced": last_synced or now_ist().isoformat(),
            "count": len(NSE_HOLIDAYS_MAP),
            "holidays": {
                d: {"description": desc, "weekday": datetime.strptime(d, "%Y-%m-%d").strftime("%A")}
                for d, desc in sorted(NSE_HOLIDAYS_MAP.items())
            }
        }
        with open(HOLIDAYS_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
    except Exception as e:
        logger.warning(f"[TZ] Failed saving holiday cache to {HOLIDAYS_CACHE_FILE}: {e}")


# Initialize cache on module import
_load_cached_holidays()


def is_market_holiday(dt: Optional[datetime] = None) -> bool:
    """Checks if the given datetime (or current IST time) falls on a known NSE trading holiday."""
    dt_ist = dt if dt is not None else now_ist()
    date_str = dt_ist.strftime("%Y-%m-%d")
    return date_str in NSE_HOLIDAYS


def is_trading_day(dt: Optional[datetime] = None) -> bool:
    """Returns True only if the day is a weekday (Mon-Fri) and NOT an exchange trading holiday."""
    dt_ist = dt if dt is not None else now_ist()
    # Weekday check: 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
    if dt_ist.weekday() >= 5:
        return False
    return not is_market_holiday(dt_ist)


def is_market_hours(dt: Optional[datetime] = None) -> bool:
    """Checks if current time is within active market session (Mon-Fri 09:15 - 15:30 IST, non-holiday)."""
    dt_ist = dt if dt is not None else now_ist()
    if not is_trading_day(dt_ist):
        return False
    return time(9, 15) <= dt_ist.time() <= time(15, 30)


def get_holiday_description(dt_or_str: Union[datetime, str, None] = None) -> Optional[str]:
    """Returns the official name/reason of the exchange holiday for a given date, or None if trading day."""
    if dt_or_str is None:
        date_str = now_ist().strftime("%Y-%m-%d")
    elif isinstance(dt_or_str, datetime):
        date_str = dt_or_str.strftime("%Y-%m-%d")
    else:
        date_str = str(dt_or_str).strip()

    return NSE_HOLIDAYS_MAP.get(date_str)


def get_upcoming_holidays(limit: int = 5) -> List[Dict[str, Any]]:
    """Returns the next upcoming NSE trading holidays from today onward."""
    today_str = ist_date_str()
    upcoming = []
    for d, desc in sorted(NSE_HOLIDAYS_MAP.items()):
        if d >= today_str:
            dt = datetime.strptime(d, "%Y-%m-%d")
            upcoming.append({
                "date": d,
                "weekday": dt.strftime("%A"),
                "description": desc,
                "is_weekday": dt.weekday() < 5
            })
            if len(upcoming) >= limit:
                break
    return upcoming


def add_holiday(date_str: str, description: str = "Market Holiday") -> None:
    """Dynamically registers a date string (YYYY-MM-DD) as an exchange holiday and persists to cache."""
    NSE_HOLIDAYS_MAP[date_str] = description
    NSE_HOLIDAYS.add(date_str)
    _save_cached_holidays()
    logger.info(f"[TZ] Added exchange holiday: {date_str} ({description})")


def remove_holiday(date_str: str) -> None:
    """Dynamically removes a date string (YYYY-MM-DD) from exchange holidays if incorrectly flagged."""
    NSE_HOLIDAYS_MAP.pop(date_str, None)
    NSE_HOLIDAYS.discard(date_str)
    _save_cached_holidays()
    logger.info(f"[TZ] Removed exchange holiday: {date_str}")


def sync_nse_holidays(years: Optional[List[int]] = None, timeout: float = 8.0) -> bool:
    """
    Dynamically fetches official trading holidays from NSE's official API endpoint.
    Automatically handles current and future years (e.g., 2026, 2027), updates the in-memory
    mapping, and writes to local persistent cache.
    
    Safe to call in background threads; falls back gracefully to local cache on network error.
    """
    import requests

    now = now_ist()
    target_years = years or [now.year, now.year + 1]
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "Accept-Language": "en-US,en;q=0.9",
    }

    session = requests.Session()
    fetched_count = 0

    try:
        # Step 1: Initialize session on NSE homepage to capture session cookies
        session.get("https://www.nseindia.com", headers=headers, timeout=timeout)
        headers["Referer"] = "https://www.nseindia.com/resources/exchange-communication-holidays"

        # Step 2: Query trading holidays for target years
        for yr in target_years:
            url = f"https://www.nseindia.com/api/holiday-master?type=trading&year={yr}"
            resp = session.get(url, headers=headers, timeout=timeout)
            if resp.status_code == 200:
                payload = resp.json()
                # FO segment covers derivative / option markets
                holiday_list = payload.get("FO") or payload.get("CM") or []
                for item in holiday_list:
                    raw_date = item.get("tradingDate", "").strip()
                    desc = item.get("description", "Exchange Holiday").strip()
                    try:
                        parsed_dt = datetime.strptime(raw_date, "%d-%b-%Y")
                        fmt_date = parsed_dt.strftime("%Y-%m-%d")
                        NSE_HOLIDAYS_MAP[fmt_date] = desc
                        NSE_HOLIDAYS.add(fmt_date)
                        fetched_count += 1
                    except Exception:
                        continue

        if fetched_count > 0:
            _save_cached_holidays(last_synced=now.isoformat())
            logger.info(f"[TZ] Successfully synced {fetched_count} NSE trading holidays for years {target_years}.")
            return True
        else:
            logger.info(f"[TZ] NSE holiday sync returned 0 records for years {target_years}. Retaining existing cache.")
            return False

    except Exception as e:
        logger.warning(f"[TZ] Could not sync holidays dynamically from NSE API: {e}. Relying on local cache.")
        return False
