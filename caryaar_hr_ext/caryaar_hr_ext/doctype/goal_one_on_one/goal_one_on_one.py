import frappe
from frappe.model.document import Document

from caryaar_hr_ext.performance import one_on_one_rules as rules

ACK_FIELDS = ("employee_acknowledged", "acknowledged_on", "acknowledged_by")


def cycle_goal_rows(employee: str, cycle: str) -> list[dict]:
    """The goals table for one person and cycle: every non-group Goal with its KRA weight from the
    person's appraisal template, the meter's target and source, and the latest reading."""
    goals = frappe.get_all("Goal", filters={"employee": employee, "appraisal_cycle": cycle, "is_group": 0},
                           fields=["name", "goal_name", "kra"], order_by="creation asc")
    names = [g.name for g in goals]
    meters = {}
    for m in frappe.get_all("Goal Meter", filters={"goal": ("in", names)},
                            fields=["goal", "method", "metric", "target_value", "unit", "standard_value", "direction"]):
        meters[m.goal] = {"method": m.method, "metric": m.metric, "target": m.target_value, "unit": m.unit,
                          "standard": m.standard_value, "direction": m.direction}
    readings = {}
    for r in frappe.get_all("Goal Meter Reading", filters={"goal": ("in", names)},
                            fields=["goal", "progress", "value", "reading_date"], order_by="reading_date desc"):
        readings.setdefault(r.goal, {"progress": r.progress, "value": r.value})
    template = frappe.db.get_value("Appraisee", {"parent": cycle, "employee": employee}, "appraisal_template")
    weights = {t.key_result_area: float(t.per_weightage or 0) for t in frappe.get_all(
        "Appraisal Template Goal", filters={"parent": template}, fields=["key_result_area", "per_weightage"])} if template else {}
    return rules.goal_rows([dict(g) for g in goals], meters, readings, weights)


class GoalOneonOne(Document):   # Frappe looks for the doctype name without spaces, so the lowercase 'on' stays
    """One meeting between a manager and an employee about the cycle's goals. The acknowledgement
    fields are written only by performance.api.acknowledge_goals; the form cannot set them."""

    def validate(self):
        if not self.get("manager") and self.get("employee"):
            self.manager = frappe.db.get_value("Employee", self.employee, "reports_to")
        if not self.get("goals"):
            for row in cycle_goal_rows(self.employee, self.appraisal_cycle):
                self.append("goals", row)
        if not self.is_new():
            stored = frappe.db.get_value(self.doctype, self.name, list(ACK_FIELDS), as_dict=True) or {}
            for field in ACK_FIELDS:
                self.set(field, stored.get(field))

    @frappe.whitelist()
    def fill_goals(self) -> int:
        self.set("goals", [])
        for row in cycle_goal_rows(self.employee, self.appraisal_cycle):
            self.append("goals", row)
        return len(self.goals)
