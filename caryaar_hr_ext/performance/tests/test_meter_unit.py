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
