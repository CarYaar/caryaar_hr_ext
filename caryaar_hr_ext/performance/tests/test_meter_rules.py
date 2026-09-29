"""Pure rules of the goal meter (no Frappe): progress by method, windows, the 01-Nov gate."""
from datetime import date, datetime

from caryaar_hr_ext.performance import meter_rules as mr


def test_ratio_progress_is_capped_and_rounded():
    assert mr.progress_ratio(2.0, 5.0, "Higher is better") == 40.0
    assert mr.progress_ratio(7.0, 5.0, "Higher is better") == 100.0
    assert mr.progress_ratio(1.234, 3.0, "Higher is better") == 41.1


def test_ratio_with_missing_target_is_none():
    assert mr.progress_ratio(2.0, 0, "Higher is better") is None
    assert mr.progress_ratio(2.0, None, "Higher is better") is None
    assert mr.progress_ratio(None, 5.0, "Higher is better") is None


def test_lower_is_better_ratio():
    # target 24 h: 12 h is fully met; 48 h is half way
    assert mr.progress_ratio(12.0, 24.0, "Lower is better") == 100.0
    assert mr.progress_ratio(48.0, 24.0, "Lower is better") == 50.0


def test_months_meeting_standard_ignores_unjudged_months():
    assert mr.progress_months([True, False, None, True]) == 66.7
    assert mr.progress_months([]) is None and mr.progress_months([None]) is None


def test_meets_standard_by_direction():
    assert mr.meets_standard(99.6, 99.5, "Higher is better") is True
    assert mr.meets_standard(30.0, 24.0, "Lower is better") is False
    assert mr.meets_standard(None, 24.0, "Lower is better") is None


def test_windows_in_cycle():
    assert mr.window_bounds("Cycle to date", date(2026, 11, 12), date(2026, 10, 1)) == (date(2026, 10, 1), date(2026, 11, 12))
    assert mr.window_bounds("Latest full month", date(2026, 11, 12), date(2026, 10, 1)) == (date(2026, 10, 1), date(2026, 10, 31))
    assert mr.window_bounds("Latest full month", date(2026, 10, 12), date(2026, 10, 1)) == (date(2026, 10, 1), date(2026, 10, 12))
    assert mr.month_windows(date(2026, 10, 1), date(2026, 12, 3)) == [(date(2026, 10, 1), date(2026, 10, 31)),
                                                                     (date(2026, 11, 1), date(2026, 11, 30))]


def test_week_windows_are_monday_to_sunday_inside_the_cycle():
    # the cycle starts Thu 01-Oct-2026: the first week is Mon 05-Oct; a week counts once its Sunday has passed
    assert mr.week_windows(date(2026, 10, 1), date(2026, 10, 20)) == [(date(2026, 10, 5), date(2026, 10, 11)),
                                                                     (date(2026, 10, 12), date(2026, 10, 18))]
    assert mr.week_windows(date(2026, 10, 1), date(2026, 10, 18)) == [(date(2026, 10, 5), date(2026, 10, 11))]
    assert mr.week_windows(date(2026, 10, 5), date(2026, 10, 12)) == [(date(2026, 10, 5), date(2026, 10, 11))]
    assert mr.week_windows(date(2026, 10, 1), date(2026, 10, 11)) == []


def test_latest_full_week_falls_back_to_cycle_to_date():
    assert "Latest full week" in mr.WINDOWS
    assert mr.window_bounds("Latest full week", date(2026, 10, 20), date(2026, 10, 1)) == (date(2026, 10, 12), date(2026, 10, 18))
    assert mr.window_bounds("Latest full week", date(2026, 10, 4), date(2026, 10, 1)) == (date(2026, 10, 1), date(2026, 10, 4))


def test_progress_gate_is_first_november():
    assert mr.writes_progress(date(2026, 10, 31)) is False and mr.writes_progress(date(2026, 11, 1)) is True


def test_stale_and_overdue():
    assert mr.is_stale(datetime(2026, 10, 5, 23, 0), date(2026, 10, 6)) is True
    assert mr.is_stale(datetime(2026, 10, 6, 23, 59), date(2026, 10, 6)) is False
    assert mr.is_stale(None, date(2026, 10, 6)) is True
    assert mr.is_overdue(date(2026, 10, 5), "started", date(2026, 10, 6)) is True
    assert mr.is_overdue(date(2026, 10, 5), "completed", date(2026, 10, 6)) is False
    assert mr.is_overdue(None, "started", date(2026, 10, 6)) is False


def test_pct():
    assert mr.pct(3, 100) == 3.0 and mr.pct(0, 0) is None and mr.pct(1, 3) == 33.3


def test_module_progress_rule():
    assert mr.progress_module(4, 1) == 25.0 and mr.progress_module(0, 0) is None and mr.progress_module(2, 5) == 100.0


def test_pack_due_on_1st_15th_and_three_days_before_a_review():
    assert mr.pack_due_today(date(2026, 10, 1), []) and mr.pack_due_today(date(2026, 10, 15), [])
    assert not mr.pack_due_today(date(2026, 10, 9), [])
    assert mr.pack_due_today(date(2026, 10, 9), [date(2026, 10, 12)])
    assert not mr.pack_due_today(date(2026, 10, 9), [date(2026, 10, 13)])


def test_goal_meter_fixture_is_consistent():
    import json
    from pathlib import Path

    rows = json.loads((Path(__file__).resolve().parents[1] / "setup_data" / "goal_meters.json").read_text())
    assert len(rows) >= 60
    for r in rows:
        assert r["method"] in mr.METHODS and r.get("window", "Cycle to date") in mr.WINDOWS
        if r["method"] == "Ratio to target":
            assert r["metric"] and r["target_value"] > 0
        if r["method"] == "Months meeting standard":
            assert r["metric"] and r["standard_value"] is not None
        if r["method"] in ("Plane module", "Manual"):
            assert not r.get("metric")
    assert len({(r["employee"], r["kra"]) for r in rows}) == len(rows)


def test_recipients_merge_settings_list_and_manager():
    assert mr.recipients("a@caryaar.test\n\n b@caryaar.test \n", "m@caryaar.test") == ["a@caryaar.test", "b@caryaar.test", "m@caryaar.test"]
    assert mr.recipients(None, None) == []
    assert mr.recipients("", "m@caryaar.test") == ["m@caryaar.test"]


def test_manual_reading_problems_in_plain_words():
    assert mr.manual_reading_problem("Ratio to target", 1, "x", False) == "This goal is measured automatically."
    assert mr.manual_reading_problem("Manual", 0, "x", False) == "This goal's meter is switched off."
    assert "your own goal" in mr.manual_reading_problem("Manual", 1, "x", True)
    assert "Evidence is required" in mr.manual_reading_problem("Manual", 1, "  ", False)
    assert mr.manual_reading_problem("Manual", 1, "reviewed in 1:1", False) is None


def test_trend_points_every_fifteen_days_and_the_latest():
    days = [(date(2026, 10, 1) + __import__("datetime").timedelta(days=i), float(i)) for i in range(0, 20)]
    assert mr.trend_points(days) == [(date(2026, 10, 1), 0.0), (date(2026, 10, 16), 15.0), (date(2026, 10, 20), 19.0)]
    assert mr.trend_points([]) == []


def _goal(**over):
    g = {"goal": "G1", "goal_name": "Convert leads", "kra": "Customer Experience", "weight": 40,
         "method": "Ratio to target", "metric": "conversion_pct", "target": 5, "standard": None, "unit": "%",
         "direction": "Higher is better", "value": 2.5, "progress": 50.0, "stale": False, "erp_progress": 0,
         "trend": [(date(2026, 10, 1), 20.0), (date(2026, 10, 16), 50.0)], "items": [], "evidence": None}
    g.update(over)
    return g


def test_pack_rows_carry_source_target_trend_and_item_dates():
    item = {"project_identifier": "DEV", "sequence_id": 7, "title": "Fix login", "assignee_name": "Shiwans",
            "state_group": "completed", "start_date": "2026-10-01", "target_date": "2026-10-05",
            "completed_at": "2026-10-04 10:00:00", "overdue": False, "archived": True}
    pack = {"goals": [_goal(),
                      _goal(goal="G2", goal_name="Keep support on time", method="Months meeting standard",
                            metric="support_on_time_pct", target=None, standard=95, value=1, progress=100.0,
                            stale=True, erp_progress=100, trend=[], items=[item])]}
    g1, g2, row = mr.pack_rows(pack)
    assert g1["source"] == "CY Admin (conversion_pct)" and g1["target"] == "5%" and g1["in_appraisal"] == 0
    assert g1["trend"] == "20% (01-Oct-2026), 50% (16-Oct-2026)"
    assert g2["target"] == "95% or better each month" and "stale" in g2["flags"]
    assert row["text"] == "DEV-7 Fix login" and row["assignee"] == "Shiwans"
    assert row["start"] == "01-Oct-2026" and row["target"] == "05-Oct-2026"
    assert row["flags"] == "archived, done 04-Oct-2026"


def test_describe_meter_in_the_persons_words():
    assert mr.describe_meter(_goal()) == "Measured from CY Admin (conversion_pct) against a target of 5%."
    assert mr.describe_meter(_goal(method="Manual", metric=None, target=None)) == "Your manager updates this after each review."
    assert mr.describe_meter(_goal(method="Plane module", metric=None, target=None)) == "Share of the items in your Plane module that are done."
    assert mr.describe_meter(_goal(method="Months meeting standard", metric="support_on_time_pct", standard=95,
                                   target=None, direction="Higher is better")) == \
        "Months where support_on_time_pct (Plane items) was 95% or better."


def test_a_cycle_is_live_by_its_dates_not_only_its_status():
    d = date(2026, 10, 2)
    # HRMS never closes a cycle on its own: the live ERP still carries Mar-Sep 2026 as In Progress
    assert mr.cycle_is_live("In Progress", date(2026, 3, 1), date(2026, 9, 30), d) is False
    assert mr.cycle_is_live("In Progress", date(2026, 10, 1), date(2027, 3, 31), d) is True
    assert mr.cycle_is_live("Completed", date(2026, 10, 1), date(2027, 3, 31), d) is False
    # a cycle that has not begun still gets its meters, but is not shown to the person nor packed
    assert mr.cycle_is_live("Not Started", date(2026, 10, 1), date(2027, 3, 31), date(2026, 9, 30)) is True
    assert mr.cycle_is_live("Not Started", date(2026, 10, 1), date(2027, 3, 31), date(2026, 9, 30), started_only=True) is False
    assert mr.cycle_is_live("In Progress", None, None, d) is True
