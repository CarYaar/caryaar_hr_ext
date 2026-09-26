import json
from pathlib import Path

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


def test_every_new_doctype_is_in_our_module_and_readable_by_hr():
    for name in ("work_activity_day", "work_adherence_day", "plane_module_progress", "performance_sync_settings"):
        d = _load(name)
        assert d["module"] == "Caryaar Hr Ext"
        assert d["custom"] == 0
        roles = {p["role"] for p in d["permissions"]}
        assert "System Manager" in roles and "HR Manager" in roles, name
        assert "modified" in d and "name" in d


def test_sync_role_can_write_intake_doctypes_only():
    for name, can_write in (("work_activity_day", 1), ("plane_module_progress", 1),
                            ("performance_sync_settings", 1), ("work_adherence_day", 0)):
        perms = {p["role"]: p for p in _load(name)["permissions"]}
        assert bool(perms.get("Performance Sync", {}).get("write", 0)) == bool(can_write), name


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


def test_workflow_fixture_matches_the_approved_design():
    wf = {w["name"]: w for w in _fx("workflow")}["Attendance Request Approval"]
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
