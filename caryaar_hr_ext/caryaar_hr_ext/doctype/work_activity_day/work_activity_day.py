from frappe.model.document import Document

from caryaar_hr_ext.performance.rules import activity_doc_name


class WorkActivityDay(Document):
    def autoname(self):
        self.name = activity_doc_name(self.employee, str(self.activity_date), self.source)
