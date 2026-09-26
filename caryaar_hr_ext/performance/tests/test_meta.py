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
