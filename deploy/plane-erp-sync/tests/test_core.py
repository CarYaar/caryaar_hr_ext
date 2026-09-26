from datetime import date, datetime, timezone

from plane_erp_sync import core


def test_window_covers_yesterday_and_today_in_ist():
    now = datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)  # 00:30 IST on 2-Oct
    start, end, days = core.ist_window(now)
    assert days == [date(2026, 10, 1), date(2026, 10, 2)]
    assert start == datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)  # 1-Oct 00:00 IST
    assert end == now


def test_every_member_gets_a_row_for_every_day_even_with_zeros():
    days = [date(2026, 10, 1), date(2026, 10, 2)]
    rows = core.activity_rows(["a@caryaar.com", "b@caryaar.com"],
                              {("a@caryaar.com", days[1]): 5}, {("a@caryaar.com", days[1]): 1}, days)
    assert len(rows) == 4
    a2 = next(r for r in rows if r["email"] == "a@caryaar.com" and r["date"] == "2026-10-02")
    assert a2["metrics"] == {"activity_count": 5, "completed_count": 1}
    b1 = next(r for r in rows if r["email"] == "b@caryaar.com" and r["date"] == "2026-10-01")
    assert b1["metrics"] == {"activity_count": 0, "completed_count": 0}


def test_activity_for_non_members_is_still_sent():
    days = [date(2026, 10, 2)]
    rows = core.activity_rows([], {("x@caryaar.com", days[0]): 2}, {}, days)
    assert rows == [{"email": "x@caryaar.com", "date": "2026-10-02",
                     "metrics": {"activity_count": 2, "completed_count": 0}}]


def test_module_rows_shape_and_clamping():
    rows = core.module_rows([("m1", "DEV", "Q4 reliability", 10, 4), ("m2", "OPS", None, 0, 0)])
    assert rows[0] == {"module_id": "m1", "project_identifier": "DEV", "module_name": "Q4 reliability",
                       "total_issues": 10, "completed_issues": 4}
    assert rows[1]["module_name"] == ""


def test_chunks():
    assert [len(c) for c in core.chunks(list(range(4500)))] == [2000, 2000, 500]
    assert core.chunks([]) == []


def test_synced_through_is_iso_with_ist_offset():
    s = core.synced_through(datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc))
    assert s == "2026-10-02T00:30:00+05:30"
