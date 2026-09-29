"""Dashboard chart source: one department's numbers for a period, as a bar per metric. The chart's
filters are department and period; the metrics a department is read by live in
performance/activity_groups.py so adding one is a one-line change there."""
import frappe
from frappe.utils import getdate, nowdate
from frappe.utils.dashboard import cache_source

from caryaar_hr_ext.performance import activity_groups


@frappe.whitelist()
@cache_source
def get(chart_name=None, chart=None, no_cache=None, filters=None, from_date=None, to_date=None,
        timespan=None, time_interval=None, heatmap_year=None):
    chart = frappe.get_doc("Dashboard Chart", chart_name) if chart_name else frappe._dict(frappe.parse_json(chart))
    f = frappe._dict(frappe.parse_json(filters) or frappe.parse_json(chart.filters_json) or {})
    start, end = activity_groups.period_bounds(f.period, getdate(nowdate()),
                                               getdate(f.from_date) if f.from_date else None,
                                               getdate(f.to_date) if f.to_date else None)
    keys = tuple(k for k in activity_groups.metrics_for(f.department) if k not in activity_groups.PLANE_KEYS)
    cols = ", ".join(f"`{k}`" for k in keys + ("activity_count", "completed_count"))
    conditions, params = ["activity_date BETWEEN %(start)s AND %(end)s"], {"start": start, "end": end}
    if f.department:
        conditions.append("department = %(department)s")
        params["department"] = f.department
    rows = frappe.db.sql(f"""SELECT employee, department, source, activity_date, {cols}
                             FROM `tabWork Activity Day` WHERE {' AND '.join(conditions)}""", params, as_dict=True)
    return activity_groups.department_chart(f.department, [dict(r) for r in rows])
