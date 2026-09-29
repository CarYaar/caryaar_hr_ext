"""One row per person, department or role for a period: Plane actions and items, and every CY Admin
number somebody in the range produced (calls, leads, bookings, jobs, campaigns, partner work, payouts).
Reads Work Activity Day day by day through performance/activity_rows.py; the pure shaping lives in
performance/activity_summary.py and performance/activity_groups.py."""
import frappe
from frappe.utils import getdate, nowdate

from caryaar_hr_ext.performance import activity_groups, activity_rows, activity_summary, rules

GROUP_BY = {"Person": "person", "Department": "department", "Role": "role"}


def execute(filters=None):
    filters = frappe._dict(filters or {})
    start, end = activity_groups.period_bounds(filters.period, getdate(nowdate()),
                                               getdate(filters.from_date) if filters.from_date else None,
                                               getdate(filters.to_date) if filters.to_date else None)
    rows = activity_rows.day_rows(start, end, filters.department, filters.employee)
    return activity_summary.summarize(rows, rules.METRIC_KEYS["CY Admin"], by=GROUP_BY.get(filters.group_by, "person"))
