"""Shared opening-hours parsing for the access-gap scripts.

Google `open_hours` is a JSON dict: {"Monday": "8 AM–5 PM", "Saturday": "Closed", ...}; values can be null.
"""
from __future__ import annotations

import json
import re

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
LATE_MIN = 19 * 60  # "open late" = open until at least 7 PM


def close_minutes(v) -> int | None:
    """Closing time in minutes after midnight for one day's string.
    24 hours / closes after midnight -> 1440; closed -> -1; missing or unparseable -> None."""
    if not v:
        return None
    s = str(v)
    if "closed" in s.lower():
        return -1
    if "24" in s:
        return 1440
    end = re.split(r"[–\-]", s.split(",")[-1])[-1].strip()
    m = re.match(r"(\d{1,2})(?::(\d{2}))?\s*(AM|PM)", end, re.I)
    if not m:
        return None
    h, mm, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3).upper()
    if ap == "AM":
        return 1440 if (h == 12 or h <= 5) else h * 60 + mm  # closes after midnight
    return (12 if h == 12 else h + 12) * 60 + mm


def day_closes(h) -> dict | None:
    """{day: closing minutes or None}; None when no day has usable hours (hours unknown)."""
    try:
        d = json.loads(h)
    except (TypeError, ValueError):
        return None
    mins = {k: close_minutes(v) for k, v in d.items()}
    return None if all(v is None for v in mins.values()) else mins


def weekday_close_3of5(h) -> int | None:
    """Latest time the place is still open on at least 3 of 5 weekdays (minutes); -1 = closed; None = unknown."""
    mins = day_closes(h)
    if mins is None:
        return None
    vals = sorted(((mins.get(k) if mins.get(k) is not None else -1) for k in WEEKDAYS), reverse=True)
    return vals[2]


def parse_hours(h) -> tuple[bool, bool, bool]:
    """-> (known, open late on >= 3 weekdays, open Saturday or Sunday)"""
    mins = day_closes(h)
    if mins is None:
        return (False, False, False)
    late = (weekday_close_3of5(h) or -1) >= LATE_MIN
    wkend = any((mins.get(k) or -1) > 0 for k in ("Saturday", "Sunday"))
    return (True, late, wkend)
