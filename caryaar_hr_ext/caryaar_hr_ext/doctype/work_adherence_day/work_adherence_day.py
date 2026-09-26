from frappe.model.document import Document

from caryaar_hr_ext.performance.rules import adherence_doc_name


class WorkAdherenceDay(Document):
    def autoname(self):
        self.name = adherence_doc_name(self.employee, str(self.adherence_date))
