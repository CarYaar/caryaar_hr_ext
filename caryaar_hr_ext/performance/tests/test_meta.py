import json
from pathlib import Path

from caryaar_hr_ext.performance import meter_rules as rules_mr
from caryaar_hr_ext.performance import rules

APP = Path(__file__).resolve().parents[2]
DT = APP / "caryaar_hr_ext" / "doctype"


def _load(name):
    return json.loads((DT / name / f"{name}.json").read_text())


def _fields(d):
    return {f["fieldname"]: f for f in d["fields"]}


def test_work_activity_day_has_every_metric_as_int():
    d = _load("work_activity_day")
    f = _fields(d)
    for key in sorted(set(rules.METRIC_KEYS["Plane"]) | set(rules.METRIC_KEYS["CY Admin"])):
        assert f[key]["fieldtype"] == "Int", key
    assert f["source"]["options"].split("\n") == list(rules.SOURCES)
    assert set(d["field_order"]) == set(f)


ROLE_FIELDS = {
    "section_funnel": ("jobs_from_bookings", "jobs_from_bookings_paid"),
    "section_marketing": ("campaigns_sent", "campaign_leads_reached", "pr_campaigns_sent", "pr_replies",
                          "creatives_rendered", "creatives_approved",
                          "leads_meta", "leads_google", "leads_whatsapp", "leads_web"),
    "section_ops": ("jobs_moved", "estimates_created", "partner_changes", "sweep_items_closed"),
    "section_partners": ("partners_created", "partners_verified", "partners_activated", "partner_documents",
                         "agreements_created", "agreements_approved", "agreements_signed",
                         "partner_checkins_closed"),
    "section_finance": ("payouts_triggered", "payments_collected_offline", "unpaid_cleared"),
    "section_plane": ("plane_items_completed",),
}


def _section_of(d, fieldname):
    f = _fields(d)
    section = None
    for name in d["field_order"]:
        if f[name]["fieldtype"] == "Section Break":
            section = name
        if name == fieldname:
            return section
    raise AssertionError(f"{fieldname} not in field_order")


def test_every_cy_admin_metric_is_a_field_on_the_doctype():
    d = _load("work_activity_day")
    f = _fields(d)
    for section, names in ROLE_FIELDS.items():
        assert f[section]["fieldtype"] == "Section Break", section
        for key in names:
            assert f[key]["fieldtype"] == "Int" and f[key].get("read_only") == 1, key
            assert key in rules.METRIC_KEYS["CY Admin"], key
            assert _section_of(d, key) == section, key
    # a section a person is not measured on stays hidden: every role section has a depends_on
    for section in ROLE_FIELDS:
        if section != "section_plane":
            assert f[section].get("depends_on", "").startswith("eval:"), section


def test_goal_meter_window_options_match_the_rules():
    from caryaar_hr_ext.performance import meter_rules as mr

    assert _fields(_load("goal_meter"))["window"]["options"].split("\n") == list(mr.WINDOWS)


def test_every_new_doctype_is_in_our_module_and_readable_by_hr():
    for name in ("work_activity_day", "work_adherence_day", "plane_module_progress", "performance_sync_settings", "goal_one_on_one"):
        d = _load(name)
        assert d["module"] == "Caryaar Hr Ext"
        assert d["custom"] == 0
        roles = {p["role"] for p in d["permissions"]}
        assert "System Manager" in roles and "HR Manager" in roles, name
        assert "modified" in d and "name" in d


def test_sync_role_has_no_doctype_permissions():
    # The intake endpoints check the role themselves; doctype permissions would only
    # open /api/resource writes that bypass validation.
    for name in ("work_activity_day", "work_adherence_day", "plane_module_progress", "performance_sync_settings"):
        assert "Performance Sync" not in {p["role"] for p in _load(name)["permissions"]}, name


def test_settings_shows_unmatched_goal_modules():
    f = _fields(_load("performance_sync_settings"))
    assert f["unmatched_goal_modules"]["read_only"] == 1


def test_settings_is_single_with_default_department_sources():
    d = _load("performance_sync_settings")
    assert d["issingle"] == 1
    default = _fields(d)["department_sources"]["default"]
    assert rules.parse_department_sources(default) == {"Operations - CAPL": ["CY Admin", "Plane"]}


FX = APP / "fixtures"


def _fx(name):
    return json.loads((FX / f"{name}.json").read_text())


def test_fixture_files_carry_no_per_site_metadata():
    for f in FX.glob("*.json"):
        for doc in json.loads(f.read_text()):
            for key in ("owner", "creation", "modified_by"):
                assert key not in doc, f"{f.name}: {key}"


SETUP = APP / "performance" / "setup_data"


def _setup(name):
    return json.loads((SETUP / f"{name}.json").read_text())


def test_workflow_fixture_matches_the_approved_design():
    wf = {w["name"]: w for w in _setup("workflow")}["Attendance Request Approval"]
    assert wf["document_type"] == "Attendance Request" and wf["is_active"] == 1 and wf["send_email_alert"] == 0
    t = {(x["state"], x["action"], x["allowed"]): x for x in wf["transitions"]}
    assert t[("Draft", "Send for Approval", "Employee")]["condition"] == 'doc.reason == "Work From Home"'
    assert t[("Pending", "Approve", "Employee")]["allow_self_approval"] == 0
    assert "cy_approver_user" in t[("Pending", "Approve", "Employee")]["condition"]


def test_new_custom_fields_present_with_cy_prefix():
    cf = {c["name"]: c for c in _fx("custom_field")}
    for name in ("Attendance Request-cy_reports_to", "Attendance Request-cy_approver_user",
                 "Goal-cy_plane_module", "Appraisal-cy_performance_category"):
        assert name in cf, name
    assert cf["Attendance Request-cy_reports_to"]["ignore_user_permissions"] == 1
    assert cf["Appraisal-cy_performance_category"]["allow_on_submit"] == 1
    assert all(c["fieldname"].startswith("cy_") for c in cf.values())


def test_performance_sync_role_fixture():
    assert "Performance Sync" in {r["name"] for r in _fx("role")}


def test_rating_report_guide_matches_handbook_bell_curve():
    from caryaar_hr_ext.caryaar_hr_ext.report.rating_distribution import rating_distribution as rd
    assert [g for _, g in rd.GUIDE] == [5, 15, 25, 50, 5]
    assert [c for c, _ in rd.GUIDE] == [name for _, name in rules.BANDS]


def test_dashboard_fixture_references_existing_charts_and_cards():
    charts = {c["name"] for c in _fx("dashboard_chart")}
    cards = {c["name"] for c in _fx("number_card")}
    dash = _fx("dashboard")[0]
    assert {c["chart"] for c in dash["charts"]} <= charts
    assert {c["card"] for c in dash["cards"]} <= cards


def test_live_wfh_records_are_not_fixtures_so_migrate_never_overwrites_hr_edits():
    import ast
    hooks = ast.literal_eval(
        (APP / "hooks.py").read_text().split("fixtures = ", 1)[1].split("\n]\n", 1)[0] + "\n]")
    dts = {f["dt"] for f in hooks}
    assert not dts & {"Workflow", "Notification", "Custom DocPerm"}
    assert "caryaar_hr_ext.performance.setup.ensure_wfh_approval_setup" in (APP / "hooks.py").read_text()
    for name in ("workflow", "notification", "custom_docperm"):
        assert not (FX / f"{name}.json").exists(), name
        assert _setup(name), name


def test_attendance_customisations_are_property_setters_so_hrms_upgrades_keep_them():
    import ast
    ps = {p["name"]: p for p in _fx("property_setter")}
    reason = ps["Attendance Request-reason-options"]
    assert (reason["doc_type"], reason["doctype_or_field"], reason["field_name"], reason["property"]) == (
        "Attendance Request", "DocField", "reason", "options")
    assert reason["value"].split("\n") == ["Work From Home", "On Duty", "Weekly Off"]
    for dt in ("Attendance", "Attendance Request"):
        p = ps[f"{dt}-main-allow_bulk_edit"]
        assert (p["doc_type"], p["doctype_or_field"], p["property"], p["value"]) == (
            dt, "DocType", "allow_bulk_edit", "1")
    hooks = ast.literal_eval(
        (APP / "hooks.py").read_text().split("fixtures = ", 1)[1].split("\n]\n", 1)[0] + "\n]")
    entry = next(f for f in hooks if f["dt"] == "Property Setter")
    # Exact names only: other live setters (e.g. the Attendance naming series) stay untouched.
    assert entry["filters"] == [["name", "in", sorted(ps)]]


WS_NAME = "Performance and Adherence"
WS_FILE = "performance_and_adherence.json"
HR_ONLY = {"HR Manager", "System Manager"}


def test_workspace_page_shows_our_cards_and_charts_to_hr_only():
    ws = json.loads((APP / "caryaar_hr_ext" / "workspace" / "performance_and_adherence" / WS_FILE).read_text())
    assert (ws["doctype"], ws["name"], ws["module"], ws["public"]) == ("Workspace", WS_NAME, "Caryaar Hr Ext", 1)
    assert {r["role"] for r in ws["roles"]} == HR_ONLY
    charts = {c["name"] for c in _fx("dashboard_chart")}
    cards = {c["name"] for c in _fx("number_card")}
    assert {c["chart_name"] for c in ws["charts"]} == charts
    assert {c["number_card_name"] for c in ws["number_cards"]} == cards
    blocks = json.loads(ws["content"])
    assert {b["data"]["chart_name"] for b in blocks if b["type"] == "chart"} == charts
    assert {b["data"]["number_card_name"] for b in blocks if b["type"] == "number_card"} == cards


def test_sidebar_links_every_screen_of_the_program():
    sb = json.loads((APP / "workspace_sidebar" / WS_FILE).read_text())
    assert (sb["doctype"], sb["name"], sb["app"], sb["standard"]) == ("Workspace Sidebar", WS_NAME, "caryaar_hr_ext", 1)
    links = {(i["link_type"], i["link_to"]) for i in sb["items"] if i["type"] == "Link"}
    program = {"Work Activity Day", "Work Adherence Day", "Plane Module Progress", "Performance Sync Settings"}
    assert ("Workspace", WS_NAME) in links
    assert {n for t, n in links if t == "DocType"} >= program | {"Goal One on One"}
    assert ("Report", "Rating Distribution") in links and ("Report", "Activity Summary") in links
    assert ("Dashboard", _fx("dashboard")[0]["name"]) in links


def test_goal_shortcuts_sit_above_the_charts_on_the_home_page():
    """29-Sep-2026, founder: 'where is the new screen, I don't see anything'. The v16 sidebar is the navigation
    people use, and the Home page's shortcut block had been placed under three charts, below the fold."""
    ws = json.loads((APP / "caryaar_hr_ext" / "workspace" / "performance_and_adherence" / WS_FILE).read_text())
    blocks = json.loads(ws["content"])
    first_chart = next(i for i, b in enumerate(blocks) if b["type"] == "chart")
    shortcuts = [i for i, b in enumerate(blocks) if b["type"] == "shortcut"]
    assert shortcuts and max(shortcuts) < first_chart


def test_desktop_icon_opens_the_sidebar_inside_frappe_hr_for_hr_only():
    icon = json.loads((APP / "desktop_icon" / WS_FILE).read_text())
    assert (icon["doctype"], icon["name"], icon["link_type"], icon["link_to"]) == (
        "Desktop Icon", WS_NAME, "Workspace Sidebar", WS_NAME)
    assert (icon["parent_icon"], icon["app"], icon["standard"]) == ("Frappe HR", "caryaar_hr_ext", 1)
    assert {r["role"] for r in icon["roles"]} == HR_ONLY


def test_app_level_desk_folders_hold_only_json():
    # Frappe imports every file in these folders, so a stray file breaks migrate.
    for folder in ("workspace_sidebar", "desktop_icon"):
        assert [p.name for p in (APP / folder).iterdir()] == [WS_FILE], folder


def test_setup_inserts_only_what_is_missing():
    from caryaar_hr_ext.performance import setup
    docs = [{"doctype": "Notification", "name": "A"}, {"doctype": "Notification", "name": "B"},
            {"doctype": "Custom DocPerm", "name": "x1", "parent": "Attendance Request", "role": "Employee", "permlevel": 0},
            {"doctype": "Workflow", "name": "Attendance Request Approval", "document_type": "Attendance Request"}]
    existing = {("Notification", "A"), ("Custom DocPerm", ("Attendance Request", "Employee", 0))}
    todo = setup.missing_docs(docs, lambda key: key in existing, lambda doctype: False)
    assert [d["name"] for d in todo] == ["B", "Attendance Request Approval"]
    # an existing workflow on the doctype (any name) is never duplicated
    assert setup.missing_docs(docs[3:], lambda key: False, lambda doctype: True) == []


def test_rating_distribution_is_computed_live_from_scores():
    from caryaar_hr_ext.caryaar_hr_ext.report.rating_distribution import rating_distribution as rd
    rows = rd.distribution([4.6, 3.8, 3.1, 2.5, 2.2, None, 0])
    got = {r["category"]: (r["people"], r["actual"]) for r in rows}
    assert got["Exceptional"] == (1, 20.0) and got["Fair"] == (2, 40.0)
    assert sum(r["people"] for r in rows) == 5  # unscored appraisals are left out


def test_bell_curve_report_and_chart_leave_out_the_founders_scorecard():
    from caryaar_hr_ext.caryaar_hr_ext.report.rating_distribution import rating_distribution as rd
    f = rd.curve_filters("Oct 2026 - Mar 2027")
    assert f["appraisal_cycle"] == "Oct 2026 - Mar 2027"
    assert f["appraisal_template"] == ("not in", list(rules.OFF_CURVE_TEMPLATES))
    chart = {c["name"]: c for c in _fx("dashboard_chart")}["Rating categories"]
    assert ["Appraisal", "appraisal_template", "not in", list(rules.OFF_CURVE_TEMPLATES)] in json.loads(chart["filters_json"])


# ─── Goal meter phase 1, Task 2 ───────────────────────────────────────────────
def _nf(name):
    d = _load(name)
    return {f["fieldname"]: f for f in d["fields"] if f["fieldtype"] not in ("Section Break", "Column Break", "Tab Break")}, d


def test_plane_work_item_doctype_shape():
    f, d = _nf("plane_work_item")
    assert d["autoname"] == "field:issue_id"
    for k in ("issue_id", "project_identifier", "sequence_id", "title", "assignee", "assignee_email", "state_group",
              "module_id", "labels", "start_date", "target_date", "completed_at", "created_at", "updated_at",
              "is_deleted", "synced_at"):
        assert k in f, k
    assert f["assignee"]["options"] == "Employee"
    assert f["state_group"]["options"].split("\n") == ["backlog", "unstarted", "started", "completed", "cancelled"]
    assert set(d["field_order"]) == {x["fieldname"] for x in d["fields"]}


def test_goal_meter_doctypes_shape():
    f, d = _nf("goal_meter")
    assert d["autoname"] == "field:goal" and f["goal"]["options"] == "Goal" and f["goal"].get("unique") == 1
    assert f["method"]["options"].split("\n") == ["Ratio to target", "Months meeting standard", "Plane module", "Manual"]
    assert f["window"]["options"].split("\n") == list(rules_mr.WINDOWS)
    r, _ = _nf("goal_meter_reading")
    for k in ("goal", "reading_date", "value", "progress", "method", "evidence", "stale", "written_to_goal", "computed_at", "entered_by"):
        assert k in r, k
    c, _ = _nf("company_metric_day")
    assert c["source"]["options"].split("\n") == ["CY Admin", "ERP"]


def test_settings_and_activity_fields_added():
    s, _ = _nf("performance_sync_settings")
    for k in ("plane_items_synced_through", "plane_items_full_pass_on", "review_pack_recipients"):
        assert k in s, k
    a, _ = _nf("work_activity_day")
    for k in ("leads_assigned_new", "bookings_within_7d", "followups_due", "followups_done_on_time", "leads_statused_48h"):
        assert a[k]["fieldtype"] == "Int", k


def test_plane_work_item_keeps_archived_apart_from_deleted_and_lists_every_module():
    f = _fields(_load("plane_work_item"))
    assert f["is_deleted"]["fieldtype"] == "Check" and f["is_archived"]["fieldtype"] == "Check"
    assert f["module_ids"]["fieldtype"] == "Small Text"


def test_goal_review_pack_report_is_not_open_to_hr_users():
    d = json.loads((APP / "caryaar_hr_ext" / "report" / "goal_review_pack" / "goal_review_pack.json").read_text())
    assert {r["role"] for r in d["roles"]} == {"HR Manager", "System Manager"}


def test_employee_reads_own_goal_meter_readings():
    d = _load("goal_meter_reading")
    f = _fields(d)
    assert f["employee"]["fieldtype"] == "Link" and f["employee"]["options"] == "Employee"
    assert f["employee"]["fetch_from"] == "goal.employee"
    perms = {p["role"]: p for p in d["permissions"]}
    assert perms["Employee"].get("read") == 1 and not perms["Employee"].get("write")


def test_goal_meter_metric_field_describes_every_key_and_role_sections_hide_when_empty():
    from caryaar_hr_ext.performance import meter_rules as mr

    f = _fields(_load("goal_meter"))
    for key in mr.SOURCE_OF:
        assert key in f["metric"]["description"], key
    w = _fields(_load("work_activity_day"))
    assert "Operations" not in w["section_ops"]["depends_on"]           # Nayan sits in Technology; agents sit in Operations
    assert "Partnerships" not in w["section_partners"]["depends_on"]    # Zoeb's row carries no partner keys


def test_goal_one_on_one_doctype_shape():
    d = _load("goal_one_on_one")
    f = _fields(d)
    for name, ftype in (("employee", "Link"), ("manager", "Link"), ("appraisal_cycle", "Link"), ("meeting_date", "Date"),
                        ("meeting_type", "Select"), ("goals", "Table"), ("notes", "Text Editor"),
                        ("agreed_actions", "Small Text"), ("one_pager_url", "Data"), ("employee_acknowledged", "Check"),
                        ("acknowledged_on", "Datetime"), ("acknowledged_by", "Link"), ("manager_user", "Data")):
        assert f[name]["fieldtype"] == ftype, name
    for name in ("employee_acknowledged", "acknowledged_on", "acknowledged_by"):
        assert f[name].get("read_only") == 1, name
    assert f["goals"]["options"] == "Goal One on One Goal"
    assert d["autoname"] == "format:1ON1-{employee}-{meeting_date}-{meeting_type}" and d["module"] == "Caryaar Hr Ext"
    assert f["meeting_type"]["options"].split("\n") == ["Goal setting", "Monthly check-in", "Mid-cycle review", "Final review"]
    roles = {p["role"]: p for p in d["permissions"]}
    assert roles["Employee"]["read"] == 1 and roles["Employee"].get("write", 0) == 1 and roles["Employee"].get("delete", 0) == 0
    assert "HR Manager" in roles and "System Manager" in roles
    c = _load("goal_one_on_one_goal")
    assert set(_fields(c)) == {"goal", "goal_name", "kra", "weight", "target_text", "measured_from", "progress"}
    assert c["istable"] == 1 and c["module"] == "Caryaar Hr Ext"


def test_workspace_lists_goal_one_on_ones():
    import json as _json

    w = _json.loads((APP / "caryaar_hr_ext" / "workspace" / "performance_and_adherence" / "performance_and_adherence.json").read_text())
    hit = [x for x in w["shortcuts"] if x["link_to"] == "Goal One on One"]
    assert len(hit) == 1 and hit[0]["label"] == "Goal 1:1s" and '"employee_acknowledged": 0' in hit[0]["stats_filter"]
    assert any(b.get("type") == "shortcut" and b["data"].get("shortcut_name") == "Goal 1:1s" for b in _json.loads(w["content"]))


def test_activity_summary_report_is_registered_for_hr():
    import json as _json

    r = _json.loads((APP / "caryaar_hr_ext" / "report" / "activity_summary" / "activity_summary.json").read_text())
    assert r["ref_doctype"] == "Work Activity Day" and r["report_type"] == "Script Report" and r["module"] == "Caryaar Hr Ext"
    assert {x["role"] for x in r["roles"]} == {"HR Manager", "System Manager"}
    w = _json.loads((APP / "caryaar_hr_ext" / "workspace" / "performance_and_adherence" / "performance_and_adherence.json").read_text())
    assert any(x["type"] == "Report" and x["link_to"] == "Activity Summary" for x in w["shortcuts"])

def test_controller_class_names_are_the_doctype_names_without_spaces():
    # Frappe's get_controller looks up doctype.replace(" ", ""); a wrong class makes migrate treat the doctype as orphaned and delete it
    import re

    for folder in sorted(p.name for p in DT.iterdir() if p.is_dir() and (p / f"{p.name}.json").exists()):
        doctype = _load(folder)["name"]
        code = (DT / folder / f"{folder}.py").read_text()
        assert re.search(rf"^class {doctype.replace(' ', '').replace('-', '')}\(", code, re.M), (folder, doctype)


def test_goal_one_on_one_survives_scoped_user_permissions_and_tracks_changes():
    d = _load("goal_one_on_one")
    f = _fields(d)
    # Hiren and Kaushik carry an Employee user permission that applies to every doctype; the hook decides
    # visibility, so both links must skip the user-permission check
    assert f["employee"].get("ignore_user_permissions") == 1 and f["manager"].get("ignore_user_permissions") == 1
    assert f["employee"].get("set_only_once") == 1
    assert d["track_changes"] == 1
    assert f["employee_user"]["fetch_from"] == "employee.user_id" and f["employee_user"].get("hidden") == 1
    js = (DT / "goal_one_on_one" / "goal_one_on_one.js").read_text()
    assert "acknowledge_goals" in js and "fill_goals" in js and "employee_user" in js
