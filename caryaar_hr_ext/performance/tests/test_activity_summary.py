"""The Activity Summary report's pure part: one row per person, zero columns hidden, a total row."""
from caryaar_hr_ext.performance import activity_summary as a


ROWS = [
    {"employee": "E1", "employee_name": "Janhavi", "department": "Operations - CAPL", "source": "CY Admin",
     "calls_handled": 51, "jobs_from_bookings": 7, "campaigns_sent": 0, "activity_count": 0, "completed_count": 0},
    {"employee": "E1", "employee_name": "Janhavi", "department": "Operations - CAPL", "source": "Plane",
     "calls_handled": 0, "jobs_from_bookings": 0, "campaigns_sent": 0, "activity_count": 4, "completed_count": 1},
    {"employee": "E2", "employee_name": "Kaushik", "department": "Marketing - CAPL", "source": "CY Admin",
     "calls_handled": 0, "jobs_from_bookings": 0, "campaigns_sent": 10, "activity_count": 0, "completed_count": 0},
]


def test_one_row_per_person_with_both_sources_and_only_used_columns():
    columns, data = a.summarize(ROWS, ("calls_handled", "jobs_from_bookings", "campaigns_sent"))
    names = [c["fieldname"] for c in columns]
    assert names == ["employee_name", "department", "plane_actions", "plane_items", "calls_handled", "jobs_from_bookings", "campaigns_sent"]
    assert [c["label"] for c in columns][2:] == ["Plane actions", "Plane items completed", "Calls dialled or received", "Jobs from bookings", "Campaigns sent"]
    assert data[0] == {"employee": "E1", "employee_name": "Janhavi", "department": "Operations - CAPL", "plane_actions": 4, "plane_items": 1,
                       "calls_handled": 51, "jobs_from_bookings": 7, "campaigns_sent": 0}
    assert data[1]["campaigns_sent"] == 10 and data[1]["plane_actions"] == 0
    assert data[-1]["employee_name"] == "Total" and data[-1]["calls_handled"] == 51 and data[-1]["campaigns_sent"] == 10


def test_a_column_nobody_used_is_hidden_and_an_empty_range_gives_no_rows():
    columns, data = a.summarize(ROWS, ("calls_handled", "payouts_triggered"))
    assert "payouts_triggered" not in [c["fieldname"] for c in columns]
    assert a.summarize([], ("calls_handled",)) == ([], [])


def test_every_metric_has_a_label():
    from caryaar_hr_ext.performance import rules

    for key in rules.METRIC_KEYS["CY Admin"]:
        assert key in a.LABELS, key


def test_end_of_day_snapshots_are_not_summed():
    # leads_assigned, leads_untouched and followups_overdue are states at the end of a day, not work done
    rows = [{"employee": "E1", "employee_name": "Janhavi", "department": "Ops", "source": "CY Admin", "leads_assigned": 1454, "calls_handled": 5},
            {"employee": "E1", "employee_name": "Janhavi", "department": "Ops", "source": "CY Admin", "leads_assigned": 1460, "calls_handled": 3}]
    columns, data = a.summarize(rows, ("calls_handled", "leads_assigned", "leads_untouched", "followups_overdue"))
    assert [c["fieldname"] for c in columns] == ["employee_name", "department", "plane_actions", "plane_items", "calls_handled"]
    assert data[0]["calls_handled"] == 8 and "leads_assigned" not in data[0]


DAY_ROWS = [
    {"employee": "E2", "employee_name": "Kaushik", "department": "Marketing - CAPL", "role": "Marketing Executive", "source": "CY Admin",
     "activity_date": "2026-09-01", "leads_meta": 6, "campaigns_sent": 2},
    {"employee": "E3", "employee_name": "Priya", "department": "Marketing - CAPL", "role": "Marketing Intern", "source": "CY Admin",
     "activity_date": "2026-09-01", "leads_meta": 6, "campaigns_sent": 1},
    {"employee": "E2", "employee_name": "Kaushik", "department": "Marketing - CAPL", "role": "Marketing Executive", "source": "CY Admin",
     "activity_date": "2026-09-02", "leads_meta": 4, "campaigns_sent": 0},
    {"employee": "E1", "employee_name": "Janhavi", "department": "Operations - CAPL", "role": "Executive - Customer Experience", "source": "CY Admin",
     "activity_date": "2026-09-01", "leads_meta": 0, "campaigns_sent": 0, "calls_handled": 51},
]


def test_grouped_by_department_gives_one_row_per_department_and_team_counts_once():
    """Founder 29-Sep-2026: 'role wise / department wise summary, I have to scroll too far'. leads_meta is the
    team's number stamped on every marketing person, so a department (or the total) must not double it."""
    columns, data = a.summarize(DAY_ROWS, ("leads_meta", "campaigns_sent", "calls_handled"), by="department")
    assert [c["fieldname"] for c in columns] == ["label", "plane_actions", "plane_items", "leads_meta", "campaigns_sent", "calls_handled"]
    assert columns[0]["label"] == "Department"
    assert [d["label"] for d in data] == ["Marketing - CAPL", "Operations - CAPL", "Total"]
    assert data[0]["leads_meta"] == 10 and data[0]["campaigns_sent"] == 3
    assert data[-1]["leads_meta"] == 10 and data[-1]["campaigns_sent"] == 3 and data[-1]["calls_handled"] == 51


def test_grouped_by_role_uses_the_designation():
    columns, data = a.summarize(DAY_ROWS, ("leads_meta", "campaigns_sent", "calls_handled"), by="role")
    assert columns[0]["label"] == "Role"
    assert [d["label"] for d in data] == ["Executive - Customer Experience", "Marketing Executive", "Marketing Intern", "Total"]
    assert data[1]["leads_meta"] == 10 and data[2]["leads_meta"] == 6


def test_person_rows_still_carry_the_department_and_the_total_dedupes_team_counts():
    columns, data = a.summarize(DAY_ROWS, ("leads_meta", "campaigns_sent", "calls_handled"))
    assert [c["fieldname"] for c in columns][:2] == ["employee_name", "department"]
    assert {d["employee_name"]: d["leads_meta"] for d in data} == {"Janhavi": 0, "Kaushik": 10, "Priya": 6, "Total": 10}


def test_board_returns_cards_department_charts_in_rule_order_and_the_grouped_table():
    """Founder 29-Sep-2026 17:12: 'can we have a date filter on the dashboard'. One period feeds the tiles,
    the department charts and the table; a department filter keeps one chart."""
    rows = DAY_ROWS + [{"employee": "E4", "employee_name": "Shiwans", "department": "Technology - CAPL", "role": "Programmer",
                        "source": "Plane", "activity_date": "2026-09-02", "activity_count": 9, "completed_count": 4}]
    keys = ("leads_meta", "campaigns_sent", "calls_handled", "campaign_leads_reached", "jobs_moved", "followups_done_on_time", "partners_activated")
    b = a.board(rows, keys, by="department")
    assert [c["label"] for c in b["cards"]] == ["Calls dialled or received", "Follow-ups done on the day", "Job status moves", "Plane items completed",
                                                "Leads reached by campaigns", "Service Partners activated"]
    assert {c["label"]: c["value"] for c in b["cards"]}["Calls dialled or received"] == 51 and {c["label"]: c["value"] for c in b["cards"]}["Plane items completed"] == 4
    assert [c["department"] for c in b["charts"]] == ["Operations - CAPL", "Marketing - CAPL", "Technology - CAPL"]   # the rules' order, not alphabetical
    marketing = b["charts"][1]
    assert marketing["labels"][0] == "Leads reached by campaigns" and dict(zip(marketing["labels"], marketing["datasets"][0]["values"]))["New leads: Meta (team)"] == 10
    assert b["columns"][0]["label"] == "Department" and [r["label"] for r in b["rows"]][-1] == "Total"
    one = a.board(rows, keys, by="role", department="Technology - CAPL")
    assert [c["department"] for c in one["charts"]] == ["Technology - CAPL"] and one["columns"][0]["label"] == "Role"
    assert a.board([], keys) == {"cards": [{"label": l, "value": 0} for l, _k in a.BOARD_CARDS], "charts": [], "columns": [], "rows": []}
