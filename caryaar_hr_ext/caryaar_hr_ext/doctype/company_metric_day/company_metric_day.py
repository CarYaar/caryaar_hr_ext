from frappe.model.document import Document


class CompanyMetricDay(Document):
    def autoname(self):
        self.name = f"{self.metric}|{self.metric_date}"
