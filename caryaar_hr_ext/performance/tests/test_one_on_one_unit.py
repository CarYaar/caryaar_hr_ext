"""The goal 1:1 under the Frappe stand-in: goals filled from the cycle, hand-edited stamps restored,
the acknowledge action, and who sees which record."""
from datetime import date

import pytest

from caryaar_hr_ext.performance.tests import _frappe_stub as stub

CYCLE, EMP, MGR = "Cycle Oct-2026", "HR-EMP-00012", "HR-EMP-00003"
REC = "1ON1-HR-EMP-00012-2026-10-02"


def _seed(fake):
    stub.seed(fake, "Appraisal Cycle", name=CYCLE, status="In Progress", start_date="2026-10-01")
    stub.seed(fake, "Employee", name=EMP, status="Active", user_id="anagha@caryaar.test", employee_name="Anagha", reports_to=MGR)
    stub.seed(fake, "Employee", name=MGR, status="Active", user_id="joel@caryaar.test", employee_name="Joel")
    stub.seed(fake, "Goal", name="HR-GOAL-1", goal_name="Lead to booking 5%", employee=EMP, appraisal_cycle=CYCLE,
              kra="Conversion", is_group=0, status="Pending")
    stub.seed(fake, "Goal Meter", name="GM-1", goal="HR-GOAL-1", employee=EMP, method="Ratio to target",
              metric="conversion_pct", target_value=5, unit="%", active=1)
    stub.seed(fake, "Goal Meter Reading", name="HR-GOAL-1|2026-10-01", goal="HR-GOAL-1", reading_date="2026-10-01",
              progress=40.0, value=2.0)
    stub.seed(fake, "Appraisee", name="APR-1", parent=CYCLE, parenttype="Appraisal Cycle", employee=EMP, appraisal_template="CX")
    stub.seed(fake, "Appraisal Template Goal", name="ATG-1", parent="CX", parenttype="Appraisal Template",
              key_result_area="Conversion", per_weightage=30)


def _record(fake, **extra):
    fields = dict(name=REC, employee=EMP, manager=MGR, appraisal_cycle=CYCLE, meeting_date="2026-10-02",
                  meeting_type="Goal setting", employee_acknowledged=0, acknowledged_on=None, acknowledged_by=None)
    fields.update(extra)
    stub.seed(fake, "Goal One on One", **fields)


def test_new_record_fills_the_goals_from_the_cycle(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 2))
    import frappe

    _seed(fake)
    doc = frappe.get_doc({"doctype": "Goal One on One", "employee": EMP, "manager": MGR, "appraisal_cycle": CYCLE,
                          "meeting_date": "2026-10-02", "meeting_type": "Goal setting"})
    doc.validate()
    assert [(g["goal"], g["weight"], g["target_text"], g["progress"]) for g in doc.goals] == [("HR-GOAL-1", 30.0, "5%", 40.0)]


def test_hand_edited_acknowledgement_is_restored(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 2))
    import frappe

    _seed(fake)
    _record(fake)
    doc = frappe.get_doc("Goal One on One", REC)
    doc.employee_acknowledged, doc.acknowledged_by = 1, "hr@caryaar.test"
    doc.validate()
    assert doc.employee_acknowledged == 0 and doc.acknowledged_by is None
