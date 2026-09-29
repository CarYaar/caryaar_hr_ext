"""Pure rules of the goal 1:1: rows filled from the cycle, who may acknowledge, the state text."""
from datetime import datetime

from caryaar_hr_ext.performance import one_on_one_rules as r


def test_goal_rows_carry_weight_target_source_and_progress():
    goals = [{"name": "HR-GOAL-1", "goal_name": "Lead to booking 5%", "kra": "Conversion"},
             {"name": "HR-GOAL-2", "goal_name": "Sprint work", "kra": "Delivery"}]
    meters = {"HR-GOAL-1": {"method": "Ratio to target", "metric": "conversion_pct", "target": 5, "unit": "%"},
              "HR-GOAL-2": {"method": "Plane module"}}
    readings = {"HR-GOAL-1": {"progress": 40.0, "value": 2.0}}
    rows = r.goal_rows(goals, meters, readings, {"Conversion": 30.0, "Delivery": 20.0})
    assert rows[0] == {"goal": "HR-GOAL-1", "goal_name": "Lead to booking 5%", "kra": "Conversion", "weight": 30.0,
                       "target_text": "5%", "measured_from": "CY Admin (conversion_pct)", "progress": 40.0}
    assert rows[1]["target_text"] == "every item in the module done" and rows[1]["progress"] is None


def test_goal_rows_without_meter_or_reading():
    rows = r.goal_rows([{"name": "G", "goal_name": "Manual thing", "kra": "K"}], {}, {}, {})
    assert rows == [{"goal": "G", "goal_name": "Manual thing", "kra": "K", "weight": None, "target_text": "",
                     "measured_from": "", "progress": None}]


def test_only_the_employee_may_acknowledge_once():
    assert r.can_acknowledge("anagha@caryaar.test", "anagha@caryaar.test", already=False) is None
    assert r.can_acknowledge("Anagha@CarYaar.test", "anagha@caryaar.test", already=False) is None
    assert "own login" in r.can_acknowledge("hr@caryaar.test", "anagha@caryaar.test", already=False)
    assert "already" in r.can_acknowledge("anagha@caryaar.test", "anagha@caryaar.test", already=True)
    assert "no ERP login" in r.can_acknowledge("anagha@caryaar.test", None, already=False)


def test_acknowledgement_state_text():
    assert r.acknowledgement_state(True, datetime(2026, 10, 3, 11, 5)) == "acknowledged on 03-Oct-2026"
    assert r.acknowledgement_state(False, None) == "not yet acknowledged"
