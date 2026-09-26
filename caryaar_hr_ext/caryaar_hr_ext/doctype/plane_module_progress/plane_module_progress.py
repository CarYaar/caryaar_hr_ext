from frappe.model.document import Document

from caryaar_hr_ext.performance.rules import module_progress


class PlaneModuleProgress(Document):
    def validate(self):
        self.progress = module_progress(self.total_issues or 0, self.completed_issues or 0) or 0
