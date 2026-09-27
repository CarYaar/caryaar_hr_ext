"""Pure decision logic for adherence, goal progress and rating categories.

No Frappe imports here: this module is tested with plain pytest and used by
performance/api.py and performance/engine.py.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple

SOURCES: tuple[str, ...] = ("Plane", "CY Admin")
METRIC_KEYS: dict[str, tuple[str, ...]] = {
    "Plane": ("activity_count", "completed_count"),
    "CY Admin": ("calls_handled", "calls_answered", "talk_seconds", "dispositions",
                 "status_moves", "notes_written", "bookings_credited",
                 "leads_assigned", "leads_untouched", "followups_overdue"),
}
MAX_ROWS = 2000
MAX_METRIC = 10_000_000
IST = timezone(timedelta(hours=5, minutes=30))
BANDS: tuple[tuple[float, str], ...] = (
    (4.5, "Exceptional"), (3.75, "Excellent"), (3.0, "Good"), (2.0, "Fair"), (0.0, "Non-Satisfactory"))
_SOURCE_SLUG = {"Plane": "PLANE", "CY Admin": "CYADMIN"}


class ActivityRow(NamedTuple):
    email: str
    date: str
    metrics: dict[str, int]


class ActivityBatch(NamedTuple):
    source: str
    synced_through: datetime
    rows: list[ActivityRow]
    covers_from: date


class ModuleRow(NamedTuple):
    module_id: str
    project_identifier: str
    module_name: str
    total_issues: int
    completed_issues: int


class DayContext(NamedTuple):
    is_holiday: bool
    attendance_status: str | None
    expected_sources: tuple[str, ...]
    fresh_sources: frozenset[str]
    activity: dict[str, dict[str, int]]
    wfh_requested: bool
    wfh_approved: bool


class AdherenceResult(NamedTuple):
    is_working_day: bool
    wfh: bool
    work_visible: bool | None
    wfh_approved: bool | None
    wfh_evidenced: bool | None
    checks_passed: int
    checks_applicable: int
    adherence_pct: float | None


def _parse_aware(value) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("synced_through must be an ISO 8601 datetime string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"synced_through is not a valid datetime: {value!r}") from e
    if dt.tzinfo is None:
        raise ValueError("synced_through must carry a time zone offset")
    return dt.astimezone(IST).replace(tzinfo=None)


def _parse_day(value) -> str:
    if not isinstance(value, str):
        raise ValueError(f"row date must be YYYY-MM-DD, got {value!r}")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as e:
        raise ValueError(f"row date must be YYYY-MM-DD, got {value!r}") from e


def _metric(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"metric {name} must be a whole number, got {value!r}")
    if value < 0 or value > MAX_METRIC:
        raise ValueError(f"metric {name} out of range: {value}")
    return value


def validate_activity_payload(source, synced_through, rows, covers_from) -> ActivityBatch:
    """Validate one intake call. ``covers_from`` is the first day the sender fully
    re-counted in this run; every row must be on or after it (see advance_stamp)."""
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
    when = _parse_aware(synced_through)
    if not isinstance(covers_from, str):
        raise ValueError(f"covers_from must be YYYY-MM-DD, got {covers_from!r}")
    first_day = date.fromisoformat(_parse_day(covers_from))
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"at most {MAX_ROWS} rows per call, got {len(rows)}")
    allowed = set(METRIC_KEYS[source])
    out: list[ActivityRow] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"row {i} must be an object")
        email = row.get("email")
        if not isinstance(email, str) or "@" not in email:
            raise ValueError(f"row {i} email is not an email address: {email!r}")
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError(f"row {i} metrics must be an object")
        unknown = set(metrics) - allowed
        if unknown:
            raise ValueError(f"row {i} has metrics not allowed for {source}: {sorted(unknown)}")
        day = _parse_day(row.get("date"))
        if date.fromisoformat(day) < first_day:
            raise ValueError(f"row {i} date {day} is before covers_from {first_day.isoformat()}")
        out.append(ActivityRow(email.strip().lower(), day,
                               {k: _metric(k, v) for k, v in metrics.items()}))
    return ActivityBatch(source, when, out, first_day)


def validate_module_payload(synced_through, modules) -> tuple[datetime, list[ModuleRow]]:
    when = _parse_aware(synced_through)
    if not isinstance(modules, list) or len(modules) > MAX_ROWS:
        raise ValueError(f"modules must be a list of at most {MAX_ROWS}")
    out: list[ModuleRow] = []
    for i, m in enumerate(modules):
        if not isinstance(m, dict):
            raise ValueError(f"module {i} must be an object")
        mid = m.get("module_id")
        if not isinstance(mid, str) or not mid.strip():
            raise ValueError(f"module {i} module_id is required")
        total = _metric("total_issues", m.get("total_issues"))
        done = _metric("completed_issues", m.get("completed_issues"))
        if done > total:
            raise ValueError(f"module {i} completed_issues ({done}) exceeds total_issues ({total})")
        out.append(ModuleRow(mid.strip(), str(m.get("project_identifier") or ""),
                             str(m.get("module_name") or "")[:140], total, done))
    return when, out


def activity_doc_name(employee: str, date_iso: str, source: str) -> str:
    return f"WACT-{employee}-{date_iso}-{_SOURCE_SLUG[source]}"


def adherence_doc_name(employee: str, date_iso: str) -> str:
    return f"WADH-{employee}-{date_iso}"


def parse_department_sources(text: str) -> dict[str, list[str]]:
    if not text or not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"department sources is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("department sources must be an object of department to list of sources")
    for dept, srcs in data.items():
        if not isinstance(srcs, list) or not srcs or any(s not in SOURCES for s in srcs):
            raise ValueError(f"{dept}: sources must be a non-empty list from {SOURCES}")
    return data


def _active(source: str, m: dict[str, int]) -> bool:
    if source == "Plane":
        return m.get("activity_count", 0) > 0 or m.get("completed_count", 0) > 0
    return m.get("calls_handled", 0) > 0 or m.get("status_moves", 0) > 0 or m.get("notes_written", 0) > 0


def _evidenced(source: str, m: dict[str, int]) -> bool:
    if source == "Plane":
        return m.get("completed_count", 0) > 0
    return m.get("calls_handled", 0) > 0


def _judge(ctx: DayContext, test) -> bool | None:
    fresh = [s for s in ctx.expected_sources if s in ctx.fresh_sources]
    if any(test(s, ctx.activity.get(s, {})) for s in fresh):
        return True
    if fresh and len(fresh) == len(ctx.expected_sources):
        return False
    return None


def adherence_day(ctx: DayContext) -> AdherenceResult:
    working = not ctx.is_holiday and ctx.attendance_status not in ("On Leave", "Absent")
    # A request still waiting for approval only makes it a WFH day when no attendance
    # says otherwise: someone marked Present in the office is not on a failed WFH day.
    wfh = ctx.attendance_status == "Work From Home" or (ctx.wfh_requested and not ctx.attendance_status)
    if not working:
        return AdherenceResult(False, wfh, None, None, None, 0, 0, None)
    visible = _judge(ctx, _active)
    approved = bool(ctx.wfh_approved) if wfh else None
    evidenced = _judge(ctx, _evidenced) if wfh else None
    checks = [c for c in (visible, approved, evidenced) if c is not None]
    passed = sum(1 for c in checks if c)
    pct = round(100.0 * passed / len(checks), 1) if checks else None
    return AdherenceResult(True, wfh, visible, approved, evidenced, passed, len(checks), pct)


def module_progress(total: int, completed: int) -> float | None:
    if not total:
        return None
    return round(100.0 * completed / total, 1)


def performance_category(final_score: float | None) -> str | None:
    if not final_score or final_score <= 0:
        return None
    for floor, name in BANDS:
        if final_score >= floor:
            return name
    return None


# D4: founders' goals sit under this scorecard, but founders are not on the bell curve.
OFF_CURVE_TEMPLATES = ("Leadership - Company Scorecard",)


def stored_category(docstatus: int, final_score: float | None, template: str | None) -> str:
    """Category to store on an appraisal: only once it is submitted, never for an off-curve scorecard."""
    if docstatus != 1 or template in OFF_CURVE_TEMPLATES:
        return ""
    return performance_category(final_score) or ""


# Stamps before this year are not real sync times: Frappe reads a never-set
# Datetime single back as 0001-01-01, and senders put 1970-01-01 on row chunks.
_REAL_STAMP_YEAR = 2000


def stored_stamp(value) -> datetime | None:
    """A saved "synced through" stamp, or None if the source has never synced."""
    if not value:
        return None
    dt = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    return dt if dt.year >= _REAL_STAMP_YEAR else None


def advance_stamp(current: datetime | None, new: datetime, covers_from: date) -> datetime | None:
    """New "synced through" stamp for a source.

    Moves forward only when the payload's first day is on or before the day of
    the current stamp, so a sender that resumes after an outage cannot mark the
    days it never sent as complete. Never moves backwards. A placeholder stamp
    (row chunks) never sets or moves it.
    """
    current = stored_stamp(current)
    if new.year < _REAL_STAMP_YEAR:
        return current
    if current is None:
        return new
    if covers_from > current.date():
        return current
    return max(current, new)


_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")


def extract_module_id(raw) -> str | None:
    """The Plane module UUID from a pasted ID or module URL (the last UUID in it)."""
    if not isinstance(raw, str):
        return None
    found = _UUID.findall(raw)
    return found[-1].lower() if found else None


MAX_RECOMPUTE_DAYS = 62


def recompute_days(from_date: str, to_date: str) -> list[date]:
    start, end = date.fromisoformat(str(from_date)), date.fromisoformat(str(to_date))
    if end < start:
        raise ValueError("from_date must be on or before to_date")
    n = (end - start).days + 1
    if n > MAX_RECOMPUTE_DAYS:
        raise ValueError(f"at most {MAX_RECOMPUTE_DAYS} days per recompute, got {n}")
    return [start + timedelta(days=i) for i in range(n)]
