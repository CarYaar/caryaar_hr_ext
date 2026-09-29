"""The nightly meter under the Frappe stand-in: what counts, what is written, who may
enter a manual reading. The Frappe integration tests cover the same paths on staging."""
from datetime import date

import pytest

from caryaar_hr_ext.performance.tests import _frappe_stub as stub

CYCLE = "Cycle Oct-2026"
EMP = "HR-EMP-00008"
MOD = "5f0c1c1e-8a55-4c3e-9d1a-0b7d7d1e2a10"
OTHER = "5f0c1c1e-8a55-4c3e-9d1a-0b7d7d1e2a99"


def _base(fake, method="Plane module", **meter_fields):
    stub.seed(fake, "Appraisal Cycle", name=CYCLE, status="In Progress", start_date="2026-10-01")
    stub.seed(fake, "Employee", name=EMP, status="Active", user_id="shiwans@caryaar.test", employee_name="Shiwans")
    stub.seed(fake, "Goal", name="HR-GOAL-1", goal_name="Sprint goal", employee=EMP, appraisal_cycle=CYCLE,
              progress=0, cy_plane_module=MOD, is_group=0, status="Pending")
    stub.seed(fake, "Goal Meter", goal="HR-GOAL-1", employee=EMP, method=method, active=1, **meter_fields)
    fake.db.singles[("Performance Sync Settings", "plane_items_synced_through")] = "2026-11-02 23:30:00"


def _item(fake, iid, state, modules, **extra):
    fields = dict(issue_id=iid, project_identifier="DEV", sequence_id=1, title=iid, state_group=state,
                  module_id=modules[0] if modules else None, module_ids=",".join(modules), is_deleted=0,
                  is_archived=0, labels="", created_at="2026-10-01 09:00:00", updated_at="2026-10-01 09:00:00")
    fields.update(extra)
    stub.seed(fake, "Plane Work Item", **fields)


def _reading(fake, day="2026-11-02"):
    return fake.db.store["Goal Meter Reading"][f"HR-GOAL-1|{day}"]


def test_archived_finished_work_still_counts_for_the_module(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 11, 2))
    from caryaar_hr_ext.performance import meter

    _base(fake)
    _item(fake, "a", "completed", [MOD], is_archived=1)   # Plane archives finished work; it stays done
    _item(fake, "b", "started", [MOD])
    _item(fake, "c", "completed", [MOD], is_deleted=1)    # deleted is gone for good
    meter.run_meter(as_of=date(2026, 11, 2))
    assert _reading(fake)["progress"] == 50.0
    assert fake.db.store["Goal"]["HR-GOAL-1"]["progress"] == 50.0


def test_item_in_two_modules_counts_for_the_goal_module(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 11, 2))
    from caryaar_hr_ext.performance import meter

    _base(fake)
    _item(fake, "a", "completed", [OTHER, MOD])   # joined the goal module second
    _item(fake, "b", "started", [MOD])
    meter.run_meter(as_of=date(2026, 11, 2))
    assert _reading(fake)["progress"] == 50.0


def test_labels_match_whatever_case_plane_uses(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 11, 2))
    from caryaar_hr_ext.performance import meter

    _base(fake, method="Ratio to target", metric="incidents_fixed_24h_pct", target_value=90,
          direction="Higher is better", window="Cycle to date")
    _item(fake, "a", "completed", [], assignee=EMP, labels="Incident",
          created_at="2026-10-05 09:00:00", completed_at="2026-10-05 12:00:00")
    _item(fake, "b", "completed", [], assignee=EMP, labels="Incident",
          created_at="2026-10-06 09:00:00", completed_at="2026-10-09 12:00:00")
    meter.run_meter(as_of=date(2026, 11, 2))
    assert (_reading(fake)["value"], _reading(fake)["progress"]) == (50.0, 55.6)


def test_documentation_counts_pages_the_person_created_or_edited(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 11, 2))
    from caryaar_hr_ext.performance import meter

    _base(fake, method="Ratio to target", metric="wiki_pages", target_value=4, direction="Higher is better")
    me, mate = "shiwans@caryaar.test", "mate@caryaar.test"
    stub.seed(fake, "Wiki Page", name="p1", owner=me, modified_by=mate, creation="2026-10-03 10:00:00")     # mine, mate fixed a typo
    stub.seed(fake, "Wiki Page", name="p2", owner=mate, modified_by=me, creation="2026-10-04 10:00:00")     # mate's, I rewrote it
    stub.seed(fake, "Version", name="v1", ref_doctype="Wiki Page", docname="p2", owner=me, creation="2026-10-10 10:00:00")
    stub.seed(fake, "Wiki Page", name="p3", owner=mate, modified_by=mate, creation="2026-10-05 10:00:00")   # nothing of mine
    stub.seed(fake, "Wiki Page", name="p4", owner=me, modified_by=me, creation="2026-09-20 10:00:00")       # before the cycle
    meter.run_meter(as_of=date(2026, 11, 2))
    assert (_reading(fake)["value"], _reading(fake)["progress"]) == (2, 50.0)


# ─── manual meters: the reading is the input, the gate still applies ──────────

def _activity_sql(fake):
    """Stand-in for the meter's one raw query: the sum of a Work Activity Day column over a window."""
    import re

    def handler(query, values):
        col = re.search(r"sum\(`(\w+)`\)", query).group(1)
        emp, source, d_from, d_to = values
        rows = fake.db.store.get("Work Activity Day", {}).values()
        return [[sum(int(r.get(col) or 0) for r in rows
                     if r["employee"] == emp and r["source"] == source
                     and str(d_from) <= str(r["activity_date"]) <= str(d_to))]]
    fake.db.sql_handler = handler


def _day(fake, day, **metrics):
    stub.seed(fake, "Work Activity Day", name=f"{EMP}-{day}", employee=EMP, source="CY Admin",
              activity_date=day, **metrics)


ROLE_METRICS = ("jobs_from_bookings", "bookings_to_jobs_pct", "calls_to_bookings_pct", "campaigns_sent",
                "campaign_leads_reached", "creatives_approved", "leads_from_channels", "jobs_moved",
                "partners_activated", "agreements_signed", "payouts_triggered", "unpaid_cleared")


def test_every_meter_metric_has_a_source(monkeypatch):
    stub.install(monkeypatch, date(2026, 10, 20))
    from caryaar_hr_ext.performance import meter
    from caryaar_hr_ext.performance import meter_rules as mr

    assert set(meter.METRICS) <= set(mr.SOURCE_OF)          # compute_reading indexes SOURCE_OF by metric
    for key in ROLE_METRICS:
        assert key in meter.METRICS and mr.SOURCE_OF[key] == "CY Admin", key


def test_bookings_to_jobs_pct_and_counts(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 20))
    from caryaar_hr_ext.performance import meter

    _base(fake, method="Ratio to target", metric="bookings_to_jobs_pct", target_value=50, unit="%",
          direction="Higher is better")
    fake.db.singles[("Performance Sync Settings", "cy_admin_synced_through")] = "2026-10-20 23:30:00"
    _activity_sql(fake)
    _day(fake, "2026-10-05", bookings_credited=6, jobs_from_bookings=3)
    _day(fake, "2026-10-19", bookings_credited=4, jobs_from_bookings=1)
    meter.run_meter(as_of=date(2026, 10, 20))
    r = _reading(fake, "2026-10-20")
    assert (r["value"], r["progress"]) == (40.0, 80.0)
    ctx = meter.MeterContext(EMP, CYCLE, date(2026, 10, 1), date(2026, 10, 20), date(2026, 10, 1), date(2026, 10, 20), None)
    assert meter.m_jobs_from_bookings(ctx) == 4
    assert meter.m_calls_to_bookings_pct(ctx) is None       # no answered calls: nothing to divide by


def test_marketing_metrics_sum_the_window(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 20))
    from caryaar_hr_ext.performance import meter

    _base(fake, method="Ratio to target", metric="leads_from_channels", target_value=100,
          direction="Higher is better", window="Latest full week")
    fake.db.singles[("Performance Sync Settings", "cy_admin_synced_through")] = "2026-10-20 23:30:00"
    _activity_sql(fake)
    _day(fake, "2026-10-11", leads_meta=50, campaigns_sent=1)                                  # the week before
    _day(fake, "2026-10-13", leads_meta=10, leads_google=5, leads_whatsapp=3, leads_web=2, campaigns_sent=2)
    _day(fake, "2026-10-19", leads_meta=40, campaigns_sent=1)                                  # this week, not over
    meter.run_meter(as_of=date(2026, 10, 20))
    r = _reading(fake, "2026-10-20")
    assert (r["value"], r["progress"]) == (20, 20.0)
    ctx = meter.MeterContext(EMP, CYCLE, date(2026, 10, 1), date(2026, 10, 20), date(2026, 10, 12), date(2026, 10, 18), None)
    assert meter.m_campaigns_sent(ctx) == 2


def test_manual_reading_entered_in_october_is_applied_on_the_first_night_of_november(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 20))
    from caryaar_hr_ext.performance import meter
    import frappe

    _base(fake, method="Manual")
    frappe.get_doc({"doctype": "Goal Meter Reading", "goal": "HR-GOAL-1", "reading_date": "2026-10-20",
                    "progress": 40, "method": "Manual", "evidence": "1:1 notes"}).insert()
    assert fake.db.store["Goal"]["HR-GOAL-1"]["progress"] == 0            # learning month: shown, not written
    assert not _reading(fake, "2026-10-20").get("written_to_goal")
    fake.today = date(2026, 11, 1)
    out = meter.run_meter(as_of=date(2026, 11, 1))
    assert fake.db.store["Goal"]["HR-GOAL-1"]["progress"] == 40.0 and out["written"] == 1
    assert _reading(fake, "2026-10-20")["written_to_goal"] == 1
    assert meter.run_meter(as_of=date(2026, 11, 2))["written"] == 0        # applied once, not every night


def test_manual_reading_after_the_gate_writes_at_once(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 11, 5))
    stub.install  # noqa: B018 - the meter module is loaded by install()
    import frappe

    _base(fake, method="Manual")
    frappe.get_doc({"doctype": "Goal Meter Reading", "goal": "HR-GOAL-1", "reading_date": "2026-11-05",
                    "progress": 60, "method": "Manual", "evidence": "review"}).insert()
    assert fake.db.store["Goal"]["HR-GOAL-1"]["progress"] == 60.0
    assert _reading(fake, "2026-11-05")["written_to_goal"] == 1
    assert _reading(fake, "2026-11-05")["employee"] == EMP               # fetched from the goal, for the Employee read


def test_manual_reading_needs_evidence_permission_and_another_person(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 11, 5), roles=("HR User",), user="hiren@caryaar.test")
    from caryaar_hr_ext.performance import meter

    _base(fake, method="Manual")
    stub.seed(fake, "Employee", name="HR-EMP-00006", status="Active", user_id="hiren@caryaar.test")
    with pytest.raises(stub.ValidationError):
        meter.write_manual_reading("HR-GOAL-1", 40, evidence="")
    fake.permission_denied.add(("Goal", "HR-GOAL-1"))                       # User Permissions apply
    with pytest.raises(stub.PermissionError):
        meter.write_manual_reading("HR-GOAL-1", 40, evidence="reviewed")
    fake.permission_denied.clear()
    out = meter.write_manual_reading("HR-GOAL-1", 40, evidence="reviewed in 1:1")
    assert out["written_to_goal"] is True and fake.db.store["Goal"]["HR-GOAL-1"]["progress"] == 40.0
    r = _reading(fake, "2026-11-05")
    assert r["entered_by"] == "hiren@caryaar.test" and r["evidence"] == "reviewed in 1:1"


def test_manual_reading_for_own_goal_is_refused(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 11, 5), roles=("HR User",), user="shiwans@caryaar.test")
    from caryaar_hr_ext.performance import meter

    _base(fake, method="Manual")
    with pytest.raises(stub.ValidationError):
        meter.write_manual_reading("HR-GOAL-1", 100, evidence="me")


# ─── the person's own view (CY Admin home screen) ────────────────────────────

def test_person_goals_returns_the_live_cycle_for_the_signed_in_email(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 2), roles=("Performance Sync",))
    from caryaar_hr_ext.performance import api

    _base(fake, method="Ratio to target", metric="conversion_pct", target_value=5, unit="%",
          direction="Higher is better", window="Cycle to date")
    stub.seed(fake, "Goal Meter Reading", name="HR-GOAL-1|2026-10-01", goal="HR-GOAL-1", employee=EMP,
              reading_date="2026-10-01", value=2.5, progress=50.0, stale=0, method="Ratio to target")
    stub.seed(fake, "Appraisal", name="HR-APR-1", employee=EMP, appraisal_cycle=CYCLE, docstatus=0,
              cy_next_review_on="2026-10-15")
    out = api.person_goals("Shiwans@caryaar.test")
    assert out["employee"] == EMP and out["employee_name"] == "Shiwans"
    c = out["cycles"][0]
    assert c["learning_month"] is True and c["next_review_on"] == "2026-10-15"
    g = c["goals"][0]
    assert (g["progress"], g["value"], g["target"], g["reading_date"]) == (50.0, 2.5, "5%", "2026-10-01")
    assert g["source"] == "CY Admin" and "target of 5%" in g["how"]
    assert api.person_goals("nobody@caryaar.test") == {"employee": None, "employee_name": None, "cycles": []}


def test_a_cycle_past_its_end_date_is_not_metered_nor_shown(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 2), roles=("Performance Sync",))
    from caryaar_hr_ext.performance import api, meter

    _base(fake, method="Manual")
    stub.seed(fake, "Appraisal Cycle", name="Cycle Mar-2026", status="In Progress",
              start_date="2026-03-01", end_date="2026-09-30")             # never closed in HRMS
    stub.seed(fake, "Goal", name="HR-GOAL-OLD", goal_name="Old goal", employee=EMP, appraisal_cycle="Cycle Mar-2026",
              progress=0, is_group=0, status="Pending")
    stub.seed(fake, "Goal Meter", goal="HR-GOAL-OLD", employee=EMP, method="Manual", active=1)
    stub.seed(fake, "Goal Meter Reading", name="HR-GOAL-OLD|2026-10-01", goal="HR-GOAL-OLD", employee=EMP,
              reading_date="2026-10-01", progress=90, method="Manual", written_to_goal=0)
    fake.today = date(2026, 11, 2)
    meter.run_meter(as_of=date(2026, 11, 2))
    assert fake.db.store["Goal"]["HR-GOAL-OLD"]["progress"] == 0                # skipped: the cycle is over
    fake.today = date(2026, 10, 2)
    out = api.person_goals("shiwans@caryaar.test")
    assert [c["cycle"] for c in out["cycles"]] == [CYCLE]


def test_a_live_cycle_with_no_goals_for_the_person_is_not_listed(monkeypatch):
    """Until 30-Sep the previous cycle is still live by its dates; a person with no goals in it
    sees the empty state, not an empty cycle."""
    fake = stub.install(monkeypatch, date(2026, 9, 28), roles=("Performance Sync",))
    from caryaar_hr_ext.performance import api

    _base(fake, method="Manual")
    stub.seed(fake, "Appraisal Cycle", name="Cycle Mar-2026", status="Not Started",
              start_date="2026-03-01", end_date="2026-09-30")
    out = api.person_goals("shiwans@caryaar.test")
    assert out["employee"] == EMP and out["cycles"] == []


def test_a_goal_without_a_value_gets_no_reading_row(monkeypatch):
    """Frappe stores a None Float as 0.0, so a written "no value" reading would read as 0%
    in the pack and the person's view. Nothing is written until there is a value."""
    fake = stub.install(monkeypatch, date(2026, 10, 2))
    from caryaar_hr_ext.performance import meter

    _base(fake)
    fake.db.store["Goal"]["HR-GOAL-1"]["cy_plane_module"] = None       # module not created yet
    out = meter.run_meter(as_of=date(2026, 10, 2))
    assert "HR-GOAL-1|2026-10-02" not in fake.db.store.get("Goal Meter Reading", {})
    assert out["no_value"] == 1 and out["readings"] == 0


def test_goal_meter_refuses_a_metric_key_the_meter_does_not_know(monkeypatch):
    # a misspelt key used to save fine and then silently produce no reading, forever
    stub.install(monkeypatch, date(2026, 10, 20))
    import frappe

    bad = frappe.get_doc({"doctype": "Goal Meter", "goal": "HR-GOAL-1", "method": "Ratio to target", "metric": "jobs_from_booking"})
    with pytest.raises(frappe.ValidationError, match="jobs_from_booking"):
        bad.validate()
    frappe.get_doc({"doctype": "Goal Meter", "goal": "HR-GOAL-1", "method": "Ratio to target", "metric": "jobs_from_bookings"}).validate()
    frappe.get_doc({"doctype": "Goal Meter", "goal": "HR-GOAL-1", "method": "Manual", "metric": ""}).validate()
    frappe.get_doc({"doctype": "Goal Meter", "goal": "HR-GOAL-1", "method": "Plane module"}).validate()
