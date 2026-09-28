import frappe
from frappe.model.document import Document


class GoalMeterReading(Document):
    """One reading per goal per day. Automatic meters insert these nightly; a Manual meter's
    reading is entered here (or through meter.write_manual_reading) and reaches Goal.progress
    through on_update, under the same 01-Nov gate as every other reading."""

    def autoname(self):
        self.name = f"{self.goal}|{self.reading_date}"

    def validate(self):
        if self.get("progress") is not None and not 0 <= float(self.progress) <= 100:
            frappe.throw("Progress must be between 0 and 100.")
        if self.get("method") == "Manual" and not self.get("entered_by"):
            self.entered_by = frappe.session.user

    def on_update(self):
        from caryaar_hr_ext.performance import meter

        meter.apply_manual_reading(self)
