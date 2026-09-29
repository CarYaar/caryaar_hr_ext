import frappe
from frappe.model.document import Document

from caryaar_hr_ext.performance import meter_rules as mr


class GoalMeter(Document):
    """How one goal is measured. A metric key the meter does not know would save fine and then
    produce no reading, forever, so it is refused here with the list HR can pick from."""

    def validate(self):
        if self.get("method") not in ("Ratio to target", "Months meeting standard"):
            return
        key = (self.get("metric") or "").strip()
        if key not in mr.SOURCE_OF:
            frappe.throw(f"Unknown metric key '{key}'. Use one of: {mr.metric_keys_text()}.")
        template = _template_of(self.get("employee"), frappe.db.get_value("Goal", self.get("goal"), "appraisal_cycle"))
        if template and not mr.source_fits_role(template, key):
            frappe.msgprint(f"{key} is measured from {mr.SOURCE_OF[key]}, which is not in the precedence for {template} "
                            f"({', '.join(mr.role_sources()[template])}). Saved anyway; check this is intended.")


def _template_of(employee, cycle):
    if not employee or not cycle:
        return None
    return frappe.db.get_value("Appraisee", {"parent": cycle, "employee": employee}, "appraisal_template")
