"""
Indian Standard Time (IST, UTC+05:30) utilities.
Guarantees consistent market timing and scheduling regardless of the host OS timezone
(e.g., Cloud VPS defaults to UTC, foreign cloud regions).
"""

from datetime import datetime, timezone, timedelta, time

# Indian Standard Time (IST) is UTC+05:30 with no daylight saving time
IST = timezone(timedelta(hours=5, minutes=30), name="IST")

# Recognized NSE / BSE equity and derivative market trading holidays (YYYY-MM-DD)
NSE_HOLIDAYS = {
    # 2025
    "2025-01-26", "2025-02-26", "2025-03-14", "2025-03-31", "2025-04-10",
    "2025-04-14", "2025-04-18", "2025-05-01", "2025-06-07", "2025-08-15",
    "2025-08-27", "2025-10-02", "2025-10-21", "2025-10-22", "2025-11-05",
    "2025-12-25",
    # 2026
    "2026-01-26", "2026-02-15", "2026-03-03", "2026-03-20", "2026-04-03",
    "2026-04-14", "2026-05-01", "2026-05-27", "2026-06-25", "2026-08-15",
    "2026-09-14", "2026-10-02", "2026-10-20", "2026-11-08", "2026-11-09",
    "2026-11-24", "2026-12-25"
}


def now_ist() -> datetime:
    """Returns the current datetime in Indian Standard Time (IST)."""
    return datetime.now(IST)


def ist_time() -> time:
    """Returns the current time of day in Indian Standard Time (IST)."""
    return datetime.now(IST).time()


def ist_date_str(fmt: str = "%Y-%m-%d") -> str:
    """Returns today's date formatted in Indian Standard Time (IST)."""
    return datetime.now(IST).strftime(fmt)


def is_market_holiday(dt: datetime = None) -> bool:
    """Checks if the given datetime (or current IST time) falls on a known NSE trading holiday."""
    dt_ist = dt if dt is not None else now_ist()
    date_str = dt_ist.strftime("%Y-%m-%d")
    return date_str in NSE_HOLIDAYS


def is_trading_day(dt: datetime = None) -> bool:
    """Returns True only if the day is a weekday (Mon-Fri) and NOT an exchange trading holiday."""
    dt_ist = dt if dt is not None else now_ist()
    # Weekday check: 0 = Monday, 4 = Friday, 5 = Saturday, 6 = Sunday
    if dt_ist.weekday() >= 5:
        return False
    return not is_market_holiday(dt_ist)


def is_market_hours(dt: datetime = None) -> bool:
    """Checks if current time is within active market session (Mon-Fri 09:15 - 15:30 IST, non-holiday)."""
    dt_ist = dt if dt is not None else now_ist()
    if not is_trading_day(dt_ist):
        return False
    return time(9, 15) <= dt_ist.time() <= time(15, 30)

