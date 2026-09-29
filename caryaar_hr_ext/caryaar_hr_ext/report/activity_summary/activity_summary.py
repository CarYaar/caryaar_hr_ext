"""One row per person for a date range: Plane actions and items, and every CY Admin number
somebody in the range produced (calls, leads, bookings, jobs, campaigns, partner work, payouts).
Reads Work Activity Day; the pure shaping lives in performance/activity_summary.py."""
import frappe
from frappe.utils import get_first_day, getdate, nowdate

from caryaar_hr_ext.performance import activity_summary, rules


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start = getdate(filters.from_date or get_first_day(nowdate()))
    end = getdate(filters.to_date or nowdate())
    keys = rules.METRIC_KEYS["CY Admin"]
    sums = ", ".join(f"COALESCE(SUM(`{k}`), 0) AS `{k}`" for k in keys + ("activity_count", "completed_count"))
    conditions, params = ["activity_date BETWEEN %(start)s AND %(end)s"], {"start": start, "end": end}
    if filters.department:
        conditions.append("department = %(department)s")
        params["department"] = filters.department
    if filters.employee:
        conditions.append("employee = %(employee)s")
        params["employee"] = filters.employee
    rows = frappe.db.sql(f"""SELECT employee, employee_name, department, source, {sums}
                             FROM `tabWork Activity Day` WHERE {' AND '.join(conditions)}
                             GROUP BY employee, employee_name, department, source""", params, as_dict=True)
    columns, data = activity_summary.summarize([dict(r) for r in rows], keys)
    return columns, data
