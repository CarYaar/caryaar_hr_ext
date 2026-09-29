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
    """Live items only: a deleted item is gone, an archived one is finished work and still counts."""
    return frappe.get_all("Plane Work Item", filters={"is_deleted": 0, **filters},
                          fields=["name", "state_group", "target_date", "completed_at", "created_at", "labels", "module_id"])


def _items_in_module(mid: str) -> list:
    """Every live item that belongs to the module, whatever other modules it is also in
    (module_ids is the comma list of all memberships)."""
    return _items(module_ids=("like", f"%{mid}%"))


def _labels(item) -> set[str]:
    return rules.parse_labels(item.labels)


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
    items = [i for i in _items_in_module(mid) if i.state_group != "cancelled"]
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
    items = [i for i in _items_in_module(mid) if i.state_group != "cancelled" and i.target_date] if mid else []
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
    """Pages the person created in the window, plus pages they saved a version of in it.
    Counting by last editor would let a colleague's typo fix take a page away."""
    user = frappe.db.get_value("Employee", ctx.employee, "user_id")
    if not user:
        return None
    window = ("between", [ctx.window_from, ctx.window_to])
    pages = set(frappe.get_all("Wiki Page", filters={"owner": user, "creation": window}, pluck="name"))
    pages |= set(frappe.get_all("Version", filters={"ref_doctype": "Wiki Page", "owner": user, "creation": window},
                                pluck="docname"))
    return len(pages)


# ─── role metrics (29-Sep-2026): every role measured on its own CY Admin work ─────

def m_jobs_from_bookings(ctx):
    """An agent's achievement is the job created from her booking (founder, 29-Sep-2026)."""
    return _sum_metric(ctx, "jobs_from_bookings")


def m_bookings_to_jobs_pct(ctx):
    return mr.pct(_sum_metric(ctx, "jobs_from_bookings"), _sum_metric(ctx, "bookings_credited"))


def m_calls_to_bookings_pct(ctx):
    return mr.pct(_sum_metric(ctx, "bookings_credited"), _sum_metric(ctx, "calls_answered"))


def m_campaigns_sent(ctx):
    return _sum_metric(ctx, "campaigns_sent")


def m_campaign_leads_reached(ctx):
    return _sum_metric(ctx, "campaign_leads_reached")


def m_creatives_approved(ctx):
    return _sum_metric(ctx, "creatives_approved")


def m_leads_from_channels(ctx):
    """The team's new leads by channel; a goal on it belongs to the marketing lead."""
    return sum(_sum_metric(ctx, k) for k in ("leads_meta", "leads_google", "leads_whatsapp", "leads_web"))


def m_jobs_moved(ctx):
    return _sum_metric(ctx, "jobs_moved")


def m_sweep_items_closed(ctx):
    """Stuck-delivery items the system raised and the coordinator closed."""
    return _sum_metric(ctx, "sweep_items_closed")


def m_partner_changes(ctx):
    return _sum_metric(ctx, "partner_changes")


def m_partners_activated(ctx):
    return _sum_metric(ctx, "partners_activated")


def m_agreements_signed(ctx):
    return _sum_metric(ctx, "agreements_signed")


def m_payouts_triggered(ctx):
    return _sum_metric(ctx, "payouts_triggered")


def m_unpaid_cleared(ctx):
    return _sum_metric(ctx, "unpaid_cleared")


METRICS: dict[str, Callable[[MeterContext], float | None]] = {
    "conversion_pct": m_conversion_pct, "followups_on_time_pct": m_followups_on_time_pct,
    "leads_statused_48h_pct": m_leads_statused_48h_pct, "module_completion": m_module_completion,
    "incidents_fixed_24h_pct": m_incidents_fixed_24h_pct, "support_on_time_pct": m_support_on_time_pct,
    "release_bugs_14d": m_release_bugs_14d, "wiki_pages": m_wiki_pages,
    "jobs_from_bookings": m_jobs_from_bookings, "bookings_to_jobs_pct": m_bookings_to_jobs_pct,
    "calls_to_bookings_pct": m_calls_to_bookings_pct, "campaigns_sent": m_campaigns_sent,
    "campaign_leads_reached": m_campaign_leads_reached, "creatives_approved": m_creatives_approved,
    "leads_from_channels": m_leads_from_channels, "jobs_moved": m_jobs_moved,
    "sweep_items_closed": m_sweep_items_closed, "partner_changes": m_partner_changes,
    "partners_activated": m_partners_activated, "agreements_signed": m_agreements_signed,
    "payouts_triggered": m_payouts_triggered, "unpaid_cleared": m_unpaid_cleared,
}
_SOURCE_OF = mr.SOURCE_OF
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


def live_cycles(as_of: date, *, started_only: bool = False) -> list[str]:
    """Cycles the meter, the setup, the packs and the person's view agree on (meter_rules.cycle_is_live)."""
    rows = frappe.get_all("Appraisal Cycle", filters={"status": ("in", ["Not Started", "In Progress"])},
                          fields=["name", "status", "start_date", "end_date"])
    return [r.name for r in rows
            if mr.cycle_is_live(r.status, getdate(r.start_date) if r.start_date else None,
                                getdate(r.end_date) if r.end_date else None, as_of, started_only=started_only)]


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


def _apply_progress(goal: str, progress, as_of: date, stale: bool) -> tuple[bool, bool]:
    """Goal.progress from a reading: only past the 01-Nov gate, only when fresh. Returns
    (applied, changed): applied means the gate let the reading through and it counts as
    written to the goal; changed means Goal.progress actually moved (a delta under 0.5 is
    not saved, so HRMS does not re-run its hooks for nothing)."""
    if not mr.writes_progress(as_of) or progress is None or stale:
        return False, False
    current = flt(frappe.db.get_value("Goal", goal, "progress"))
    if abs(flt(progress) - current) < 0.5:
        return True, False
    doc = frappe.get_doc("Goal", goal)
    doc.progress = flt(progress)
    doc.save(ignore_permissions=True)
    return True, True


def _write_reading(gm, as_of: date, reading: dict) -> bool:
    """Store an automatic reading; Goal.progress follows it under the gate."""
    name = f"{gm.goal}|{as_of}"
    values = {"value": reading["value"], "progress": reading["progress"], "method": reading["method"],
              "stale": 1 if reading["stale"] else 0, "computed_at": now_datetime()}
    if frappe.db.exists("Goal Meter Reading", name):
        frappe.db.set_value("Goal Meter Reading", name, values)
    else:
        frappe.get_doc({"doctype": "Goal Meter Reading", "goal": gm.goal, "reading_date": as_of, **values}
                       ).insert(ignore_permissions=True)
    applied, changed = _apply_progress(gm.goal, reading["progress"], as_of, reading["stale"])
    if applied:
        frappe.db.set_value("Goal Meter Reading", name, "written_to_goal", 1)
    return changed


def _apply_latest_manual(gm, as_of: date) -> tuple[bool, bool]:
    """A Manual meter has no nightly reading: the newest reading entered by hand on or before
    as_of reaches Goal.progress once the gate is open. Returns (has_reading, changed); a
    reading already written is left alone, so October's entry is applied once on 01-Nov."""
    rows = frappe.get_all("Goal Meter Reading", filters={"goal": gm.goal, "reading_date": ("<=", as_of)},
                          fields=["name", "progress", "written_to_goal"], order_by="reading_date desc", limit=1)
    if not rows:
        return False, False
    r = rows[0]
    if r.written_to_goal:
        return True, False
    applied, changed = _apply_progress(gm.goal, r.progress, as_of, stale=False)
    if applied:
        frappe.db.set_value("Goal Meter Reading", r.name, "written_to_goal", 1)
    return True, changed


def apply_manual_reading(reading) -> bool:
    """Goal Meter Reading.on_update: a reading entered by hand (desk or write_manual_reading)
    for a Manual meter reaches Goal.progress at once when the gate is open; before 01-Nov it
    is shown, not written, and the nightly job applies it on the first night of November."""
    if reading.get("written_to_goal") or frappe.db.get_value("Goal Meter", reading.goal, "method") != "Manual":
        return False
    applied, changed = _apply_progress(reading.goal, reading.get("progress"), getdate(nowdate()), stale=False)
    if applied:
        frappe.db.set_value("Goal Meter Reading", reading.name, "written_to_goal", 1)
    return changed


def run_meter(as_of: date | None = None) -> dict:
    """One pass over every active meter whose goal's cycle is Not Started or In Progress
    and whose employee is Active. Called by engine.run_nightly and on demand (a string
    date from bench execute is accepted)."""
    as_of = getdate(as_of) if as_of else getdate(nowdate())
    counts = {"readings": 0, "written": 0, "stale": 0, "skipped": 0, "manual": 0, "no_value": 0}
    cycles = live_cycles(as_of)
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
            if gm.method == "Manual":
                has_reading, changed = _apply_latest_manual(gm, as_of)
                counts["manual"] += 1 if has_reading else 0
                counts["written"] += 1 if changed else 0
                counts["skipped"] += 0 if has_reading else 1
                continue
            reading = compute_reading(gm, as_of)
            if reading is None:
                counts["skipped"] += 1
                continue
            if reading["value"] is None and reading["progress"] is None:
                # Nothing to record yet (no module, no rows in the window). A Float stored as
                # None reads back as 0.0 in Frappe, which the pack would show as 0%: write nothing.
                counts["no_value"] += 1
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


def _is_own_goal(employee: str) -> bool:
    mine = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")
    return bool(mine) and mine == employee


@frappe.whitelist(methods=["POST"])
def write_manual_reading(goal: str, progress: float, evidence: str = "") -> dict:
    """A manager's reading for a Manual meter (spec G7): evidence required, never for one's
    own goal, and only where the user may write the Goal itself (User Permissions apply).
    The reading is saved through the document, so on_update writes Goal.progress under the gate."""
    frappe.only_for(("HR Manager", "HR User", "System Manager"))
    gm = frappe.db.get_value("Goal Meter", goal, ["method", "active", "employee"], as_dict=True)
    if not gm:
        frappe.throw("No meter for this goal.")
    problem = mr.manual_reading_problem(gm.method, gm.active, evidence, _is_own_goal(gm.employee))
    if problem:
        frappe.throw(problem)
    frappe.has_permission("Goal", "write", doc=goal, throw=True)
    as_of = getdate(nowdate())
    name = f"{goal}|{as_of}"
    values = {"value": flt(progress), "progress": max(0.0, min(100.0, flt(progress))), "method": "Manual",
              "stale": 0, "evidence": (evidence or "")[:500], "entered_by": frappe.session.user,
              "computed_at": now_datetime()}
    if frappe.db.exists("Goal Meter Reading", name):
        doc = frappe.get_doc("Goal Meter Reading", name)
        doc.update(values)
        doc.save(ignore_permissions=True)
    else:
        frappe.get_doc({"doctype": "Goal Meter Reading", "goal": goal, "reading_date": as_of, **values}
                       ).insert(ignore_permissions=True)
    return {"written_to_goal": bool(frappe.db.get_value("Goal Meter Reading", name, "written_to_goal"))}
