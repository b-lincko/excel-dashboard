from __future__ import annotations

from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional, Union

DateLike = Union[str, datetime, date, None]

FORMATS = [
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
    "%m/%d/%Y %H:%M",
    "%m/%d/%Y",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d-%b-%Y",
    "%d-%b-%Y %H:%M",
]


def parse_date(value: DateLike) -> Optional[datetime]:
    """Parse the workbook's date formats. String results are memoized: the
    dashboard re-parses the same few thousand distinct date strings tens of
    thousands of times per aggregation (this was seconds of CPU per load)."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return _parse_date_str(str(value))


@lru_cache(maxsize=65536)
def _parse_date_str(text: str) -> Optional[datetime]:
    text = text.strip()
    if not text or text.upper() in {"N/A", "NA", "NONE", "-", "#N/A"}:
        return None
    # Excel serial number
    try:
        if text.replace(".", "", 1).isdigit():
            serial = float(text)
            if 20000 < serial < 80000:
                return datetime(1899, 12, 30) + timedelta(days=serial)
    except Exception:
        pass
    for fmt in FORMATS:
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
        except Exception:
            continue
    try:
        return datetime.fromisoformat(text.replace("Z", ""))
    except Exception:
        return None


def format_date(value: DateLike, with_time: bool = True) -> str:
    dt = parse_date(value)
    if not dt:
        return ""
    return dt.strftime("%Y-%m-%d %H:%M") if with_time else dt.strftime("%Y-%m-%d")


def to_date(value: DateLike) -> Optional[date]:
    dt = parse_date(value)
    return dt.date() if dt else None


def days_between(start: DateLike, end: DateLike) -> Optional[float]:
    a = parse_date(start)
    b = parse_date(end)
    if not a or not b:
        return None
    return (b - a).total_seconds() / 86400.0


def iso_week_key(dt: datetime) -> tuple[int, int]:
    iso = dt.isocalendar()
    return int(iso[0]), int(iso[1])


def week_bounds(year: int, week: int) -> tuple[datetime, datetime]:
    # Monday of ISO week
    monday = datetime.fromisocalendar(year, week, 1)
    sunday = monday + timedelta(days=6, hours=23, minutes=59, seconds=59)
    return monday, sunday


def quarter_of(dt: datetime) -> int:
    return (dt.month - 1) // 3 + 1
