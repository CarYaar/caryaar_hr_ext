import frappe
from frappe.model.document import Document

from caryaar_hr_ext.performance import one_on_one_rules as rules

ACK_FIELDS = ("employee_acknowledged", "acknowledged_on", "acknowledged_by")
HR = {"HR Manager", "System Manager"}
FROZEN_AFTER_ACK = ("employee", "manager", "appraisal_cycle", "meeting_date", "meeting_type")


def cycle_goal_rows(employee: str, cycle: str) -> list[dict]:
    """The goals table for one person and cycle: every live, non-group Goal with its KRA weight from
    the person's appraisal template, the meter's target and source, and the latest reading."""
    goals = frappe.get_all("Goal", filters={"employee": employee, "appraisal_cycle": cycle, "is_group": 0, "status": ("!=", "Archived")},
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


def _is_hr() -> bool:
    return bool(set(frappe.get_roles(frappe.session.user)) & HR)


class GoalOneonOne(Document):   # Frappe looks for the doctype name without spaces, so the lowercase 'on' stays
    """One meeting between a manager and an employee about the cycle's goals. The acknowledgement
    fields are written only by performance.api.acknowledge_goals: a new record always starts
    unacknowledged, and a saved record keeps what the database holds. Once acknowledged, the goals
    and the meeting facts are frozen for everyone but HR, so the record proves what was agreed."""

    def validate(self):
        if self.is_new():
            self.employee_acknowledged, self.acknowledged_on, self.acknowledged_by = 0, None, None
        else:
            stored = frappe.db.get_value(self.doctype, self.name, list(ACK_FIELDS) + list(FROZEN_AFTER_ACK), as_dict=True) or {}
            for field in ACK_FIELDS:
                self.set(field, stored.get(field))
            if not _is_hr():
                if stored.get("manager") and self.get("manager") != stored.get("manager"):
                    frappe.throw("Only HR can change the manager on a 1:1 record.")
                if stored.get("employee_acknowledged"):
                    changed = [f for f in FROZEN_AFTER_ACK if str(self.get(f) or "") != str(stored.get(f) or "")]
                    if changed or self._goals_changed():
                        frappe.throw("These goals were acknowledged by the employee; only HR can change the goals or the meeting facts now.")
        if not self.get("manager") and self.get("employee"):
            self.manager = frappe.db.get_value("Employee", self.employee, "reports_to")
            if self.manager:
                self.manager_name = frappe.db.get_value("Employee", self.manager, "employee_name")
                self.manager_user = frappe.db.get_value("Employee", self.manager, "user_id")
        if not self.get("goals"):
            for row in cycle_goal_rows(self.employee, self.appraisal_cycle):
                self.append("goals", row)

    def _goals_changed(self) -> bool:
        stored = sorted(r.goal for r in frappe.get_all("Goal One on One Goal", filters={"parent": self.name}, fields=["goal"]))
        return sorted((g.get("goal") if isinstance(g, dict) else g.goal) or "" for g in (self.get("goals") or [])) != stored

    @frappe.whitelist()
    def fill_goals(self) -> int:
        frappe.has_permission(self.doctype, "write", self.name, throw=True)
        self.set("goals", [])
        for row in cycle_goal_rows(self.employee, self.appraisal_cycle):
            self.append("goals", row)
        return len(self.goals)
