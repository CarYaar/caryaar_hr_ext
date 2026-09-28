"""Nightly performance engine (scheduled at 23:30 IST in hooks.py).

For each active employee and each of the last four days: builds a DayContext
from attendance, WFH requests, holidays and synced activity, then stores the
rules.adherence_day result as a Work Adherence Day. Afterwards runs the goal
meter (performance/meter.py) and updates appraisal rating categories. Every unit of
work is fail-soft: an error is logged and the run continues.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import frappe
from frappe.utils import flt, get_datetime, getdate, nowdate

from caryaar_hr_ext.performance import meter, rules

_SYNC_FIELD = {"Plane": "plane_synced_through", "CY Admin": "cy_admin_synced_through"}
_YES_NO = {True: "Yes", False: "No", None: ""}
DAYS_BACK = 4


def run_nightly() -> None:
    today = getdate(nowdate())
    for i in range(DAYS_BACK):
        _guard(f"adherence {today - timedelta(days=i)}", run_day, today - timedelta(days=i))
    _guard("goal meter", meter.run_meter)
    _guard("performance categories", update_performance_categories)


def _guard(label: str, fn, *args):
    try:
        out = fn(*args)
        frappe.db.commit()
        return out
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title=f"Performance engine: {label}", message=frappe.get_traceback())
        frappe.db.set_single_value("Performance Sync Settings", "last_error",
                                   f"{frappe.utils.now()} {label} failed; see Error Log")
        frappe.db.commit()
        return None


def _fresh_sources(settings, day: date) -> frozenset[str]:
    end = datetime.combine(day, time(23, 59, 59))
    return frozenset(src for src, field in _SYNC_FIELD.items()
                     if settings.get(field) and get_datetime(settings.get(field)) >= end)


def _holiday_list(emp, day: date) -> str | None:
    # HRMS 16 resolves holidays through dated Holiday List Assignments (via the
    # employee_holiday_list hook); ERPNext's resolver routes there. As of `day`,
    # not today, so a recompute of an old day uses the list that applied then.
    from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

    return get_holiday_list_for_employee(emp.name, raise_exception=False, as_on=day)


def _context(emp, day: date, dept_sources: dict, fresh: frozenset[str]) -> rules.DayContext:
    hl = _holiday_list(emp, day)
    is_holiday = bool(hl and frappe.db.exists("Holiday", {"parent": hl, "holiday_date": day}))
    status = frappe.db.get_value("Attendance", {"employee": emp.name, "attendance_date": day,
                                                "docstatus": 1}, "status")
    reqs = frappe.get_all("Attendance Request",
                          filters={"employee": emp.name, "reason": "Work From Home",
                                   "from_date": ("<=", day), "to_date": (">=", day),
                                   "workflow_state": ("in", ["Pending", "Approved"])},
                          fields=["docstatus"])
    fields = ["source", *rules.METRIC_KEYS["Plane"], *rules.METRIC_KEYS["CY Admin"]]
    activity = {r.source: {k: int(r.get(k) or 0) for k in fields if k != "source"}
                for r in frappe.get_all("Work Activity Day",
                                        filters={"employee": emp.name, "activity_date": day}, fields=fields)}
    return rules.DayContext(
        is_holiday=is_holiday, attendance_status=status,
        expected_sources=tuple(dept_sources.get(emp.department or "", ["Plane"])),
        fresh_sources=fresh, activity=activity,
        wfh_requested=bool(reqs), wfh_approved=any(r.docstatus == 1 for r in reqs))


def run_day(day: date) -> int:
    settings = frappe.get_single("Performance Sync Settings")
    dept_sources = rules.parse_department_sources(settings.department_sources or "")
    fresh = _fresh_sources(settings, day)
    written = 0
    for emp in frappe.get_all("Employee", filters={"status": "Active"},
                              fields=["name", "department", "holiday_list", "company", "date_of_joining"]):
        if emp.date_of_joining and getdate(emp.date_of_joining) > day:
            continue
        try:
            ctx = _context(emp, day, dept_sources, fresh)
            res = rules.adherence_day(ctx)
            values = {"is_working_day": int(res.is_working_day), "attendance_status": ctx.attendance_status or "",
                      "expected_sources": ", ".join(ctx.expected_sources), "wfh": int(res.wfh),
                      "work_visible": _YES_NO[res.work_visible], "wfh_approved": _YES_NO[res.wfh_approved],
                      "wfh_evidenced": _YES_NO[res.wfh_evidenced], "checks_passed": res.checks_passed,
                      "checks_applicable": res.checks_applicable, "adherence_pct": res.adherence_pct or 0}
            name = rules.adherence_doc_name(emp.name, day.isoformat())
            if frappe.db.exists("Work Adherence Day", name):
                frappe.db.set_value("Work Adherence Day", name, values)
            else:
                frappe.get_doc({"doctype": "Work Adherence Day", "employee": emp.name,
                                "adherence_date": day, **values}).insert(ignore_permissions=True)
            written += 1
        except Exception:
            frappe.log_error(title=f"Performance engine: adherence {emp.name} {day}",
                             message=frappe.get_traceback())
    return written


def update_performance_categories() -> int:
    """Store the rating category only on submitted appraisals, and never on the founders'
    scorecard (D4). Mid-cycle scores are provisional; the Rating Distribution report shows
    them live to HR instead."""
    changed = 0
    for a in frappe.get_all("Appraisal", filters={"docstatus": ("<", 2)},
                            fields=["name", "docstatus", "final_score", "appraisal_template",
                                    "cy_performance_category"]):
        cat = rules.stored_category(a.docstatus, flt(a.final_score), a.appraisal_template)
        if cat != (a.cy_performance_category or ""):
            frappe.db.set_value("Appraisal", a.name, "cy_performance_category", cat, update_modified=False)
            changed += 1
    return changed
