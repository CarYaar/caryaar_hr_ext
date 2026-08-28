import frappe
from frappe.model.document import Document


class InternshipCertificate(Document):
    def validate(self):
        if self.start_date and self.end_date and self.start_date > self.end_date:
            frappe.throw("Start date cannot be after end date.")
