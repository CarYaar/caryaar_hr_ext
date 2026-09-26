import frappe
from frappe.tests import IntegrationTestCase

from caryaar_hr_ext.performance import api, engine
from caryaar_hr_ext.performance.rules import activity_doc_name


def _employee(email):
    name = frappe.db.get_value("Employee", {"user_id": email}, "name")
    if name:
        return name
    doc = frappe.get_doc({
        "doctype": "Employee", "first_name": "Perf", "last_name": email.split("@")[0],
        "gender": "Male", "date_of_birth": "1995-01-01", "date_of_joining": "2026-01-01",
        "company": frappe.db.get_value("Company", {}, "name"), "status": "Active",
        "company_email": email.upper(), "prefered_contact_email": "Company Email",
    }).insert(ignore_permissions=True)
    return doc.name


class TestIngest(IntegrationTestCase):
    def setUp(self):
        self.emp = _employee("perf.test.one@caryaar.test")

    def test_ingest_matches_company_email_case_insensitively_and_upserts(self):
        payload = dict(source="CY Admin", synced_through="2026-10-02T00:15:00+05:30",
                       rows=[{"email": "Perf.Test.One@CarYaar.test", "date": "2026-10-01",
                              "metrics": {"calls_handled": 3}},
                             {"email": "nobody@caryaar.test", "date": "2026-10-01",
                              "metrics": {"calls_handled": 1}}])
        out = api.ingest_activity(**payload)
        self.assertEqual(out["accepted"], 1)
        self.assertEqual(out["unmapped"], ["nobody@caryaar.test"])
        payload["rows"][0]["metrics"] = {"calls_handled": 7}
        api.ingest_activity(**payload)
        name = activity_doc_name(self.emp, "2026-10-01", "CY Admin")
        self.assertEqual(frappe.db.count("Work Activity Day", {"employee": self.emp, "activity_date": "2026-10-01"}), 1)
        self.assertEqual(frappe.db.get_value("Work Activity Day", name, "calls_handled"), 7)
        s = frappe.get_single("Performance Sync Settings")
        self.assertIn("nobody@caryaar.test", s.unmapped_emails or "")
        self.assertEqual(str(s.cy_admin_synced_through), "2026-10-02 00:15:00")

    def test_resend_without_snapshot_metrics_keeps_them(self):
        api.ingest_activity(source="CY Admin", synced_through="2026-10-01T22:00:00+05:30",
                            rows=[{"email": "perf.test.one@caryaar.test", "date": "2026-10-01",
                                   "metrics": {"calls_handled": 2, "leads_assigned": 30}}])
        api.ingest_activity(source="CY Admin", synced_through="2026-10-02T00:15:00+05:30",
                            rows=[{"email": "perf.test.one@caryaar.test", "date": "2026-10-01",
                                   "metrics": {"calls_handled": 4}}])
        name = activity_doc_name(self.emp, "2026-10-01", "CY Admin")
        self.assertEqual(frappe.db.get_value("Work Activity Day", name, ["calls_handled", "leads_assigned"]), (4, 30))

    def test_ingest_rejects_bad_payload_with_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            api.ingest_activity(source="Slack", synced_through="2026-10-02T00:15:00+05:30", rows=[])

    def test_synced_through_never_moves_backwards(self):
        api.ingest_activity(source="Plane", synced_through="2026-10-05T10:00:00+05:30", rows=[])
        api.ingest_activity(source="Plane", synced_through="2026-10-04T10:00:00+05:30", rows=[])
        self.assertEqual(str(frappe.get_single("Performance Sync Settings").plane_synced_through), "2026-10-05 10:00:00")

    def test_module_progress_upsert(self):
        body = dict(synced_through="2026-10-01T10:00:00+05:30", modules=[
            {"module_id": "mod-test-1", "project_identifier": "DEV", "module_name": "Test",
             "total_issues": 10, "completed_issues": 4}])
        api.ingest_module_progress(**body)
        body["modules"][0]["completed_issues"] = 5
        api.ingest_module_progress(**body)
        self.assertEqual(frappe.db.get_value("Plane Module Progress", "mod-test-1", "progress"), 50.0)
