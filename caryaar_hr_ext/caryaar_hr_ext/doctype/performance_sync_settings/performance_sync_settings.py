import frappe
from frappe.model.document import Document

from caryaar_hr_ext.performance.rules import parse_department_sources


class PerformanceSyncSettings(Document):
    def validate(self):
        try:
            parse_department_sources(self.department_sources or "")
        except ValueError as e:
            frappe.throw(str(e))
