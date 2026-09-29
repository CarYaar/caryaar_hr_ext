"""Pure rules behind the department and role views of activity (dashboard charts + the grouped report)."""
from datetime import date

from caryaar_hr_ext.performance import activity_groups as g


def _row(emp, dep, role, source, day, **m):
    return {"employee": emp, "employee_name": emp.title(), "department": dep, "role": role, "source": source,
            "activity_date": day, **m}


def test_period_bounds_cover_the_founders_four_windows_and_custom():
    today = date(2026, 9, 29)
    assert g.period_bounds("This month", today) == (date(2026, 9, 1), today)
    assert g.period_bounds("Last month", today) == (date(2026, 8, 1), date(2026, 8, 31))
    assert g.period_bounds("Last 7 days", today) == (date(2026, 9, 23), today)
    assert g.period_bounds("Last 30 days", today) == (date(2026, 8, 31), today)
    assert g.period_bounds("Custom", today, date(2026, 9, 10), date(2026, 9, 12)) == (date(2026, 9, 10), date(2026, 9, 12))
    assert g.period_bounds("Custom", today) == (date(2026, 9, 1), today)          # no dates given: this month
    assert g.period_bounds("nonsense", today) == (date(2026, 9, 1), today)


def test_every_department_has_its_own_metrics_and_unknown_ones_read_plane():
    assert g.metrics_for("Operations - CAPL")[:3] == ("calls_handled", "followups_done_on_time", "leads_statused_48h")
    assert "campaign_leads_reached" in g.metrics_for("Marketing - CAPL") and "leads_meta" in g.metrics_for("Marketing - CAPL")
    assert g.metrics_for("Technology - CAPL")[0] == "plane_items"
    assert g.metrics_for("Finance & Accounts - CAPL")[0] == "payouts_triggered"
    assert g.metrics_for("Workshop Relations - CAPL")[0] == "partners_activated"
    assert g.metrics_for("Something New - CAPL") == g.DEFAULT_METRICS == ("plane_items", "plane_actions")
    assert g.metrics_for(None) == g.DEFAULT_METRICS
    for dep, keys in g.DEPARTMENT_METRICS.items():
        for k in keys:
            assert k in g.LABELS or k in g.PLANE_KEYS, (dep, k)


def test_group_sums_by_department_dedupes_team_counts_per_day_and_sums_the_rest():
    """leads_meta is the team's number stamped on every marketing person: two people on one day
    must read 6, not 12; two days read 6 + 4. Personal counts add up across people."""
    rows = [_row("kaushik", "Marketing - CAPL", "Marketing Executive", "CY Admin", date(2026, 9, 1), leads_meta=6, campaigns_sent=2),
            _row("priya", "Marketing - CAPL", "Marketing Intern", "CY Admin", date(2026, 9, 1), leads_meta=6, campaigns_sent=1),
            _row("kaushik", "Marketing - CAPL", "Marketing Executive", "CY Admin", date(2026, 9, 2), leads_meta=4, campaigns_sent=0),
            _row("kaushik", "Marketing - CAPL", "Marketing Executive", "Plane", date(2026, 9, 2), activity_count=5, completed_count=1),
            _row("anagha", "Operations - CAPL", "Executive - Customer Experience", "CY Admin", date(2026, 9, 1), calls_handled=37)]
    keys = ("leads_meta", "campaigns_sent", "calls_handled")
    by_dep = g.group_sums(rows, "department", keys)
    assert by_dep["Marketing - CAPL"]["leads_meta"] == 10 and by_dep["Marketing - CAPL"]["campaigns_sent"] == 3
    assert by_dep["Marketing - CAPL"]["plane_items"] == 1 and by_dep["Marketing - CAPL"]["plane_actions"] == 5
    assert by_dep["Operations - CAPL"]["calls_handled"] == 37 and by_dep["Operations - CAPL"]["leads_meta"] == 0
    by_role = g.group_sums(rows, "role", keys)
    assert set(by_role) == {"Marketing Executive", "Marketing Intern", "Executive - Customer Experience"}
    assert by_role["Marketing Executive"]["leads_meta"] == 10 and by_role["Marketing Intern"]["leads_meta"] == 6
    by_person = g.group_sums(rows, "person", keys)
    assert by_person["kaushik"]["label"] == "Kaushik" and by_person["kaushik"]["leads_meta"] == 10
    everyone = g.group_sums(rows, "all", keys)
    assert list(everyone) == ["Total"] and everyone["Total"]["leads_meta"] == 10 and everyone["Total"]["campaigns_sent"] == 3


def test_group_sums_without_dates_treats_the_rows_as_one_day():
    rows = [{"employee": "a", "employee_name": "A", "department": "D", "source": "CY Admin", "leads_meta": 6, "calls_handled": 1},
            {"employee": "b", "employee_name": "B", "department": "D", "source": "CY Admin", "leads_meta": 6, "calls_handled": 2}]
    assert g.group_sums(rows, "department", ("leads_meta", "calls_handled"))["D"] == {
        "label": "D", "department": "D", "plane_actions": 0, "plane_items": 0, "leads_meta": 6, "calls_handled": 3}


def test_department_chart_lists_the_departments_metrics_in_order_with_labels():
    rows = [_row("shiwans", "Technology - CAPL", "Programmer", "Plane", date(2026, 9, 1), activity_count=12, completed_count=3),
            _row("nayan", "Technology - CAPL", "Tech Intern", "CY Admin", date(2026, 9, 1), jobs_moved=4, sweep_items_closed=2)]
    chart = g.department_chart("Technology - CAPL", rows)
    assert chart["labels"] == ["Plane items completed", "Plane actions", "Job status moves", "Sweep items closed"]
    assert chart["datasets"] == [{"name": "Technology", "values": [3, 12, 4, 2]}]
    assert chart["type"] == "bar"
    empty = g.department_chart("Technology - CAPL", [])
    assert empty["datasets"][0]["values"] == [0, 0, 0, 0]


def test_roadside_assistance_is_a_department_read_from_plane_for_now():
    """Founder 29-Sep-2026 18:40: a department of its own for RSA; Amey's work comes from Plane until the
    RSA tech exists in CY Admin. The board and the precedence rules must know the department by name."""
    from caryaar_hr_ext.performance import meter_rules as mr
    assert g.metrics_for("Roadside Assistance - CAPL")[:2] == ("plane_items", "plane_actions")
    assert "Roadside Assistance" in g.DEPARTMENT_METRICS
    assert mr.role_sources().get("Roadside Assistance") == ["Plane", "CY Admin"]
