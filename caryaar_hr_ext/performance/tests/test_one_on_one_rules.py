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
                       "kra_weight": 30.0, "kra_goals": 1, "baseline": "",
                       "target_text": "5%", "measured_from": "CY Admin (conversion_pct)", "progress": 40.0}
    assert rows[1]["target_text"] == "every item in the module done" and rows[1]["progress"] is None


def test_goal_rows_without_meter_or_reading():
    rows = r.goal_rows([{"name": "G", "goal_name": "Manual thing", "kra": "K"}], {}, {}, {})
    assert rows == [{"goal": "G", "goal_name": "Manual thing", "kra": "K", "weight": None, "kra_weight": None, "kra_goals": 1,
                     "target_text": "", "baseline": "", "measured_from": "", "progress": None}]


def test_goals_under_one_kra_share_its_weight():
    """29-Sep-2026: the verdict goals sit under KRAs that already had one (five people). HRMS averages the
    goals under a KRA and applies the KRA weight once, so neither the page nor the record may say 30% twice."""
    goals = [{"name": "A", "goal_name": "Leads to bookings", "kra": "Conversion"},
             {"name": "B", "goal_name": "Bookings to jobs", "kra": "Conversion"},
             {"name": "C", "goal_name": "Follow-ups", "kra": "Follow-ups"},
             {"name": "D", "goal_name": "One", "kra": "Thirds"}, {"name": "E", "goal_name": "Two", "kra": "Thirds"},
             {"name": "F", "goal_name": "Three", "kra": "Thirds"}]
    rows = r.goal_rows(goals, {}, {}, {"Conversion": 30.0, "Follow-ups": 20.0, "Thirds": 20.0})
    assert [(x["weight"], x["kra_weight"], x["kra_goals"]) for x in rows] == [
        (15.0, 30.0, 2), (15.0, 30.0, 2), (20.0, 20.0, 1), (6.7, 20.0, 3), (6.7, 20.0, 3), (6.7, 20.0, 3)]


def test_only_the_employee_may_acknowledge_once():
    assert r.can_acknowledge("anagha@caryaar.test", "anagha@caryaar.test", already=False) is None
    assert r.can_acknowledge("Anagha@CarYaar.test", "anagha@caryaar.test", already=False) is None
    assert "own login" in r.can_acknowledge("hr@caryaar.test", "anagha@caryaar.test", already=False)
    assert "already" in r.can_acknowledge("anagha@caryaar.test", "anagha@caryaar.test", already=True)
    assert "no ERP login" in r.can_acknowledge("anagha@caryaar.test", None, already=False)


def test_acknowledgement_state_text():
    assert r.acknowledgement_state(True, datetime(2026, 10, 3, 11, 5)) == "acknowledged on 03-Oct-2026"
    assert r.acknowledgement_state(False, None) == "not yet acknowledged"


def test_target_and_baseline_read_from_the_bold_label_paragraphs():
    """The 27-Sep-2026 goal descriptions are '<p><b>Label:</b> text</p>' paragraphs. A parser that turned
    every tag into a newline left the value on the line after the label, and every page lost its baselines."""
    d = ("<p><b>Target:</b> Rating from half of delivered jobs, from Jan-2027</p>"
         "<p><b>Baseline:</b> Not usable yet: 18 of 19 ratings are 1 star.</p><p><b>Measured from:</b> WMS &amp; CRM</p>")
    assert r.description_field(d, "baseline") == "Not usable yet: 18 of 19 ratings are 1 star."
    assert r.description_field(d, "target") == "Rating from half of delivered jobs, from Jan-2027"
    assert r.description_field(d, "measured from") == "WMS & CRM"
    assert r.description_field("", "target") == "" and r.description_field(None, "baseline") == ""


def test_goal_rows_fall_back_to_the_description_for_manual_targets_and_carry_the_baseline():
    goals = [{"name": "M", "goal_name": "Ratings", "kra": "CSAT",
              "description": "<p><b>Target:</b> half of delivered jobs</p><p><b>Baseline:</b> 18 of 19 read 1 star</p>"},
             {"name": "A", "goal_name": "Conversion", "kra": "Conv", "description": "<p><b>Target:</b> 3% then 5%</p>"}]
    rows = r.goal_rows(goals, {"M": {"method": "Manual"}, "A": {"method": "Ratio to target", "metric": "conversion_pct", "target": 5, "unit": "%"}}, {}, {})
    assert rows[0]["target_text"] == "half of delivered jobs" and rows[0]["baseline"] == "18 of 19 read 1 star"
    assert rows[1]["target_text"] == "5%" and rows[1]["baseline"] == ""          # the meter's target wins over the prose
