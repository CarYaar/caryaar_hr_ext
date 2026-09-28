"""Pure rules for the goal meter: progress by method, windows in IST, the 01-Nov gate,
stale and overdue tests, and when a review pack is due. No Frappe imports; tested with
plain pytest and used by performance/meter.py and performance/review_pack.py."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Sequence

PROGRESS_GATE = date(2026, 11, 1)   # G8: readings from 01-Oct, Goal.progress written from 01-Nov
METHODS = ("Ratio to target", "Months meeting standard", "Plane module", "Manual")
WINDOWS = ("Cycle to date", "Latest full month")
HIGHER, LOWER = "Higher is better", "Lower is better"


def _r1(x: float) -> float:
    return round(x + 1e-9, 1)


def pct(n, d) -> float | None:
    """n as a percentage of d, one decimal; None when there is nothing to divide by."""
    return None if not d else _r1(100.0 * float(n) / float(d))


def progress_ratio(value, target, direction) -> float | None:
    """Value against the final target, capped at 100. Lower-is-better: fully met at or
    below the target, else target/value."""
    if value is None or target in (None, 0):
        return None
    v, t = float(value), float(target)
    if direction == LOWER:
        if v <= t:
            return 100.0
        return _r1(min(100.0, 100.0 * t / v)) if v > 0 else None
    return _r1(min(100.0, 100.0 * v / t))


def meets_standard(value, standard, direction) -> bool | None:
    if value is None or standard is None:
        return None
    return float(value) <= float(standard) if direction == LOWER else float(value) >= float(standard)


def progress_months(met: Sequence[bool | None]) -> float | None:
    """Share of judged months that met the standard; unjudged months (None) are skipped."""
    judged = [m for m in met if m is not None]
    return None if not judged else _r1(100.0 * sum(1 for m in judged if m) / len(judged))


def progress_module(total: int, done: int) -> float | None:
    return None if not total else _r1(min(100.0, 100.0 * done / total))


def _month_end(d: date) -> date:
    nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return nxt - timedelta(days=1)


def month_windows(cycle_start: date, as_of: date) -> list[tuple[date, date]]:
    """Every full month of the cycle that has ended before as_of."""
    out, start = [], cycle_start.replace(day=1)
    while _month_end(start) < as_of:
        out.append((max(start, cycle_start), _month_end(start)))
        start = _month_end(start) + timedelta(days=1)
    return out


def window_bounds(window: str, as_of: date, cycle_start: date) -> tuple[date, date]:
    if window == "Latest full month":
        months = month_windows(cycle_start, as_of)
        if months:
            return months[-1]
    return cycle_start, as_of


def writes_progress(as_of: date) -> bool:
    return as_of >= PROGRESS_GATE


def is_stale(stamp: datetime | None, as_of: date) -> bool:
    """A source is fresh for a day only if it synced past 23:00 of that day."""
    return stamp is None or stamp < datetime.combine(as_of, time(23, 0))


def is_overdue(target_date: date | None, state_group: str, as_of: date) -> bool:
    return bool(target_date) and state_group not in ("completed", "cancelled") and target_date < as_of


def pack_due_today(as_of: date, review_dates: Sequence[date]) -> bool:
    """G9: the 1st and 15th, and three days before a review date."""
    return as_of.day in (1, 15) or any(rd - as_of == timedelta(days=3) for rd in review_dates)
