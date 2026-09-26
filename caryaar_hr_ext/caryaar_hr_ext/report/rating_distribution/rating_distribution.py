"""Company-wide rating spread for one appraisal cycle, next to the handbook's guide (spec D5)."""
from collections import Counter

GUIDE = (("Exceptional", 5), ("Excellent", 15), ("Good", 25), ("Fair", 50), ("Non-Satisfactory", 5))


def execute(filters=None):
    import frappe  # imported here so the GUIDE constant is testable without Frappe

    filters = filters or {}
    cycle = filters.get("appraisal_cycle")
    if not cycle:
        frappe.throw("Choose an appraisal cycle.")
    counts = Counter(frappe.get_all(
        "Appraisal", filters={"appraisal_cycle": cycle, "docstatus": ("<", 2),
                              "cy_performance_category": ("is", "set")},
        pluck="cy_performance_category"))
    total = sum(counts.values())
    columns = [
        {"fieldname": "category", "label": "Category", "fieldtype": "Data", "width": 170},
        {"fieldname": "people", "label": "People", "fieldtype": "Int", "width": 90},
        {"fieldname": "actual", "label": "Actual %", "fieldtype": "Percent", "width": 110},
        {"fieldname": "guide", "label": "Guide %", "fieldtype": "Percent", "width": 110},
    ]
    data = [{"category": c, "people": counts.get(c, 0),
             "actual": round(100.0 * counts.get(c, 0) / total, 1) if total else 0, "guide": g}
            for c, g in GUIDE]
    return columns, data
