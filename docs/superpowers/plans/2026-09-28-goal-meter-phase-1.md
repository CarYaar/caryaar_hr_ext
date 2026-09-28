# Goal Meter, phase 1: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** every goal in the Oct-2026 to Mar-2027 cycle that has a Plane or per-agent CY Admin source gets a nightly reading and, from 01-Nov-2026, its `Goal.progress` in the ERP; every Plane project's work items are mirrored in the ERP; managers and founders get a review pack per person on the 1st and 15th and before a review.

**Architecture:** three feeds into the ERP (Plane work items every 15 minutes from the existing `plane-erp-sync` container; per-agent CY Admin metrics through the existing hourly and nightly sync, plus a morning follow-up snapshot; the ERP's own tables read in place), one nightly meter in `caryaar_hr_ext.performance.meter` that writes `Goal Meter Reading` rows and `Goal.progress`, and one review pack builder used by a Script Report and a scheduled email. Pure rules live in `performance/rules.py` and a new `performance/meter_rules.py`, tested with plain pytest; Frappe-dependent code is tested on the staging clone.

**Tech Stack:** Frappe 16 / HRMS 16 app `caryaar_hr_ext` (Python 3.12, pytest for pure modules, Frappe test runner on staging); `deploy/plane-erp-sync` (psycopg, urllib, pytest); `caryaar-api` (FastAPI, SQLAlchemy async, Alembic, Celery beat, pytest with `l2` marker against `TEST_DATABASE_URL`).

**Spec:** `docs/superpowers/specs/2026-09-28-goal-meter-design.md` (decisions G1 to G11, metric catalogue in section 5). Phase 2 (company metrics, finance and HR metrics, Meta spend, Appraisal button) is a separate plan.

## Global Constraints

- Plane's database is read-only for us: the sync connects with `default_transaction_read_only=on` and only SELECTs (spec section 1).
- The ERP intakes accept only the `Performance Sync` role (and System Manager); CY Admin never uses the Administrator key (spec section 1).
- Readings are taken from 01-Oct-2026; `Goal.progress` is written only from **01-Nov-2026** (G8). The gate is one constant, `meter_rules.PROGRESS_GATE = date(2026, 11, 1)`.
- One writer of `Goal.progress`: `meter.run_meter`. The old `engine.update_goal_progress` is removed in Task 6.
- A source whose `synced_through` stamp is older than the reading date yields a reading marked stale that repeats the last value; a reading never lowers a goal because a feed was down (G11).
- Days and windows are IST; every bound datetime sent to Postgres from caryaar-api is a `datetime` object cast in SQL (`CAST(:x AS timestamptz)`), never an ISO string.
- Copy in labels and messages: business English, "Service Partners", dates DD-MMM-YYYY, no em dashes.
- No new Plane features: the only Plane write is module creation in Task 9, through the `cy-automation` token on the VM.

## Review Focus

1. An employee with two goals on one KRA where one is Manual with no reading: the appraisal average must ignore nothing HRMS would not ignore (HRMS averages all non-archived goals), so the pack must show the manual goal as "no reading" loudly. Pinned in Task 8 (`test_pack_flags_manual_goal_without_reading`).
2. A Plane item moved out of a goal's module after it was counted: the next reading drops it (module completion is recomputed from current membership, never accumulated). Pinned in Task 6 (`test_module_completion_uses_current_membership`).
3. A goal whose target is 0 or blank on a Ratio meter: progress is None (skipped), never a division error or 100 percent. Pinned in Task 5 (`test_ratio_with_missing_target_is_none`).
4. The Plane sync's daily full pass sends every item; the incremental pass sends only items updated since the stamp minus one day; a soft-deleted item arrives with `is_deleted` true and the ERP keeps it flagged, never deletes. Pinned in Task 4 (`test_full_pass_uses_epoch_since`) and Task 3 (`test_deleted_item_is_flagged_not_removed`).
5. The morning follow-up snapshot runs after midnight IST; a follow-up rescheduled during the day to a later date still counts as due that day and as done only if the agent touched the customer that day. Pinned in Task 7 (`test_followup_done_requires_a_touch_on_the_day`).

---

## File structure

`caryaar_hr_ext` (ERP app):
- `caryaar_hr_ext/performance/rules.py` (modify): work-item payload validation, METRIC_KEYS for the five new CY Admin metrics.
- `caryaar_hr_ext/performance/meter_rules.py` (create): pure progress, window, gate, stale and overdue rules.
- `caryaar_hr_ext/performance/meter.py` (create): metric evaluators, `run_meter(as_of)`, reading and progress writes.
- `caryaar_hr_ext/performance/api.py` (modify): `ingest_work_items`.
- `caryaar_hr_ext/performance/engine.py` (modify): `run_nightly` calls `meter.run_meter`; `update_goal_progress` removed.
- `caryaar_hr_ext/performance/review_pack.py` (create): `build_pack`, `send_review_packs`.
- `caryaar_hr_ext/performance/setup.py` (modify): `ensure_goal_meters`.
- `caryaar_hr_ext/performance/setup_data/goal_meters.json` (create): meter rows keyed by (employee, kra).
- `caryaar_hr_ext/caryaar_hr_ext/doctype/plane_work_item/`, `goal_meter/`, `goal_meter_reading/`, `company_metric_day/` (create): JSON + `.py` + `__init__.py`.
- `caryaar_hr_ext/caryaar_hr_ext/doctype/performance_sync_settings/performance_sync_settings.json` (modify): three fields.
- `caryaar_hr_ext/caryaar_hr_ext/doctype/work_activity_day/work_activity_day.json` (modify): five Int fields.
- `caryaar_hr_ext/caryaar_hr_ext/report/goal_review_pack/` (create): `.py`, `.js`, `.json`.
- `caryaar_hr_ext/templates/emails/review_pack.html` (create).
- `caryaar_hr_ext/fixtures/custom_field.json` (modify): `Appraisal-cy_next_review_on`.
- `caryaar_hr_ext/hooks.py` (modify): scheduler entries, after_migrate.
- `caryaar_hr_ext/performance/tests/test_rules.py`, `test_meter_rules.py` (create), `test_meta.py`, `test_integration.py` (modify).

`deploy/plane-erp-sync`:
- `plane_erp_sync/sql.py`, `core.py`, `main.py` (modify); `tests/test_core.py`, `tests/test_main.py` (modify).
- `ops/goal_modules.py` (create).

`caryaar-api`:
- `migrations/versions/267_agent_followup_snapshots.py` (create).
- `app/models/performance.py` (create): `AgentFollowupSnapshot`.
- `app/services/performance/agent_activity.py` (modify): five metrics, snapshot writer.
- `app/tasks/performance_activity_sync.py` (modify): morning snapshot beat at 00:05 IST.
- `tests/services/performance/test_agent_activity_pure.py`, `test_agent_activity_l2.py` (modify).

---

### Task 1: Work-item payload rules (pure)

**Files:**
- Modify: `caryaar_hr_ext/performance/rules.py` (after `validate_module_payload`)
- Test: `caryaar_hr_ext/performance/tests/test_rules.py`

**Interfaces:**
- Consumes: `_parse_aware`, `_parse_day`, `MAX_ROWS` from `rules.py`.
- Produces: `WORK_ITEM_STATES: tuple[str, ...]`, `class WorkItemRow(NamedTuple)`, `validate_work_items_payload(synced_through, items) -> tuple[datetime, list[WorkItemRow]]`.

- [ ] **Step 1: Write the failing tests**

```python
# append to caryaar_hr_ext/performance/tests/test_rules.py
from datetime import datetime

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
    assert when == datetime(2026, 9, 28, 13, 0)
    row = rows[0]
    assert row.assignee_email == "shiwans.vaishya@caryaar.com"
    assert row.labels == ("cy-admin", "db") and row.state_group == "started"
    assert row.updated_at == datetime(2026, 9, 28, 12, 30) and row.completed_at is None


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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd /Users/sahaib/caryaar/caryaar-erp/caryaar_hr_ext && python3 -m pytest caryaar_hr_ext/performance/tests/test_rules.py -q -k work_item`
Expected: FAIL with `AttributeError: module ... has no attribute 'validate_work_items_payload'`

- [ ] **Step 3: Implement the rules**

```python
# rules.py, after validate_module_payload
WORK_ITEM_STATES: tuple[str, ...] = ("backlog", "unstarted", "started", "completed", "cancelled")
TITLE_MAX = 140


class WorkItemRow(NamedTuple):
    issue_id: str
    project_identifier: str
    sequence_id: int
    title: str
    assignee_email: str | None
    state_group: str
    module_id: str | None
    labels: tuple[str, ...]
    start_date: str | None
    target_date: str | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime
    is_deleted: bool


def _opt_day(value) -> str | None:
    return None if value in (None, "") else _parse_day(value)


def _opt_aware(value) -> datetime | None:
    return None if value in (None, "") else _parse_aware(value)


def validate_work_items_payload(synced_through, items) -> tuple[datetime, list[WorkItemRow]]:
    """One intake call from the Plane sync: every non-draft work item changed since the
    sender's last stamp (or all of them on the daily full pass)."""
    when = _parse_aware(synced_through)
    if not isinstance(items, list):
        raise ValueError("items must be a list")
    if len(items) > MAX_ROWS:
        raise ValueError(f"at most {MAX_ROWS} items per call, got {len(items)}")
    out: list[WorkItemRow] = []
    for i, it in enumerate(items):
        if not isinstance(it, dict):
            raise ValueError(f"item {i} must be an object")
        issue_id = it.get("issue_id")
        if not isinstance(issue_id, str) or len(issue_id) < 8:
            raise ValueError(f"item {i} issue_id is missing")
        state = it.get("state_group")
        if state not in WORK_ITEM_STATES:
            raise ValueError(f"item {i} state_group must be one of {WORK_ITEM_STATES}, got {state!r}")
        email = it.get("assignee_email")
        if email is not None and (not isinstance(email, str) or "@" not in email):
            raise ValueError(f"item {i} assignee_email is not an email address: {email!r}")
        seq = it.get("sequence_id")
        if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0:
            raise ValueError(f"item {i} sequence_id must be a whole number")
        labels = it.get("labels") or []
        if not isinstance(labels, list) or any(not isinstance(x, str) for x in labels):
            raise ValueError(f"item {i} labels must be a list of strings")
        module_id = it.get("module_id")
        out.append(WorkItemRow(
            issue_id=issue_id, project_identifier=str(it.get("project_identifier") or "")[:20],
            sequence_id=seq, title=str(it.get("title") or "")[:TITLE_MAX],
            assignee_email=email.strip().lower() if email else None, state_group=state,
            module_id=str(module_id) if module_id else None, labels=tuple(labels),
            start_date=_opt_day(it.get("start_date")), target_date=_opt_day(it.get("target_date")),
            completed_at=_opt_aware(it.get("completed_at")), created_at=_parse_aware(it.get("created_at")),
            updated_at=_parse_aware(it.get("updated_at")), is_deleted=bool(it.get("is_deleted", False))))
    return when, out
```

Also add the five CY Admin metric keys (Task 7 sends them; the intake must accept them from the same release):

```python
METRIC_KEYS: dict[str, tuple[str, ...]] = {
    "Plane": ("activity_count", "completed_count"),
    "CY Admin": ("calls_handled", "calls_answered", "talk_seconds", "dispositions",
                 "status_moves", "notes_written", "bookings_credited",
                 "leads_assigned", "leads_untouched", "followups_overdue",
                 "leads_assigned_new", "bookings_within_7d", "followups_due",
                 "followups_done_on_time", "leads_statused_48h"),
}
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_rules.py -q`
Expected: all pass (existing tests untouched).

- [ ] **Step 5: Commit**

```bash
git add caryaar_hr_ext/performance/rules.py caryaar_hr_ext/performance/tests/test_rules.py
git commit -m "feat(performance): validate Plane work-item payloads; accept five new CY Admin metrics"
```

---

### Task 2: Doctypes and settings fields

**Files:**
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/plane_work_item/{__init__.py,plane_work_item.json,plane_work_item.py}`
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/goal_meter/{__init__.py,goal_meter.json,goal_meter.py}`
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/goal_meter_reading/{__init__.py,goal_meter_reading.json,goal_meter_reading.py}`
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/company_metric_day/{__init__.py,company_metric_day.json,company_metric_day.py}`
- Modify: `caryaar_hr_ext/caryaar_hr_ext/doctype/performance_sync_settings/performance_sync_settings.json`
- Modify: `caryaar_hr_ext/caryaar_hr_ext/doctype/work_activity_day/work_activity_day.json`
- Test: `caryaar_hr_ext/performance/tests/test_meta.py`

**Interfaces:**
- Produces doctype names and fields used by Tasks 3, 6, 8: `Plane Work Item` (autoname `field:issue_id`; fields `issue_id`, `project_identifier`, `sequence_id` Int, `title`, `assignee` Link Employee, `assignee_email`, `state_group` Select, `module_id`, `labels` Small Text, `start_date` Date, `target_date` Date, `completed_at` Datetime, `created_at` Datetime, `updated_at` Datetime, `is_deleted` Check, `synced_at` Datetime); `Goal Meter` (autoname `field:goal`; `goal` Link Goal unique, `employee` Link Employee fetch_from `goal.employee`, `method` Select `Ratio to target\nMonths meeting standard\nPlane module\nManual`, `metric` Data, `window` Select `Cycle to date\nLatest full month`, `target_value` Float, `standard_value` Float, `unit` Data, `direction` Select `Higher is better\nLower is better`, `source_note` Small Text, `active` Check default 1); `Goal Meter Reading` (naming `By script`, name `<goal>|<YYYY-MM-DD>`; `goal` Link Goal, `reading_date` Date, `value` Float, `progress` Percent, `method` Data, `evidence` Small Text, `stale` Check, `written_to_goal` Check, `computed_at` Datetime, `entered_by` Link User); `Company Metric Day` (naming By script `<metric>|<date>`; `metric` Data, `metric_date` Date, `value` Float, `detail` JSON, `source` Select `CY Admin\nERP`, `synced_at` Datetime). `Performance Sync Settings` gains `plane_items_synced_through` Datetime read-only, `plane_items_full_pass_on` Date read-only, `review_pack_recipients` Small Text (default the three founders' user ids, one per line). `Work Activity Day` gains Int fields `leads_assigned_new`, `bookings_within_7d`, `followups_due`, `followups_done_on_time`, `leads_statused_48h` (default 0).

- [ ] **Step 1: Write the failing meta test**

```python
# append to caryaar_hr_ext/performance/tests/test_meta.py (this file already loads doctype JSON files without Frappe)
import json
from pathlib import Path

DT = Path(__file__).resolve().parents[2] / "caryaar_hr_ext" / "doctype"


def _fields(name):
    d = json.loads((DT / name / f"{name}.json").read_text())
    return {f["fieldname"]: f for f in d["fields"] if f["fieldtype"] not in ("Section Break", "Column Break")}, d


def test_plane_work_item_doctype_shape():
    f, d = _fields("plane_work_item")
    assert d["autoname"] == "field:issue_id"
    for k in ("issue_id", "project_identifier", "sequence_id", "title", "assignee", "assignee_email", "state_group",
              "module_id", "labels", "start_date", "target_date", "completed_at", "created_at", "updated_at",
              "is_deleted", "synced_at"):
        assert k in f, k
    assert f["assignee"]["options"] == "Employee"
    assert f["state_group"]["options"].split("\n") == ["backlog", "unstarted", "started", "completed", "cancelled"]


def test_goal_meter_doctypes_shape():
    f, d = _fields("goal_meter")
    assert d["autoname"] == "field:goal" and f["goal"]["options"] == "Goal" and f["goal"].get("unique") == 1
    assert f["method"]["options"].split("\n") == ["Ratio to target", "Months meeting standard", "Plane module", "Manual"]
    assert f["window"]["options"].split("\n") == ["Cycle to date", "Latest full month"]
    r, _ = _fields("goal_meter_reading")
    for k in ("goal", "reading_date", "value", "progress", "method", "evidence", "stale", "written_to_goal", "computed_at", "entered_by"):
        assert k in r, k
    c, _ = _fields("company_metric_day")
    assert c["source"]["options"].split("\n") == ["CY Admin", "ERP"]


def test_settings_and_activity_fields_added():
    s, _ = _fields("performance_sync_settings")
    for k in ("plane_items_synced_through", "plane_items_full_pass_on", "review_pack_recipients"):
        assert k in s, k
    a, _ = _fields("work_activity_day")
    for k in ("leads_assigned_new", "bookings_within_7d", "followups_due", "followups_done_on_time", "leads_statused_48h"):
        assert a[k]["fieldtype"] == "Int", k
```

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_meta.py -q`
Expected: FAIL with `FileNotFoundError` for `plane_work_item.json`.

- [ ] **Step 3: Create the doctype files**

Copy the conventions of `plane_module_progress.json` (module `Caryaar Hr Ext`, `engine: InnoDB`, permissions System Manager full + HR Manager read/report/export). `plane_work_item.json`:

```json
{
 "doctype": "DocType", "name": "Plane Work Item", "module": "Caryaar Hr Ext", "custom": 0, "engine": "InnoDB",
 "autoname": "field:issue_id", "naming_rule": "By fieldname", "sort_field": "modified", "sort_order": "DESC",
 "track_changes": 0, "in_create": 1,
 "field_order": ["issue_id", "project_identifier", "sequence_id", "title", "col1", "assignee", "assignee_email",
                 "state_group", "module_id", "labels", "sec_dates", "start_date", "target_date", "completed_at",
                 "col2", "created_at", "updated_at", "is_deleted", "synced_at"],
 "fields": [
  {"fieldname": "issue_id", "fieldtype": "Data", "label": "Plane issue ID", "reqd": 1, "unique": 1},
  {"fieldname": "project_identifier", "fieldtype": "Data", "label": "Project", "in_list_view": 1, "in_standard_filter": 1},
  {"fieldname": "sequence_id", "fieldtype": "Int", "label": "Number", "in_list_view": 1},
  {"fieldname": "title", "fieldtype": "Data", "label": "Title", "length": 140, "in_list_view": 1},
  {"fieldname": "col1", "fieldtype": "Column Break"},
  {"fieldname": "assignee", "fieldtype": "Link", "label": "Assignee", "options": "Employee", "in_standard_filter": 1, "search_index": 1},
  {"fieldname": "assignee_email", "fieldtype": "Data", "label": "Assignee email"},
  {"fieldname": "state_group", "fieldtype": "Select", "label": "State", "options": "backlog\nunstarted\nstarted\ncompleted\ncancelled", "in_list_view": 1, "in_standard_filter": 1},
  {"fieldname": "module_id", "fieldtype": "Data", "label": "Plane module ID", "search_index": 1},
  {"fieldname": "labels", "fieldtype": "Small Text", "label": "Labels"},
  {"fieldname": "sec_dates", "fieldtype": "Section Break", "label": "Dates"},
  {"fieldname": "start_date", "fieldtype": "Date", "label": "Start date"},
  {"fieldname": "target_date", "fieldtype": "Date", "label": "Due date", "search_index": 1},
  {"fieldname": "completed_at", "fieldtype": "Datetime", "label": "Completed at"},
  {"fieldname": "col2", "fieldtype": "Column Break"},
  {"fieldname": "created_at", "fieldtype": "Datetime", "label": "Created in Plane"},
  {"fieldname": "updated_at", "fieldtype": "Datetime", "label": "Updated in Plane"},
  {"fieldname": "is_deleted", "fieldtype": "Check", "label": "Deleted or archived in Plane", "default": "0"},
  {"fieldname": "synced_at", "fieldtype": "Datetime", "label": "Synced at", "read_only": 1}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
  {"role": "HR Manager", "read": 1, "report": 1, "export": 1}
 ]
}
```

`goal_meter.json` fields (same envelope, `autoname: "field:goal"`):

```json
[
 {"fieldname": "goal", "fieldtype": "Link", "label": "Goal", "options": "Goal", "reqd": 1, "unique": 1, "in_list_view": 1},
 {"fieldname": "employee", "fieldtype": "Link", "label": "Employee", "options": "Employee", "fetch_from": "goal.employee", "read_only": 1, "in_list_view": 1, "in_standard_filter": 1},
 {"fieldname": "method", "fieldtype": "Select", "label": "Method", "options": "Ratio to target\nMonths meeting standard\nPlane module\nManual", "reqd": 1, "in_list_view": 1},
 {"fieldname": "metric", "fieldtype": "Data", "label": "Metric key", "description": "Blank for Plane module and Manual. See the metric catalogue in the design spec."},
 {"fieldname": "window", "fieldtype": "Select", "label": "Window", "options": "Cycle to date\nLatest full month", "default": "Cycle to date"},
 {"fieldname": "col1", "fieldtype": "Column Break"},
 {"fieldname": "target_value", "fieldtype": "Float", "label": "Target", "in_list_view": 1},
 {"fieldname": "standard_value", "fieldtype": "Float", "label": "Standard to meet each month"},
 {"fieldname": "unit", "fieldtype": "Data", "label": "Unit"},
 {"fieldname": "direction", "fieldtype": "Select", "label": "Direction", "options": "Higher is better\nLower is better", "default": "Higher is better"},
 {"fieldname": "source_note", "fieldtype": "Small Text", "label": "Where the number comes from"},
 {"fieldname": "active", "fieldtype": "Check", "label": "Active", "default": "1"}
]
```

Permissions for Goal Meter: System Manager full; HR Manager read/write/create/report; HR User read. `goal_meter_reading.json`: `naming_rule: "By script"`, autoname empty, fields listed in the Interfaces block, `progress` Percent, `entered_by` Link User; permissions System Manager full, HR Manager read/write/create/report, HR User read. `company_metric_day.json`: By script; fields `metric` Data reqd, `metric_date` Date reqd, `value` Float, `detail` JSON, `source` Select `CY Admin\nERP`, `synced_at` Datetime; permissions as Plane Work Item.

Each `.py` controller:

```python
# goal_meter_reading.py
import frappe
from frappe.model.document import Document


class GoalMeterReading(Document):
    def autoname(self):
        self.name = f"{self.goal}|{self.reading_date}"

    def validate(self):
        if self.progress is not None and not 0 <= float(self.progress) <= 100:
            frappe.throw("Progress must be between 0 and 100.")
```

```python
# company_metric_day.py
from frappe.model.document import Document


class CompanyMetricDay(Document):
    def autoname(self):
        self.name = f"{self.metric}|{self.metric_date}"
```

`plane_work_item.py` and `goal_meter.py`: plain `class ...(Document): pass`. Every folder gets an empty `__init__.py`.

Add to `performance_sync_settings.json` after `cy_admin_synced_through`: `{"fieldname": "plane_items_synced_through", "fieldtype": "Datetime", "label": "Plane work items synced through", "read_only": 1}`, `{"fieldname": "plane_items_full_pass_on", "fieldtype": "Date", "label": "Last full pass of Plane work items", "read_only": 1}`, and in a new section `sec_pack` "Review packs": `{"fieldname": "review_pack_recipients", "fieldtype": "Small Text", "label": "Review pack always goes to (one user per line)", "default": "maxson.lewis@caryaar.com\njoel.dsouza@caryaar.com\nsahaib.singh@caryaar.com"}`. Keep `field_order` in step.

Add to `work_activity_day.json` after `followups_overdue` (and to `field_order`): `leads_assigned_new` "Leads assigned that day", `bookings_within_7d` "Bookings within 7 days of assignment", `followups_due` "Follow-ups due that day", `followups_done_on_time` "Follow-ups done on the day", `leads_statused_48h` "Leads given a status within 48 h" (all Int, default "0").

- [ ] **Step 4: Run the meta tests**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_meta.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add caryaar_hr_ext/caryaar_hr_ext/doctype caryaar_hr_ext/performance/tests/test_meta.py
git commit -m "feat(performance): Plane Work Item, Goal Meter, Goal Meter Reading, Company Metric Day doctypes; settings and activity fields"
```

---

### Task 3: `ingest_work_items` intake

**Files:**
- Modify: `caryaar_hr_ext/performance/api.py` (after `ingest_module_progress`)
- Test: `caryaar_hr_ext/performance/tests/test_integration.py` (Frappe runner, staging)

**Interfaces:**
- Consumes: `rules.validate_work_items_payload`, `_email_map`, `_stamp`, `_set`.
- Produces: whitelisted `caryaar_hr_ext.performance.api.ingest_work_items(synced_through, items, full_pass=0) -> {"accepted": int, "unmapped": [..], "synced_through": iso|None}`.

- [ ] **Step 1: Write the failing integration test**

```python
# append to test_integration.py (these run with `bench --site <site> run-tests --module caryaar_hr_ext.performance.tests.test_integration` on staging)
def test_ingest_work_items_upserts_and_flags_deleted(self):
    from caryaar_hr_ext.performance import api
    item = {"issue_id": "11111111-2222-3333-4444-555555555555", "project_identifier": "DEV", "sequence_id": 9001,
            "title": "Test item", "assignee_email": None, "state_group": "started", "module_id": None, "labels": ["bug"],
            "start_date": None, "target_date": "2026-10-10", "completed_at": None,
            "created_at": "2026-10-01T09:00:00+05:30", "updated_at": "2026-10-01T09:00:00+05:30", "is_deleted": False}
    out = api.ingest_work_items("2026-10-01T10:00:00+05:30", [item])
    self.assertEqual(out["accepted"], 1)
    doc = frappe.get_doc("Plane Work Item", item["issue_id"])
    self.assertEqual(doc.state_group, "started"); self.assertEqual(doc.labels, "bug")
    item["state_group"] = "completed"; item["completed_at"] = "2026-10-02T18:00:00+05:30"; item["is_deleted"] = True
    api.ingest_work_items("2026-10-02T19:00:00+05:30", [item])
    doc.reload()
    self.assertEqual(doc.state_group, "completed"); self.assertEqual(doc.is_deleted, 1)   # flagged, never removed
    self.assertEqual(str(frappe.db.get_single_value("Performance Sync Settings", "plane_items_synced_through"))[:16],
                     "2026-10-02 19:00")
    frappe.delete_doc("Plane Work Item", item["issue_id"], force=True)


def test_ingest_work_items_full_pass_records_the_day(self):
    from caryaar_hr_ext.performance import api
    api.ingest_work_items("2026-10-03T00:30:00+05:30", [], full_pass=1)
    self.assertEqual(str(frappe.db.get_single_value("Performance Sync Settings", "plane_items_full_pass_on")), "2026-10-03")
```

- [ ] **Step 2: Run on staging to verify it fails**

Run (on the staging VM, inside the backend container): `bench --site erp.caryaar.com run-tests --module caryaar_hr_ext.performance.tests.test_integration`
Expected: FAIL with `AttributeError: ... 'ingest_work_items'`. (Staging must be running; Task 10 has the start command. If staging is down when this task is executed, record a Ruling and run it in Task 10.)

- [ ] **Step 3: Implement the intake**

```python
@frappe.whitelist(methods=["POST"])
def ingest_work_items(synced_through=None, items=None, full_pass=0):
    """Every Plane project's work items, upserted by issue id. A deleted or archived
    item arrives flagged and stays flagged: the review pack shows what happened to it."""
    frappe.only_for(("Performance Sync", "System Manager"))
    try:
        when, rows = rules.validate_work_items_payload(synced_through, items or [])
    except ValueError as e:
        frappe.throw(str(e), exc=frappe.ValidationError)
    emails = _email_map()
    accepted, unmapped = 0, set()
    for r in rows:
        emp = emails.get(r.assignee_email) if r.assignee_email else None
        if r.assignee_email and not emp:
            unmapped.add(r.assignee_email)
        values = {"project_identifier": r.project_identifier, "sequence_id": r.sequence_id, "title": r.title,
                  "assignee": emp, "assignee_email": r.assignee_email, "state_group": r.state_group,
                  "module_id": r.module_id, "labels": ",".join(r.labels), "start_date": r.start_date,
                  "target_date": r.target_date, "completed_at": r.completed_at, "created_at": r.created_at,
                  "updated_at": r.updated_at, "is_deleted": 1 if r.is_deleted else 0, "synced_at": now_datetime()}
        if frappe.db.exists("Plane Work Item", r.issue_id):
            frappe.db.set_value("Plane Work Item", r.issue_id, values, update_modified=False)
        else:
            frappe.get_doc({"doctype": "Plane Work Item", "issue_id": r.issue_id, **values}).insert(ignore_permissions=True)
        accepted += 1
    current = _stamp("plane_items_synced_through")
    if when.year > 1971 and (not current or when > current):   # chunk calls carry a 1970 placeholder
        _set("plane_items_synced_through", when)
    if int(full_pass or 0):
        _set("plane_items_full_pass_on", when.date())
    if unmapped:
        known = set(filter(None, (frappe.db.get_single_value(_SINGLE, "unmapped_emails") or "").split("\n")))
        _set("unmapped_emails", "\n".join(sorted(known | unmapped)))
    stamp = _stamp("plane_items_synced_through")
    return {"accepted": accepted, "unmapped": sorted(unmapped), "synced_through": stamp.isoformat() if stamp else None}
```

Also extend `get_sync_state` to include `"Plane items": plane_items_synced_through` and `"Plane items full pass": plane_items_full_pass_on` (as ISO strings or None); the sync reads both.

- [ ] **Step 4: Run the integration tests on staging**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add caryaar_hr_ext/performance/api.py caryaar_hr_ext/performance/tests/test_integration.py
git commit -m "feat(performance): ingest_work_items intake with full-pass and stamp rules"
```

---

### Task 4: Plane sync sends every project's work items

**Files:**
- Modify: `deploy/plane-erp-sync/plane_erp_sync/sql.py`, `core.py`, `main.py`
- Test: `deploy/plane-erp-sync/tests/test_core.py`, `tests/test_main.py`

**Interfaces:**
- Consumes: ERP `ingest_work_items`, `get_sync_state` keys `"Plane items"`, `"Plane items full pass"`.
- Produces: `sql.WORK_ITEMS_SQL`, `core.work_item_rows(rows) -> list[dict]`, `core.work_items_since(now_utc, stamp, full_pass_on) -> tuple[datetime, bool]`, `main.collect_work_items(conn, slug, since) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_core.py
from datetime import date, datetime, timezone
from plane_erp_sync import core, sql


def test_work_item_rows_shape_and_clipping():
    raw = [("id-1", "DEV", 12, "x" * 200, date(2026, 10, 1), date(2026, 10, 10), None,
            datetime(2026, 9, 28, 4, 30, tzinfo=timezone.utc), datetime(2026, 9, 28, 7, 0, tzinfo=timezone.utc),
            "started", False, "Shiwans@caryaar.com", "mod-1", "bug,db")]
    row = core.work_item_rows(raw)[0]
    assert row["issue_id"] == "id-1" and row["sequence_id"] == 12 and len(row["title"]) == 140
    assert row["labels"] == ["bug", "db"] and row["assignee_email"] == "shiwans@caryaar.com"
    assert row["start_date"] == "2026-10-01" and row["completed_at"] is None
    assert row["created_at"].endswith("+00:00") and row["is_deleted"] is False


def test_work_items_since_incremental_overlaps_one_day():
    now = datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc)
    since, full = core.work_items_since(now, "2026-10-02T11:00:00+05:30", "2026-10-02")
    assert full is False and since == datetime(2026, 10, 1, 5, 30, tzinfo=timezone.utc)


def test_full_pass_uses_epoch_since():
    now = datetime(2026, 10, 2, 19, 0, tzinfo=timezone.utc)   # 00:30 IST on 03-Oct
    since, full = core.work_items_since(now, "2026-10-02T23:50:00+05:30", "2026-10-02")
    assert full is True and since == datetime(1970, 1, 1, tzinfo=timezone.utc)


def test_first_ever_run_is_a_full_pass():
    assert core.work_items_since(datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc), None, None)[1] is True


def test_work_items_query_excludes_drafts_and_yaar_copies():
    assert "NOT i.is_draft" in sql.WORK_ITEMS_SQL and "yaar-space" in sql.WORK_ITEMS_SQL
    for t, cols in {"issues": {"sequence_id", "name", "start_date", "target_date", "archived_at", "updated_at"},
                    "labels": {"id", "name", "deleted_at"}, "label_issues": {"issue_id", "label_id", "deleted_at"}}.items():
        assert cols <= sql.REQUIRED_COLUMNS[t]
```

```python
# tests/test_main.py
def test_work_items_are_sent_in_chunks_then_final_stamp(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(main.erp, "call", lambda base, tok, method, body: calls.append((method, body)) or {"unmapped": []})
    items = [{"issue_id": f"i{n}"} for n in range(2001)]
    main.send_work_items("https://erp", "tok", items, "2026-10-02T11:00:00+05:30", full_pass=True)
    methods = [m for m, _ in calls]
    assert methods == [main.WORK_ITEMS_METHOD] * 3
    assert calls[0][1]["synced_through"].startswith("1970") and calls[1][1]["synced_through"].startswith("1970")
    assert calls[2][1] == {"synced_through": "2026-10-02T11:00:00+05:30", "items": [], "full_pass": 1}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd deploy/plane-erp-sync && python3 -m pytest tests -q`
Expected: FAIL on `work_item_rows`, `work_items_since`, `WORK_ITEMS_SQL`, `send_work_items` not found.

- [ ] **Step 3: Implement**

`sql.py`: extend `REQUIRED_COLUMNS` (issues += `sequence_id, name, project_id, start_date, target_date, created_at, updated_at, archived_at`; `labels: {id, name, deleted_at}`; `label_issues: {issue_id, label_id, deleted_at}`; `module_issues += created_at`; `issue_assignees += created_at`; `states: {id, group}`; `projects += identifier`) and add:

```python
WORK_ITEMS_SQL = """
SELECT i.id::text, p.identifier, i.sequence_id, i.name, i.start_date, i.target_date, i.completed_at,
       i.created_at, i.updated_at, coalesce(s."group", 'backlog') AS state_group,
       (i.deleted_at IS NOT NULL OR i.archived_at IS NOT NULL) AS is_deleted,
       (SELECT lower(u.email) FROM issue_assignees ia JOIN users u ON u.id = ia.assignee_id
         WHERE ia.issue_id = i.id AND ia.deleted_at IS NULL ORDER BY ia.created_at LIMIT 1) AS assignee_email,
       (SELECT mi.module_id::text FROM module_issues mi
         WHERE mi.issue_id = i.id AND mi.deleted_at IS NULL ORDER BY mi.created_at LIMIT 1) AS module_id,
       (SELECT string_agg(l.name, ',' ORDER BY l.name) FROM label_issues li JOIN labels l ON l.id = li.label_id
         WHERE li.issue_id = i.id AND li.deleted_at IS NULL AND l.deleted_at IS NULL) AS labels
FROM issues i
JOIN projects p ON p.id = i.project_id AND p.deleted_at IS NULL
JOIN workspaces w ON w.id = i.workspace_id AND w.slug = %(slug)s
LEFT JOIN states s ON s.id = i.state_id
WHERE NOT i.is_draft
  AND coalesce(i.external_source, '') <> 'yaar-space'
  AND greatest(i.updated_at, coalesce(i.deleted_at, i.updated_at)) >= %(since)s
"""
```

`core.py`:

```python
EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
FULL_PASS_HOUR_IST = 0


def work_item_rows(rows) -> list[dict]:
    out = []
    for (iid, pid, seq, title, start, target, done, created, updated, state, deleted, email, module, labels) in rows:
        out.append({"issue_id": str(iid), "project_identifier": pid or "", "sequence_id": int(seq or 0),
                    "title": (title or "")[:140], "assignee_email": (email or "").lower() or None,
                    "state_group": state, "module_id": str(module) if module else None,
                    "labels": [x for x in (labels or "").split(",") if x],
                    "start_date": start.isoformat() if start else None, "target_date": target.isoformat() if target else None,
                    "completed_at": done.astimezone(timezone.utc).isoformat() if done else None,
                    "created_at": created.astimezone(timezone.utc).isoformat(),
                    "updated_at": updated.astimezone(timezone.utc).isoformat(), "is_deleted": bool(deleted)})
    return out


def work_items_since(now_utc: datetime, stamp: str | None, full_pass_on: str | None) -> tuple[datetime, bool]:
    """Incremental from the ERP stamp minus one day; a full pass on the first run and once a day
    in the first IST hour, so a missed edit or a soft delete always heals within a day."""
    today = now_utc.astimezone(IST).date()
    if not stamp or (now_utc.astimezone(IST).hour == FULL_PASS_HOUR_IST and (not full_pass_on or date.fromisoformat(full_pass_on) < today)):
        return EPOCH, True
    return datetime.fromisoformat(stamp).astimezone(timezone.utc) - timedelta(days=1), False
```

`main.py`:

```python
WORK_ITEMS_METHOD = "caryaar_hr_ext.performance.api.ingest_work_items"


def collect_work_items(conn, slug: str, since: datetime) -> list[dict]:
    return core.work_item_rows(conn.execute(sql.WORK_ITEMS_SQL, {"slug": slug, "since": since}).fetchall())


def send_work_items(base: str, token: str, items: list[dict], stamp: str, full_pass: bool) -> set[str]:
    unmapped: set[str] = set()
    for part in core.chunks(items):
        out = erp.call(base, token, WORK_ITEMS_METHOD, {"synced_through": "1970-01-01T00:00:00+05:30", "items": part})
        unmapped |= set(out.get("unmapped", []))
    erp.call(base, token, WORK_ITEMS_METHOD, {"synced_through": stamp, "items": [], "full_pass": 1 if full_pass else 0})
    return unmapped
```

In `run_once`: after the module send, `since, full = core.work_items_since(now, state.get("Plane items"), state.get("Plane items full pass"))`; `items = collect_work_items(conn, slug, since)` (inside the same `with connect()` block: move the work-item collection into `collect` or open the connection once around both); `unmapped |= send_work_items(base, token, items, stamp, full)`; add `"items": len(items), "full_pass": full` to the returned dict and to the dry-run JSON.

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest tests -q`
Expected: PASS, including the existing stamp tests.

- [ ] **Step 5: Dry run against the real Plane DB (read-only) from the VM**

Run: `gcloud compute ssh caryaar-plane --zone asia-south1-a --project caryaar-api-dev --tunnel-through-iap --command 'sudo docker exec plane-erp-sync python -m plane_erp_sync.main --dry-run | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d[\"rows\"]), d.get(\"items\", \"n/a\"))"'` after the image is rebuilt (Task 10 has the rebuild command; until then run the module locally with `PLANE_DB_HOST` over an SSH tunnel is not available, so this step executes in Task 10).
Expected: the item count equals the workspace's non-draft items (about 1,400 at 28-Sep-2026).

- [ ] **Step 6: Commit**

```bash
git add deploy/plane-erp-sync
git commit -m "feat(plane-sync): mirror every project's work items into the ERP with a daily full pass"
```

---

### Task 5: Meter rules (pure)

**Files:**
- Create: `caryaar_hr_ext/performance/meter_rules.py`
- Test: `caryaar_hr_ext/performance/tests/test_meter_rules.py`

**Interfaces:**
- Produces: `PROGRESS_GATE`, `METHODS`, `WINDOWS`, `progress_ratio(value, target, direction) -> float | None`, `progress_months(met: Sequence[bool | None]) -> float | None`, `progress_module(total, done) -> float | None`, `window_bounds(window, as_of, cycle_start) -> tuple[date, date]`, `month_windows(cycle_start, as_of) -> list[tuple[date, date]]`, `meets_standard(value, standard, direction) -> bool | None`, `writes_progress(as_of) -> bool`, `is_stale(stamp, as_of) -> bool`, `is_overdue(target_date, state_group, as_of) -> bool`, `pct(n, d) -> float | None`.

- [ ] **Step 1: Write the failing tests**

```python
from datetime import date, datetime
import pytest
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
    # target 24 h, value 12 h -> fully met; value 48 h -> half
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
    assert mr.window_bounds("Latest full month", date(2026, 10, 12), date(2026, 10, 1)) == (date(2026, 10, 1), date(2026, 10, 12))  # no full month yet: to date
    assert mr.month_windows(date(2026, 10, 1), date(2026, 12, 3)) == [(date(2026, 10, 1), date(2026, 10, 31)), (date(2026, 11, 1), date(2026, 11, 30))]


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
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_meter_rules.py -q`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
"""Pure rules for the goal meter: progress by method, windows in IST, the 01-Nov gate,
stale and overdue tests. No Frappe imports; tested with plain pytest."""
from __future__ import annotations
from datetime import date, datetime, time, timedelta
from typing import Sequence

PROGRESS_GATE = date(2026, 11, 1)
METHODS = ("Ratio to target", "Months meeting standard", "Plane module", "Manual")
WINDOWS = ("Cycle to date", "Latest full month")
HIGHER, LOWER = "Higher is better", "Lower is better"


def _r1(x: float) -> float:
    return round(x + 1e-9, 1)


def pct(n, d) -> float | None:
    return None if not d else _r1(100.0 * float(n) / float(d))


def progress_ratio(value, target, direction) -> float | None:
    if value is None or target in (None, 0):
        return None
    v, t = float(value), float(target)
    if direction == LOWER:
        return 100.0 if v <= t else _r1(min(100.0, 100.0 * t / v)) if v > 0 else None
    return _r1(min(100.0, 100.0 * v / t))


def meets_standard(value, standard, direction) -> bool | None:
    if value is None or standard is None:
        return None
    return float(value) <= float(standard) if direction == LOWER else float(value) >= float(standard)


def progress_months(met: Sequence[bool | None]) -> float | None:
    judged = [m for m in met if m is not None]
    return None if not judged else _r1(100.0 * sum(1 for m in judged if m) / len(judged))


def progress_module(total: int, done: int) -> float | None:
    return None if not total else _r1(min(100.0, 100.0 * done / total))


def _month_end(d: date) -> date:
    nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=1)
    return nxt - timedelta(days=1)


def month_windows(cycle_start: date, as_of: date) -> list[tuple[date, date]]:
    out, start = [], cycle_start.replace(day=1)
    while _month_end(start) < as_of:
        out.append((max(start, cycle_start), _month_end(start)))
        start = _month_end(start) + timedelta(days=1)
    return out


def window_bounds(window: str, as_of: date, cycle_start: date) -> tuple[date, date]:
    if window == "Latest full month":
        months = month_windows(cycle_start, as_of)
        if months:
            return months[-1]
    return cycle_start, as_of


def writes_progress(as_of: date) -> bool:
    return as_of >= PROGRESS_GATE


def is_stale(stamp: datetime | None, as_of: date) -> bool:
    return stamp is None or stamp < datetime.combine(as_of, time(23, 0))


def is_overdue(target_date: date | None, state_group: str, as_of: date) -> bool:
    return bool(target_date) and state_group not in ("completed", "cancelled") and target_date < as_of
```

- [ ] **Step 4: Run the tests**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_meter_rules.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add caryaar_hr_ext/performance/meter_rules.py caryaar_hr_ext/performance/tests/test_meter_rules.py
git commit -m "feat(performance): pure meter rules (ratio, months, module, windows, gate, stale, overdue)"
```

---

### Task 6: The nightly meter

**Files:**
- Create: `caryaar_hr_ext/performance/meter.py`
- Modify: `caryaar_hr_ext/performance/engine.py` (remove `update_goal_progress`, call the meter), `caryaar_hr_ext/hooks.py` (no change to the cron, the meter runs inside `run_nightly`)
- Test: `caryaar_hr_ext/performance/tests/test_integration.py` (staging) and `test_meter_rules.py` for the pure evaluators' helpers

**Interfaces:**
- Consumes: doctypes from Task 2, `meter_rules`, `rules.extract_module_id`.
- Produces: `meter.run_meter(as_of: date | None = None) -> dict` (counts: readings, written, stale, skipped), `meter.METRICS: dict[str, Callable[[MeterContext], float | None]]`, `meter.MeterContext(employee, cycle, cycle_start, as_of, window_from, window_to, meter)`, `meter.compute_reading(gm, as_of) -> dict | None`, `meter.write_manual_reading(goal, progress, evidence)` (whitelisted, used by the pack UI later).

- [ ] **Step 1: Write the failing integration tests (staging)**

```python
def _seed_goal(self, employee, kra, name):
    return frappe.get_doc({"doctype": "Goal", "goal_name": name, "employee": employee, "appraisal_cycle": "Oct 2026 - Mar 2027",
                           "kra": kra, "start_date": "2026-10-01", "end_date": "2027-03-31"}).insert(ignore_permissions=True)


def test_ratio_meter_reads_activity_rows_and_gates_progress(self):
    from caryaar_hr_ext.performance import meter
    g = self._seed_goal("HR-EMP-00012", "Lead to booking conversion", "T conversion")
    frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": "Ratio to target", "metric": "conversion_pct",
                    "window": "Cycle to date", "target_value": 5, "unit": "%", "direction": "Higher is better"}).insert()
    for day, assigned, booked in (("2026-10-02", 100, 2), ("2026-10-03", 100, 3)):
        frappe.get_doc({"doctype": "Work Activity Day", "employee": "HR-EMP-00012", "activity_date": day, "source": "CY Admin",
                        "leads_assigned_new": assigned, "bookings_within_7d": booked}).insert(ignore_permissions=True)
    frappe.db.set_single_value("Performance Sync Settings", "cy_admin_synced_through", "2026-10-04 23:30:00")
    out = meter.run_meter(as_of=frappe.utils.getdate("2026-10-04"))
    r = frappe.get_doc("Goal Meter Reading", f"{g.name}|2026-10-04")
    self.assertEqual((r.value, r.progress, r.stale, r.written_to_goal), (2.5, 50.0, 0, 0))   # October: not written
    self.assertEqual(frappe.db.get_value("Goal", g.name, "progress"), 0)
    out = meter.run_meter(as_of=frappe.utils.getdate("2026-11-02"))
    self.assertEqual(frappe.db.get_value("Goal", g.name, "progress"), 50.0)                    # November: written


def test_stale_source_repeats_last_reading(self):
    from caryaar_hr_ext.performance import meter
    frappe.db.set_single_value("Performance Sync Settings", "cy_admin_synced_through", "2026-10-01 23:30:00")
    meter.run_meter(as_of=frappe.utils.getdate("2026-10-05"))
    r = frappe.get_doc("Goal Meter Reading", "<name of the goal above>|2026-10-05")
    self.assertEqual(r.stale, 1)


def test_module_completion_uses_current_membership(self):
    from caryaar_hr_ext.performance import meter
    g = self._seed_goal("HR-EMP-00008", "Committed sprint work delivered", "T sprint")
    g.db_set("cy_plane_module", "mod-t1")
    frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": "Plane module"}).insert()
    for n, state in (("a", "completed"), ("b", "started"), ("c", "cancelled")):
        frappe.get_doc({"doctype": "Plane Work Item", "issue_id": f"t1-{n}", "project_identifier": "DEV", "sequence_id": 1,
                        "title": n, "state_group": state, "module_id": "mod-t1", "created_at": "2026-10-01 09:00:00",
                        "updated_at": "2026-10-01 09:00:00"}).insert(ignore_permissions=True)
    frappe.db.set_single_value("Performance Sync Settings", "plane_items_synced_through", "2026-10-06 23:30:00")
    meter.run_meter(as_of=frappe.utils.getdate("2026-10-06"))
    self.assertEqual(frappe.db.get_value("Goal Meter Reading", f"{g.name}|2026-10-06", "progress"), 50.0)   # 1 of 2 non-cancelled
    frappe.db.set_value("Plane Work Item", "t1-a", "module_id", None)                                       # moved out
    meter.run_meter(as_of=frappe.utils.getdate("2026-10-07"))
    self.assertEqual(frappe.db.get_value("Goal Meter Reading", f"{g.name}|2026-10-07", "progress"), 0.0)
```

- [ ] **Step 2: Run on staging to verify they fail**

Expected: FAIL with `ModuleNotFoundError: caryaar_hr_ext.performance.meter`.

- [ ] **Step 3: Implement `meter.py`**

```python
"""Nightly goal meter: one reading per active Goal Meter per day; from 01-Nov-2026 the
reading's progress is written to Goal.progress through the document so HRMS hooks run.
Metric evaluators read the ERP only (Work Activity Day, Plane Work Item, Wiki Page)."""
from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Callable, NamedTuple
import frappe
from frappe.utils import flt, get_datetime, getdate, nowdate, now_datetime
from caryaar_hr_ext.performance import meter_rules as mr, rules

CYCLE_START = date(2026, 10, 1)


class MeterContext(NamedTuple):
    employee: str
    cycle: str
    cycle_start: date
    as_of: date
    window_from: date
    window_to: date
    meter: "frappe._dict"


def _sum_metric(ctx: MeterContext, key: str, source: str = "CY Admin") -> int:
    row = frappe.db.sql(f"""SELECT coalesce(sum(`{key}`), 0) FROM `tabWork Activity Day`
                            WHERE employee = %s AND source = %s AND activity_date BETWEEN %s AND %s""",
                        (ctx.employee, source, ctx.window_from, ctx.window_to))
    return int(row[0][0] or 0)


def _items(ctx: MeterContext, **filters) -> list:
    return frappe.get_all("Plane Work Item", filters={"is_deleted": 0, **filters},
                          fields=["name", "state_group", "target_date", "completed_at", "created_at", "labels", "module_id"])


def _module_id(ctx: MeterContext) -> str | None:
    return rules.extract_module_id(frappe.db.get_value("Goal", ctx.meter.goal, "cy_plane_module"))


def m_conversion_pct(ctx):      # bookings within 7 days / leads assigned in the window
    return mr.pct(_sum_metric(ctx, "bookings_within_7d"), _sum_metric(ctx, "leads_assigned_new"))


def m_followups_on_time_pct(ctx):
    return mr.pct(_sum_metric(ctx, "followups_done_on_time"), _sum_metric(ctx, "followups_due"))


def m_leads_statused_48h_pct(ctx):
    return mr.pct(_sum_metric(ctx, "leads_statused_48h"), _sum_metric(ctx, "leads_assigned_new"))


def m_module_completion(ctx):
    mid = _module_id(ctx)
    if not mid:
        return None
    items = [i for i in _items(ctx, module_id=mid) if i.state_group != "cancelled"]
    return mr.progress_module(len(items), sum(1 for i in items if i.state_group == "completed"))


def m_incidents_fixed_24h_pct(ctx):   # items labelled incident, assigned to the person, created in the window
    items = [i for i in _items(ctx, assignee=ctx.employee) if "incident" in (i.labels or "").split(",")
             and ctx.window_from <= getdate(i.created_at) <= ctx.window_to]
    fixed = [i for i in items if i.completed_at and get_datetime(i.completed_at) - get_datetime(i.created_at) <= timedelta(hours=24)]
    return mr.pct(len(fixed), len(items))


def m_support_on_time_pct(ctx):       # items in the goal's module completed by their due date
    mid = _module_id(ctx)
    items = [i for i in _items(ctx, module_id=mid) if i.state_group != "cancelled" and i.target_date] if mid else []
    done = [i for i in items if i.completed_at and getdate(i.completed_at) <= getdate(i.target_date)]
    due = [i for i in items if getdate(i.target_date) <= ctx.window_to]
    return mr.pct(len(done), len(due))


def m_release_bugs_14d(ctx):          # bugs raised within 14 days of a release item, per release, in the window
    releases = [i for i in _items(ctx, assignee=ctx.employee) if "release" in (i.labels or "").split(",") and i.completed_at
                and ctx.window_from <= getdate(i.completed_at) <= ctx.window_to]
    if not releases:
        return None
    bugs = [i for i in _items(ctx) if "bug" in (i.labels or "").split(",")]
    n = sum(1 for r in releases for b in bugs if 0 <= (get_datetime(b.created_at) - get_datetime(r.completed_at)).days <= 14)
    return round(n / len(releases), 1)


def m_wiki_pages(ctx):
    user = frappe.db.get_value("Employee", ctx.employee, "user_id")
    return frappe.db.count("Wiki Page", {"modified_by": user, "modified": ("between", [ctx.window_from, ctx.window_to])}) if user else None


METRICS: dict[str, Callable[[MeterContext], float | None]] = {
    "conversion_pct": m_conversion_pct, "followups_on_time_pct": m_followups_on_time_pct,
    "leads_statused_48h_pct": m_leads_statused_48h_pct, "module_completion": m_module_completion,
    "incidents_fixed_24h_pct": m_incidents_fixed_24h_pct, "support_on_time_pct": m_support_on_time_pct,
    "release_bugs_14d": m_release_bugs_14d, "wiki_pages": m_wiki_pages,
}
_SOURCE_OF = {"conversion_pct": "CY Admin", "followups_on_time_pct": "CY Admin", "leads_statused_48h_pct": "CY Admin",
              "module_completion": "Plane items", "incidents_fixed_24h_pct": "Plane items",
              "support_on_time_pct": "Plane items", "release_bugs_14d": "Plane items", "wiki_pages": "ERP"}
_STAMP_FIELD = {"CY Admin": "cy_admin_synced_through", "Plane items": "plane_items_synced_through"}


def _stamp(source: str) -> datetime | None:
    field = _STAMP_FIELD.get(source)
    return rules.stored_stamp(frappe.db.get_single_value("Performance Sync Settings", field)) if field else now_datetime()


def _last_reading(goal: str, before: date):
    rows = frappe.get_all("Goal Meter Reading", filters={"goal": goal, "reading_date": ("<", before)},
                          fields=["value", "progress"], order_by="reading_date desc", limit=1)
    return rows[0] if rows else None


def compute_reading(gm, as_of: date) -> dict | None:
    """The reading for one meter, or None when the meter is manual or cannot be computed."""
    if gm.method == "Manual":
        return None
    goal = frappe.db.get_value("Goal", gm.goal, ["employee", "appraisal_cycle"], as_dict=True)
    metric = "module_completion" if gm.method == "Plane module" else gm.metric
    fn = METRICS.get(metric)
    if not fn or not goal:
        return None
    if gm.method == "Months meeting standard":
        met = []
        for w_from, w_to in mr.month_windows(CYCLE_START, as_of):
            ctx = MeterContext(goal.employee, goal.appraisal_cycle, CYCLE_START, as_of, w_from, w_to, gm)
            met.append(mr.meets_standard(fn(ctx), gm.standard_value, gm.direction))
        value, progress = (met.count(True) if met else None), mr.progress_months(met)
    else:
        w_from, w_to = mr.window_bounds(gm.window or "Cycle to date", as_of, CYCLE_START)
        ctx = MeterContext(goal.employee, goal.appraisal_cycle, CYCLE_START, as_of, w_from, w_to, gm)
        value = fn(ctx)
        progress = value if gm.method == "Plane module" else mr.progress_ratio(value, gm.target_value, gm.direction)
    stale = mr.is_stale(_stamp(_SOURCE_OF[metric]), as_of)
    if stale:
        last = _last_reading(gm.goal, as_of)
        if last:
            value, progress = last.value, last.progress
    return {"value": value, "progress": progress, "stale": stale, "method": gm.method}


def _write_reading(gm, as_of: date, reading: dict) -> bool:
    name = f"{gm.goal}|{as_of}"
    values = {"value": reading["value"], "progress": reading["progress"], "method": reading["method"],
              "stale": 1 if reading["stale"] else 0, "computed_at": now_datetime()}
    if frappe.db.exists("Goal Meter Reading", name):
        frappe.db.set_value("Goal Meter Reading", name, values)
    else:
        frappe.get_doc({"doctype": "Goal Meter Reading", "goal": gm.goal, "reading_date": as_of, **values}).insert(ignore_permissions=True)
    written = False
    if mr.writes_progress(as_of) and reading["progress"] is not None and not reading["stale"]:
        current = flt(frappe.db.get_value("Goal", gm.goal, "progress"))
        if abs(reading["progress"] - current) >= 0.5:
            doc = frappe.get_doc("Goal", gm.goal)
            doc.progress = reading["progress"]
            doc.save(ignore_permissions=True)      # HRMS hooks: status, parent goal, appraisal score
            written = True
        frappe.db.set_value("Goal Meter Reading", name, "written_to_goal", 1)
    return written


def run_meter(as_of: date | None = None) -> dict:
    as_of = as_of or getdate(nowdate())
    counts = {"readings": 0, "written": 0, "stale": 0, "skipped": 0}
    meters = frappe.get_all("Goal Meter", filters={"active": 1}, fields=["name", "goal", "method", "metric", "window",
                                                                         "target_value", "standard_value", "direction"])
    for gm in meters:
        frappe.db.savepoint("cy_meter")
        try:
            reading = compute_reading(gm, as_of)
            if reading is None:
                counts["skipped"] += 1
                continue
            if _write_reading(gm, as_of, reading):
                counts["written"] += 1
            counts["readings"] += 1
            counts["stale"] += 1 if reading["stale"] else 0
        except Exception:
            frappe.db.rollback(save_point="cy_meter")
            frappe.log_error(title=f"Goal meter: {gm.goal} skipped", message=frappe.get_traceback())
            counts["skipped"] += 1
    return counts


@frappe.whitelist(methods=["POST"])
def write_manual_reading(goal: str, progress: float, evidence: str = "") -> dict:
    """A manager's reading for a Manual meter; writes progress at once, under the same gate."""
    frappe.only_for(("HR Manager", "HR User", "System Manager"))
    gm = frappe.get_doc("Goal Meter", goal)
    if gm.method != "Manual":
        frappe.throw("This goal is measured automatically.")
    as_of = getdate(nowdate())
    reading = {"value": flt(progress), "progress": max(0.0, min(100.0, flt(progress))), "stale": False, "method": "Manual"}
    written = _write_reading(gm, as_of, reading)
    frappe.db.set_value("Goal Meter Reading", f"{goal}|{as_of}", {"evidence": evidence[:500], "entered_by": frappe.session.user})
    return {"written_to_goal": written}
```

`engine.py`: delete `update_goal_progress` and its use; in `run_nightly` replace the goal-progress guard with `_guard("goal meter", meter.run_meter)` (import `from caryaar_hr_ext.performance import meter, rules`). Keep `unmatched_goal_modules` updated inside `m_module_completion` by appending `f"{gm.goal}: no module"` when `mid` is missing (write the joined list to the settings at the end of `run_meter`).

- [ ] **Step 4: Run the staging integration tests**

Expected: PASS for the three new tests; the existing adherence tests still pass.

- [ ] **Step 5: Commit**

```bash
git add caryaar_hr_ext/performance/meter.py caryaar_hr_ext/performance/engine.py caryaar_hr_ext/performance/tests/test_integration.py
git commit -m "feat(performance): nightly goal meter with readings, the 01-Nov gate and stale handling; module progress folded in"
```

---

### Task 7: CY Admin: five per-agent metrics and the morning follow-up snapshot

**Files:**
- Create: `caryaar-api/migrations/versions/267_agent_followup_snapshots.py`
- Create: `caryaar-api/app/models/performance.py`
- Modify: `caryaar-api/app/services/performance/agent_activity.py`
- Modify: `caryaar-api/app/tasks/performance_activity_sync.py`
- Test: `caryaar-api/tests/services/performance/test_agent_activity_pure.py`, `test_agent_activity_l2.py`, `tests/migrations/test_267_agent_followup_snapshots.py`

**Interfaces:**
- Consumes: `compute_agent_activity`, `build_rows`, `METRICS_DAILY`.
- Produces: table `agent_followup_snapshots(day date, agent_user_id uuid, customer_id uuid, due_at timestamptz, primary key (day, agent_user_id, customer_id))`; `snapshot_followups_due(session, day) -> int`; five new keys in `METRICS_DAILY`: `leads_assigned_new`, `bookings_within_7d`, `followups_due`, `followups_done_on_time`, `leads_statused_48h`; beat `performance-followup-snapshot` at 00:05 IST.

- [ ] **Step 1: Write the failing tests**

```python
# tests/migrations/test_267_agent_followup_snapshots.py
from tests.migrations.conftest import migration_module   # the existing helper that imports a migration by number

def test_267_creates_the_snapshot_table():
    m = migration_module("267")
    src = open(m.__file__).read()
    assert "agent_followup_snapshots" in src and "due_at" in src and "primary key" in src.lower()
```

```python
# tests/services/performance/test_agent_activity_pure.py
def test_new_daily_keys_are_sent_and_default_to_zero():
    from app.services.performance.agent_activity import METRICS_DAILY, build_rows
    for k in ("leads_assigned_new", "bookings_within_7d", "followups_due", "followups_done_on_time", "leads_statused_48h"):
        assert k in METRICS_DAILY
    row = build_rows({"u1": "a@caryaar.com"}, date(2026, 10, 2), {}, include_snapshots=False)[0]
    assert row["metrics"]["followups_due"] == 0 and row["metrics"]["bookings_within_7d"] == 0
```

```python
# tests/services/performance/test_agent_activity_l2.py (pytestmark = pytest.mark.l2; seed helpers already exist in this file)
async def test_followup_done_requires_a_touch_on_the_day(test_session):
    day = date(2026, 10, 2)
    agent = await _seed_agent(test_session, "fu@caryaar.test")
    c1 = await _seed_customer(test_session, agent, next_action_at=datetime(2026, 10, 2, 5, 0, tzinfo=timezone.utc))
    c2 = await _seed_customer(test_session, agent, next_action_at=datetime(2026, 10, 2, 6, 0, tzinfo=timezone.utc))
    assert await snapshot_followups_due(test_session, day) == 2
    await _seed_note(test_session, c1, agent, at=datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc))     # touched
    await _reschedule(test_session, c2, datetime(2026, 10, 9, 5, 0, tzinfo=timezone.utc))              # moved, never touched
    rows = await compute_agent_activity(test_session, day, include_snapshots=False)
    m = next(r for r in rows if r["email"] == "fu@caryaar.test")["metrics"]
    assert (m["followups_due"], m["followups_done_on_time"]) == (2, 1)


async def test_bookings_within_7d_and_statused_48h(test_session):
    agent = await _seed_agent(test_session, "cv@caryaar.test")
    c = await _seed_customer(test_session, agent, assigned_at=datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc))
    await _seed_booking(test_session, c, at=datetime(2026, 10, 5, 4, 0, tzinfo=timezone.utc))
    await _seed_status(test_session, c, agent, at=datetime(2026, 10, 2, 4, 0, tzinfo=timezone.utc))
    d1 = next(r for r in await compute_agent_activity(test_session, date(2026, 10, 1), include_snapshots=False) if r["email"] == "cv@caryaar.test")["metrics"]
    d5 = next(r for r in await compute_agent_activity(test_session, date(2026, 10, 5), include_snapshots=False) if r["email"] == "cv@caryaar.test")["metrics"]
    assert d1["leads_assigned_new"] == 1 and d1["leads_statused_48h"] == 1 and d5["bookings_within_7d"] == 1
```

Add the seed helpers used above to the L2 file if they do not exist yet: `_seed_agent(session, email)` inserts a `users` row (CY_ADMIN, ACTIVE); `_seed_customer(session, agent_id, *, assigned_at=None, next_action_at=None)` inserts a `customers` row assigned to the agent; `_seed_note`, `_seed_status`, `_seed_booking`, `_reschedule` insert `customer_notes`, `lead_status_history`, `bookings` rows and update `next_action_at`. Use the same INSERT-by-`text()` style as the file's existing helpers.

- [ ] **Step 2: Run to verify they fail**

Run: `cd /Users/sahaib/caryaar/caryaar-api && python3 -m pytest tests/services/performance/test_agent_activity_pure.py tests/migrations/test_267_agent_followup_snapshots.py -q` and `TEST_DATABASE_URL=postgresql+asyncpg://caryaar_test:caryaar_test_pw@127.0.0.1:15433/caryaar_test python3 -m pytest tests/services/performance/test_agent_activity_l2.py -q`
Expected: FAIL (missing keys, missing migration, missing `snapshot_followups_due`).

- [ ] **Step 3: Implement**

Migration `267_agent_followup_snapshots.py` (additive; downgrade drops the table):

```python
def upgrade() -> None:
    op.create_table(
        "agent_followup_snapshots",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("agent_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("day", "agent_user_id", "customer_id", name="pk_agent_followup_snapshots"),
    )
```

`app/models/performance.py`: the matching SQLAlchemy model `AgentFollowupSnapshot`.

`agent_activity.py`:

```python
METRICS_DAILY = ("calls_handled", "calls_answered", "talk_seconds", "dispositions", "status_moves", "notes_written",
                 "bookings_credited", "leads_assigned_new", "bookings_within_7d", "followups_due",
                 "followups_done_on_time", "leads_statused_48h")

_SNAPSHOT_FOLLOWUPS_SQL = text("""
    INSERT INTO agent_followup_snapshots (day, agent_user_id, customer_id, due_at)
    SELECT CAST(:day AS date), assigned_to_user_id, id, next_action_at FROM customers
    WHERE deleted_at IS NULL AND assigned_to_user_id IS NOT NULL
      AND next_action_at >= CAST(:start AS timestamptz) AND next_action_at < CAST(:end AS timestamptz)
    ON CONFLICT DO NOTHING""")


async def snapshot_followups_due(session: AsyncSession, day: date) -> int:
    """Run in the first minutes of the IST day: what is due today, before anyone moves it."""
    start, end = ist_day_bounds(day)
    res = await session.execute(_SNAPSHOT_FOLLOWUPS_SQL, {"day": day, "start": start, "end": end})
    await session.commit()
    return res.rowcount or 0

_COUNT_SQL.update({
    "leads_assigned_new": """SELECT CAST(assigned_to_user_id AS text), count(*) FROM customers
        WHERE deleted_at IS NULL AND assigned_to_user_id IS NOT NULL
          AND assigned_at >= CAST(:start AS timestamptz) AND assigned_at < CAST(:end AS timestamptz) GROUP BY 1""",
    "bookings_within_7d": """SELECT CAST(c.assigned_to_user_id AS text), count(*) FROM bookings b
        JOIN customers c ON c.id = b.customer_id AND c.deleted_at IS NULL AND c.assigned_to_user_id IS NOT NULL
        WHERE b.created_at >= CAST(:start AS timestamptz) AND b.created_at < CAST(:end AS timestamptz)
          AND c.assigned_at IS NOT NULL AND b.created_at <= c.assigned_at + interval '7 days' GROUP BY 1""",
    "followups_due": """SELECT CAST(agent_user_id AS text), count(*) FROM agent_followup_snapshots
        WHERE day = CAST(:day AS date) GROUP BY 1""",
    "followups_done_on_time": """SELECT CAST(s.agent_user_id AS text), count(*) FROM agent_followup_snapshots s
        WHERE s.day = CAST(:day AS date) AND EXISTS (
          SELECT 1 FROM customer_notes n WHERE n.customer_id = s.customer_id AND n.author_user_id = s.agent_user_id
            AND n.created_at >= CAST(:start AS timestamptz) AND n.created_at < CAST(:end AS timestamptz)
          UNION ALL SELECT 1 FROM lead_status_history h WHERE h.customer_id = s.customer_id AND h.changed_by = s.agent_user_id
            AND h.created_at >= CAST(:start AS timestamptz) AND h.created_at < CAST(:end AS timestamptz)
          UNION ALL SELECT 1 FROM voice_calls v WHERE v.customer_id = s.customer_id AND v.agent_user_id = s.agent_user_id
            AND v.source = 'HUMAN_AGENT' AND v.created_at >= CAST(:start AS timestamptz) AND v.created_at < CAST(:end AS timestamptz))
        GROUP BY 1""",
    "leads_statused_48h": """SELECT CAST(assigned_to_user_id AS text), count(*) FROM customers
        WHERE deleted_at IS NULL AND assigned_to_user_id IS NOT NULL AND lead_status IS NOT NULL
          AND assigned_at >= CAST(:start AS timestamptz) AND assigned_at < CAST(:end AS timestamptz)
          AND lead_status_changed_at <= assigned_at + interval '48 hours' GROUP BY 1""",
})
```

`params` in `compute_agent_activity` gains `"day": day`. Check `voice_calls.customer_id` exists (grep the model); if the column is named differently, use that name and record a Ruling.

`performance_activity_sync.py`: a new task `snapshot_followups(day=None)` that opens a write session, calls `snapshot_followups_due`, returns `{"day": ..., "snapshotted": n}`; beat entry `"performance-followup-snapshot": {"task": ..., "schedule": crontab(hour=0, minute=5)}` next to the existing two, behind the same `PERFORMANCE_SYNC_ENABLED` gate.

- [ ] **Step 4: Run the tests**

Run the three commands from Step 2. Expected: PASS. Also `python3 -m pytest tests/tasks/test_performance_activity_sync.py -q` still passes.

- [ ] **Step 5: Commit**

```bash
git add migrations/versions/267_agent_followup_snapshots.py app/models/performance.py app/services/performance/agent_activity.py app/tasks/performance_activity_sync.py tests
git commit -m "feat(performance): five per-agent goal metrics and the morning follow-up snapshot (mig 267)"
```

---

### Task 8: Review pack: report and scheduled email

**Files:**
- Create: `caryaar_hr_ext/performance/review_pack.py`
- Create: `caryaar_hr_ext/caryaar_hr_ext/report/goal_review_pack/{__init__.py,goal_review_pack.json,goal_review_pack.js,goal_review_pack.py}`
- Create: `caryaar_hr_ext/templates/emails/review_pack.html`
- Modify: `caryaar_hr_ext/fixtures/custom_field.json` (add `Appraisal-cy_next_review_on`), `caryaar_hr_ext/hooks.py` (cron `0 8 * * *` → `caryaar_hr_ext.performance.review_pack.send_scheduled_packs`)
- Test: `caryaar_hr_ext/performance/tests/test_meter_rules.py` (pure pack helpers), `test_integration.py` (build_pack on staging)

**Interfaces:**
- Consumes: Goal, Goal Meter, Goal Meter Reading, Plane Work Item, Work Adherence Day, Employee.reports_to, settings `review_pack_recipients`.
- Produces: `review_pack.build_pack(employee: str, cycle: str, as_of: date) -> dict` (keys `employee`, `employee_name`, `cycle`, `as_of`, `learning_month: bool`, `goals: list[dict]`, `adherence: {"days": int, "pct": float | None}`, `uncounted_items: int`, `manual_missing: list[str]`); `review_pack.pack_rows(pack) -> list[dict]` (flat rows with `row_type` goal|item); `review_pack.send_pack(employee, cycle, as_of) -> list[str]` (recipients); `review_pack.send_scheduled_packs()`; `meter_rules.pack_due_today(as_of, review_dates: Sequence[date]) -> bool`.

- [ ] **Step 1: Write the failing tests**

```python
# test_meter_rules.py
def test_pack_due_on_1st_15th_and_three_days_before_a_review():
    assert mr.pack_due_today(date(2026, 10, 1), []) and mr.pack_due_today(date(2026, 10, 15), [])
    assert not mr.pack_due_today(date(2026, 10, 9), [])
    assert mr.pack_due_today(date(2026, 10, 9), [date(2026, 10, 12)])
    assert not mr.pack_due_today(date(2026, 10, 9), [date(2026, 10, 13)])
```

```python
# test_integration.py (staging)
def test_pack_flags_manual_goal_without_reading(self):
    from caryaar_hr_ext.performance import review_pack
    g = self._seed_goal("HR-EMP-00014", "Brand consistency", "T manual")
    frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": "Manual"}).insert()
    pack = review_pack.build_pack("HR-EMP-00014", "Oct 2026 - Mar 2027", frappe.utils.getdate("2026-10-20"))
    self.assertIn(g.name, pack["manual_missing"])
    goal = next(x for x in pack["goals"] if x["goal"] == g.name)
    self.assertEqual(goal["progress"], None)
    rows = review_pack.pack_rows(pack)
    self.assertTrue(any(r["row_type"] == "goal" and r["goal"] == g.name for r in rows))


def test_pack_lists_module_items_with_overdue_flag_and_counts_uncounted(self):
    from caryaar_hr_ext.performance import review_pack
    g = self._seed_goal("HR-EMP-00008", "Committed sprint work delivered", "T pack sprint")
    g.db_set("cy_plane_module", "mod-p1")
    frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": "Plane module"}).insert()
    frappe.get_doc({"doctype": "Plane Work Item", "issue_id": "p1-a", "project_identifier": "DEV", "sequence_id": 5, "title": "late",
                    "state_group": "started", "module_id": "mod-p1", "assignee": "HR-EMP-00008", "target_date": "2026-10-05",
                    "created_at": "2026-10-01 09:00:00", "updated_at": "2026-10-01 09:00:00"}).insert(ignore_permissions=True)
    frappe.get_doc({"doctype": "Plane Work Item", "issue_id": "p1-b", "project_identifier": "DEV", "sequence_id": 6, "title": "loose",
                    "state_group": "started", "assignee": "HR-EMP-00008",
                    "created_at": "2026-10-01 09:00:00", "updated_at": "2026-10-01 09:00:00"}).insert(ignore_permissions=True)
    pack = review_pack.build_pack("HR-EMP-00008", "Oct 2026 - Mar 2027", frappe.utils.getdate("2026-10-10"))
    goal = next(x for x in pack["goals"] if x["goal"] == g.name)
    self.assertEqual([(i["sequence_id"], i["overdue"]) for i in goal["items"]], [(5, True)])
    self.assertEqual(pack["uncounted_items"], 1)
```

- [ ] **Step 2: Run to verify they fail**

Expected: `pack_due_today` missing (pure), `review_pack` module missing (staging).

- [ ] **Step 3: Implement**

`meter_rules.py` addition:

```python
def pack_due_today(as_of: date, review_dates: Sequence[date]) -> bool:
    return as_of.day in (1, 15) or any(rd - as_of == timedelta(days=3) for rd in review_dates)
```

`review_pack.py`:

```python
"""Per-person review pack: goals with meters and readings, the Plane items counted,
adherence for the window, and what still needs a manual reading."""
from __future__ import annotations
from datetime import date, timedelta
import frappe
from frappe.utils import flt, getdate, nowdate
from caryaar_hr_ext.performance import meter_rules as mr, rules

TREND_STEP_DAYS = 15


def _readings(goal: str, as_of: date) -> list:
    return frappe.get_all("Goal Meter Reading", filters={"goal": goal, "reading_date": ("<=", as_of)},
                          fields=["reading_date", "value", "progress", "stale", "evidence", "method", "entered_by"],
                          order_by="reading_date asc")


def _trend(readings: list) -> list[tuple[str, float | None]]:
    out, last_day = [], None
    for r in readings:
        if last_day is None or (r.reading_date - last_day).days >= TREND_STEP_DAYS:
            out.append((r.reading_date.isoformat(), r.progress)); last_day = r.reading_date
    if readings and out and out[-1][0] != readings[-1].reading_date.isoformat():
        out.append((readings[-1].reading_date.isoformat(), readings[-1].progress))
    return out


def _items_for(goal_doc, as_of: date) -> list[dict]:
    mid = rules.extract_module_id(goal_doc.cy_plane_module)
    if not mid:
        return []
    rows = frappe.get_all("Plane Work Item", filters={"module_id": mid, "is_deleted": 0},
                          fields=["issue_id", "project_identifier", "sequence_id", "title", "assignee", "assignee_email",
                                  "state_group", "start_date", "target_date", "completed_at"], order_by="target_date asc")
    return [{**r, "overdue": mr.is_overdue(r.target_date, r.state_group, as_of)} for r in rows]


def build_pack(employee: str, cycle: str, as_of: date) -> dict:
    emp = frappe.db.get_value("Employee", employee, ["employee_name", "reports_to"], as_dict=True)
    goals, manual_missing, counted_ids = [], [], set()
    for g in frappe.get_all("Goal", filters={"employee": employee, "appraisal_cycle": cycle, "status": ("!=", "Archived")},
                            fields=["name", "goal_name", "kra", "progress", "cy_plane_module"], order_by="kra asc"):
        gm = frappe.db.get_value("Goal Meter", g.name, ["method", "metric", "window", "target_value", "standard_value",
                                                        "unit", "direction", "active"], as_dict=True)
        readings = _readings(g.name, as_of)
        latest = readings[-1] if readings else None
        weight = frappe.db.get_value("Appraisal KRA", {"parent": ("in", frappe.get_all("Appraisal", {"employee": employee, "appraisal_cycle": cycle}, pluck="name")), "kra": g.kra}, "per_weightage")
        items = _items_for(g, as_of)
        counted_ids |= {i["issue_id"] for i in items}
        if gm and gm.method == "Manual" and (not latest or (as_of - latest.reading_date).days > 30):
            manual_missing.append(g.name)
        goals.append({"goal": g.name, "goal_name": g.goal_name, "kra": g.kra, "weight": weight,
                      "method": gm.method if gm else "No meter", "metric": gm.metric if gm else None,
                      "target": gm.target_value if gm else None, "standard": gm.standard_value if gm else None,
                      "unit": gm.unit if gm else None, "value": latest.value if latest else None,
                      "progress": latest.progress if latest else None, "stale": bool(latest and latest.stale),
                      "erp_progress": flt(g.progress), "trend": _trend(readings), "items": items,
                      "evidence": latest.evidence if latest else None})
    adh = frappe.get_all("Work Adherence Day", filters={"employee": employee, "adherence_date": ("between", [date(2026, 10, 1), as_of]),
                                                        "is_working_day": 1}, fields=["adherence_pct"])
    judged = [flt(a.adherence_pct) for a in adh if a.adherence_pct is not None]
    uncounted = frappe.db.count("Plane Work Item", {"assignee": employee, "is_deleted": 0, "state_group": ("!=", "cancelled"),
                                                     "issue_id": ("not in", list(counted_ids) or ["-"])})
    return {"employee": employee, "employee_name": emp.employee_name, "reports_to": emp.reports_to, "cycle": cycle,
            "as_of": as_of.isoformat(), "learning_month": not mr.writes_progress(as_of), "goals": goals,
            "adherence": {"days": len(judged), "pct": round(sum(judged) / len(judged), 1) if judged else None},
            "uncounted_items": uncounted, "manual_missing": manual_missing}


def pack_rows(pack: dict) -> list[dict]:
    rows = []
    for g in pack["goals"]:
        rows.append({"row_type": "goal", "goal": g["goal"], "text": g["goal_name"], "kra": g["kra"], "weight": g["weight"],
                     "method": g["method"], "target": g["target"], "value": g["value"], "progress": g["progress"],
                     "flags": ", ".join(f for f, on in (("stale", g["stale"]), ("no reading", g["progress"] is None)) if on)})
        for i in g["items"]:
            rows.append({"row_type": "item", "goal": g["goal"], "text": f"{i['project_identifier']}-{i['sequence_id']} {i['title']}",
                         "kra": "", "weight": None, "method": i["state_group"], "target": i["target_date"],
                         "value": None, "progress": None,
                         "flags": ("overdue" if i["overdue"] else "") + (f" done {getdate(i['completed_at'])}" if i["completed_at"] else "")})
    return rows


def _recipients(pack: dict) -> list[str]:
    always = [x.strip() for x in (frappe.db.get_single_value("Performance Sync Settings", "review_pack_recipients") or "").split("\n") if x.strip()]
    manager = frappe.db.get_value("Employee", pack["reports_to"], "user_id") if pack["reports_to"] else None
    return sorted({*always, *([manager] if manager else [])})


def send_pack(employee: str, cycle: str, as_of: date) -> list[str]:
    pack = build_pack(employee, cycle, as_of)
    recipients = _recipients(pack)
    html = frappe.render_template("caryaar_hr_ext/templates/emails/review_pack.html", {"pack": pack, "rows": pack_rows(pack)})
    frappe.sendmail(recipients=recipients, subject=f"Review pack: {pack['employee_name']}, {as_of.strftime('%d-%b-%Y')}",
                    message=html, now=False)
    return recipients


def send_scheduled_packs() -> dict:
    """08:00 IST daily: sends on the 1st and 15th, and 3 days before an appraisal's review date."""
    as_of = getdate(nowdate())
    sent = 0
    for cycle in frappe.get_all("Appraisal Cycle", filters={"status": ("in", ["Not Started", "In Progress"]),
                                                             "start_date": ("<=", as_of)}, pluck="name"):
        for a in frappe.get_all("Appraisal Cycle Appraisee", filters={"parent": cycle}, fields=["employee"]):
            review_dates = [getdate(d) for d in frappe.get_all("Appraisal", {"employee": a.employee, "appraisal_cycle": cycle,
                                                                             "cy_next_review_on": ("is", "set")}, pluck="cy_next_review_on")]
            if frappe.db.get_value("Employee", a.employee, "status") == "Active" and mr.pack_due_today(as_of, review_dates):
                try:
                    send_pack(a.employee, cycle, as_of); sent += 1
                except Exception:
                    frappe.log_error(title=f"Review pack: {a.employee}", message=frappe.get_traceback())
    return {"sent": sent, "as_of": as_of.isoformat()}
```

`templates/emails/review_pack.html`: a plain table (Goal, KRA, weight, method, target, value, progress, flags) with item rows indented, an adherence line, the uncounted-items line ("N other Plane items assigned, not tied to a goal"), the learning-month note when `pack.learning_month`, and the manual goals needing a reading. No em dashes.

Report `goal_review_pack.json`: Script Report, ref_doctype Goal, roles HR Manager, HR User, System Manager, module Caryaar Hr Ext. `.js` filters: employee (Link Employee, reqd), appraisal_cycle (Link, reqd, default the active cycle), as_of (Date, default today). `.py`:

```python
def execute(filters=None):
    filters = frappe._dict(filters or {})
    pack = build_pack(filters.employee, filters.appraisal_cycle, getdate(filters.as_of or nowdate()))
    columns = [
        {"fieldname": "row_type", "label": "Row", "fieldtype": "Data", "width": 60},
        {"fieldname": "text", "label": "Goal / item", "fieldtype": "Data", "width": 420},
        {"fieldname": "kra", "label": "KRA", "fieldtype": "Data", "width": 220},
        {"fieldname": "weight", "label": "Weight %", "fieldtype": "Float", "width": 80},
        {"fieldname": "method", "label": "Method / state", "fieldtype": "Data", "width": 160},
        {"fieldname": "target", "label": "Target / due", "fieldtype": "Data", "width": 120},
        {"fieldname": "value", "label": "Value", "fieldtype": "Float", "width": 90},
        {"fieldname": "progress", "label": "Progress %", "fieldtype": "Percent", "width": 100},
        {"fieldname": "flags", "label": "Flags", "fieldtype": "Data", "width": 200},
    ]
    return columns, pack_rows(pack), None, None, [
        {"value": pack["adherence"]["pct"], "label": "Adherence % (working days)", "datatype": "Percent"},
        {"value": pack["uncounted_items"], "label": "Plane items not tied to a goal", "datatype": "Int"},
        {"value": len(pack["manual_missing"]), "label": "Manual goals needing a reading", "datatype": "Int"},
    ]
```

Custom field fixture entry: `{"doctype": "Custom Field", "dt": "Appraisal", "fieldname": "cy_next_review_on", "fieldtype": "Date", "label": "Next review on", "insert_after": "appraisal_cycle", "module": "Caryaar Hr Ext", "name": "Appraisal-cy_next_review_on", "description": "The review pack is emailed 3 days before this date."}`.

`hooks.py` scheduler: add `"0 8 * * *": ["caryaar_hr_ext.performance.review_pack.send_scheduled_packs"]`.

- [ ] **Step 4: Run the tests**

Pure: `python3 -m pytest caryaar_hr_ext/performance/tests -q` → PASS. Staging: the two integration tests → PASS; open the report in the desk for one employee and send one pack to a test mailbox with `bench --site erp.caryaar.com execute caryaar_hr_ext.performance.review_pack.send_pack --kwargs '{"employee": "HR-EMP-00008", "cycle": "Oct 2026 - Mar 2027", "as_of": "2026-10-01"}'` on staging (emails muted there; check Email Queue).

- [ ] **Step 5: Commit**

```bash
git add caryaar_hr_ext/performance/review_pack.py caryaar_hr_ext/performance/meter_rules.py caryaar_hr_ext/caryaar_hr_ext/report/goal_review_pack caryaar_hr_ext/templates/emails/review_pack.html caryaar_hr_ext/fixtures/custom_field.json caryaar_hr_ext/hooks.py caryaar_hr_ext/performance/tests
git commit -m "feat(performance): Goal Review Pack report and scheduled email (1st, 15th, 3 days before a review)"
```

---

### Task 9: Setup: goal meters fixture and Plane modules for the cycle

**Files:**
- Create: `caryaar_hr_ext/performance/setup_data/goal_meters.json`
- Modify: `caryaar_hr_ext/performance/setup.py` (`ensure_goal_meters`), `caryaar_hr_ext/hooks.py` (after_migrate)
- Create: `deploy/plane-erp-sync/ops/goal_modules.py`
- Test: `caryaar_hr_ext/performance/tests/test_meter_rules.py` (fixture consistency)

**Interfaces:**
- Produces: `setup.ensure_goal_meters()` (after_migrate; creates a Goal Meter for every goal in a Not Started or In Progress cycle whose (employee, kra) matches a fixture row and has no meter; never updates an existing meter), fixture rows `{"employee": "HR-EMP-00012", "kra": "Lead to booking conversion", "method": "Ratio to target", "metric": "conversion_pct", "window": "Cycle to date", "target_value": 5, "unit": "%", "direction": "Higher is better"}` for every goal in the cycle (61 rows at 28-Sep-2026: Ratio/Months for the CY Admin and Plane metrics in section 5 of the spec, `Plane module` for the ~12 Plane goals, `Manual` for the rest, with the target numbers copied from each goal's description); `ops/goal_modules.py`: for each Plane-module meter, creates a module named after the goal in the department's Plane project (DEV for Technology, MKT for Marketing, OPS for Customer Experience and Workshop Relations, PARTNER, FINANCE, HR, CORP for the founders) through the `cy-automation` token on the VM, then writes `cy_plane_module` on the goal through the ERP REST API. Idempotent: skips a goal whose `cy_plane_module` is set or whose module name already exists.

- [ ] **Step 1: Write the failing test**

```python
# test_meter_rules.py
import json
from pathlib import Path


def test_goal_meter_fixture_is_consistent():
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
```

- [ ] **Step 2: Run to verify it fails**

Expected: FAIL with `FileNotFoundError` for `goal_meters.json`.

- [ ] **Step 3: Write the fixture and the setup**

`goal_meters.json`: one row per (employee, kra) in the cycle. Map every goal as follows (read the goal descriptions in the ERP for the target numbers; the metric keys are the ones registered in `meter.METRICS`):
- Customer Experience (Anagha HR-EMP-00012, Janhavi HR-EMP-00010): Lead to booking conversion → Ratio, `conversion_pct`, target 5, unit %; Customer follow-ups on time → Ratio, `followups_on_time_pct`, target 95; CRM data completeness → Ratio, `leads_statused_48h_pct`, target 100; Customer satisfaction → Manual; Job updates to customers on time → Manual (phase 2 metric).
- Hiren HR-EMP-00006: Service Partners onboarded → Manual (phase 2 `partners_onboarded`); turnaround → Manual (phase 2); Disputes and escalations → Manual (phase 2); Quality audits → Plane module; Team development (conversion) → Ratio `conversion_pct` target 5.
- Shiwans HR-EMP-00008: Committed sprint work → Plane module; Production reliability → Months meeting standard, `incidents_fixed_24h_pct`, standard 100, direction Higher; Release quality → Months meeting standard, `release_bugs_14d`, standard 1, direction Lower; Support to operations → Ratio `support_on_time_pct` target 90; Documentation → Ratio `wiki_pages` target 12 (2 a month for 6 months), window Cycle to date.
- Nayan HR-EMP-00011: Learning plan → Plane module; Assigned tasks → Plane module; Code review feedback → Manual; Documentation → Ratio `wiki_pages` target 6; Team participation → Manual.
- Kaushik HR-EMP-00014: Content calendar → Plane module; Reach through ATL → Plane module; Ground leads and research → Manual (phase 2 `ground_leads`); Cost per lead → Manual (phase 2); Brand consistency → Manual.
- Zoeb HR-EMP-00005: Partnerships signed → Plane module; Revenue from partnerships → Manual (phase 2); Partner activation → Manual (phase 2); Partner retention → Manual (phase 2); Founders' office execution → Plane module.
- Shubham HR-EMP-00007: all five Manual in phase 1 (books, AP/AR, GST/TDS, payouts, MIS); MIS → Plane module.
- Reema HR-EMP-00004, Melita HR-EMP-00016: Hiring turnaround, Attendance and payroll accuracy, Policy compliance → Manual (phase 2 ERP metrics); Appraisal cycle on time → Plane module; Employee engagement → Manual.
- Founders: Company Revenue, Company Profitability → Manual (phase 2 ERP); New Customers Onboarded (Sahaib HR-EMP-00002) → Manual (phase 2); Customers Managed, Partners Onboarded, Partners Managed (Joel HR-EMP-00003) → Manual (phase 2); Technology Development, Technology Maintained (Sahaib) → Plane module.

`setup.py`:

```python
def ensure_goal_meters() -> int:
    rows = json.loads((Path(__file__).parent / "setup_data" / "goal_meters.json").read_text())
    wanted = {(r["employee"], r["kra"]): r for r in rows}
    cycles = frappe.get_all("Appraisal Cycle", filters={"status": ("in", ["Not Started", "In Progress"])}, pluck="name")
    created = 0
    for g in frappe.get_all("Goal", filters={"appraisal_cycle": ("in", cycles), "is_group": 0, "status": ("!=", "Archived")},
                            fields=["name", "employee", "kra"]):
        r = wanted.get((g.employee, g.kra))
        if not r or frappe.db.exists("Goal Meter", g.name):
            continue
        frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": r["method"], "metric": r.get("metric"),
                        "window": r.get("window", "Cycle to date"), "target_value": r.get("target_value"),
                        "standard_value": r.get("standard_value"), "unit": r.get("unit"),
                        "direction": r.get("direction", "Higher is better"), "source_note": r.get("source_note"),
                        "active": 1}).insert(ignore_permissions=True)
        created += 1
    return created
```

Add `"caryaar_hr_ext.performance.setup.ensure_goal_meters"` to `after_migrate` in `hooks.py`.

`ops/goal_modules.py` (run from the operator's Mac; Plane part through `gcloud compute ssh caryaar-plane ... --command 'python3 -'` with the token read on the VM, ERP part through `~/.config/caryaar/frappe.env`): list Goal Meters with method Plane module and a blank `cy_plane_module` on the goal, resolve the project by the employee's department (map above), `POST /api/v1/workspaces/caryaar/projects/{project}/modules/ {"name": "<goal_name>"}` unless a module of that name exists, then `frappe.client.set_value("Goal", goal, "cy_plane_module", module_id)`. Print one line per goal.

- [ ] **Step 4: Run the tests and the setup on staging**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests -q` → PASS. On staging: `bench --site erp.caryaar.com execute caryaar_hr_ext.performance.setup.ensure_goal_meters` → prints the count (about 61). Run `ops/goal_modules.py --dry-run` locally → lists the modules it would create; do not create modules until Task 10 (they are real Plane objects).

- [ ] **Step 5: Commit**

```bash
git add caryaar_hr_ext/performance/setup_data/goal_meters.json caryaar_hr_ext/performance/setup.py caryaar_hr_ext/hooks.py deploy/plane-erp-sync/ops/goal_modules.py caryaar_hr_ext/performance/tests/test_meter_rules.py
git commit -m "feat(performance): goal meter fixture, after_migrate setup and the Plane module creator"
```

---

### Task 10: Staging verification and production rollout

**Files:**
- Modify: `caryaar_hr_ext/docs/superpowers/specs/2026-09-28-goal-meter-design.md` (a "Rollout record" section at the end)

- [ ] **Step 1: Staging**

Start the staging VM (`gcloud compute instances start frappe-staging --zone asia-south1-a --project cy-erp`), restore the latest prod backup as in the leave-migration rehearsal, set `mute_emails` and `pause_scheduler` in site config, install the branch, `bench --site erp.caryaar.com migrate`, run the Frappe tests from Tasks 3, 6, 8, then `ensure_goal_meters`, then `bench execute caryaar_hr_ext.performance.meter.run_meter` and open the Goal Review Pack report for Anagha and Shiwans. Record counts in the rollout record. Stop the VM afterwards.

- [ ] **Step 2: Production ERP**

Push the branch; the founder builds the derived image and switches the four services plus `docker compose restart frontend` in one command (the recreate changes the backend IP; see the program memory). Run `migrate` (fixtures land the Appraisal field; after_migrate creates the meters). Verify: `Goal Meter` count, `Performance Sync Settings` shows the new stamps blank, the report opens.

- [ ] **Step 3: Plane sync**

On `caryaar-plane`: rebuild and restart the `plane-erp-sync` container from the branch (`deploy/plane-erp-sync/deploy-on-vm.sh`), run `--dry-run` once, then let it run; within 20 minutes `Plane Work Item` holds every item and `plane_items_synced_through` is set; the first run is a full pass.

- [ ] **Step 4: CY Admin**

Founder runs `deploy.sh prod` (migration 267 is additive). Confirm the beat entries in the worker log (`performance-followup-snapshot` at 00:05 IST), and the next morning that `agent_followup_snapshots` has rows and `Work Activity Day` rows carry the five new keys.

- [ ] **Step 5: Plane modules and first packs**

Run `ops/goal_modules.py` (creates about 12 modules; the founder tells managers to move items in). Wait for one nightly run; check three readings by hand (one Ratio, one Months, one Plane module). Send one pack to the founders with `send_pack` for one employee as the sample. Add the rollout record to the spec and commit.

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/specs/2026-09-28-goal-meter-design.md
git commit -m "docs(performance): goal meter phase 1 rollout record"
```
