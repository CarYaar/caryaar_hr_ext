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
