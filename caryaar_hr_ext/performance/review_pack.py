"""Per-person review pack: goals with meters and readings, the Plane items counted,
adherence for the window, and what still needs a manual reading. One builder feeds
the Goal Review Pack report and the scheduled email (spec G9)."""
from __future__ import annotations

from datetime import date

import frappe
from frappe.utils import flt, getdate, nowdate

from caryaar_hr_ext.performance import meter_rules as mr, rules

TREND_STEP_DAYS = 15
MANUAL_STALE_DAYS = 30
CYCLE_START = date(2026, 10, 1)
TEMPLATE = "caryaar_hr_ext/templates/emails/review_pack.html"


def _readings(goal: str, as_of: date) -> list:
    return frappe.get_all("Goal Meter Reading", filters={"goal": goal, "reading_date": ("<=", as_of)},
                          fields=["reading_date", "value", "progress", "stale", "evidence", "method", "entered_by"],
                          order_by="reading_date asc")


def _trend(readings: list) -> list[tuple[str, float | None]]:
    out, last_day = [], None
    for r in readings:
        if last_day is None or (getdate(r.reading_date) - last_day).days >= TREND_STEP_DAYS:
            out.append((str(r.reading_date), r.progress))
            last_day = getdate(r.reading_date)
    if readings and out and out[-1][0] != str(readings[-1].reading_date):
        out.append((str(readings[-1].reading_date), readings[-1].progress))
    return out


def _items_for(module_raw, as_of: date) -> list[dict]:
    mid = rules.extract_module_id(module_raw)
    if not mid:
        return []
    rows = frappe.get_all("Plane Work Item", filters={"module_id": mid, "is_deleted": 0},
                          fields=["issue_id", "project_identifier", "sequence_id", "title", "assignee", "assignee_email",
                                  "state_group", "start_date", "target_date", "completed_at"], order_by="target_date asc")
    return [{**r, "overdue": mr.is_overdue(getdate(r.target_date) if r.target_date else None, r.state_group, as_of)}
            for r in rows]


def _weights(employee: str, cycle: str) -> dict[str, float]:
    appraisals = frappe.get_all("Appraisal", filters={"employee": employee, "appraisal_cycle": cycle,
                                                      "docstatus": ("<", 2)}, pluck="name")
    if not appraisals:
        return {}
    return {r.kra: flt(r.per_weightage) for r in frappe.get_all(
        "Appraisal KRA", filters={"parent": ("in", appraisals)}, fields=["kra", "per_weightage"])}


def build_pack(employee: str, cycle: str, as_of: date) -> dict:
    as_of = getdate(as_of)
    emp = frappe.db.get_value("Employee", employee, ["employee_name", "reports_to"], as_dict=True) or frappe._dict()
    weights = _weights(employee, cycle)
    goals, manual_missing, counted = [], [], set()
    for g in frappe.get_all("Goal", filters={"employee": employee, "appraisal_cycle": cycle, "is_group": 0,
                                             "status": ("!=", "Archived")},
                            fields=["name", "goal_name", "kra", "progress", "cy_plane_module"], order_by="kra asc"):
        gm = frappe.db.get_value("Goal Meter", g.name, ["method", "metric", "window", "target_value", "standard_value",
                                                        "unit", "direction", "active"], as_dict=True)
        readings = _readings(g.name, as_of)
        latest = readings[-1] if readings else None
        items = _items_for(g.cy_plane_module, as_of)
        counted |= {i["issue_id"] for i in items}
        if gm and gm.method == "Manual" and (not latest or (as_of - getdate(latest.reading_date)).days > MANUAL_STALE_DAYS):
            manual_missing.append(g.name)
        goals.append({"goal": g.name, "goal_name": g.goal_name, "kra": g.kra, "weight": weights.get(g.kra),
                      "method": gm.method if gm else "No meter", "metric": gm.metric if gm else None,
                      "target": gm.target_value if gm else None, "standard": gm.standard_value if gm else None,
                      "unit": gm.unit if gm else None, "value": latest.value if latest else None,
                      "progress": latest.progress if latest else None, "stale": bool(latest and latest.stale),
                      "erp_progress": flt(g.progress), "trend": _trend(readings), "items": items,
                      "evidence": latest.evidence if latest else None})
    # Judged days only: the engine stores 0 with checks_applicable = 0 for a day it has not
    # judged yet (today, a day the sources have not synced), the same filter the department
    # chart uses. Counting those would read as a false 0%.
    adh = frappe.get_all("Work Adherence Day", filters={"employee": employee, "is_working_day": 1,
                                                        "checks_applicable": (">", 0),
                                                        "adherence_date": ("between", [CYCLE_START, as_of])},
                         fields=["adherence_pct"])
    judged = [flt(a.adherence_pct) for a in adh]
    uncounted = frappe.db.count("Plane Work Item", {"assignee": employee, "is_deleted": 0,
                                                     "state_group": ("not in", ["cancelled", "completed"]),
                                                     "issue_id": ("not in", list(counted) or ["-"])})
    return {"employee": employee, "employee_name": emp.get("employee_name") or employee,
            "reports_to": emp.get("reports_to"), "cycle": cycle, "as_of": as_of.isoformat(),
            "learning_month": not mr.writes_progress(as_of), "goals": goals,
            "adherence": {"days": len(judged), "pct": round(sum(judged) / len(judged), 1) if judged else None},
            "uncounted_items": uncounted, "manual_missing": manual_missing}


def pack_rows(pack: dict) -> list[dict]:
    rows = []
    for g in pack["goals"]:
        flags = [f for f, on in (("stale", g["stale"]), ("no reading", g["progress"] is None)) if on]
        rows.append({"row_type": "goal", "goal": g["goal"], "text": g["goal_name"], "kra": g["kra"], "weight": g["weight"],
                     "method": g["method"], "target": g["target"], "value": g["value"], "progress": g["progress"],
                     "flags": ", ".join(flags)})
        for i in g["items"]:
            done = f" done {getdate(i['completed_at']).strftime('%d-%b-%Y')}" if i["completed_at"] else ""
            rows.append({"row_type": "item", "goal": g["goal"],
                         "text": f"{i['project_identifier']}-{i['sequence_id']} {i['title']}", "kra": "",
                         "weight": None, "method": i["state_group"], "target": i["target_date"], "value": None,
                         "progress": None, "flags": ("overdue" if i["overdue"] else "") + done})
    return rows


def _recipients(pack: dict) -> list[str]:
    manager = frappe.db.get_value("Employee", pack["reports_to"], "user_id") if pack.get("reports_to") else None
    return mr.recipients(frappe.db.get_single_value("Performance Sync Settings", "review_pack_recipients"), manager)


def send_pack(employee: str, cycle: str, as_of: date) -> list[str]:
    """Builds and queues one person's pack. Returns the recipients; an empty list means it was
    not sent (nobody to send to) and an Error Log entry says so."""
    as_of = getdate(as_of)
    pack = build_pack(employee, cycle, as_of)
    recipients = _recipients(pack)
    if not recipients:
        frappe.log_error(title=f"Review pack: no recipients for {employee}",
                         message="No manager (Employee.reports_to) and Performance Sync Settings has no "
                                 "review pack recipients. Nothing was sent.")
        return []
    html = frappe.render_template(TEMPLATE, {"pack": pack, "rows": pack_rows(pack)})
    frappe.sendmail(recipients=recipients,
                    subject=f"Review pack: {pack['employee_name']}, {as_of.strftime('%d-%b-%Y')}",
                    message=html, now=False)
    return recipients


def _appraisees(cycle: str) -> list[str]:
    """Employees in the cycle: HRMS v16 keeps them in the child doctype "Appraisee"."""
    return frappe.get_all("Appraisee", filters={"parent": cycle, "parenttype": "Appraisal Cycle"}, pluck="employee")


def send_scheduled_packs() -> dict:
    """08:00 IST daily (hooks.py): sends on the 1st and 15th, and 3 days before an appraisal's review date."""
    as_of = getdate(nowdate())
    sent, skipped = 0, 0
    for cycle in frappe.get_all("Appraisal Cycle", filters={"status": ("in", ["Not Started", "In Progress"]),
                                                             "start_date": ("<=", as_of)}, pluck="name"):
        for employee in _appraisees(cycle):
            review_dates = [getdate(d) for d in frappe.get_all(
                "Appraisal", {"employee": employee, "appraisal_cycle": cycle, "cy_next_review_on": ("is", "set")},
                pluck="cy_next_review_on")]
            if frappe.db.get_value("Employee", employee, "status") != "Active":
                continue
            if not mr.pack_due_today(as_of, review_dates):
                continue
            try:
                if send_pack(employee, cycle, as_of):
                    sent += 1
                else:
                    skipped += 1
            except Exception:
                frappe.log_error(title=f"Review pack: {employee}", message=frappe.get_traceback())
                skipped += 1
    return {"sent": sent, "skipped": skipped, "as_of": as_of.isoformat()}
