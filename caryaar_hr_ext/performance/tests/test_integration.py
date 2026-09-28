"""Frappe integration tests for the intake endpoints and the nightly engine.

Run on a bench (staging), never locally: conftest.py skips this file when frappe
is not importable. Dates avoid 02-Oct (Gandhi Jayanti): HRMS refuses attendance
requests whose only day is a holiday.
"""
import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate

from caryaar_hr_ext.performance import api, engine, meter
from caryaar_hr_ext.performance.rules import activity_doc_name, adherence_doc_name

WORKDAY = "2026-10-06"      # Tuesday
OTHER_WORKDAY = "2026-10-07"
TEST_HOLIDAY = "2026-10-09"  # a holiday only on the test holiday list below


def _company():
    return frappe.db.get_value("Company", {}, "name")


def _employee(email):
    # Created with the email upper-cased so intake has to match case-insensitively;
    # looked up the same way so setUp never creates a second copy.
    name = frappe.db.get_value("Employee", {"company_email": ("in", [email, email.upper()])}, "name")
    if name:
        return name
    return frappe.get_doc({
        "doctype": "Employee", "first_name": "Perf", "last_name": email.split("@")[0],
        "gender": "Male", "date_of_birth": "1995-01-01", "date_of_joining": "2026-01-01",
        "company": _company(), "status": "Active",
        "company_email": email.upper(), "prefered_contact_email": "Company Email",
    }).insert(ignore_permissions=True).name


def _holiday_list():
    name = "Perf Test Holidays FY26-27"
    if not frappe.db.exists("Holiday List", name):
        frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": name,
                        "from_date": "2026-04-01", "to_date": "2027-03-31",
                        "holidays": [{"holiday_date": TEST_HOLIDAY, "description": "Test holiday"}]}
                       ).insert(ignore_permissions=True)
    return name


def _assign_holidays(emp):
    if frappe.db.exists("Holiday List Assignment", {"assigned_to": emp, "docstatus": 1}):
        return
    doc = frappe.get_doc({"doctype": "Holiday List Assignment", "applicable_for": "Employee",
                          "assigned_to": emp, "holiday_list": _holiday_list(), "from_date": "2026-04-01"})
    doc.insert(ignore_permissions=True)
    doc.submit()


def _settings(**values):
    for field, value in values.items():
        frappe.db.set_single_value("Performance Sync Settings", field, value)


def _cy(day, **metrics):
    return {"email": "perf.test.one@caryaar.test", "date": day, "metrics": metrics}


class TestIngest(IntegrationTestCase):
    def setUp(self):
        self.emp = _employee("perf.test.one@caryaar.test")
        _settings(cy_admin_synced_through=None, plane_synced_through=None, unmapped_emails="")

    def test_ingest_matches_company_email_case_insensitively_and_upserts(self):
        body = dict(source="CY Admin", synced_through="2026-10-07T00:15:00+05:30", covers_from=WORKDAY,
                    rows=[{"email": "Perf.Test.One@CarYaar.test", "date": WORKDAY, "metrics": {"calls_handled": 3}},
                          {"email": "nobody@caryaar.test", "date": WORKDAY, "metrics": {"calls_handled": 1}}])
        out = api.ingest_activity(**body)
        self.assertEqual((out["accepted"], out["unmapped"]), (1, ["nobody@caryaar.test"]))
        body["rows"][0]["metrics"] = {"calls_handled": 7}
        api.ingest_activity(**body)
        self.assertEqual(frappe.db.count("Work Activity Day", {"employee": self.emp, "activity_date": WORKDAY}), 1)
        self.assertEqual(frappe.db.get_value("Work Activity Day", activity_doc_name(self.emp, WORKDAY, "CY Admin"),
                                             "calls_handled"), 7)
        self.assertIn("nobody@caryaar.test", frappe.db.get_single_value("Performance Sync Settings", "unmapped_emails"))

    def test_resend_without_snapshot_metrics_keeps_them(self):
        api.ingest_activity(source="CY Admin", synced_through="2026-10-06T22:00:00+05:30", covers_from=WORKDAY,
                            rows=[_cy(WORKDAY, calls_handled=2, leads_assigned=30)])
        api.ingest_activity(source="CY Admin", synced_through="2026-10-07T00:15:00+05:30", covers_from=WORKDAY,
                            rows=[_cy(WORKDAY, calls_handled=4)])
        name = activity_doc_name(self.emp, WORKDAY, "CY Admin")
        self.assertEqual(frappe.db.get_value("Work Activity Day", name, ["calls_handled", "leads_assigned"]), (4, 30))

    def test_stamp_never_jumps_over_days_that_were_never_sent(self):
        _settings(cy_admin_synced_through="2026-10-05 10:00:00")
        api.ingest_activity(source="CY Admin", synced_through="2026-10-08T10:00:00+05:30",
                            covers_from="2026-10-08", rows=[])
        self.assertEqual(str(frappe.db.get_single_value("Performance Sync Settings", "cy_admin_synced_through")),
                         "2026-10-05 10:00:00")
        api.ingest_activity(source="CY Admin", synced_through="2026-10-08T10:00:00+05:30",
                            covers_from="2026-10-05", rows=[])
        self.assertEqual(api.get_sync_state()["CY Admin"], "2026-10-08T10:00:00")

    def test_ingest_rejects_bad_payload_with_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            api.ingest_activity(source="Slack", synced_through="2026-10-07T00:15:00+05:30",
                                covers_from=WORKDAY, rows=[])

    def test_module_progress_upsert(self):
        body = dict(synced_through="2026-10-06T10:00:00+05:30", modules=[
            {"module_id": "mod-test-1", "project_identifier": "DEV", "module_name": "Test",
             "total_issues": 10, "completed_issues": 4}])
        api.ingest_module_progress(**body)
        body["modules"][0]["completed_issues"] = 5
        api.ingest_module_progress(**body)
        self.assertEqual(frappe.db.get_value("Plane Module Progress", "mod-test-1", "progress"), 50.0)


    def test_ingest_work_items_upserts_and_flags_deleted(self):
        item = {"issue_id": "11111111-2222-3333-4444-555555555555", "project_identifier": "DEV", "sequence_id": 9001,
                "title": "Test item", "assignee_email": None, "state_group": "started", "module_id": None, "labels": ["bug"],
                "start_date": None, "target_date": "2026-10-10", "completed_at": None,
                "created_at": "2026-10-01T09:00:00+05:30", "updated_at": "2026-10-01T09:00:00+05:30", "is_deleted": False}
        out = api.ingest_work_items("2026-10-01T10:00:00+05:30", [item])
        self.assertEqual(out["accepted"], 1)
        doc = frappe.get_doc("Plane Work Item", item["issue_id"])
        self.assertEqual(doc.state_group, "started")
        self.assertEqual(doc.labels, "bug")
        item["state_group"] = "completed"
        item["completed_at"] = "2026-10-02T18:00:00+05:30"
        item["is_deleted"] = True
        api.ingest_work_items("2026-10-02T19:00:00+05:30", [item])
        doc.reload()
        self.assertEqual(doc.state_group, "completed")
        self.assertEqual(doc.is_deleted, 1)  # flagged, never removed
        self.assertEqual(str(frappe.db.get_single_value("Performance Sync Settings", "plane_items_synced_through"))[:16],
                         "2026-10-02 19:00")
        frappe.delete_doc("Plane Work Item", item["issue_id"], force=True)

    def test_ingest_work_items_full_pass_records_the_day(self):
        api.ingest_work_items("2026-10-03T00:30:00+05:30", [], full_pass=1)
        self.assertEqual(str(frappe.db.get_single_value("Performance Sync Settings", "plane_items_full_pass_on")), "2026-10-03")


class TestEngine(IntegrationTestCase):
    def setUp(self):
        self.emp = _employee("perf.test.two@caryaar.test")
        _assign_holidays(self.emp)
        _settings(plane_synced_through="2026-10-20 00:00:00", cy_admin_synced_through=None, department_sources="{}")

    def _row(self, day):
        return frappe.get_doc("Work Adherence Day", adherence_doc_name(self.emp, day))

    def test_day_with_plane_activity_is_visible(self):
        api.ingest_activity(source="Plane", synced_through="2026-10-20T00:00:00+05:30", covers_from=WORKDAY,
                            rows=[{"email": "perf.test.two@caryaar.test", "date": WORKDAY,
                                   "metrics": {"activity_count": 3, "completed_count": 1}}])
        engine.run_day(getdate(WORKDAY))
        row = self._row(WORKDAY)
        self.assertEqual((row.work_visible, row.adherence_pct), ("Yes", 100))

    def test_holiday_from_holiday_list_assignment_has_no_checks(self):
        engine.run_day(getdate(TEST_HOLIDAY))
        row = self._row(TEST_HOLIDAY)
        self.assertEqual((row.is_working_day, row.checks_applicable), (0, 0))

    def test_day_after_last_sync_is_pending(self):
        engine.run_day(getdate("2026-10-21"))
        row = self._row("2026-10-21")
        self.assertEqual((row.work_visible or "", row.checks_applicable), ("", 0))

    def test_present_with_pending_request_is_not_a_wfh_day(self):
        att = frappe.get_doc({"doctype": "Attendance", "employee": self.emp, "attendance_date": WORKDAY,
                              "status": "Present", "company": _company()}).insert(ignore_permissions=True)
        att.submit()
        req = frappe.get_doc({"doctype": "Attendance Request", "employee": self.emp, "from_date": OTHER_WORKDAY,
                              "to_date": OTHER_WORKDAY, "reason": "Work From Home"}).insert(ignore_permissions=True)
        frappe.db.set_value("Attendance Request", req.name, {"workflow_state": "Pending", "from_date": WORKDAY,
                                                             "to_date": WORKDAY})
        engine.run_day(getdate(WORKDAY))
        self.assertEqual(self._row(WORKDAY).wfh, 0)

    def test_rejected_wfh_request_does_not_make_a_wfh_day(self):
        # A workflow only lets a document be created in its first state (Draft);
        # mark it Rejected afterwards, as the approval flow would.
        req = frappe.get_doc({"doctype": "Attendance Request", "employee": self.emp, "from_date": OTHER_WORKDAY,
                              "to_date": OTHER_WORKDAY, "reason": "Work From Home"}).insert(ignore_permissions=True)
        frappe.db.set_value("Attendance Request", req.name, "workflow_state", "Rejected")
        engine.run_day(getdate(OTHER_WORKDAY))
        self.assertEqual(self._row(OTHER_WORKDAY).wfh, 0)

    def test_recompute_writes_every_day_and_bounds_the_range(self):
        out = api.recompute(WORKDAY, OTHER_WORKDAY)
        self.assertEqual(out["days"], 2)
        self.assertTrue(frappe.db.exists("Work Adherence Day", adherence_doc_name(self.emp, OTHER_WORKDAY)))
        with self.assertRaises(frappe.ValidationError):
            api.recompute("2026-10-01", "2026-12-31")

    # ─── goal meter (phase 1, Task 6) ─────────────────────────────────────────
    def _cycle(self):
        name = frappe.db.get_value("Appraisal Cycle", {"cycle_name": "Perf Test Cycle"}, "name")
        if name:
            return name
        cycle = frappe.get_doc({"doctype": "Appraisal Cycle", "cycle_name": "Perf Test Cycle",
                                "start_date": "2026-10-01", "end_date": "2027-03-31", "company": _company(),
                                "kra_evaluation_method": "Automated Based on Goal Progress"}
                               ).insert(ignore_permissions=True)
        frappe.db.set_value("Appraisal Cycle", cycle.name, "status", "In Progress")
        return cycle.name

    def _seed_goal(self, name, kra=None, module=None):
        kra = kra or frappe.get_all("KRA", pluck="name", limit=1)[0]
        return frappe.get_doc({"doctype": "Goal", "goal_name": name, "employee": self.emp, "kra": kra,
                               "appraisal_cycle": self._cycle(), "start_date": "2026-10-01", "end_date": "2027-03-31",
                               "cy_plane_module": module}).insert(ignore_permissions=True)

    def _item(self, issue_id, state, module_id, **extra):
        frappe.get_doc({"doctype": "Plane Work Item", "issue_id": issue_id, "project_identifier": "DEV", "sequence_id": 1,
                        "title": issue_id, "state_group": state, "module_id": module_id,
                        "created_at": "2026-10-01 09:00:00", "updated_at": "2026-10-01 09:00:00", **extra}
                       ).insert(ignore_permissions=True)

    def test_bad_module_id_is_recorded_and_other_goals_still_update(self):
        good_module = "5f0c1c1e-8a55-4c3e-9d1a-0b7d7d1e2a10"
        self._item("t0-a", "completed", good_module); self._item("t0-b", "started", good_module)
        bad = self._seed_goal("Perf bad module", module="not a module")
        good = self._seed_goal("Perf good module", module=f"https://pitstop.mycaryaar.com/caryaar/modules/{good_module}/")
        for g in (bad, good):
            frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": "Plane module"}).insert(ignore_permissions=True)
        frappe.db.set_single_value("Performance Sync Settings", "plane_items_synced_through", "2026-11-02 23:30:00")
        meter.run_meter(as_of=getdate("2026-11-02"))
        self.assertEqual(frappe.db.get_value("Goal", good.name, "progress"), 50.0)
        self.assertEqual(frappe.db.get_value("Goal", bad.name, "progress"), 0)
        self.assertIn(bad.name, frappe.db.get_single_value("Performance Sync Settings", "unmatched_goal_modules"))

    def test_ratio_meter_reads_activity_rows_and_gates_progress(self):
        g = self._seed_goal("T conversion")
        frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": "Ratio to target", "metric": "conversion_pct",
                        "window": "Cycle to date", "target_value": 5, "unit": "%", "direction": "Higher is better"}
                       ).insert(ignore_permissions=True)
        for day, assigned, booked in (("2026-10-02", 100, 2), ("2026-10-03", 100, 3)):
            frappe.get_doc({"doctype": "Work Activity Day", "employee": self.emp, "activity_date": day, "source": "CY Admin",
                            "leads_assigned_new": assigned, "bookings_within_7d": booked}).insert(ignore_permissions=True)
        frappe.db.set_single_value("Performance Sync Settings", "cy_admin_synced_through", "2026-10-04 23:30:00")
        meter.run_meter(as_of=getdate("2026-10-04"))
        r = frappe.get_doc("Goal Meter Reading", f"{g.name}|2026-10-04")
        self.assertEqual((r.value, r.progress, r.stale, r.written_to_goal), (2.5, 50.0, 0, 0))   # October: not written
        self.assertEqual(frappe.db.get_value("Goal", g.name, "progress"), 0)
        frappe.db.set_single_value("Performance Sync Settings", "cy_admin_synced_through", "2026-11-02 23:30:00")
        meter.run_meter(as_of=getdate("2026-11-02"))
        self.assertEqual(frappe.db.get_value("Goal", g.name, "progress"), 50.0)                   # November: written

    def test_stale_source_repeats_last_reading(self):
        g = self._seed_goal("T stale")
        frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": "Ratio to target", "metric": "conversion_pct",
                        "target_value": 5, "direction": "Higher is better"}).insert(ignore_permissions=True)
        frappe.db.set_single_value("Performance Sync Settings", "cy_admin_synced_through", "2026-10-04 23:30:00")
        meter.run_meter(as_of=getdate("2026-10-04"))
        meter.run_meter(as_of=getdate("2026-10-05"))                    # source did not sync past 05-Oct
        r = frappe.get_doc("Goal Meter Reading", f"{g.name}|2026-10-05")
        self.assertEqual(r.stale, 1)

    def test_module_completion_uses_current_membership(self):
        g = self._seed_goal("T sprint", module="mod-t1")
        frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": "Plane module"}).insert(ignore_permissions=True)
        for n, state in (("a", "completed"), ("b", "started"), ("c", "cancelled")):
            self._item(f"t1-{n}", state, "mod-t1")
        frappe.db.set_single_value("Performance Sync Settings", "plane_items_synced_through", "2026-10-07 23:30:00")
        meter.run_meter(as_of=getdate("2026-10-06"))
        self.assertEqual(frappe.db.get_value("Goal Meter Reading", f"{g.name}|2026-10-06", "progress"), 50.0)
        frappe.db.set_value("Plane Work Item", "t1-a", "module_id", None)                          # moved out
        meter.run_meter(as_of=getdate("2026-10-07"))
        self.assertEqual(frappe.db.get_value("Goal Meter Reading", f"{g.name}|2026-10-07", "progress"), 0.0)
