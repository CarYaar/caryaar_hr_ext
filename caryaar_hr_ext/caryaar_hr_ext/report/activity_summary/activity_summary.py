"""One row per person, department or role for a period: Plane actions and items, and every CY Admin
number somebody in the range produced (calls, leads, bookings, jobs, campaigns, partner work, payouts).
Reads Work Activity Day day by day, with the Employee designation as the role; the pure shaping lives
in performance/activity_summary.py and performance/activity_groups.py."""
import frappe
from frappe.utils import getdate, nowdate

from caryaar_hr_ext.performance import activity_groups, activity_summary, rules

GROUP_BY = {"Person": "person", "Department": "department", "Role": "role"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = activity_groups.period_bounds(filters.period, getdate(nowdate()),
                                               getdate(filters.from_date) if filters.from_date else None,
                                               getdate(filters.to_date) if filters.to_date else None)
    keys = rules.METRIC_KEYS["CY Admin"]
    cols = ", ".join(f"w.`{k}`" for k in keys + ("activity_count", "completed_count"))
    conditions, params = ["w.activity_date BETWEEN %(start)s AND %(end)s"], {"start": start, "end": end}
    if filters.department:
        conditions.append("w.department = %(department)s")
        params["department"] = filters.department
    if filters.employee:
        conditions.append("w.employee = %(employee)s")
        params["employee"] = filters.employee
    rows = frappe.db.sql(f"""SELECT w.employee, w.employee_name, w.department, w.source, w.activity_date,
                                    e.designation AS role, {cols}
                             FROM `tabWork Activity Day` w LEFT JOIN `tabEmployee` e ON e.name = w.employee
                             WHERE {' AND '.join(conditions)}""", params, as_dict=True)
    return activity_summary.summarize([dict(r) for r in rows], keys, by=GROUP_BY.get(filters.group_by, "person"))
