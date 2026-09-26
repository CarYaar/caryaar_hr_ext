"""Company-wide rating spread for one appraisal cycle, next to the handbook's guide (spec D5).

Categories are computed live from each appraisal's current final score, so HR can
see the provisional spread mid-cycle; the stored Appraisal category is only set
once an appraisal is submitted (performance/engine.py).
"""
from collections import Counter

from caryaar_hr_ext.performance.rules import performance_category

GUIDE = (("Exceptional", 5), ("Excellent", 15), ("Good", 25), ("Fair", 50), ("Non-Satisfactory", 5))


def distribution(scores) -> list[dict]:
    counts = Counter(c for c in (performance_category(s) for s in scores) if c)
    total = sum(counts.values())
    return [{"category": c, "people": counts.get(c, 0),
             "actual": round(100.0 * counts.get(c, 0) / total, 1) if total else 0, "guide": g}
            for c, g in GUIDE]


def execute(filters=None):
    import frappe  # imported here so distribution() and GUIDE are testable without Frappe

    filters = filters or {}
    cycle = filters.get("appraisal_cycle")
    if not cycle:
        frappe.throw("Choose an appraisal cycle.")
    scores = frappe.get_all("Appraisal", filters={"appraisal_cycle": cycle, "docstatus": ("<", 2)},
                            pluck="final_score")
    columns = [
        {"fieldname": "category", "label": "Category", "fieldtype": "Data", "width": 170},
        {"fieldname": "people", "label": "People", "fieldtype": "Int", "width": 90},
        {"fieldname": "actual", "label": "Actual %", "fieldtype": "Percent", "width": 110},
        {"fieldname": "guide", "label": "Guide %", "fieldtype": "Percent", "width": 110},
    ]
    return columns, distribution(scores)
