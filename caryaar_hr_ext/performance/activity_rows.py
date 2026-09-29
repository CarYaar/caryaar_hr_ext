"""The one query behind the Activity Summary report and the Activity board: Work Activity Day rows,
one per person, source and day, with the Employee designation as the role."""
import frappe

from caryaar_hr_ext.performance import rules


def day_rows(start, end, department: str | None = None, employee: str | None = None) -> list[dict]:
    keys = rules.METRIC_KEYS["CY Admin"]
    cols = ", ".join(f"w.`{k}`" for k in keys + ("activity_count", "completed_count"))
    conditions, params = ["w.activity_date BETWEEN %(start)s AND %(end)s"], {"start": start, "end": end}
    if department:
        conditions.append("w.department = %(department)s")
        params["department"] = department
    if employee:
        conditions.append("w.employee = %(employee)s")
        params["employee"] = employee
    rows = frappe.db.sql(f"""SELECT w.employee, w.employee_name, w.department, w.source, w.activity_date,
                                    e.designation AS role, {cols}
                             FROM `tabWork Activity Day` w LEFT JOIN `tabEmployee` e ON e.name = w.employee
                             WHERE {' AND '.join(conditions)}""", params, as_dict=True)
    return [dict(r) for r in rows]
