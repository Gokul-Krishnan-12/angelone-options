"""
Indian Standard Time (IST, UTC+05:30) utilities.
Guarantees consistent market timing and scheduling regardless of the host OS timezone
(e.g., Cloud VPS defaults to UTC, foreign cloud regions).
"""

from datetime import datetime, timezone, timedelta, time

# Indian Standard Time (IST) is UTC+05:30 with no daylight saving time
IST = timezone(timedelta(hours=5, minutes=30), name="IST")


def now_ist() -> datetime:
    """Returns the current datetime in Indian Standard Time (IST)."""
    return datetime.now(IST)


def ist_time() -> time:
    """Returns the current time of day in Indian Standard Time (IST)."""
    return datetime.now(IST).time()


def ist_date_str(fmt: str = "%Y-%m-%d") -> str:
    """Returns today's date formatted in Indian Standard Time (IST)."""
    return datetime.now(IST).strftime(fmt)
