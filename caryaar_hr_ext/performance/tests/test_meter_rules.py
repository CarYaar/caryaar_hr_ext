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
