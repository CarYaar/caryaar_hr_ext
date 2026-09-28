"""Nightly goal meter: one reading per active Goal Meter per day; from 01-Nov-2026 the
reading's progress is written to Goal.progress through the document so HRMS hooks run
(status, parent goal, appraisal score). Metric evaluators read the ERP only:
Work Activity Day (CY Admin per-agent metrics), Plane Work Item (the Plane mirror) and
Wiki Page. Every meter is fail-soft: one bad goal never stops the others."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Callable, NamedTuple

import frappe
from frappe.utils import flt, get_datetime, getdate, nowdate, now_datetime

from caryaar_hr_ext.performance import meter_rules as mr, rules

DEFAULT_CYCLE_START = date(2026, 10, 1)


class MeterContext(NamedTuple):
    employee: str
    cycle: str
    cycle_start: date
    as_of: date
    window_from: date
    window_to: date
    meter: "frappe._dict"


# ─── source reads ─────────────────────────────────────────────────────────────

def _sum_metric(ctx: MeterContext, key: str, source: str = "CY Admin") -> int:
    if key not in rules.METRIC_KEYS.get(source, ()):
        raise ValueError(f"unknown metric column {key!r}")
    row = frappe.db.sql(f"""SELECT coalesce(sum(`{key}`), 0) FROM `tabWork Activity Day`
                            WHERE employee = %s AND source = %s AND activity_date BETWEEN %s AND %s""",
                        (ctx.employee, source, ctx.window_from, ctx.window_to))
    return int(row[0][0] or 0)


def _items(**filters) -> list:
    return frappe.get_all("Plane Work Item", filters={"is_deleted": 0, **filters},
                          fields=["name", "state_group", "target_date", "completed_at", "created_at", "labels", "module_id"])


def _labels(item) -> set[str]:
    return {x.strip() for x in (item.labels or "").split(",") if x.strip()}


def _module_id(ctx: MeterContext) -> str | None:
    return rules.extract_module_id(frappe.db.get_value("Goal", ctx.meter.goal, "cy_plane_module"))


# ─── metric evaluators (value in the goal's unit) ─────────────────────────────

def m_conversion_pct(ctx):
    """Bookings within 7 days of assignment as a share of leads assigned in the window."""
    return mr.pct(_sum_metric(ctx, "bookings_within_7d"), _sum_metric(ctx, "leads_assigned_new"))


def m_followups_on_time_pct(ctx):
    return mr.pct(_sum_metric(ctx, "followups_done_on_time"), _sum_metric(ctx, "followups_due"))


def m_leads_statused_48h_pct(ctx):
    return mr.pct(_sum_metric(ctx, "leads_statused_48h"), _sum_metric(ctx, "leads_assigned_new"))


def m_module_completion(ctx):
    """Current membership of the goal's module: an item moved out stops counting."""
    mid = _module_id(ctx)
    if not mid:
        return None
    items = [i for i in _items(module_id=mid) if i.state_group != "cancelled"]
    return mr.progress_module(len(items), sum(1 for i in items if i.state_group == "completed"))


def m_incidents_fixed_24h_pct(ctx):
    """Items labelled incident, assigned to the person, created in the window: share fixed within 24 h."""
    items = [i for i in _items(assignee=ctx.employee) if "incident" in _labels(i)
             and ctx.window_from <= getdate(i.created_at) <= ctx.window_to]
    fixed = [i for i in items if i.completed_at
             and get_datetime(i.completed_at) - get_datetime(i.created_at) <= timedelta(hours=24)]
    return mr.pct(len(fixed), len(items))


def m_support_on_time_pct(ctx):
    """Items in the goal's module that were due in the window: share completed by their due date."""
    mid = _module_id(ctx)
    items = [i for i in _items(module_id=mid) if i.state_group != "cancelled" and i.target_date] if mid else []
    due = [i for i in items if ctx.window_from <= getdate(i.target_date) <= ctx.window_to]
    done = [i for i in due if i.completed_at and getdate(i.completed_at) <= getdate(i.target_date)]
    return mr.pct(len(done), len(due))


def m_release_bugs_14d(ctx):
    """Bugs raised within 14 days after each release item completed in the window, per release."""
    releases = [i for i in _items(assignee=ctx.employee) if "release" in _labels(i) and i.completed_at
                and ctx.window_from <= getdate(i.completed_at) <= ctx.window_to]
    if not releases:
        return None
    bugs = [i for i in _items() if "bug" in _labels(i)]
    n = sum(1 for r in releases for b in bugs
            if 0 <= (get_datetime(b.created_at) - get_datetime(r.completed_at)).days <= 14)
    return round(n / len(releases), 1)


def m_wiki_pages(ctx):
    user = frappe.db.get_value("Employee", ctx.employee, "user_id")
    if not user:
        return None
    return frappe.db.count("Wiki Page", {"modified_by": user,
                                         "modified": ("between", [ctx.window_from, ctx.window_to])})


METRICS: dict[str, Callable[[MeterContext], float | None]] = {
    "conversion_pct": m_conversion_pct, "followups_on_time_pct": m_followups_on_time_pct,
    "leads_statused_48h_pct": m_leads_statused_48h_pct, "module_completion": m_module_completion,
    "incidents_fixed_24h_pct": m_incidents_fixed_24h_pct, "support_on_time_pct": m_support_on_time_pct,
    "release_bugs_14d": m_release_bugs_14d, "wiki_pages": m_wiki_pages,
}
_SOURCE_OF = {"conversion_pct": "CY Admin", "followups_on_time_pct": "CY Admin", "leads_statused_48h_pct": "CY Admin",
              "module_completion": "Plane items", "incidents_fixed_24h_pct": "Plane items",
              "support_on_time_pct": "Plane items", "release_bugs_14d": "Plane items", "wiki_pages": "ERP"}
_STAMP_FIELD = {"CY Admin": "cy_admin_synced_through", "Plane items": "plane_items_synced_through"}


# ─── readings ─────────────────────────────────────────────────────────────────

def _stamp(source: str) -> datetime | None:
    field = _STAMP_FIELD.get(source)
    if not field:
        return now_datetime()   # the ERP itself is always fresh
    return rules.stored_stamp(frappe.db.get_single_value("Performance Sync Settings", field))


def _last_reading(goal: str, before: date):
    rows = frappe.get_all("Goal Meter Reading", filters={"goal": goal, "reading_date": ("<", before)},
                          fields=["value", "progress"], order_by="reading_date desc", limit=1)
    return rows[0] if rows else None


def _cycle_start(cycle: str) -> date:
    start = frappe.db.get_value("Appraisal Cycle", cycle, "start_date")
    return getdate(start) if start else DEFAULT_CYCLE_START


def compute_reading(gm, as_of: date) -> dict | None:
    """The reading for one meter: {value, progress, stale, method}, or None when the meter is
    manual, its goal is gone, or the metric is unknown."""
    if gm.method == "Manual":
        return None
    goal = frappe.db.get_value("Goal", gm.goal, ["employee", "appraisal_cycle"], as_dict=True)
    metric = "module_completion" if gm.method == "Plane module" else (gm.metric or "")
    fn = METRICS.get(metric)
    if not fn or not goal:
        return None
    cycle_start = _cycle_start(goal.appraisal_cycle)
    if gm.method == "Months meeting standard":
        met = []
        for w_from, w_to in mr.month_windows(cycle_start, as_of):
            ctx = MeterContext(goal.employee, goal.appraisal_cycle, cycle_start, as_of, w_from, w_to, gm)
            met.append(mr.meets_standard(fn(ctx), gm.standard_value, gm.direction))
        value = float(met.count(True)) if met else None
        progress = mr.progress_months(met)
    else:
        w_from, w_to = mr.window_bounds(gm.window or "Cycle to date", as_of, cycle_start)
        ctx = MeterContext(goal.employee, goal.appraisal_cycle, cycle_start, as_of, w_from, w_to, gm)
        value = fn(ctx)
        progress = value if gm.method == "Plane module" else mr.progress_ratio(value, gm.target_value, gm.direction)
    stale = mr.is_stale(_stamp(_SOURCE_OF[metric]), as_of)
    if stale:
        last = _last_reading(gm.goal, as_of)
        if last:
            value, progress = last.value, last.progress
    return {"value": value, "progress": progress, "stale": stale, "method": gm.method}


def _write_reading(gm, as_of: date, reading: dict) -> bool:
    """Store the reading; write Goal.progress only past the gate, only when fresh, only on change."""
    name = f"{gm.goal}|{as_of}"
    values = {"value": reading["value"], "progress": reading["progress"], "method": reading["method"],
              "stale": 1 if reading["stale"] else 0, "computed_at": now_datetime()}
    if frappe.db.exists("Goal Meter Reading", name):
        frappe.db.set_value("Goal Meter Reading", name, values)
    else:
        frappe.get_doc({"doctype": "Goal Meter Reading", "goal": gm.goal, "reading_date": as_of, **values}
                       ).insert(ignore_permissions=True)
    written = False
    if mr.writes_progress(as_of) and reading["progress"] is not None and not reading["stale"]:
        current = flt(frappe.db.get_value("Goal", gm.goal, "progress"))
        if abs(reading["progress"] - current) >= 0.5:
            doc = frappe.get_doc("Goal", gm.goal)
            doc.progress = reading["progress"]
            doc.save(ignore_permissions=True)
            written = True
        frappe.db.set_value("Goal Meter Reading", name, "written_to_goal", 1)
    return written


def run_meter(as_of: date | None = None) -> dict:
    """One pass over every active meter whose goal's cycle is Not Started or In Progress
    and whose employee is Active. Called by engine.run_nightly and on demand."""
    as_of = as_of or getdate(nowdate())
    counts = {"readings": 0, "written": 0, "stale": 0, "skipped": 0}
    cycles = frappe.get_all("Appraisal Cycle", filters={"status": ("in", ["Not Started", "In Progress"])}, pluck="name")
    emps = frappe.get_all("Employee", filters={"status": "Active"}, pluck="name")
    unmatched: list[str] = []
    for gm in frappe.get_all("Goal Meter", filters={"active": 1},
                             fields=["name", "goal", "method", "metric", "window", "target_value",
                                     "standard_value", "direction"]):
        goal = frappe.db.get_value("Goal", gm.goal, ["employee", "appraisal_cycle", "cy_plane_module"], as_dict=True)
        if not goal or goal.appraisal_cycle not in cycles or goal.employee not in emps:
            counts["skipped"] += 1
            continue
        if gm.method == "Plane module" and not rules.extract_module_id(goal.cy_plane_module):
            unmatched.append(f"{gm.goal}: {goal.cy_plane_module or 'no module'}")
        frappe.db.savepoint("cy_meter")
        try:
            reading = compute_reading(gm, as_of)
            if reading is None:
                counts["skipped"] += 1
                continue
            if _write_reading(gm, as_of, reading):
                counts["written"] += 1
            counts["readings"] += 1
            counts["stale"] += 1 if reading["stale"] else 0
        except Exception:
            frappe.db.rollback(save_point="cy_meter")
            frappe.log_error(title=f"Goal meter: {gm.goal} skipped", message=frappe.get_traceback())
            counts["skipped"] += 1
    frappe.db.set_single_value("Performance Sync Settings", "unmatched_goal_modules", "\n".join(unmatched))
    return counts


@frappe.whitelist(methods=["POST"])
def write_manual_reading(goal: str, progress: float, evidence: str = "") -> dict:
    """A manager's reading for a Manual meter; writes progress at once, under the same gate."""
    frappe.only_for(("HR Manager", "HR User", "System Manager"))
    gm = frappe.get_doc("Goal Meter", goal)
    if gm.method != "Manual":
        frappe.throw("This goal is measured automatically.")
    as_of = getdate(nowdate())
    reading = {"value": flt(progress), "progress": max(0.0, min(100.0, flt(progress))), "stale": False, "method": "Manual"}
    written = _write_reading(gm, as_of, reading)
    frappe.db.set_value("Goal Meter Reading", f"{goal}|{as_of}",
                        {"evidence": (evidence or "")[:500], "entered_by": frappe.session.user})
    return {"written_to_goal": written}
