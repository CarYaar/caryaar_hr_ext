from datetime import date, datetime

import pytest

from caryaar_hr_ext.performance import rules as r

IST_EOD = datetime(2026, 10, 1, 23, 59, 59)


# ---------- payload validation ----------
def _row(email="Janhavi.Nanaware@CarYaar.com", day="2026-10-01", **metrics):
    return {"email": email, "date": day, "metrics": metrics or {"calls_handled": 3}}


def test_valid_cy_admin_payload_normalises_email_and_parses_time():
    b = r.validate_activity_payload("CY Admin", "2026-10-02T00:15:00+05:30", [_row()], covers_from="2026-10-01")
    assert b.source == "CY Admin"
    assert b.rows[0].email == "janhavi.nanaware@caryaar.com"
    assert b.rows[0].metrics == {"calls_handled": 3}
    assert b.synced_through == datetime(2026, 10, 2, 0, 15)  # naive IST


def test_synced_through_in_utc_is_converted_to_ist():
    b = r.validate_activity_payload("Plane", "2026-10-01T18:45:00Z", [_row(activity_count=1)], covers_from="2026-10-01")
    assert b.synced_through == datetime(2026, 10, 2, 0, 15)


@pytest.mark.parametrize("source", ["plane", "Slack", "", None])
def test_unknown_source_rejected(source):
    with pytest.raises(ValueError, match="source"):
        r.validate_activity_payload(source, "2026-10-01T10:00:00+05:30", [_row()], covers_from="2026-10-01")


def test_role_metric_keys_are_accepted():
    # Every role's CY Admin metrics travel on the same payload as the contact-centre ones.
    b = r.validate_activity_payload("CY Admin", "2026-10-02T00:15:00+05:30",
                                    [_row(jobs_from_bookings=2, campaigns_sent=1, plane_items_completed=3)],
                                    covers_from="2026-10-01")
    assert b.rows[0].metrics == {"jobs_from_bookings": 2, "campaigns_sent": 1, "plane_items_completed": 3}


def test_metric_not_allowed_for_source_rejected():
    with pytest.raises(ValueError, match="calls_handled"):
        r.validate_activity_payload("Plane", "2026-10-01T10:00:00+05:30", [_row(calls_handled=1)], covers_from="2026-10-01")


def test_a_misspelt_role_metric_is_rejected_by_name():
    # a typo in the sender never becomes a silently dropped column
    with pytest.raises(ValueError, match="jobs_from_booking"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row(jobs_from_booking=1)],
                                    covers_from="2026-10-01")


@pytest.mark.parametrize("bad", [-1, 1.5, "3", True, 10**8])
def test_bad_metric_values_rejected(bad):
    with pytest.raises(ValueError):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row(calls_handled=bad)], covers_from="2026-10-01")


@pytest.mark.parametrize("day", ["2026-13-01", "01-10-2026", "", None])
def test_bad_dates_rejected(day):
    with pytest.raises(ValueError, match="date"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row(day=day)], covers_from="2026-10-01")


def test_naive_synced_through_rejected():
    with pytest.raises(ValueError, match="time zone"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00", [_row()], covers_from="2026-10-01")


def test_too_many_rows_rejected():
    with pytest.raises(ValueError, match="2000"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row()] * 2001, covers_from="2026-10-01")


def test_email_without_at_rejected():
    with pytest.raises(ValueError, match="email"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row(email="janhavi")], covers_from="2026-10-01")


def test_module_payload_valid_and_bounded():
    t, mods = r.validate_module_payload("2026-10-01T10:00:00+05:30", [
        {"module_id": "5f0c1c1e-8a55-4c3e-9d1a-0b7d7d1e2a10", "project_identifier": "DEV",
         "module_name": "Q4 reliability", "total_issues": 10, "completed_issues": 4}])
    assert mods[0].completed_issues == 4 and t == datetime(2026, 10, 1, 10, 0)
    with pytest.raises(ValueError, match="completed_issues"):
        r.validate_module_payload("2026-10-01T10:00:00+05:30", [
            {"module_id": "x", "project_identifier": "DEV", "module_name": "m",
             "total_issues": 2, "completed_issues": 3}])


# ---------- names ----------
def test_doc_names_are_deterministic():
    assert r.activity_doc_name("HR-EMP-00010", "2026-10-01", "CY Admin") == "WACT-HR-EMP-00010-2026-10-01-CYADMIN"
    assert r.activity_doc_name("HR-EMP-00010", "2026-10-01", "Plane") == "WACT-HR-EMP-00010-2026-10-01-PLANE"
    assert r.adherence_doc_name("HR-EMP-00010", "2026-10-01") == "WADH-HR-EMP-00010-2026-10-01"


# ---------- department sources ----------
def test_department_sources_parse_and_validate():
    assert r.parse_department_sources('{"Operations - CAPL": ["CY Admin", "Plane"]}') == {
        "Operations - CAPL": ["CY Admin", "Plane"]}
    assert r.parse_department_sources("") == {}
    with pytest.raises(ValueError):
        r.parse_department_sources('{"Operations - CAPL": ["Slack"]}')
    with pytest.raises(ValueError):
        r.parse_department_sources("not json")


# ---------- adherence ----------
def _ctx(**kw):
    base = dict(is_holiday=False, attendance_status="Present", expected_sources=("Plane",),
                fresh_sources=frozenset({"Plane"}), activity={}, wfh_requested=False, wfh_approved=False)
    base.update(kw)
    return r.DayContext(**base)


def test_visible_work_on_a_normal_day_passes():
    res = r.adherence_day(_ctx(activity={"Plane": {"activity_count": 2, "completed_count": 0}}))
    assert res.work_visible is True and res.checks_passed == 1 and res.checks_applicable == 1
    assert res.adherence_pct == 100.0


def test_no_activity_with_fresh_source_fails():
    res = r.adherence_day(_ctx())
    assert res.work_visible is False and res.adherence_pct == 0.0


def test_stale_source_makes_the_day_pending_not_failed():
    res = r.adherence_day(_ctx(fresh_sources=frozenset()))
    assert res.work_visible is None and res.checks_applicable == 0 and res.adherence_pct is None


@pytest.mark.parametrize("kw", [dict(is_holiday=True), dict(attendance_status="On Leave"),
                                dict(attendance_status="Absent")])
def test_no_checks_on_non_working_days(kw):
    res = r.adherence_day(_ctx(**kw))
    assert res.is_working_day is False and res.checks_applicable == 0


def test_cy_admin_activity_counts_for_customer_experience():
    res = r.adherence_day(_ctx(expected_sources=("CY Admin", "Plane"),
                               fresh_sources=frozenset({"CY Admin"}),
                               activity={"CY Admin": {"calls_handled": 5}}))
    assert res.work_visible is True


def test_one_fresh_source_quiet_and_one_stale_is_pending():
    res = r.adherence_day(_ctx(expected_sources=("CY Admin", "Plane"),
                               fresh_sources=frozenset({"Plane"})))
    assert res.work_visible is None


def test_wfh_day_approved_and_evidenced():
    res = r.adherence_day(_ctx(attendance_status="Work From Home", wfh_requested=True, wfh_approved=True,
                               activity={"Plane": {"activity_count": 4, "completed_count": 1}}))
    assert (res.wfh, res.wfh_approved, res.wfh_evidenced) == (True, True, True)
    assert res.checks_passed == 3 and res.checks_applicable == 3


def test_wfh_day_without_approval_or_completed_work():
    res = r.adherence_day(_ctx(attendance_status="Work From Home",
                               activity={"Plane": {"activity_count": 4, "completed_count": 0}}))
    assert res.wfh_approved is False and res.wfh_evidenced is False
    assert res.checks_passed == 1 and res.checks_applicable == 3


def test_half_day_is_a_working_day():
    assert r.adherence_day(_ctx(attendance_status="Half Day")).is_working_day is True


# ---------- goal progress and categories ----------
@pytest.mark.parametrize("total,done,expected", [(10, 4, 40.0), (3, 3, 100.0), (0, 0, None), (7, 0, 0.0)])
def test_module_progress(total, done, expected):
    assert r.module_progress(total, done) == expected


@pytest.mark.parametrize("score,cat", [(4.5, "Exceptional"), (4.49, "Excellent"), (3.75, "Excellent"),
                                        (3.74, "Good"), (3.0, "Good"), (2.99, "Fair"), (2.0, "Fair"),
                                        (1.99, "Non-Satisfactory"), (0.1, "Non-Satisfactory"),
                                        (0, None), (None, None)])
def test_performance_category_bands(score, cat):
    assert r.performance_category(score) == cat


# ---------- final-review fixes ----------
def test_stamp_advances_only_when_the_payload_covers_from_the_current_stamp_day():
    cur = datetime(2026, 10, 5, 10, 0)
    new = datetime(2026, 10, 8, 10, 0)
    assert r.advance_stamp(None, new, date(2026, 10, 8)) == new               # first sync
    assert r.advance_stamp(cur, new, date(2026, 10, 5)) == new                # contiguous backfill
    assert r.advance_stamp(cur, new, date(2026, 10, 7)) == cur                # gap: 6-Oct never sent
    assert r.advance_stamp(cur, datetime(2026, 10, 4), date(2026, 10, 4)) == cur  # never backwards


def test_first_real_sync_sets_the_stamp_despite_unset_and_placeholder_values():
    real = datetime(2026, 9, 26, 23, 42)
    unset = datetime(1, 1, 1)             # Frappe reads a never-set Datetime single back as 0001-01-01
    placeholder = datetime(1970, 1, 1)    # the Plane runner's stamp on row chunks
    assert r.advance_stamp(unset, real, date(2026, 8, 26)) == real
    assert r.advance_stamp(None, placeholder, date(2026, 8, 26)) is None
    assert r.advance_stamp(unset, placeholder, date(2026, 8, 26)) is None
    cur = datetime(2026, 9, 25, 10, 0)
    assert r.advance_stamp(cur, placeholder, date(2026, 9, 1)) == cur


def test_stored_stamp_reads_unset_values_as_never_synced():
    assert r.stored_stamp(None) is None
    assert r.stored_stamp("") is None
    assert r.stored_stamp(datetime(1, 1, 1)) is None
    assert r.stored_stamp("1970-01-01 00:00:00") is None
    assert r.stored_stamp("2026-09-26 23:42:07") == datetime(2026, 9, 26, 23, 42, 7)
    assert r.stored_stamp(datetime(2026, 9, 26, 23, 42, 7)) == datetime(2026, 9, 26, 23, 42, 7)


def test_pending_request_does_not_turn_an_office_day_into_a_wfh_day():
    res = r.adherence_day(_ctx(attendance_status="Present", wfh_requested=True,
                               activity={"Plane": {"activity_count": 3, "completed_count": 0}}))
    assert res.wfh is False and res.checks_applicable == 1 and res.adherence_pct == 100.0


def test_pending_request_with_no_attendance_yet_is_a_wfh_day():
    res = r.adherence_day(_ctx(attendance_status=None, wfh_requested=True))
    assert res.wfh is True and res.wfh_approved is False


@pytest.mark.parametrize("raw,expected", [
    ("5f0c1c1e-8a55-4c3e-9d1a-0b7d7d1e2a10", "5f0c1c1e-8a55-4c3e-9d1a-0b7d7d1e2a10"),
    ("https://pitstop.mycaryaar.com/caryaar/projects/257911e1-8d3e-430a-89ad-bf02a6cf9d06/modules/5F0C1C1E-8A55-4C3E-9D1A-0B7D7D1E2A10/",
     "5f0c1c1e-8a55-4c3e-9d1a-0b7d7d1e2a10"),
    ("  not a module  ", None), ("", None), (None, None)])
def test_module_id_is_extracted_from_whatever_was_pasted(raw, expected):
    assert r.extract_module_id(raw) == expected


def test_recompute_range_is_bounded_and_ordered():
    days = r.recompute_days("2026-10-01", "2026-10-03")
    assert [d.isoformat() for d in days] == ["2026-10-01", "2026-10-02", "2026-10-03"]
    with pytest.raises(ValueError, match="62"):
        r.recompute_days("2026-10-01", "2026-12-31")
    with pytest.raises(ValueError, match="before"):
        r.recompute_days("2026-10-05", "2026-10-01")


def test_covers_from_is_required_and_bounds_the_rows():
    with pytest.raises(ValueError, match="covers_from"):
        r.validate_activity_payload("Plane", "2026-10-02T00:15:00+05:30", [_row(activity_count=1)], covers_from=None)
    with pytest.raises(ValueError, match="before covers_from"):
        r.validate_activity_payload("Plane", "2026-10-02T00:15:00+05:30",
                                    [_row(day="2026-09-30", activity_count=1)], covers_from="2026-10-01")
    b = r.validate_activity_payload("Plane", "2026-10-02T00:15:00+05:30", [], covers_from="2026-10-01")
    assert b.covers_from == date(2026, 10, 1)


def test_founders_scorecard_never_gets_a_bell_curve_category():
    # D4: founders' goals sit under the Leadership scorecard but they are not on the curve.
    assert r.OFF_CURVE_TEMPLATES == ("Leadership - Company Scorecard",)
    assert r.stored_category(1, 4.6, "Leadership - Company Scorecard") == ""
    assert r.stored_category(1, 4.6, "Technology") == "Exceptional"
    assert r.stored_category(0, 4.6, "Technology") == ""       # draft scores stay provisional
    assert r.stored_category(1, None, "Technology") == ""


# ─── Plane work items (goal meter phase 1, Task 1) ────────────────────────────
from datetime import datetime as _dt

from caryaar_hr_ext.performance import rules


def _item(**kw):
    base = {"issue_id": "8f1e0d3a-1111-4444-8888-aaaaaaaaaaaa", "project_identifier": "DEV",
            "sequence_id": 1233, "title": "Goal meter: nightly readings", "assignee_email": "Shiwans.Vaishya@caryaar.com",
            "state_group": "started", "module_id": "0b2c-mod", "labels": ["cy-admin", "db"],
            "start_date": "2026-10-01", "target_date": "2026-10-10", "completed_at": None,
            "created_at": "2026-09-28T10:00:00+05:30", "updated_at": "2026-09-28T12:30:00+05:30", "is_deleted": False}
    base.update(kw)
    return base


def test_valid_work_items_payload_normalises_email_and_times():
    when, rows = rules.validate_work_items_payload("2026-09-28T13:00:00+05:30", [_item()])
    assert when == _dt(2026, 9, 28, 13, 0)
    row = rows[0]
    assert row.assignee_email == "shiwans.vaishya@caryaar.com"
    assert row.labels == ("cy-admin", "db") and row.state_group == "started"
    assert row.updated_at == _dt(2026, 9, 28, 12, 30) and row.completed_at is None


def test_work_item_without_assignee_or_module_is_allowed():
    _, rows = rules.validate_work_items_payload("2026-09-28T13:00:00+05:30",
                                                [_item(assignee_email=None, module_id=None, labels=[])])
    assert rows[0].assignee_email is None and rows[0].module_id is None and rows[0].labels == ()


def test_unknown_state_group_rejected():
    with pytest.raises(ValueError, match="state_group"):
        rules.validate_work_items_payload("2026-09-28T13:00:00+05:30", [_item(state_group="done")])


def test_work_items_over_max_rows_rejected():
    with pytest.raises(ValueError, match="at most"):
        rules.validate_work_items_payload("2026-09-28T13:00:00+05:30", [_item()] * (rules.MAX_ROWS + 1))


def test_work_item_title_is_clipped_to_140():
    _, rows = rules.validate_work_items_payload("2026-09-28T13:00:00+05:30", [_item(title="x" * 300)])
    assert len(rows[0].title) == 140


def test_new_cy_admin_metric_keys_are_accepted():
    for k in ("leads_assigned_new", "bookings_within_7d", "followups_due", "followups_done_on_time", "leads_statused_48h"):
        assert k in rules.METRIC_KEYS["CY Admin"], k


def test_work_item_carries_archived_flag_and_every_module():
    a, b = "0b2c0000-0000-4000-8000-000000000001", "0b2c0000-0000-4000-8000-000000000002"
    _, rows = rules.validate_work_items_payload("2026-09-28T13:00:00+05:30",
                                                [_item(module_id=a, module_ids=[a, b], is_archived=True)])
    assert rows[0].module_ids == (a, b) and rows[0].module_id == a
    assert rows[0].is_archived is True and rows[0].is_deleted is False


def test_work_item_module_ids_default_from_module_id():
    a = "0b2c0000-0000-4000-8000-000000000001"
    _, rows = rules.validate_work_items_payload("2026-09-28T13:00:00+05:30", [_item(module_id=a)])
    assert rows[0].module_ids == (a,)
    _, rows = rules.validate_work_items_payload("2026-09-28T13:00:00+05:30", [_item(module_id=None, module_ids=[])])
    assert rows[0].module_ids == () and rows[0].module_id is None


def test_parse_labels_is_case_insensitive():
    assert rules.parse_labels("Bug, incident ,RELEASE") == {"bug", "incident", "release"}
    assert rules.parse_labels(None) == set()
