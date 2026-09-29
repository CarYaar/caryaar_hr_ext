# Goal One on One and the one-pagers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A Goal One on One record in the ERP where the employee acknowledges their goals with their own login, and one branded artifact per employee built from the ERP that links to it.

**Architecture:** Pure rules in `performance/one_on_one_rules.py` (tested without Frappe); a new doctype pair (`Goal One on One`, child `Goal One on One Goal`) with a thin controller; a whitelisted acknowledge method in `performance/api.py`; permission hooks so the employee and the manager see their records; a notification created if missing by `performance/setup.py`; a generator under `scripts/goal_onepagers/` that reads the ERP over REST (`person_goals` plus Employee and template rows), renders `template.html`, and writes the published URL back with one `set_value`.

**Tech Stack:** Frappe 16 / HRMS 16 (caryaar_hr_ext), Python 3.10+, pytest with `tests/_frappe_stub.py`, Jinja2 for the template (available in the bench; the generator runs on the operator's Mac where it is installed with `pip install jinja2`), GSAP 3.13.0 from cdnjs on the page.

**Spec:** `docs/superpowers/specs/2026-09-29-goal-onepagers-and-acknowledgement-design.md`

## Global Constraints

- Business English, no em dashes, "Service Partners", dates DD-MMM-YYYY in anything a person reads.
- No emoji in the ERP or the page; lucide inline SVG only on the page.
- Every doctype JSON has `module` "Caryaar Hr Ext", `custom` 0, permissions for System Manager and HR Manager (test_meta.py checks the list of our doctypes; add the new names there).
- Doctype changes ship through the derived ERP image and `bench migrate` (Frappe 16 imports DocType JSON by content hash).
- The acknowledgement fields are written only by `acknowledge_goals`; the form cannot set them.
- The generator makes one write to the ERP, `one_pager_url`, and only with `--set-url`.

## Review Focus

1. A manager who holds only the Employee role and a self-scoped Employee user permission (Hiren, Kaushik) can open and edit the records of their reports. Pinned in Task 3 (`test_manager_sees_and_edits_reports_records`).
2. An acknowledgement attempted by HR or the manager on the employee's behalf is refused with a plain reason, and the record stays unacknowledged. Pinned in Task 3 (`test_only_the_employees_own_login_can_acknowledge`).
3. A record saved from the form with the acknowledgement fields edited is restored from the database. Pinned in Task 2 (`test_hand_edited_acknowledgement_is_restored`).
4. A person with goals but no meter yet gets rows with a blank target and blank source, never an exception. Pinned in Task 1 (`test_goal_rows_without_meter_or_reading`).
5. A page for a person with no goals says so, and a page for a person whose record is acknowledged shows the date. Pinned in Task 5 (`test_page_states`).

---

### Task 1: Pure rules

**Files:**
- Create: `caryaar_hr_ext/performance/one_on_one_rules.py`
- Test: `caryaar_hr_ext/performance/tests/test_one_on_one_rules.py`

**Interfaces:**
- Produces: `goal_rows(goals: list[dict], meters: dict[str, dict], readings: dict[str, dict], template_weights: dict[str, float]) -> list[dict]` with keys goal, goal_name, kra, weight, target_text, measured_from, progress; `can_acknowledge(session_user: str, employee_user: str | None, already: bool) -> str | None` (None means allowed); `acknowledgement_state(acknowledged: bool, acknowledged_on) -> str`.
- Consumes: `meter_rules.target_text(g)`, `meter_rules.source_text(g)`, `meter_rules.fmt_day(value)`.

- [ ] **Step 1: Write the failing tests**

```python
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
                       "target_text": "5%", "measured_from": "CY Admin (conversion_pct)", "progress": 40.0}
    assert rows[1]["target_text"] == "every item in the module done" and rows[1]["progress"] is None


def test_goal_rows_without_meter_or_reading():
    rows = r.goal_rows([{"name": "G", "goal_name": "Manual thing", "kra": "K"}], {}, {}, {})
    assert rows == [{"goal": "G", "goal_name": "Manual thing", "kra": "K", "weight": None, "target_text": "",
                     "measured_from": "", "progress": None}]


def test_only_the_employee_may_acknowledge_once():
    assert r.can_acknowledge("anagha@caryaar.test", "anagha@caryaar.test", already=False) is None
    assert r.can_acknowledge("Anagha@CarYaar.test", "anagha@caryaar.test", already=False) is None
    assert "your own" in r.can_acknowledge("hr@caryaar.test", "anagha@caryaar.test", already=False)
    assert "already" in r.can_acknowledge("anagha@caryaar.test", "anagha@caryaar.test", already=True)
    assert "no ERP login" in r.can_acknowledge("anagha@caryaar.test", None, already=False)


def test_acknowledgement_state_text():
    assert r.acknowledgement_state(True, datetime(2026, 10, 3, 11, 5)) == "acknowledged on 03-Oct-2026"
    assert r.acknowledgement_state(False, None) == "not yet acknowledged"
```

- [ ] **Step 2: Run to verify RED.** Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_one_on_one_rules.py -q -p no:cacheprovider`. Expected: FAIL with `ModuleNotFoundError: caryaar_hr_ext.performance.one_on_one_rules`.

- [ ] **Step 3: Implement**

```python
"""Pure rules of the goal 1:1 (no Frappe): the goals table filled from the cycle, who may
acknowledge, and the state text the one-pager and the list show."""
from __future__ import annotations

from datetime import date, datetime

from caryaar_hr_ext.performance import meter_rules as mr


def goal_rows(goals: list[dict], meters: dict[str, dict], readings: dict[str, dict],
              template_weights: dict[str, float]) -> list[dict]:
    """One row per goal: weight from the person's template row for the KRA, target and source from
    the meter, progress from the latest reading; blanks, never errors, where a piece is missing."""
    rows = []
    for g in goals:
        meter = meters.get(g["name"]) or {}
        reading = readings.get(g["name"]) or {}
        rows.append({"goal": g["name"], "goal_name": g.get("goal_name") or "", "kra": g.get("kra") or "",
                     "weight": template_weights.get(g.get("kra") or ""),
                     "target_text": mr.target_text(meter) if meter else "",
                     "measured_from": mr.source_text(meter) if meter else "",
                     "progress": reading.get("progress")})
    return rows


def can_acknowledge(session_user: str, employee_user: str | None, already: bool) -> str | None:
    """Why the stamp is refused, in plain words; None when the employee's own login may acknowledge."""
    if not employee_user:
        return "This employee has no ERP login, so the acknowledgement cannot be recorded."
    if (session_user or "").strip().lower() != employee_user.strip().lower():
        return "Only the employee can acknowledge their own goals from their own login."
    if already:
        return "These goals are already acknowledged."
    return None


def acknowledgement_state(acknowledged: bool, acknowledged_on: datetime | date | str | None) -> str:
    return f"acknowledged on {mr.fmt_day(acknowledged_on)}" if acknowledged and acknowledged_on else "not yet acknowledged"
```

- [ ] **Step 4: Run to verify GREEN.** Same command. Expected: 4 passed.
- [ ] **Step 5: Commit.** `git add caryaar_hr_ext/performance/one_on_one_rules.py caryaar_hr_ext/performance/tests/test_one_on_one_rules.py && git commit -m "feat(performance): pure rules for the goal 1:1 (rows, acknowledgement, state)"`

### Task 2: The doctypes and the controller

**Files:**
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/goal_one_on_one/goal_one_on_one.json`, `goal_one_on_one.py`, `__init__.py`; `caryaar_hr_ext/caryaar_hr_ext/doctype/goal_one_on_one_goal/goal_one_on_one_goal.json`, `goal_one_on_one_goal.py`, `__init__.py`
- Modify: `caryaar_hr_ext/performance/tests/test_meta.py` (add the two names to the list in `test_every_new_doctype_is_in_our_module_and_readable_by_hr` and the sync-role test, child excluded from permissions checks), `caryaar_hr_ext/performance/tests/_frappe_stub.py` (TARGET_MODULES + `fake.controllers["Goal One on One"]`)
- Test: `caryaar_hr_ext/performance/tests/test_meta.py`, `caryaar_hr_ext/performance/tests/test_one_on_one_unit.py`

**Interfaces:**
- Produces: doctype `Goal One on One` (fields in spec section 3), child `Goal One on One Goal`; controller `GoalOneOnOne.validate` (fills goals when empty, restores the three acknowledgement fields from the database on every save of an existing record), `GoalOneOnOne.fill_goals()` whitelisted document method; module function `cycle_goal_rows(employee, cycle) -> list[dict]` in the controller module (reads Goal, Goal Meter, latest Goal Meter Reading, the appraisee's template weights through `frappe.get_all`).
- Consumes: `one_on_one_rules.goal_rows`.

- [ ] **Step 1: Failing tests.** In `test_meta.py` add:

```python
def test_goal_one_on_one_doctype_shape():
    d = _load("goal_one_on_one"); f = _fields(d)
    for name, ftype in (("employee", "Link"), ("manager", "Link"), ("appraisal_cycle", "Link"), ("meeting_date", "Date"),
                        ("meeting_type", "Select"), ("goals", "Table"), ("notes", "Text Editor"), ("agreed_actions", "Small Text"),
                        ("one_pager_url", "Data"), ("employee_acknowledged", "Check"), ("acknowledged_on", "Datetime"),
                        ("acknowledged_by", "Link")):
        assert f[name]["fieldtype"] == ftype, name
    for name in ("employee_acknowledged", "acknowledged_on", "acknowledged_by"):
        assert f[name].get("read_only") == 1, name
    assert f["goals"]["options"] == "Goal One on One Goal" and d["autoname"] == "format:1ON1-{employee}-{meeting_date}"
    assert f["meeting_type"]["options"].split("\n") == ["Goal setting", "Monthly check-in", "Mid-cycle review", "Final review"]
    roles = {p["role"]: p for p in d["permissions"]}
    assert roles["Employee"]["read"] == 1 and roles["Employee"].get("write", 0) == 1 and roles["Employee"].get("delete", 0) == 0
    c = _fields(_load("goal_one_on_one_goal"))
    assert set(c) == {"goal", "goal_name", "kra", "weight", "target_text", "measured_from", "progress"} and _load("goal_one_on_one_goal")["istable"] == 1
```

  and in a new `test_one_on_one_unit.py` (stand-in):

```python
"""The goal 1:1 under the Frappe stand-in: goals filled from the cycle, hand-edited stamps restored."""
from datetime import date

import pytest

from caryaar_hr_ext.performance.tests import _frappe_stub as stub

CYCLE, EMP, MGR = "Cycle Oct-2026", "HR-EMP-00012", "HR-EMP-00003"


def _seed(fake):
    stub.seed(fake, "Appraisal Cycle", name=CYCLE, status="In Progress", start_date="2026-10-01")
    stub.seed(fake, "Employee", name=EMP, status="Active", user_id="anagha@caryaar.test", employee_name="Anagha", reports_to=MGR)
    stub.seed(fake, "Employee", name=MGR, status="Active", user_id="joel@caryaar.test", employee_name="Joel")
    stub.seed(fake, "Goal", name="HR-GOAL-1", goal_name="Lead to booking 5%", employee=EMP, appraisal_cycle=CYCLE, kra="Conversion", is_group=0, status="Pending")
    stub.seed(fake, "Goal Meter", name="GM-1", goal="HR-GOAL-1", employee=EMP, method="Ratio to target", metric="conversion_pct", target_value=5, unit="%", active=1)
    stub.seed(fake, "Appraisee", parent=CYCLE, parenttype="Appraisal Cycle", employee=EMP, appraisal_template="CX")
    stub.seed(fake, "Appraisal Template Goal", parent="CX", parenttype="Appraisal Template", key_result_area="Conversion", per_weightage=30)


def test_new_record_fills_the_goals_from_the_cycle(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 2))
    import frappe
    _seed(fake)
    doc = frappe.get_doc({"doctype": "Goal One on One", "employee": EMP, "manager": MGR, "appraisal_cycle": CYCLE,
                          "meeting_date": "2026-10-02", "meeting_type": "Goal setting"})
    doc.validate()
    assert [(g["goal"], g["weight"], g["target_text"]) for g in doc.goals] == [("HR-GOAL-1", 30.0, "5%")]


def test_hand_edited_acknowledgement_is_restored(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 2))
    import frappe
    _seed(fake)
    stub.seed(fake, "Goal One on One", name="1ON1-HR-EMP-00012-2026-10-02", employee=EMP, manager=MGR, appraisal_cycle=CYCLE,
              meeting_date="2026-10-02", meeting_type="Goal setting", employee_acknowledged=0, acknowledged_on=None, acknowledged_by=None)
    doc = frappe.get_doc("Goal One on One", "1ON1-HR-EMP-00012-2026-10-02")
    doc.employee_acknowledged, doc.acknowledged_by = 1, "hr@caryaar.test"
    doc.validate()
    assert doc.employee_acknowledged == 0 and doc.acknowledged_by is None
```

  The stand-in's `seed` stores child rows under their own doctype with `parent`; `frappe.get_all(child, filters={"parent": ...})` reads them. If `get_all` in the stub does not filter child rows by parent, extend the stub (test-only code) rather than the controller.

- [ ] **Step 2: RED.** Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_meta.py caryaar_hr_ext/performance/tests/test_one_on_one_unit.py -q -p no:cacheprovider`. Expected: FAIL (`KeyError` on the JSON load and `DoesNotExistError` or `KeyError` for the controller).
- [ ] **Step 3: Implement.** The parent JSON follows `goal_meter.json` (same top-level keys, `"modified": "2026-09-30 10:00:00.000000"`, `"track_changes": 1`, `"autoname": "format:1ON1-{employee}-{meeting_date}"`, `"title_field": "employee_name"`); fields in the spec's order with `fetch_from` for `employee_name` (`employee.employee_name`) and `manager_name` (`manager.employee_name`); `employee`, `meeting_date`, `meeting_type`, `employee_acknowledged` with `in_list_view: 1`; permissions rows: System Manager (all), HR Manager (all), Employee (read, write, create, no delete, no export). The child JSON has `istable: 1`, the seven fields (goal Link Goal, goal_name Data, kra Link KRA, weight Percent, target_text Data, measured_from Data, progress Percent) with `in_list_view: 1` on goal_name, kra, weight, target_text, progress; no permissions. Controller:

```python
import frappe
from frappe.model.document import Document

from caryaar_hr_ext.performance import one_on_one_rules as rules

ACK_FIELDS = ("employee_acknowledged", "acknowledged_on", "acknowledged_by")


def cycle_goal_rows(employee: str, cycle: str) -> list[dict]:
    goals = frappe.get_all("Goal", filters={"employee": employee, "appraisal_cycle": cycle, "is_group": 0},
                           fields=["name", "goal_name", "kra"], order_by="creation asc")
    meters = {m.goal: m for m in frappe.get_all("Goal Meter", filters={"goal": ("in", [g.name for g in goals])},
                                                fields=["goal", "method", "metric", "target_value as target", "unit", "standard_value as standard", "direction"])}
    readings = {}
    for r in frappe.get_all("Goal Meter Reading", filters={"goal": ("in", [g.name for g in goals])},
                            fields=["goal", "progress", "value", "reading_date"], order_by="reading_date desc"):
        readings.setdefault(r.goal, r)
    template = frappe.db.get_value("Appraisee", {"parent": cycle, "employee": employee}, "appraisal_template")
    weights = {t.key_result_area: float(t.per_weightage or 0) for t in frappe.get_all(
        "Appraisal Template Goal", filters={"parent": template}, fields=["key_result_area", "per_weightage"])} if template else {}
    return rules.goal_rows([dict(g) for g in goals], {k: dict(v) for k, v in meters.items()},
                           {k: dict(v) for k, v in readings.items()}, weights)


class GoalOneOnOne(Document):
    """One meeting between a manager and an employee about the cycle's goals. The acknowledgement
    fields are written only by performance.api.acknowledge_goals; the form cannot set them."""

    def validate(self):
        if not self.get("goals"):
            for row in cycle_goal_rows(self.employee, self.appraisal_cycle):
                self.append("goals", row)
        if not self.is_new():
            stored = frappe.db.get_value(self.doctype, self.name, list(ACK_FIELDS), as_dict=True) or {}
            for f in ACK_FIELDS:
                self.set(f, stored.get(f))

    @frappe.whitelist()
    def fill_goals(self):
        self.set("goals", [])
        for row in cycle_goal_rows(self.employee, self.appraisal_cycle):
            self.append("goals", row)
        return len(self.goals)
```

  Register the controller in the stand-in (`TARGET_MODULES` gets `"caryaar_hr_ext.caryaar_hr_ext.doctype.goal_one_on_one.goal_one_on_one"`, `fake.controllers["Goal One on One"] = ...GoalOneOnOne`). The stand-in's `Document` needs `append`, `set`, `is_new` and `get`; add what is missing to the stub, not to production code.

- [ ] **Step 4: GREEN.** Same command plus the whole suite: `python3 -m pytest caryaar_hr_ext/performance/tests -q -p no:cacheprovider`. Expected: all pass.
- [ ] **Step 5: Commit.** `git add caryaar_hr_ext/caryaar_hr_ext/doctype/goal_one_on_one caryaar_hr_ext/caryaar_hr_ext/doctype/goal_one_on_one_goal caryaar_hr_ext/performance/tests && git commit -m "feat(performance): Goal One on One doctype with goals filled from the cycle"`

### Task 3: Acknowledge action, permissions, notification

**Files:**
- Modify: `caryaar_hr_ext/performance/api.py` (add `acknowledge_goals`), `caryaar_hr_ext/hooks.py` (`permission_query_conditions`, `has_permission`, notification already handled by setup), `caryaar_hr_ext/performance/setup.py` (`FILES` includes the new notification file), `caryaar_hr_ext/performance/setup_data/notification.json` (append the "Goals acknowledged" notification)
- Create: `caryaar_hr_ext/performance/one_on_one_permissions.py`
- Test: `caryaar_hr_ext/performance/tests/test_one_on_one_unit.py`, `caryaar_hr_ext/performance/tests/test_setup_hooks.py`

**Interfaces:**
- Produces: `api.acknowledge_goals(name: str) -> dict` (whitelisted POST, any logged-in user; returns `{"ok": True, "acknowledged_on": ...}` or raises `frappe.ValidationError` with the rule's reason); `one_on_one_permissions.query_conditions(user) -> str` (SQL fragment: employee's or manager's own Employee, empty for HR Manager and System Manager); `one_on_one_permissions.has_permission(doc, ptype, user) -> bool`.
- Consumes: `one_on_one_rules.can_acknowledge`.

- [ ] **Step 1: Failing tests** (stand-in, in `test_one_on_one_unit.py`):

```python
def test_only_the_employees_own_login_can_acknowledge(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 2), roles=("Employee",), user="hr@caryaar.test")
    import frappe
    from caryaar_hr_ext.performance import api
    _seed(fake)
    stub.seed(fake, "Goal One on One", name="1ON1-HR-EMP-00012-2026-10-02", employee=EMP, manager=MGR, appraisal_cycle=CYCLE,
              meeting_date="2026-10-02", meeting_type="Goal setting", employee_acknowledged=0)
    with pytest.raises(frappe.ValidationError, match="own login"):
        api.acknowledge_goals("1ON1-HR-EMP-00012-2026-10-02")
    fake.session.user = "anagha@caryaar.test"
    out = api.acknowledge_goals("1ON1-HR-EMP-00012-2026-10-02")
    row = fake.db.store["Goal One on One"]["1ON1-HR-EMP-00012-2026-10-02"]
    assert out["ok"] and row["employee_acknowledged"] == 1 and row["acknowledged_by"] == "anagha@caryaar.test" and row["acknowledged_on"]
    with pytest.raises(frappe.ValidationError, match="already"):
        api.acknowledge_goals("1ON1-HR-EMP-00012-2026-10-02")


def test_manager_sees_and_edits_reports_records(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 2), roles=("Employee",), user="joel@caryaar.test")
    from caryaar_hr_ext.performance import one_on_one_permissions as p
    _seed(fake)
    cond = p.query_conditions("joel@caryaar.test")
    assert "HR-EMP-00003" in cond and "`tabGoal One on One`.manager" in cond and "`tabGoal One on One`.employee" in cond
    doc = type("D", (), {"employee": EMP, "manager": MGR})()
    assert p.has_permission(doc, "write", "joel@caryaar.test") is True
    assert p.has_permission(doc, "write", "anagha@caryaar.test") is True      # the employee edits notes on their own record
    assert p.has_permission(doc, "read", "kaushik@caryaar.test") is False
    fake.roles = ("HR Manager",)
    assert p.query_conditions("hr@caryaar.test") == "" and p.has_permission(doc, "delete", "hr@caryaar.test") is True
```

  and in `test_setup_hooks.py`: the notification file contains a doc named "Goals acknowledged" on document_type "Goal One on One", event "Value Change", value_changed "employee_acknowledged", recipients include humanresource@caryaar.com and the manager's user; the hooks module lists `permission_query_conditions["Goal One on One"]` and `has_permission["Goal One on One"]` pointing at the new module (import `caryaar_hr_ext.hooks` as a plain module; it has no Frappe imports at top level).

- [ ] **Step 2: RED.** Expected: `AttributeError: acknowledge_goals`, `ModuleNotFoundError`, and the JSON assertion.
- [ ] **Step 3: Implement.**

```python
# api.py
@frappe.whitelist(methods=["POST"])
def acknowledge_goals(name: str = "") -> dict:
    """The employee acknowledges the goals on their own Goal One on One record. Any logged-in user
    may call it; the rule decides, and only the employee's own login passes."""
    from frappe.utils import now_datetime

    from caryaar_hr_ext.performance import one_on_one_rules as rules

    doc = frappe.get_doc("Goal One on One", name)
    employee_user = frappe.db.get_value("Employee", doc.employee, "user_id")
    problem = rules.can_acknowledge(frappe.session.user, employee_user, bool(doc.get("employee_acknowledged")))
    if problem:
        frappe.throw(problem)
    stamp = now_datetime()
    doc.db_set({"employee_acknowledged": 1, "acknowledged_on": stamp, "acknowledged_by": frappe.session.user}, notify=True)
    doc.add_comment("Comment", f"Goals acknowledged by {frappe.session.user}")
    return {"ok": True, "acknowledged_on": str(stamp)}
```

```python
# one_on_one_permissions.py
"""Who sees a Goal One on One: HR and System Managers everything; everyone else their own
records as the employee or as the manager. The hook decides, so the self-scoped Employee
user permissions some managers carry do not hide their reports' records."""
import frappe

WIDE = ("HR Manager", "System Manager")


def _own_employee(user: str) -> str | None:
    return frappe.db.get_value("Employee", {"user_id": user}, "name")


def query_conditions(user: str | None = None) -> str:
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & set(WIDE):
        return ""
    emp = _own_employee(user)
    if not emp:
        return "1=0"
    return f"(`tabGoal One on One`.employee = {frappe.db.escape(emp)} or `tabGoal One on One`.manager = {frappe.db.escape(emp)})"


def has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & set(WIDE):
        return True
    emp = _own_employee(user)
    if not emp:
        return False
    if ptype == "delete":
        return False
    return emp in (doc.employee, doc.manager)
```

  hooks.py: `permission_query_conditions = {"Goal One on One": "caryaar_hr_ext.performance.one_on_one_permissions.query_conditions"}` and `has_permission = {"Goal One on One": "caryaar_hr_ext.performance.one_on_one_permissions.has_permission"}`. Notification doc appended to `setup_data/notification.json` in the same shape as the WFH ones (channel Email, event Value Change, value_changed employee_acknowledged, condition `doc.employee_acknowledged == 1`, recipients: the manager through the `manager` field's user (use the `receiver_by_document_field` "manager" on an Employee link is not supported, so recipients are `cc: humanresource@caryaar.com` plus `receiver_by_document_field: acknowledged_by` for the employee's copy, and the manager's user through a Python condition-free `receiver_by_role` is wrong; instead the message is sent to HR and the employee, and the manager gets the system notification through `send_system_notification: 1` with the manager assigned via `doc.manager_user` fetched field). Add `manager_user` (Data, fetch_from `manager.user_id`, hidden) to the parent JSON in this task so the notification can use `receiver_by_document_field: manager_user`. The stand-in's `frappe.get_roles(user)` returns `fake.roles`; `fake.session.user` is settable; `frappe.db.escape` may need adding to the stub as `lambda s: "'" + s.replace("'", "''") + "'"`.

- [ ] **Step 4: GREEN**, whole suite.
- [ ] **Step 5: Commit.** `git commit -am "feat(performance): acknowledge goals from the employee's own login; 1:1 visibility for managers; notification"`

### Task 4: Workspace shortcut, list defaults, rollout notes

**Files:**
- Modify: `caryaar_hr_ext/caryaar_hr_ext/workspace/performance_and_adherence/performance_and_adherence.json` (a shortcut "Goal 1:1s" to the list with `stats_filter` `{"employee_acknowledged": 0}` labelled "Not acknowledged"), the parent doctype JSON (`"sort_field": "meeting_date"`, `"sort_order": "DESC"`), spec section 5 (rollout notes: image perf7, migrate, the workspace check).
- Test: `test_meta.py` (`test_workspace_lists_goal_one_on_ones`: the workspace JSON `shortcuts` has an entry with `link_to` "Goal One on One").

- [ ] **Step 1: Failing test, RED, implement, GREEN** as above (the workspace JSON `shortcuts` list gets `{"color": "Purple", "doc_view": "List", "label": "Goal 1:1s", "link_to": "Goal One on One", "stats_filter": "{\"employee_acknowledged\": 0}", "type": "DocType"}`; bump the workspace `modified`).
- [ ] **Step 2: Commit.** `git commit -am "feat(performance): Goal 1:1s on the Performance and Adherence workspace"`

### Task 5: The one-pager generator and template

**Files:**
- Create: `scripts/goal_onepagers/build.py`, `scripts/goal_onepagers/template.html`, `scripts/goal_onepagers/fixture_anagha.json`, `scripts/goal_onepagers/README.md`
- Test: `scripts/goal_onepagers/test_build.py` (plain pytest, no Frappe; run with `python3 -m pytest scripts/goal_onepagers -q`)

**Interfaces:**
- Produces: `build.render(person: dict) -> str` (HTML), `build.person_payload(employee_id: str) -> dict` (REST reads: Employee, the cycle's appraisee template weights, `person_goals(email)`, the Goal One on One record for the cycle), CLI `python3 scripts/goal_onepagers/build.py <employee_id> [--out out/] [--set-url <employee_id> <url>] [--create-1on1 <manager_employee_id> <YYYY-MM-DD>]`.
- Consumes: `~/.config/caryaar/frappe.env` (FRAPPE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET) with `User-Agent: Mozilla/5.0` (Cloudflare refuses Python's default), `person_goals` output shape (`cycles[].goals[]` with goal_name, kra, weight, target, value, progress, source, how, trend, items; `next_review_on`, `learning_month`), `one_on_one_rules.acknowledgement_state`.

- [ ] **Step 1: Failing test**

```python
import json
from pathlib import Path

from scripts.goal_onepagers import build

FIX = json.loads((Path(__file__).parent / "fixture_anagha.json").read_text())


def test_page_carries_every_number_and_the_acknowledgement_link():
    html = build.render(FIX)
    for text in ("Anagha Khedekar", "Executive - Customer Experience", "01-Oct-2026", "31-Mar-2027", "Lead to booking conversion",
                 "5%", "CY Admin", "30%", "not yet acknowledged", "erp.caryaar.com/app/goal-one-on-one/1ON1-HR-EMP-00012-2026-10-02"):
        assert text in html, text
    assert "—" not in html and "prefers-reduced-motion" in html and "gsap" in html


def test_page_states():
    acked = dict(FIX, one_on_one=dict(FIX["one_on_one"], employee_acknowledged=1, acknowledged_on="2026-10-03 11:05:00"))
    assert "acknowledged on 03-Oct-2026" in build.render(acked)
    empty = dict(FIX, cycles=[])
    html = build.render(empty)
    assert "no goals" in html.lower() and "Anagha Khedekar" in html
```

  The fixture is one person, two goals (one ratio metric with a reading, one Plane module), template weights, a Goal One on One record not yet acknowledged, `next_review_on` "2027-01-15".

- [ ] **Step 2: RED.** `python3 -m pytest scripts/goal_onepagers -q -p no:cacheprovider`. Expected: `ModuleNotFoundError`.
- [ ] **Step 3: Implement.** `build.py` renders `template.html` with Jinja2 (`autoescape=True`); `person_payload` composes the REST calls; `--set-url` calls `frappe.client.set_value` on the record's `one_pager_url`; `--create-1on1` posts a Goal One on One (`frappe.client.insert`) with meeting_type Goal setting. `template.html`: brand tokens on `:root` with the dark blocks, Inter and Newsreader from Google Fonts, the road-and-car loop from the recap film's logo paths (an SVG group translated along a path with GSAP `MotionPathPlugin` from cdnjs, `repeat: -1`, `ease: "none"`, 40 seconds, paused when `prefers-reduced-motion`), goal cards with `gsap.from` on load from a visible resting state (`opacity: 1` in CSS; the tween only moves), KRA bars filled once. Every date through `fmt_day`. Copy in business English: the target, the baseline, "measured from", "how it is scored", "your 1:1 record".
- [ ] **Step 4: GREEN.** Then render the fixture to `scripts/goal_onepagers/out/fixture_anagha.html` and open it in a browser (Playwright screenshot at 400 px and 1200 px width) to check the layout; publish it as the review artifact for the founder.
- [ ] **Step 5: Commit.** `git add scripts/goal_onepagers && git commit -m "feat(performance): goal one-pager generator and template"`

### Task 6: Rollout

**Files:** spec section 5 (rollout record); memory `project_goal_onepagers_and_ack_2026_09_29`; Plane DEV-1241.

- [ ] Ship the ERP app: merge to main, build the derived image (perf7: replace `app/` on the VM with a `git archive` of the merged commit, `Dockerfile.perf7` from perf6 with the new label, build, verify the image carries `goal_one_on_one.json`), compose backup, bench backup, switch the four services plus frontend restart in one chain, `bench migrate`, verify the doctype and the workspace shortcut over REST.
- [ ] Founder reviews the fixture page; fix wording or motion once.
- [ ] After Maxson closes the goals: `--create-1on1` for the thirteen (manager = reports_to, meeting date = the 1:1 date), generate, publish, `--set-url`, and the founder shares each artifact with the person and the manager. Melita first needs her own ERP user (CORP-98).
- [ ] Verify with one real acknowledgement (Anagha or Shiwans on their own login): the fields stamp, the comment appears, the notification reaches HR and the manager, the page regenerated shows the date.
