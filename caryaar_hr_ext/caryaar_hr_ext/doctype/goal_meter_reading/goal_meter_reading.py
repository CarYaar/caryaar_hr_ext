import frappe
from frappe.model.document import Document


class GoalMeterReading(Document):
    def autoname(self):
        self.name = f"{self.goal}|{self.reading_date}"

    def validate(self):
        if self.progress is not None and not 0 <= float(self.progress) <= 100:
            frappe.throw("Progress must be between 0 and 100.")
