"""after_migrate hooks run under the Frappe stand-in: a missing import or a wrong
doctype name would otherwise crash every `bench migrate` on staging and prod."""
import json
from datetime import date
from pathlib import Path

from caryaar_hr_ext.performance.tests import _frappe_stub as stub

FIXTURE = Path(__file__).resolve().parents[1] / "setup_data" / "goal_meters.json"


def test_ensure_goal_meters_creates_a_meter_for_a_fixture_pair(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 9, 30))
    from caryaar_hr_ext.performance import setup

    row = json.loads(FIXTURE.read_text())[0]
    stub.seed(fake, "Appraisal Cycle", name="Cycle Oct-2026", status="Not Started")
    stub.seed(fake, "Goal", name="HR-GOAL-2026-0001", employee=row["employee"], kra=row["kra"],
              appraisal_cycle="Cycle Oct-2026", is_group=0, status="Pending")
    assert setup.ensure_goal_meters() == 1
    meter = fake.db.store["Goal Meter"]["HR-GOAL-2026-0001"]
    assert meter["method"] == row["method"] and meter["active"] == 1
    assert setup.ensure_goal_meters() == 0     # an existing meter is never touched


def test_review_pack_recipients_default_is_backfilled_once(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 9, 30))
    from caryaar_hr_ext.performance import setup

    assert setup.ensure_review_pack_recipients() is True
    stored = fake.db.singles[("Performance Sync Settings", "review_pack_recipients")]
    assert "sahaib.singh@caryaar.com" in stored and "maxson.lewis@caryaar.com" in stored
    fake.db.singles[("Performance Sync Settings", "review_pack_recipients")] = "only@caryaar.test"
    assert setup.ensure_review_pack_recipients() is False   # HR's edit survives the next migrate


def test_goals_acknowledged_notification_and_permission_hooks_are_registered(monkeypatch):
    stub.install(monkeypatch, date(2026, 10, 2))          # hooks.py imports frappe at module level
    from caryaar_hr_ext.performance import setup

    docs = [d for d in setup.load_docs() if d["doctype"] == "Notification" and d["name"] == "Goals acknowledged"]
    assert len(docs) == 1
    n = docs[0]
    assert n["document_type"] == "Goal One on One" and n["event"] == "Value Change" and n["value_changed"] == "employee_acknowledged"
    targets = {r.get("cc") or r.get("receiver_by_document_field") for r in n["recipients"]}
    assert targets == {"humanresource@caryaar.com", "manager_user"} and len(n["subject"]) <= 140
    import importlib

    hooks = importlib.import_module("caryaar_hr_ext.hooks")
    assert hooks.permission_query_conditions["Goal One on One"].endswith("one_on_one_permissions.query_conditions")
    assert hooks.has_permission["Goal One on One"].endswith("one_on_one_permissions.has_permission")
