"""One person's goals, meters, readings and the Plane items counted, as of a date.
The same builder feeds the scheduled email (performance/review_pack.py)."""
import frappe
from frappe.utils import getdate, nowdate

from caryaar_hr_ext.performance.review_pack import build_pack, pack_rows


def execute(filters=None):
    filters = frappe._dict(filters or {})
    pack = build_pack(filters.employee, filters.appraisal_cycle, getdate(filters.as_of or nowdate()))
    columns = [
        {"fieldname": "row_type", "label": "Row", "fieldtype": "Data", "width": 60},
        {"fieldname": "text", "label": "Goal / item", "fieldtype": "Data", "width": 420},
        {"fieldname": "kra", "label": "KRA", "fieldtype": "Data", "width": 220},
        {"fieldname": "weight", "label": "Weight %", "fieldtype": "Float", "width": 80},
        {"fieldname": "method", "label": "Method / state", "fieldtype": "Data", "width": 160},
        {"fieldname": "target", "label": "Target / due", "fieldtype": "Data", "width": 120},
        {"fieldname": "value", "label": "Value", "fieldtype": "Float", "width": 90},
        {"fieldname": "progress", "label": "Progress %", "fieldtype": "Percent", "width": 100},
        {"fieldname": "flags", "label": "Flags", "fieldtype": "Data", "width": 200},
    ]
    summary = [
        {"value": pack["adherence"]["pct"], "label": "Adherence % (working days)", "datatype": "Percent"},
        {"value": pack["uncounted_items"], "label": "Plane items not tied to a goal", "datatype": "Int"},
        {"value": len(pack["manual_missing"]), "label": "Manual goals needing a reading", "datatype": "Int"},
    ]
    return columns, pack_rows(pack), None, None, summary
