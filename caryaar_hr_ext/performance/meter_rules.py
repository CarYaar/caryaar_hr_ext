"""Pure rules for the goal meter: progress by method, windows in IST, the 01-Nov gate,
stale and overdue tests, and when a review pack is due. No Frappe imports; tested with
plain pytest and used by performance/meter.py and performance/review_pack.py."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Sequence

PROGRESS_GATE = date(2026, 11, 1)   # G8: readings from 01-Oct, Goal.progress written from 01-Nov
METHODS = ("Ratio to target", "Months meeting standard", "Plane module", "Manual")
WINDOWS = ("Cycle to date", "Latest full month", "Latest full week")
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


def week_windows(cycle_start: date, as_of: date) -> list[tuple[date, date]]:
    """Every Monday-to-Sunday week that starts on or after cycle_start and whose Sunday has
    passed before as_of (marketing goals read the week, never the day)."""
    out, monday = [], cycle_start + timedelta(days=(7 - cycle_start.weekday()) % 7)
    while monday + timedelta(days=6) < as_of:
        out.append((monday, monday + timedelta(days=6)))
        monday += timedelta(days=7)
    return out


def window_bounds(window: str, as_of: date, cycle_start: date) -> tuple[date, date]:
    """The dates a reading sums over; a window with no full period yet reads cycle to date."""
    if window == "Latest full month":
        months = month_windows(cycle_start, as_of)
        if months:
            return months[-1]
    elif window == "Latest full week":
        weeks = week_windows(cycle_start, as_of)
        if weeks:
            return weeks[-1]
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


def recipients(always_raw: str | None, manager_user: str | None) -> list[str]:
    """The pack goes to the settings list (one user per line) plus the person's manager;
    empty when neither exists, so the caller can skip and log instead of sending to nobody."""
    people = {x.strip() for x in (always_raw or "").split("\n") if x.strip()}
    if manager_user:
        people.add(manager_user.strip())
    return sorted(people)


# ─── what the pack and the person read ───────────────────────────────────────

ROLE_METRICS = ("jobs_from_bookings", "bookings_to_jobs_pct", "calls_to_bookings_pct",          # agents
                "campaigns_sent", "campaign_leads_reached", "creatives_approved", "leads_from_channels",  # marketing
                "jobs_moved", "sweep_items_closed", "partner_changes",                              # ops
                "partners_activated", "agreements_signed",                                         # Service Partners
                "payouts_triggered", "unpaid_cleared")                                             # finance
METRIC_ROLES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("agents", ("conversion_pct", "followups_on_time_pct", "leads_statused_48h_pct",
                "jobs_from_bookings", "bookings_to_jobs_pct", "calls_to_bookings_pct")),
    ("marketing", ("campaigns_sent", "campaign_leads_reached", "creatives_approved", "leads_from_channels")),
    ("operations", ("jobs_moved", "sweep_items_closed", "partner_changes")),
    ("service partners", ("partners_activated", "agreements_signed")),
    ("finance", ("payouts_triggered", "unpaid_cleared")),
    ("tech", ("incidents_fixed_24h_pct", "support_on_time_pct", "release_bugs_14d")),
    ("everyone", ("module_completion", "wiki_pages")),
)


def metric_keys_text() -> str:
    """The metric keys HR may put on a Goal Meter, by role (the Setup page and the validation error)."""
    return "; ".join(f"{role}: {', '.join(keys)}" for role, keys in METRIC_ROLES)


SOURCE_OF = {"conversion_pct": "CY Admin", "followups_on_time_pct": "CY Admin", "leads_statused_48h_pct": "CY Admin",
             "module_completion": "Plane items", "incidents_fixed_24h_pct": "Plane items",
             "support_on_time_pct": "Plane items", "release_bugs_14d": "Plane items", "wiki_pages": "ERP",
             **{k: "CY Admin" for k in ROLE_METRICS}}


def fmt_day(value) -> str:
    """DD-MMM-YYYY (house style) from a date, a datetime or an ISO string; empty for nothing."""
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        value = value.date()
    elif isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return value.strftime("%d-%b-%Y")


def _num(x) -> str:
    return f"{int(x)}" if float(x).is_integer() else f"{x}"


def _with_unit(x, unit) -> str:
    unit = unit or ""
    return f"{_num(x)}{unit}" if unit in ("", "%") else f"{_num(x)} {unit}"


def target_text(g: dict) -> str:
    """The target as the pack and the person read it: "5%", "95% or better each month"."""
    m = g.get("method")
    if m == "Ratio to target" and g.get("target") is not None:
        return _with_unit(g["target"], g.get("unit"))
    if m == "Months meeting standard" and g.get("standard") is not None:
        side = "or less" if g.get("direction") == LOWER else "or better"
        return f"{_with_unit(g['standard'], g.get('unit'))} {side} each month"
    if m == "Plane module":
        return "every item in the module done"
    return ""


def source_text(g: dict) -> str:
    m = g.get("method")
    if m == "Manual":
        return "Manual (manager enters)"
    if m == "Plane module":
        return "Plane module"
    metric = g.get("metric") or ""
    return f"{SOURCE_OF.get(metric, 'ERP')} ({metric})" if metric else "ERP"


def source_name(g: dict) -> str:
    m = g.get("method")
    if m == "Manual":
        return "Manager"
    if m == "Plane module":
        return "Plane"
    return SOURCE_OF.get(g.get("metric") or "", "ERP")


def describe_meter(g: dict) -> str:
    """One sentence on how the goal is measured, in the person's words."""
    m = g.get("method")
    if m == "Manual":
        return "Your manager updates this after each review."
    if m == "Plane module":
        return "Share of the items in your Plane module that are done."
    metric = g.get("metric") or ""
    src = SOURCE_OF.get(metric, "ERP")
    if m == "Months meeting standard":
        return f"Months where {metric} ({src}) was {target_text(g).replace(' each month', '')}."
    return f"Measured from {src} ({metric}) against a target of {target_text(g)}."


def trend_points(readings: Sequence[tuple[date, float | None]], step_days: int = 15) -> list[tuple[date, float | None]]:
    """One point every step_days from the first reading, plus the latest reading."""
    out: list[tuple[date, float | None]] = []
    last: date | None = None
    for day, progress in readings:
        if last is None or (day - last).days >= step_days:
            out.append((day, progress))
            last = day
    if readings and out[-1][0] != readings[-1][0]:
        out.append(tuple(readings[-1]))
    return out


def _pct_text(x) -> str:
    return f"{_num(x)}%"


def trend_text(trend) -> str:
    return ", ".join(f"{_pct_text(p)} ({fmt_day(d)})" for d, p in trend if p is not None)


def pack_rows(pack: dict) -> list[dict]:
    """The review pack as rows: one per goal (source, target, latest value and progress, the
    percentage HRMS averages, the trend) and one per Plane item counted under it."""
    rows = []
    for g in pack["goals"]:
        flags = [f for f, on in (("stale", g.get("stale")), ("no reading", g.get("progress") is None)) if on]
        rows.append({"row_type": "goal", "goal": g["goal"], "text": g["goal_name"], "kra": g.get("kra"),
                     "weight": g.get("weight"), "method": g.get("method"), "source": source_text(g),
                     "target": target_text(g), "start": "", "assignee": "", "value": g.get("value"),
                     "progress": g.get("progress"), "in_appraisal": g.get("erp_progress"),
                     "trend": trend_text(g.get("trend") or []), "flags": ", ".join(flags)})
        for i in g.get("items") or []:
            iflags = [f for f, on in (("overdue", i.get("overdue")), ("archived", i.get("archived"))) if on]
            if i.get("completed_at"):
                iflags.append(f"done {fmt_day(i['completed_at'])}")
            rows.append({"row_type": "item", "goal": g["goal"],
                         "text": f"{i['project_identifier']}-{i['sequence_id']} {i['title']}", "kra": "",
                         "weight": None, "method": i.get("state_group"), "source": "",
                         "target": fmt_day(i.get("target_date")), "start": fmt_day(i.get("start_date")),
                         "assignee": i.get("assignee_name") or "", "value": None, "progress": None,
                         "in_appraisal": None, "trend": "", "flags": ", ".join(iflags)})
    return rows


def manual_reading_problem(method, active, evidence, is_self: bool) -> str | None:
    """Why a manual reading cannot be written, in plain words; None when it can."""
    if method != "Manual":
        return "This goal is measured automatically."
    if not active:
        return "This goal's meter is switched off."
    if is_self:
        return "A reading for your own goal must come from your manager."
    if not (evidence or "").strip():
        return "Evidence is required: a link or a note on what was checked."
    return None


def person_view(pack: dict, next_review_on=None) -> dict:
    """What the person sees on their CY Admin home screen: their goals, how each is measured,
    the latest reading, the Plane items counted and the next review date."""
    goals = []
    for g in pack["goals"]:
        goals.append({"goal": g["goal"], "goal_name": g["goal_name"], "kra": g.get("kra"), "weight": g.get("weight"),
                      "method": g.get("method"), "source": source_name(g), "target": target_text(g),
                      "value": g.get("value"), "progress": g.get("progress"), "in_appraisal": g.get("erp_progress"),
                      "stale": bool(g.get("stale")), "reading_date": g.get("reading_date"), "how": describe_meter(g),
                      "trend": [(fmt_day(d), p) for d, p in (g.get("trend") or [])],
                      "items": [{"key": f"{i['project_identifier']}-{i['sequence_id']}", "title": i["title"],
                                 "state": i.get("state_group"), "target_date": fmt_day(i.get("target_date")),
                                 "overdue": bool(i.get("overdue")), "done_on": fmt_day(i.get("completed_at"))}
                                for i in g.get("items") or []]})
    return {"cycle": pack["cycle"], "as_of": pack["as_of"], "learning_month": pack["learning_month"],
            "next_review_on": next_review_on, "adherence_pct": (pack.get("adherence") or {}).get("pct"),
            "uncounted_items": pack.get("uncounted_items"), "goals": goals}


def cycle_is_live(status, start_date: date | None, end_date: date | None, as_of: date, *,
                  started_only: bool = False) -> bool:
    """A cycle counts only while its dates say so. HRMS never closes a cycle on its own, so
    the live ERP still carries the previous cycle as In Progress; the end date settles it.
    started_only also drops a cycle that has not begun (the person's view and the packs),
    while the meter and its setup keep a Not Started cycle so meters exist before day one."""
    if status not in ("Not Started", "In Progress"):
        return False
    if end_date is not None and end_date < as_of:
        return False
    if started_only and start_date is not None and start_date > as_of:
        return False
    return True
