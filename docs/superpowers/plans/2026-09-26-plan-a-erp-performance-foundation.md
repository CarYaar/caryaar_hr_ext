# Plan A: ERP performance foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the ERP the records, intake endpoint and nightly engine that turn Plane and CY Admin activity into per-person adherence, goal progress and rating categories, and version the live WFH approval setup as app fixtures.

**Architecture:** Pure decision logic lives in `caryaar_hr_ext/performance/rules.py` (no Frappe import, tested locally with pytest). Thin Frappe glue (`api.py` intake endpoint, `engine.py` nightly job, four new DocTypes, one Script Report, dashboard fixtures) calls those rules. Plans B (Plane sync) and C (CY Admin export) are separate plans; both only POST to the intake endpoint defined here, so this plan ships and is testable on its own.

**Tech Stack:** Frappe 16.27 / HRMS 16.13 (production ERP runs in Docker on VM `caryaar-erpnext`, project `cy-erp`, time zone Asia/Kolkata), Python 3.12, pytest 8 (local, for pure rules only), Frappe `IntegrationTestCase` (run on the staging bench).

**Spec:** `docs/superpowers/specs/2026-09-26-performance-plane-wfh-program-design.md` (sections W1, W2, W4, W4c, W5).

## Global Constraints

- Custom fields use the `cy_` prefix. New DocTypes live in module `Caryaar Hr Ext`.
- The sync clients authenticate as a dedicated ERP user holding only role `Performance Sync`. Never the Administrator key.
- All day boundaries are IST (the ERP stores naive datetimes in Asia/Kolkata).
- Labels and copy: no em dashes, sentence case, "Service Partners" never vendor or garage, dates shown DD-MMM-YYYY.
- Fail-soft: one bad goal, employee or row is logged and skipped; the rest of the run completes.
- Rating bands (spec D6): Exceptional 4.50+, Excellent 3.75 to 4.49, Good 3.00 to 3.74, Fair 2.00 to 2.99, Non-Satisfactory below 2.00.
- Adherence is computed from October but only counts from 01-Nov-2026 (spec D9); that is a reporting filter, not an engine rule.
- Production changes (staging VM start, app deploy, API user, secrets) each need an explicit founder go at that step.

## Review Focus

1. **A sync payload names a person by a differently cased email, or by their company email instead of their login email.** Expected: they are still matched; anyone truly unknown is returned in `unmapped` and recorded in settings, never silently dropped. Pinned in Task 4.
2. **The same day is sent twice (retry, hourly re-sync), sometimes without the end-of-day snapshot metrics.** Expected: the existing record is updated, never duplicated, and metrics absent from the re-send keep their earlier value. Pinned in Task 1 (deterministic names) and Task 4.
3. **A source stops syncing.** Expected: days after its last confirmed sync show "pending", not "work not visible", so an outage never marks everyone non-adherent. Pinned in Task 1.
4. **Holidays, weekly offs, leave and absent days.** Expected: no adherence check applies on those days. Pinned in Task 1.
5. **A goal whose appraisal cycle is not active, or a malformed Plane module id on a goal.** Expected: that goal is skipped with a log entry and every other goal still updates. Pinned in Task 5.

## Not in this plan (and why)

- Manager response time and monthly goal-hygiene checks from spec W4b need workflow timestamps from the Version log; they are a follow-up once the core checks are live.
- Plane and CY Admin data collection: Plans B and C.
- Keeping scoped manager user permissions in step with reporting lines: only three rows exist; revisit when headcount grows.

---

## File Structure

```
caryaar_hr_ext/
  performance/
    __init__.py                 empty; must never import frappe
    rules.py                    pure logic: payload validation, doc names, adherence, bands, progress
    api.py                      whitelisted intake endpoints (Frappe)
    engine.py                   nightly job: adherence days, goal progress, categories (Frappe)
    tests/
      __init__.py
      conftest.py               skips Frappe-only tests when frappe is not importable
      test_rules.py             pure tests (local pytest)
      test_meta.py              pure tests over DocType and fixture JSON
      test_integration.py       Frappe IntegrationTestCase (staging bench only)
  caryaar_hr_ext/
    doctype/
      work_activity_day/        {__init__.py, work_activity_day.json, work_activity_day.py}
      work_adherence_day/       {__init__.py, work_adherence_day.json, work_adherence_day.py}
      plane_module_progress/    {__init__.py, plane_module_progress.json, plane_module_progress.py}
      performance_sync_settings/{__init__.py, performance_sync_settings.json, performance_sync_settings.py}
    report/
      rating_distribution/      {__init__.py, rating_distribution.json, rating_distribution.py}
  fixtures/
    custom_field.json           regenerated: Employee + Attendance Request + Goal + Appraisal cy_ fields
    role.json                   + Performance Sync
    workflow.json, workflow_state.json, workflow_action_master.json,
    notification.json, custom_docperm.json      exported from production (Task 3)
    dashboard_chart.json, number_card.json, dashboard.json    (Task 6)
  hooks.py                      fixtures filters, scheduler_events
scripts/
  export_live_fixtures.py       read-only export of live records into fixture format
```

---

### Task 1: Pure performance rules

**Files:**
- Create: `caryaar_hr_ext/performance/__init__.py` (empty)
- Create: `caryaar_hr_ext/performance/rules.py`
- Create: `caryaar_hr_ext/performance/tests/__init__.py` (empty)
- Create: `caryaar_hr_ext/performance/tests/conftest.py`
- Test: `caryaar_hr_ext/performance/tests/test_rules.py`

**Interfaces:**
- Produces (used by Tasks 2, 4, 5, 6 and by Plans B and C through the payload contract):
  - `SOURCES: tuple[str, ...] = ("Plane", "CY Admin")`
  - `METRIC_KEYS: dict[str, tuple[str, ...]]`
  - `class ActivityRow(NamedTuple): email: str; date: str; metrics: dict[str, int]`
  - `class ActivityBatch(NamedTuple): source: str; synced_through: datetime; rows: list[ActivityRow]`
  - `validate_activity_payload(source, synced_through, rows) -> ActivityBatch` (raises `ValueError`)
  - `class ModuleRow(NamedTuple): module_id: str; project_identifier: str; module_name: str; total_issues: int; completed_issues: int`
  - `validate_module_payload(synced_through, modules) -> tuple[datetime, list[ModuleRow]]` (raises `ValueError`)
  - `activity_doc_name(employee: str, date_iso: str, source: str) -> str`
  - `adherence_doc_name(employee: str, date_iso: str) -> str`
  - `parse_department_sources(text: str) -> dict[str, list[str]]` (raises `ValueError`)
  - `class DayContext(NamedTuple)` and `class AdherenceResult(NamedTuple)` (fields below)
  - `adherence_day(ctx: DayContext) -> AdherenceResult`
  - `module_progress(total: int, completed: int) -> float | None`
  - `performance_category(final_score: float | None) -> str | None`

- [ ] **Step 1: Write the conftest so local pytest never collects Frappe-only tests**

```python
# caryaar_hr_ext/performance/tests/conftest.py
import importlib.util

collect_ignore = []
if importlib.util.find_spec("frappe") is None:
    collect_ignore.append("test_integration.py")
```

- [ ] **Step 2: Write the failing tests**

```python
# caryaar_hr_ext/performance/tests/test_rules.py
from datetime import date, datetime

import pytest

from caryaar_hr_ext.performance import rules as r

IST_EOD = datetime(2026, 10, 1, 23, 59, 59)


# ---------- payload validation ----------
def _row(email="Janhavi.Nanaware@CarYaar.com", day="2026-10-01", **metrics):
    return {"email": email, "date": day, "metrics": metrics or {"calls_handled": 3}}


def test_valid_cy_admin_payload_normalises_email_and_parses_time():
    b = r.validate_activity_payload("CY Admin", "2026-10-02T00:15:00+05:30", [_row()])
    assert b.source == "CY Admin"
    assert b.rows[0].email == "janhavi.nanaware@caryaar.com"
    assert b.rows[0].metrics == {"calls_handled": 3}
    assert b.synced_through == datetime(2026, 10, 2, 0, 15)  # naive IST


def test_synced_through_in_utc_is_converted_to_ist():
    b = r.validate_activity_payload("Plane", "2026-10-01T18:45:00Z", [_row(activity_count=1)])
    assert b.synced_through == datetime(2026, 10, 2, 0, 15)


@pytest.mark.parametrize("source", ["plane", "Slack", "", None])
def test_unknown_source_rejected(source):
    with pytest.raises(ValueError, match="source"):
        r.validate_activity_payload(source, "2026-10-01T10:00:00+05:30", [_row()])


def test_metric_not_allowed_for_source_rejected():
    with pytest.raises(ValueError, match="calls_handled"):
        r.validate_activity_payload("Plane", "2026-10-01T10:00:00+05:30", [_row(calls_handled=1)])


@pytest.mark.parametrize("bad", [-1, 1.5, "3", True, 10**8])
def test_bad_metric_values_rejected(bad):
    with pytest.raises(ValueError):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row(calls_handled=bad)])


@pytest.mark.parametrize("day", ["2026-13-01", "01-10-2026", "", None])
def test_bad_dates_rejected(day):
    with pytest.raises(ValueError, match="date"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row(day=day)])


def test_naive_synced_through_rejected():
    with pytest.raises(ValueError, match="time zone"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00", [_row()])


def test_too_many_rows_rejected():
    with pytest.raises(ValueError, match="2000"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row()] * 2001)


def test_email_without_at_rejected():
    with pytest.raises(ValueError, match="email"):
        r.validate_activity_payload("CY Admin", "2026-10-01T10:00:00+05:30", [_row(email="janhavi")])


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
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_rules.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'caryaar_hr_ext.performance.rules'` (or `ImportError`).

- [ ] **Step 4: Write the implementation**

```python
# caryaar_hr_ext/performance/rules.py
"""Pure decision logic for adherence, goal progress and rating categories.

No Frappe imports here: this module is tested with plain pytest and used by
performance/api.py and performance/engine.py.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from typing import NamedTuple

SOURCES: tuple[str, ...] = ("Plane", "CY Admin")
METRIC_KEYS: dict[str, tuple[str, ...]] = {
    "Plane": ("activity_count", "completed_count"),
    "CY Admin": ("calls_handled", "calls_answered", "talk_seconds", "dispositions",
                 "status_moves", "notes_written", "bookings_credited",
                 "leads_assigned", "leads_untouched", "followups_overdue"),
}
MAX_ROWS = 2000
MAX_METRIC = 10_000_000
IST = timezone(timedelta(hours=5, minutes=30))
BANDS: tuple[tuple[float, str], ...] = (
    (4.5, "Exceptional"), (3.75, "Excellent"), (3.0, "Good"), (2.0, "Fair"), (0.0, "Non-Satisfactory"))
_SOURCE_SLUG = {"Plane": "PLANE", "CY Admin": "CYADMIN"}


class ActivityRow(NamedTuple):
    email: str
    date: str
    metrics: dict[str, int]


class ActivityBatch(NamedTuple):
    source: str
    synced_through: datetime
    rows: list[ActivityRow]


class ModuleRow(NamedTuple):
    module_id: str
    project_identifier: str
    module_name: str
    total_issues: int
    completed_issues: int


class DayContext(NamedTuple):
    is_holiday: bool
    attendance_status: str | None
    expected_sources: tuple[str, ...]
    fresh_sources: frozenset[str]
    activity: dict[str, dict[str, int]]
    wfh_requested: bool
    wfh_approved: bool


class AdherenceResult(NamedTuple):
    is_working_day: bool
    wfh: bool
    work_visible: bool | None
    wfh_approved: bool | None
    wfh_evidenced: bool | None
    checks_passed: int
    checks_applicable: int
    adherence_pct: float | None


def _parse_aware(value) -> datetime:
    if not isinstance(value, str) or not value:
        raise ValueError("synced_through must be an ISO 8601 datetime string")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as e:
        raise ValueError(f"synced_through is not a valid datetime: {value!r}") from e
    if dt.tzinfo is None:
        raise ValueError("synced_through must carry a time zone offset")
    return dt.astimezone(IST).replace(tzinfo=None)


def _parse_day(value) -> str:
    if not isinstance(value, str):
        raise ValueError(f"row date must be YYYY-MM-DD, got {value!r}")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as e:
        raise ValueError(f"row date must be YYYY-MM-DD, got {value!r}") from e


def _metric(name: str, value) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"metric {name} must be a whole number, got {value!r}")
    if value < 0 or value > MAX_METRIC:
        raise ValueError(f"metric {name} out of range: {value}")
    return value


def validate_activity_payload(source, synced_through, rows) -> ActivityBatch:
    if source not in SOURCES:
        raise ValueError(f"source must be one of {SOURCES}, got {source!r}")
    when = _parse_aware(synced_through)
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"at most {MAX_ROWS} rows per call, got {len(rows)}")
    allowed = set(METRIC_KEYS[source])
    out: list[ActivityRow] = []
    for i, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"row {i} must be an object")
        email = row.get("email")
        if not isinstance(email, str) or "@" not in email:
            raise ValueError(f"row {i} email is not an email address: {email!r}")
        metrics = row.get("metrics")
        if not isinstance(metrics, dict):
            raise ValueError(f"row {i} metrics must be an object")
        unknown = set(metrics) - allowed
        if unknown:
            raise ValueError(f"row {i} has metrics not allowed for {source}: {sorted(unknown)}")
        out.append(ActivityRow(email.strip().lower(), _parse_day(row.get("date")),
                               {k: _metric(k, v) for k, v in metrics.items()}))
    return ActivityBatch(source, when, out)


def validate_module_payload(synced_through, modules) -> tuple[datetime, list[ModuleRow]]:
    when = _parse_aware(synced_through)
    if not isinstance(modules, list) or len(modules) > MAX_ROWS:
        raise ValueError(f"modules must be a list of at most {MAX_ROWS}")
    out: list[ModuleRow] = []
    for i, m in enumerate(modules):
        if not isinstance(m, dict):
            raise ValueError(f"module {i} must be an object")
        mid = m.get("module_id")
        if not isinstance(mid, str) or not mid.strip():
            raise ValueError(f"module {i} module_id is required")
        total = _metric("total_issues", m.get("total_issues"))
        done = _metric("completed_issues", m.get("completed_issues"))
        if done > total:
            raise ValueError(f"module {i} completed_issues ({done}) exceeds total_issues ({total})")
        out.append(ModuleRow(mid.strip(), str(m.get("project_identifier") or ""),
                             str(m.get("module_name") or "")[:140], total, done))
    return when, out


def activity_doc_name(employee: str, date_iso: str, source: str) -> str:
    return f"WACT-{employee}-{date_iso}-{_SOURCE_SLUG[source]}"


def adherence_doc_name(employee: str, date_iso: str) -> str:
    return f"WADH-{employee}-{date_iso}"


def parse_department_sources(text: str) -> dict[str, list[str]]:
    if not text or not text.strip():
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"department sources is not valid JSON: {e}") from e
    if not isinstance(data, dict):
        raise ValueError("department sources must be an object of department to list of sources")
    for dept, srcs in data.items():
        if not isinstance(srcs, list) or not srcs or any(s not in SOURCES for s in srcs):
            raise ValueError(f"{dept}: sources must be a non-empty list from {SOURCES}")
    return data


def _active(source: str, m: dict[str, int]) -> bool:
    if source == "Plane":
        return m.get("activity_count", 0) > 0 or m.get("completed_count", 0) > 0
    return m.get("calls_handled", 0) > 0 or m.get("status_moves", 0) > 0 or m.get("notes_written", 0) > 0


def _evidenced(source: str, m: dict[str, int]) -> bool:
    if source == "Plane":
        return m.get("completed_count", 0) > 0
    return m.get("calls_handled", 0) > 0


def _judge(ctx: DayContext, test) -> bool | None:
    fresh = [s for s in ctx.expected_sources if s in ctx.fresh_sources]
    if any(test(s, ctx.activity.get(s, {})) for s in fresh):
        return True
    if fresh and len(fresh) == len(ctx.expected_sources):
        return False
    return None


def adherence_day(ctx: DayContext) -> AdherenceResult:
    working = not ctx.is_holiday and ctx.attendance_status not in ("On Leave", "Absent")
    wfh = ctx.attendance_status == "Work From Home" or ctx.wfh_requested
    if not working:
        return AdherenceResult(False, wfh, None, None, None, 0, 0, None)
    visible = _judge(ctx, _active)
    approved = bool(ctx.wfh_approved) if wfh else None
    evidenced = _judge(ctx, _evidenced) if wfh else None
    checks = [c for c in (visible, approved, evidenced) if c is not None]
    passed = sum(1 for c in checks if c)
    pct = round(100.0 * passed / len(checks), 1) if checks else None
    return AdherenceResult(True, wfh, visible, approved, evidenced, passed, len(checks), pct)


def module_progress(total: int, completed: int) -> float | None:
    if not total:
        return None
    return round(100.0 * completed / total, 1)


def performance_category(final_score: float | None) -> str | None:
    if not final_score or final_score <= 0:
        return None
    for floor, name in BANDS:
        if final_score >= floor:
            return name
    return None
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_rules.py -q`
Expected: all tests pass (about 45 including parametrised cases).

- [ ] **Step 6: Commit**

```bash
git add caryaar_hr_ext/performance
git commit -m "feat(performance): pure rules for intake validation, adherence, goal progress and rating bands"
```

---

### Task 2: DocTypes for activity, adherence, module progress and settings

**Files:**
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/work_activity_day/{__init__.py,work_activity_day.json,work_activity_day.py}`
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/work_adherence_day/{__init__.py,work_adherence_day.json,work_adherence_day.py}`
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/plane_module_progress/{__init__.py,plane_module_progress.json,plane_module_progress.py}`
- Create: `caryaar_hr_ext/caryaar_hr_ext/doctype/performance_sync_settings/{__init__.py,performance_sync_settings.json,performance_sync_settings.py}`
- Test: `caryaar_hr_ext/performance/tests/test_meta.py`

**Interfaces:**
- Consumes: `rules.activity_doc_name`, `rules.adherence_doc_name`, `rules.parse_department_sources`, `rules.METRIC_KEYS`.
- Produces: DocTypes `Work Activity Day` (fields: employee, employee_name, department, activity_date, source, synced_at, plus every key in `METRIC_KEYS`), `Work Adherence Day` (employee, employee_name, department, adherence_date, is_working_day, attendance_status, expected_sources, wfh, work_visible, wfh_approved, wfh_evidenced, checks_passed, checks_applicable, adherence_pct), `Plane Module Progress` (module_id, project_identifier, module_name, total_issues, completed_issues, progress, synced_at), single `Performance Sync Settings` (department_sources, plane_synced_through, cy_admin_synced_through, plane_modules_synced_through, unmapped_emails, last_error).

- [ ] **Step 1: Write the failing meta tests**

```python
# caryaar_hr_ext/performance/tests/test_meta.py
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_meta.py -q`
Expected: FAIL with `FileNotFoundError` for `work_activity_day.json`.

- [ ] **Step 3: Create the four DocTypes**

Each folder gets an empty `__init__.py`. JSON files:

```json
// caryaar_hr_ext/caryaar_hr_ext/doctype/work_activity_day/work_activity_day.json
{
 "doctype": "DocType", "name": "Work Activity Day", "module": "Caryaar Hr Ext", "custom": 0,
 "istable": 0, "issingle": 0, "engine": "InnoDB", "track_changes": 0,
 "autoname": "", "naming_rule": "By script", "title_field": "employee_name",
 "sort_field": "activity_date", "sort_order": "DESC",
 "owner": "Administrator", "modified_by": "Administrator",
 "creation": "2026-09-26 18:00:00.000000", "modified": "2026-09-26 18:00:00.000000",
 "field_order": ["employee", "employee_name", "department", "activity_date", "source", "synced_at",
  "section_plane", "activity_count", "completed_count",
  "section_cy", "calls_handled", "calls_answered", "talk_seconds", "dispositions", "status_moves",
  "notes_written", "bookings_credited", "leads_assigned", "leads_untouched", "followups_overdue"],
 "fields": [
  {"fieldname": "employee", "fieldtype": "Link", "options": "Employee", "label": "Employee", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1, "search_index": 1},
  {"fieldname": "employee_name", "fieldtype": "Data", "label": "Employee name", "fetch_from": "employee.employee_name", "read_only": 1, "in_list_view": 1},
  {"fieldname": "department", "fieldtype": "Link", "options": "Department", "label": "Department", "fetch_from": "employee.department", "read_only": 1, "in_standard_filter": 1},
  {"fieldname": "activity_date", "fieldtype": "Date", "label": "Date", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1, "search_index": 1},
  {"fieldname": "source", "fieldtype": "Select", "options": "Plane\nCY Admin", "label": "Source", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1},
  {"fieldname": "synced_at", "fieldtype": "Datetime", "label": "Synced at", "read_only": 1},
  {"fieldname": "section_plane", "fieldtype": "Section Break", "label": "Plane"},
  {"fieldname": "activity_count", "fieldtype": "Int", "label": "Actions in Plane", "default": "0"},
  {"fieldname": "completed_count", "fieldtype": "Int", "label": "Tasks completed", "default": "0"},
  {"fieldname": "section_cy", "fieldtype": "Section Break", "label": "CY Admin"},
  {"fieldname": "calls_handled", "fieldtype": "Int", "label": "Calls handled", "default": "0"},
  {"fieldname": "calls_answered", "fieldtype": "Int", "label": "Calls answered", "default": "0"},
  {"fieldname": "talk_seconds", "fieldtype": "Int", "label": "Talk time (seconds)", "default": "0"},
  {"fieldname": "dispositions", "fieldtype": "Int", "label": "Calls with an outcome", "default": "0"},
  {"fieldname": "status_moves", "fieldtype": "Int", "label": "Lead status changes", "default": "0"},
  {"fieldname": "notes_written", "fieldtype": "Int", "label": "Notes written", "default": "0"},
  {"fieldname": "bookings_credited", "fieldtype": "Int", "label": "Bookings credited", "default": "0"},
  {"fieldname": "leads_assigned", "fieldtype": "Int", "label": "Leads assigned (end of day)", "default": "0"},
  {"fieldname": "leads_untouched", "fieldtype": "Int", "label": "Leads untouched (end of day)", "default": "0"},
  {"fieldname": "followups_overdue", "fieldtype": "Int", "label": "Follow-ups overdue (end of day)", "default": "0"}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
  {"role": "HR Manager", "read": 1, "report": 1, "export": 1},
  {"role": "Performance Sync", "read": 1, "write": 1, "create": 1}
 ]
}
```

```python
# caryaar_hr_ext/caryaar_hr_ext/doctype/work_activity_day/work_activity_day.py
from frappe.model.document import Document

from caryaar_hr_ext.performance.rules import activity_doc_name


class WorkActivityDay(Document):
    def autoname(self):
        self.name = activity_doc_name(self.employee, str(self.activity_date), self.source)
```

```json
// caryaar_hr_ext/caryaar_hr_ext/doctype/work_adherence_day/work_adherence_day.json
{
 "doctype": "DocType", "name": "Work Adherence Day", "module": "Caryaar Hr Ext", "custom": 0,
 "istable": 0, "issingle": 0, "engine": "InnoDB", "track_changes": 0,
 "autoname": "", "naming_rule": "By script", "title_field": "employee_name",
 "sort_field": "adherence_date", "sort_order": "DESC",
 "owner": "Administrator", "modified_by": "Administrator",
 "creation": "2026-09-26 18:00:00.000000", "modified": "2026-09-26 18:00:00.000000",
 "field_order": ["employee", "employee_name", "department", "adherence_date", "is_working_day",
  "attendance_status", "expected_sources", "wfh", "column_break_1", "work_visible", "wfh_approved",
  "wfh_evidenced", "checks_passed", "checks_applicable", "adherence_pct"],
 "fields": [
  {"fieldname": "employee", "fieldtype": "Link", "options": "Employee", "label": "Employee", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1, "search_index": 1},
  {"fieldname": "employee_name", "fieldtype": "Data", "label": "Employee name", "fetch_from": "employee.employee_name", "read_only": 1, "in_list_view": 1},
  {"fieldname": "department", "fieldtype": "Link", "options": "Department", "label": "Department", "fetch_from": "employee.department", "read_only": 1, "in_standard_filter": 1},
  {"fieldname": "adherence_date", "fieldtype": "Date", "label": "Date", "reqd": 1, "in_list_view": 1, "in_standard_filter": 1, "search_index": 1},
  {"fieldname": "is_working_day", "fieldtype": "Check", "label": "Working day", "read_only": 1},
  {"fieldname": "attendance_status", "fieldtype": "Data", "label": "Attendance", "read_only": 1},
  {"fieldname": "expected_sources", "fieldtype": "Data", "label": "Work record", "read_only": 1},
  {"fieldname": "wfh", "fieldtype": "Check", "label": "WFH day", "read_only": 1},
  {"fieldname": "column_break_1", "fieldtype": "Column Break"},
  {"fieldname": "work_visible", "fieldtype": "Select", "options": "\nYes\nNo", "label": "Work visible", "read_only": 1, "in_list_view": 1},
  {"fieldname": "wfh_approved", "fieldtype": "Select", "options": "\nYes\nNo", "label": "WFH approved before the day", "read_only": 1},
  {"fieldname": "wfh_evidenced", "fieldtype": "Select", "options": "\nYes\nNo", "label": "WFH work shown", "read_only": 1},
  {"fieldname": "checks_passed", "fieldtype": "Int", "label": "Checks passed", "read_only": 1},
  {"fieldname": "checks_applicable", "fieldtype": "Int", "label": "Checks that applied", "read_only": 1},
  {"fieldname": "adherence_pct", "fieldtype": "Percent", "label": "Adherence", "read_only": 1, "in_list_view": 1}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
  {"role": "HR Manager", "read": 1, "report": 1, "export": 1},
  {"role": "Performance Sync", "read": 1}
 ]
}
```

```python
# caryaar_hr_ext/caryaar_hr_ext/doctype/work_adherence_day/work_adherence_day.py
from frappe.model.document import Document

from caryaar_hr_ext.performance.rules import adherence_doc_name


class WorkAdherenceDay(Document):
    def autoname(self):
        self.name = adherence_doc_name(self.employee, str(self.adherence_date))
```

```json
// caryaar_hr_ext/caryaar_hr_ext/doctype/plane_module_progress/plane_module_progress.json
{
 "doctype": "DocType", "name": "Plane Module Progress", "module": "Caryaar Hr Ext", "custom": 0,
 "istable": 0, "issingle": 0, "engine": "InnoDB", "track_changes": 0,
 "autoname": "field:module_id", "naming_rule": "By fieldname", "title_field": "module_name",
 "sort_field": "modified", "sort_order": "DESC",
 "owner": "Administrator", "modified_by": "Administrator",
 "creation": "2026-09-26 18:00:00.000000", "modified": "2026-09-26 18:00:00.000000",
 "field_order": ["module_id", "project_identifier", "module_name", "total_issues", "completed_issues", "progress", "synced_at"],
 "fields": [
  {"fieldname": "module_id", "fieldtype": "Data", "label": "Plane module ID", "reqd": 1, "unique": 1},
  {"fieldname": "project_identifier", "fieldtype": "Data", "label": "Project", "in_list_view": 1, "in_standard_filter": 1},
  {"fieldname": "module_name", "fieldtype": "Data", "label": "Module", "in_list_view": 1},
  {"fieldname": "total_issues", "fieldtype": "Int", "label": "Tasks", "default": "0"},
  {"fieldname": "completed_issues", "fieldtype": "Int", "label": "Tasks done", "default": "0"},
  {"fieldname": "progress", "fieldtype": "Percent", "label": "Progress", "in_list_view": 1},
  {"fieldname": "synced_at", "fieldtype": "Datetime", "label": "Synced at", "read_only": 1}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1, "report": 1, "export": 1},
  {"role": "HR Manager", "read": 1, "report": 1},
  {"role": "Performance Sync", "read": 1, "write": 1, "create": 1}
 ]
}
```

```python
# caryaar_hr_ext/caryaar_hr_ext/doctype/plane_module_progress/plane_module_progress.py
from frappe.model.document import Document

from caryaar_hr_ext.performance.rules import module_progress


class PlaneModuleProgress(Document):
    def validate(self):
        self.progress = module_progress(self.total_issues or 0, self.completed_issues or 0) or 0
```

```json
// caryaar_hr_ext/caryaar_hr_ext/doctype/performance_sync_settings/performance_sync_settings.json
{
 "doctype": "DocType", "name": "Performance Sync Settings", "module": "Caryaar Hr Ext", "custom": 0,
 "istable": 0, "issingle": 1, "engine": "InnoDB", "track_changes": 1,
 "owner": "Administrator", "modified_by": "Administrator",
 "creation": "2026-09-26 18:00:00.000000", "modified": "2026-09-26 18:00:00.000000",
 "field_order": ["department_sources", "section_sync", "plane_synced_through", "plane_modules_synced_through",
  "cy_admin_synced_through", "unmapped_emails", "last_error"],
 "fields": [
  {"fieldname": "department_sources", "fieldtype": "Code", "options": "JSON", "label": "Work record by department",
   "description": "Departments whose work record is not Plane alone. Everyone else defaults to Plane.",
   "default": "{\"Operations - CAPL\": [\"CY Admin\", \"Plane\"]}"},
  {"fieldname": "section_sync", "fieldtype": "Section Break", "label": "Sync health"},
  {"fieldname": "plane_synced_through", "fieldtype": "Datetime", "label": "Plane activity synced through", "read_only": 1},
  {"fieldname": "plane_modules_synced_through", "fieldtype": "Datetime", "label": "Plane modules synced through", "read_only": 1},
  {"fieldname": "cy_admin_synced_through", "fieldtype": "Datetime", "label": "CY Admin synced through", "read_only": 1},
  {"fieldname": "unmapped_emails", "fieldtype": "Small Text", "label": "Emails not matched to an employee", "read_only": 1},
  {"fieldname": "last_error", "fieldtype": "Small Text", "label": "Last engine error", "read_only": 1}
 ],
 "permissions": [
  {"role": "System Manager", "read": 1, "write": 1, "create": 1},
  {"role": "HR Manager", "read": 1, "write": 1},
  {"role": "Performance Sync", "read": 1, "write": 1}
 ]
}
```

```python
# caryaar_hr_ext/caryaar_hr_ext/doctype/performance_sync_settings/performance_sync_settings.py
import frappe
from frappe.model.document import Document

from caryaar_hr_ext.performance.rules import parse_department_sources


class PerformanceSyncSettings(Document):
    def validate(self):
        try:
            parse_department_sources(self.department_sources or "")
        except ValueError as e:
            frappe.throw(str(e))
```

JSON files must be written without the `// path` comment lines shown above (those mark the file only).

- [ ] **Step 4: Run to verify the meta tests pass**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests -q`
Expected: all pass (rules + meta).

- [ ] **Step 5: Commit**

```bash
git add caryaar_hr_ext/caryaar_hr_ext/doctype caryaar_hr_ext/performance/tests/test_meta.py
git commit -m "feat(performance): doctypes for work activity, adherence, Plane module progress and sync settings"
```

---

### Task 3: Version the live WFH approval setup and new fields as fixtures

**Files:**
- Create: `scripts/export_live_fixtures.py`
- Modify: `caryaar_hr_ext/hooks.py` (fixtures block)
- Create/replace: `caryaar_hr_ext/fixtures/{custom_field,role,workflow,workflow_state,workflow_action_master,notification,custom_docperm}.json`
- Test: `caryaar_hr_ext/performance/tests/test_meta.py` (extend)

**Interfaces:**
- Consumes: live production records created on 26-Sep (Workflow "Attendance Request Approval", Workflow States Draft and Cancelled, Workflow Actions "Send for Approval" and "Cancel", three Notifications, Custom DocPerms on Attendance Request, Custom Fields `cy_reports_to` and `cy_approver_user`).
- Produces: fixture files that `bench migrate` re-applies on any site; Custom Fields `Goal.cy_plane_module` and `Appraisal.cy_performance_category`; Role `Performance Sync`.

- [ ] **Step 1: Write the failing fixture tests** (append to `test_meta.py`)

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_meta.py -q`
Expected: FAIL (`workflow.json` not found; custom fields missing).

- [ ] **Step 3: Write the read-only export script**

```python
# scripts/export_live_fixtures.py
"""Export live ERP records into this app's fixture files (READ-ONLY on the ERP).

Mirrors frappe's export_json post-processing: drops per-site metadata from each
document and child row so `bench migrate` can re-apply them on any site.

Usage: set FRAPPE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET (e.g. `set -a; . ~/.config/caryaar/frappe.env; set +a`)
       python3 scripts/export_live_fixtures.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

FX = Path(__file__).resolve().parents[1] / "caryaar_hr_ext" / "fixtures"
TOP_DROP = ("modified", "modified_by", "creation", "owner", "idx", "lft", "rgt",
            "_user_tags", "_comments", "_assign", "_liked_by", "_seen")
CHILD_DROP = TOP_DROP + ("docstatus", "doctype", "modified", "name")

EXPORTS = {
    "custom_field": ("Custom Field", [["fieldname", "like", "cy_%"],
                                      ["dt", "in", ["Employee", "Attendance Request"]]]),
    "workflow": ("Workflow", [["name", "=", "Attendance Request Approval"]]),
    "workflow_state": ("Workflow State", [["name", "in", ["Draft", "Cancelled"]]]),
    "workflow_action_master": ("Workflow Action Master", [["name", "in", ["Send for Approval", "Cancel"]]]),
    "notification": ("Notification", [["name", "in", ["WFH request awaiting manager approval",
                                                      "WFH request awaiting HR approval",
                                                      "WFH request decided"]]]),
    "custom_docperm": ("Custom DocPerm", [["parent", "=", "Attendance Request"]]),
}


def strip(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k not in TOP_DROP}
    for k, v in list(out.items()):
        if isinstance(v, list):
            out[k] = [{ck: cv for ck, cv in row.items() if ck not in CHILD_DROP}
                      for row in v if isinstance(row, dict)]
    return out


def _get(path: str) -> dict:
    url = os.environ.get("FRAPPE_URL", "https://erp.caryaar.com") + path
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {os.environ['FRAPPE_API_KEY']}:{os.environ['FRAPPE_API_SECRET']}",
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def export(doctype: str, filters: list) -> list[dict]:
    q = urllib.parse.urlencode({"filters": json.dumps(filters), "fields": json.dumps(["name"]),
                                "limit_page_length": "500", "order_by": "name asc"})
    names = [d["name"] for d in _get(f"/api/resource/{urllib.parse.quote(doctype)}?{q}")["data"]]
    return [strip(_get(f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(n)}")["data"])
            for n in names]


def main() -> int:
    for fname, (doctype, filters) in EXPORTS.items():
        docs = export(doctype, filters)
        if not docs:
            print(f"ERROR: nothing exported for {doctype} {filters}", file=sys.stderr)
            return 1
        (FX / f"{fname}.json").write_text(json.dumps(docs, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"{fname}.json: {len(docs)} {doctype}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run the export (read-only GETs against production)**

Run: `cd /Users/sahaib/caryaar/caryaar-erp/caryaar_hr_ext && set -a && . ~/.config/caryaar/frappe.env && set +a && python3 scripts/export_live_fixtures.py`
Expected output (counts): `custom_field.json: 8 Custom Field` (the 6 Employee identity fields already in the repo + 2 Attendance Request), `workflow.json: 1`, `workflow_state.json: 2`, `workflow_action_master.json: 2`, `notification.json: 3`, `custom_docperm.json: 5`.
Then: `git diff --stat caryaar_hr_ext/fixtures/custom_field.json` and read the diff. The Employee rows must match what was committed before except for dropped metadata keys; stop and ask the founder if any Employee field's properties differ.

- [ ] **Step 5: Append the two new custom fields and the role**

```bash
python3 - <<'EOF'
import json
from pathlib import Path
fx = Path("caryaar_hr_ext/fixtures")
cf = json.loads((fx / "custom_field.json").read_text())
cf = [c for c in cf if c["name"] not in ("Goal-cy_plane_module", "Appraisal-cy_performance_category")]
cf += [
  {"doctype": "Custom Field", "name": "Goal-cy_plane_module", "dt": "Goal", "fieldname": "cy_plane_module",
   "fieldtype": "Data", "label": "Plane module ID", "insert_after": "kra", "module": "Caryaar Hr Ext",
   "description": "Paste the Plane module ID. Progress then updates every night from the module's tasks."},
  {"doctype": "Custom Field", "name": "Appraisal-cy_performance_category", "dt": "Appraisal",
   "fieldname": "cy_performance_category", "fieldtype": "Select",
   "options": "\nExceptional\nExcellent\nGood\nFair\nNon-Satisfactory", "label": "Performance category",
   "insert_after": "final_score", "read_only": 1, "allow_on_submit": 1, "module": "Caryaar Hr Ext",
   "in_standard_filter": 1},
]
(fx / "custom_field.json").write_text(json.dumps(sorted(cf, key=lambda c: c["name"]), indent=1, sort_keys=True) + "\n")
roles = json.loads((fx / "role.json").read_text())
if not any(r["name"] == "Performance Sync" for r in roles):
    roles.append({"doctype": "Role", "name": "Performance Sync", "role_name": "Performance Sync",
                  "desk_access": 0, "two_factor_auth": 0, "is_custom": 1})
(fx / "role.json").write_text(json.dumps(roles, indent=1, sort_keys=True) + "\n")
EOF
```

The existing `role.json` entry uses exactly the keys `doctype`, `name`, `role_name`, `desk_access`; drop `two_factor_auth` and `is_custom` from the new entry if the migrate on staging warns about them. `desk_access: 0` makes the sync user API-only.

- [ ] **Step 6: Point the hooks at the new fixtures and schedule the engine**

Replace the `fixtures = [...]` block in `caryaar_hr_ext/hooks.py` with:

```python
# ─── Fixtures ────────────────────────────────────────────────────────────
# Identity card fields (Employee), the WFH approval setup that went live on
# 26-Sep-2026 (Attendance Request fields, workflow, notifications, docperms)
# and the performance program fields (Goal, Appraisal) ship as fixtures so
# `bench migrate` recreates them on any site this app is installed on.
fixtures = [
    {
        "dt": "Custom Field",
        "filters": [["fieldname", "like", "cy_%"],
                    ["dt", "in", ["Employee", "Attendance Request", "Goal", "Appraisal"]]],
    },
    {"dt": "Role", "filters": [["role_name", "in", ["Identity Manager", "Performance Sync"]]]},
    {
        "dt": "Print Format",
        "filters": [
            ["name", "in",
             ["CY Card Front", "CY Card Back", "CY Internship Certificate"]],
        ],
    },
    {"dt": "Workflow State", "filters": [["name", "in", ["Draft", "Cancelled"]]]},
    {"dt": "Workflow Action Master", "filters": [["name", "in", ["Send for Approval", "Cancel"]]]},
    {"dt": "Workflow", "filters": [["name", "=", "Attendance Request Approval"]]},
    {"dt": "Notification", "filters": [["name", "in", [
        "WFH request awaiting manager approval",
        "WFH request awaiting HR approval",
        "WFH request decided"]]]},
    {"dt": "Custom DocPerm", "filters": [["parent", "=", "Attendance Request"]]},
]

# ─── Performance engine ──────────────────────────────────────────────────
# 23:30 IST (site time zone Asia/Kolkata): adherence for today and the three
# days before (late syncs), then goal progress from Plane modules, then
# rating categories.
scheduler_events = {
    "cron": {
        "30 23 * * *": ["caryaar_hr_ext.performance.engine.run_nightly"],
    },
}
```

- [ ] **Step 7: Run all pure tests**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests -q`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/export_live_fixtures.py caryaar_hr_ext/fixtures caryaar_hr_ext/hooks.py caryaar_hr_ext/performance/tests/test_meta.py
git commit -m "feat(fixtures): version the live WFH approval setup and add performance fields, role and schedule"
```

---

### Task 4: Intake endpoints

**Files:**
- Create: `caryaar_hr_ext/performance/api.py`
- Test: `caryaar_hr_ext/performance/tests/test_integration.py` (Frappe; runs on the staging bench in Task 7)

**Interfaces:**
- Consumes: `rules.validate_activity_payload`, `rules.validate_module_payload`, `rules.activity_doc_name`, `rules.METRIC_KEYS`; DocTypes from Task 2.
- Produces (the contract Plans B and C code against):
  - `POST /api/method/caryaar_hr_ext.performance.api.ingest_activity` with JSON body `{"source": "Plane" | "CY Admin", "synced_through": "<ISO datetime with offset>", "rows": [{"email": str, "date": "YYYY-MM-DD", "metrics": {<METRIC_KEYS[source]>: int}}]}` returns `{"message": {"accepted": int, "unmapped": [str]}}`.
  - `POST /api/method/caryaar_hr_ext.performance.api.ingest_module_progress` with `{"synced_through": str, "modules": [{"module_id", "project_identifier", "module_name", "total_issues", "completed_issues"}]}` returns `{"message": {"accepted": int}}`.
  - Validation errors return HTTP 417 with the `ValueError` text.

- [ ] **Step 1: Write the failing integration test**

```python
# caryaar_hr_ext/performance/tests/test_integration.py
import frappe
from frappe.tests import IntegrationTestCase

from caryaar_hr_ext.performance import api, engine
from caryaar_hr_ext.performance.rules import activity_doc_name


def _employee(email):
    name = frappe.db.get_value("Employee", {"user_id": email}, "name")
    if name:
        return name
    doc = frappe.get_doc({
        "doctype": "Employee", "first_name": "Perf", "last_name": email.split("@")[0],
        "gender": "Male", "date_of_birth": "1995-01-01", "date_of_joining": "2026-01-01",
        "company": frappe.db.get_value("Company", {}, "name"), "status": "Active",
        "company_email": email.upper(), "prefered_contact_email": "Company Email",
    }).insert(ignore_permissions=True)
    return doc.name


class TestIngest(IntegrationTestCase):
    def setUp(self):
        self.emp = _employee("perf.test.one@caryaar.test")

    def test_ingest_matches_company_email_case_insensitively_and_upserts(self):
        payload = dict(source="CY Admin", synced_through="2026-10-02T00:15:00+05:30",
                       rows=[{"email": "Perf.Test.One@CarYaar.test", "date": "2026-10-01",
                              "metrics": {"calls_handled": 3}},
                             {"email": "nobody@caryaar.test", "date": "2026-10-01",
                              "metrics": {"calls_handled": 1}}])
        out = api.ingest_activity(**payload)
        self.assertEqual(out["accepted"], 1)
        self.assertEqual(out["unmapped"], ["nobody@caryaar.test"])
        payload["rows"][0]["metrics"] = {"calls_handled": 7}
        api.ingest_activity(**payload)
        name = activity_doc_name(self.emp, "2026-10-01", "CY Admin")
        self.assertEqual(frappe.db.count("Work Activity Day", {"employee": self.emp, "activity_date": "2026-10-01"}), 1)
        self.assertEqual(frappe.db.get_value("Work Activity Day", name, "calls_handled"), 7)
        s = frappe.get_single("Performance Sync Settings")
        self.assertIn("nobody@caryaar.test", s.unmapped_emails or "")
        self.assertEqual(str(s.cy_admin_synced_through), "2026-10-02 00:15:00")

    def test_resend_without_snapshot_metrics_keeps_them(self):
        api.ingest_activity(source="CY Admin", synced_through="2026-10-01T22:00:00+05:30",
                            rows=[{"email": "perf.test.one@caryaar.test", "date": "2026-10-01",
                                   "metrics": {"calls_handled": 2, "leads_assigned": 30}}])
        api.ingest_activity(source="CY Admin", synced_through="2026-10-02T00:15:00+05:30",
                            rows=[{"email": "perf.test.one@caryaar.test", "date": "2026-10-01",
                                   "metrics": {"calls_handled": 4}}])
        name = activity_doc_name(self.emp, "2026-10-01", "CY Admin")
        self.assertEqual(frappe.db.get_value("Work Activity Day", name, ["calls_handled", "leads_assigned"]), (4, 30))

    def test_ingest_rejects_bad_payload_with_validation_error(self):
        with self.assertRaises(frappe.ValidationError):
            api.ingest_activity(source="Slack", synced_through="2026-10-02T00:15:00+05:30", rows=[])

    def test_synced_through_never_moves_backwards(self):
        api.ingest_activity(source="Plane", synced_through="2026-10-05T10:00:00+05:30", rows=[])
        api.ingest_activity(source="Plane", synced_through="2026-10-04T10:00:00+05:30", rows=[])
        self.assertEqual(str(frappe.get_single("Performance Sync Settings").plane_synced_through), "2026-10-05 10:00:00")

    def test_module_progress_upsert(self):
        body = dict(synced_through="2026-10-01T10:00:00+05:30", modules=[
            {"module_id": "mod-test-1", "project_identifier": "DEV", "module_name": "Test",
             "total_issues": 10, "completed_issues": 4}])
        api.ingest_module_progress(**body)
        body["modules"][0]["completed_issues"] = 5
        api.ingest_module_progress(**body)
        self.assertEqual(frappe.db.get_value("Plane Module Progress", "mod-test-1", "progress"), 50.0)
```

- [ ] **Step 2: Write the implementation**

```python
# caryaar_hr_ext/performance/api.py
"""Intake endpoints for Plane (Plan B) and CY Admin (Plan C) activity.

Callers authenticate with the API key of an ERP user holding only the
Performance Sync role. Payloads are validated by performance.rules.
"""
from __future__ import annotations

import frappe
from frappe.utils import now_datetime

from caryaar_hr_ext.performance import rules

_SYNC_FIELD = {"Plane": "plane_synced_through", "CY Admin": "cy_admin_synced_through"}


def _email_map() -> dict[str, str]:
    rows = frappe.get_all("Employee", filters={"status": "Active"},
                          fields=["name", "user_id", "company_email"])
    out: dict[str, str] = {}
    for r in rows:
        for e in (r.company_email, r.user_id):
            if e:
                out.setdefault(e.strip().lower(), r.name)
    return out


def _advance(settings, field: str, when) -> None:
    current = settings.get(field)
    if not current or frappe.utils.get_datetime(current) < when:
        settings.set(field, when)


@frappe.whitelist(methods=["POST"])
def ingest_activity(source=None, synced_through=None, rows=None):
    frappe.only_for(("Performance Sync", "System Manager"))
    try:
        batch = rules.validate_activity_payload(source, synced_through, rows)
    except ValueError as e:
        frappe.throw(str(e), exc=frappe.ValidationError)

    emails = _email_map()
    accepted, unmapped = 0, set()
    for row in batch.rows:
        emp = emails.get(row.email)
        if not emp:
            unmapped.add(row.email)
            continue
        # Only the metrics this row carries are written: a nightly re-send of
        # yesterday omits the end-of-day snapshot metrics and must not zero them.
        values = dict(row.metrics)
        values["synced_at"] = now_datetime()
        name = rules.activity_doc_name(emp, row.date, batch.source)
        if frappe.db.exists("Work Activity Day", name):
            frappe.db.set_value("Work Activity Day", name, values)
        else:
            frappe.get_doc({"doctype": "Work Activity Day", "employee": emp, "activity_date": row.date,
                            "source": batch.source, **values}).insert(ignore_permissions=True)
        accepted += 1

    settings = frappe.get_single("Performance Sync Settings")
    _advance(settings, _SYNC_FIELD[batch.source], batch.synced_through)
    if unmapped:
        known = set(filter(None, (settings.unmapped_emails or "").split("\n")))
        settings.unmapped_emails = "\n".join(sorted(known | unmapped))
    settings.save(ignore_permissions=True)
    return {"accepted": accepted, "unmapped": sorted(unmapped)}


@frappe.whitelist(methods=["POST"])
def ingest_module_progress(synced_through=None, modules=None):
    frappe.only_for(("Performance Sync", "System Manager"))
    try:
        when, rows = rules.validate_module_payload(synced_through, modules)
    except ValueError as e:
        frappe.throw(str(e), exc=frappe.ValidationError)
    for m in rows:
        values = {"project_identifier": m.project_identifier, "module_name": m.module_name,
                  "total_issues": m.total_issues, "completed_issues": m.completed_issues,
                  "synced_at": now_datetime()}
        if frappe.db.exists("Plane Module Progress", m.module_id):
            doc = frappe.get_doc("Plane Module Progress", m.module_id)
            doc.update(values)
            doc.save(ignore_permissions=True)
        else:
            frappe.get_doc({"doctype": "Plane Module Progress", "module_id": m.module_id, **values}
                           ).insert(ignore_permissions=True)
    settings = frappe.get_single("Performance Sync Settings")
    _advance(settings, "plane_modules_synced_through", when)
    settings.save(ignore_permissions=True)
    return {"accepted": len(rows)}
```

- [ ] **Step 3: Confirm pure tests still pass locally**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests -q`
Expected: all pass; `test_integration.py` is skipped locally by `conftest.py` because frappe is not importable. The integration tests run in Task 7.

- [ ] **Step 4: Commit**

```bash
git add caryaar_hr_ext/performance/api.py caryaar_hr_ext/performance/tests/test_integration.py
git commit -m "feat(performance): intake endpoints for Plane and CY Admin activity and Plane module progress"
```

---

### Task 5: Nightly engine

**Files:**
- Create: `caryaar_hr_ext/performance/engine.py`
- Test: `caryaar_hr_ext/performance/tests/test_integration.py` (extend)

**Interfaces:**
- Consumes: `rules.DayContext`, `rules.adherence_day`, `rules.adherence_doc_name`, `rules.module_progress`, `rules.performance_category`, `rules.parse_department_sources`, `rules.METRIC_KEYS`; DocTypes from Task 2; HRMS `Attendance`, `Attendance Request`, `Holiday`, `Goal`, `Appraisal`.
- Produces: `run_nightly() -> None` (scheduled in Task 3), `run_day(day: date) -> int` (rows written), `update_goal_progress() -> int`, `update_performance_categories() -> int`.

- [ ] **Step 1: Extend the integration tests**

```python
class TestEngine(IntegrationTestCase):
    def setUp(self):
        self.emp = _employee("perf.test.two@caryaar.test")
        s = frappe.get_single("Performance Sync Settings")
        s.plane_synced_through = "2026-10-03 00:00:00"
        s.department_sources = "{}"
        s.save(ignore_permissions=True)

    def test_day_with_plane_activity_is_visible(self):
        api.ingest_activity(source="Plane", synced_through="2026-10-03T00:00:00+05:30",
                            rows=[{"email": "perf.test.two@caryaar.test", "date": "2026-10-01",
                                   "metrics": {"activity_count": 3, "completed_count": 1}}])
        engine.run_day(frappe.utils.getdate("2026-10-01"))
        row = frappe.get_doc("Work Adherence Day", f"WADH-{self.emp}-2026-10-01")
        self.assertEqual(row.work_visible, "Yes")
        self.assertEqual(row.adherence_pct, 100)

    def test_day_after_last_sync_is_pending(self):
        engine.run_day(frappe.utils.getdate("2026-10-04"))
        row = frappe.get_doc("Work Adherence Day", f"WADH-{self.emp}-2026-10-04")
        self.assertEqual(row.work_visible or "", "")
        self.assertEqual(row.checks_applicable, 0)

    def test_rejected_wfh_request_does_not_make_a_wfh_day(self):
        frappe.get_doc({"doctype": "Attendance Request", "employee": self.emp, "from_date": "2026-10-02",
                        "to_date": "2026-10-02", "reason": "Work From Home",
                        "workflow_state": "Rejected"}).insert(ignore_permissions=True)
        engine.run_day(frappe.utils.getdate("2026-10-02"))
        row = frappe.get_doc("Work Adherence Day", f"WADH-{self.emp}-2026-10-02")
        self.assertEqual(row.wfh, 0)

    def test_goal_update_failure_does_not_stop_others(self):
        frappe.get_doc({"doctype": "Plane Module Progress", "module_id": "mod-engine-1",
                        "total_issues": 4, "completed_issues": 2}).insert(ignore_permissions=True)
        # A goal pointing at a module that does not exist is skipped; the engine returns normally.
        self.assertIsInstance(engine.update_goal_progress(), int)
```

- [ ] **Step 2: Write the implementation**

```python
# caryaar_hr_ext/performance/engine.py
"""Nightly performance engine (scheduled at 23:30 IST in hooks.py).

For each active employee and each of the last four days: builds a DayContext
from attendance, WFH requests, holidays and synced activity, then stores the
rules.adherence_day result as a Work Adherence Day. Afterwards updates goal
progress from Plane modules and appraisal rating categories. Every unit of
work is fail-soft: an error is logged and the run continues.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta

import frappe
from frappe.utils import flt, get_datetime, getdate, nowdate

from caryaar_hr_ext.performance import rules

_SYNC_FIELD = {"Plane": "plane_synced_through", "CY Admin": "cy_admin_synced_through"}
_YES_NO = {True: "Yes", False: "No", None: ""}
DAYS_BACK = 4


def run_nightly() -> None:
    today = getdate(nowdate())
    for i in range(DAYS_BACK):
        _guard(f"adherence {today - timedelta(days=i)}", run_day, today - timedelta(days=i))
    _guard("goal progress", update_goal_progress)
    _guard("performance categories", update_performance_categories)


def _guard(label: str, fn, *args):
    try:
        out = fn(*args)
        frappe.db.commit()
        return out
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title=f"Performance engine: {label}", message=frappe.get_traceback())
        frappe.db.set_single_value("Performance Sync Settings", "last_error",
                                   f"{frappe.utils.now()} {label} failed; see Error Log")
        frappe.db.commit()
        return None


def _fresh_sources(settings, day: date) -> frozenset[str]:
    end = datetime.combine(day, time(23, 59, 59))
    return frozenset(src for src, field in _SYNC_FIELD.items()
                     if settings.get(field) and get_datetime(settings.get(field)) >= end)


def _holiday_list(emp) -> str | None:
    return emp.holiday_list or frappe.get_cached_value("Company", emp.company, "default_holiday_list")


def _context(emp, day: date, dept_sources: dict, fresh: frozenset[str]) -> rules.DayContext:
    hl = _holiday_list(emp)
    is_holiday = bool(hl and frappe.db.exists("Holiday", {"parent": hl, "holiday_date": day}))
    status = frappe.db.get_value("Attendance", {"employee": emp.name, "attendance_date": day,
                                                "docstatus": 1}, "status")
    reqs = frappe.get_all("Attendance Request",
                          filters={"employee": emp.name, "reason": "Work From Home",
                                   "from_date": ("<=", day), "to_date": (">=", day),
                                   "workflow_state": ("in", ["Pending", "Approved"])},
                          fields=["docstatus"])
    fields = ["source", *rules.METRIC_KEYS["Plane"], *rules.METRIC_KEYS["CY Admin"]]
    activity = {r.source: {k: int(r.get(k) or 0) for k in fields if k != "source"}
                for r in frappe.get_all("Work Activity Day",
                                        filters={"employee": emp.name, "activity_date": day}, fields=fields)}
    return rules.DayContext(
        is_holiday=is_holiday, attendance_status=status,
        expected_sources=tuple(dept_sources.get(emp.department or "", ["Plane"])),
        fresh_sources=fresh, activity=activity,
        wfh_requested=bool(reqs), wfh_approved=any(r.docstatus == 1 for r in reqs))


def run_day(day: date) -> int:
    settings = frappe.get_single("Performance Sync Settings")
    dept_sources = rules.parse_department_sources(settings.department_sources or "")
    fresh = _fresh_sources(settings, day)
    written = 0
    for emp in frappe.get_all("Employee", filters={"status": "Active"},
                              fields=["name", "department", "holiday_list", "company", "date_of_joining"]):
        if emp.date_of_joining and getdate(emp.date_of_joining) > day:
            continue
        try:
            ctx = _context(emp, day, dept_sources, fresh)
            res = rules.adherence_day(ctx)
            values = {"is_working_day": int(res.is_working_day), "attendance_status": ctx.attendance_status or "",
                      "expected_sources": ", ".join(ctx.expected_sources), "wfh": int(res.wfh),
                      "work_visible": _YES_NO[res.work_visible], "wfh_approved": _YES_NO[res.wfh_approved],
                      "wfh_evidenced": _YES_NO[res.wfh_evidenced], "checks_passed": res.checks_passed,
                      "checks_applicable": res.checks_applicable, "adherence_pct": res.adherence_pct or 0}
            name = rules.adherence_doc_name(emp.name, day.isoformat())
            if frappe.db.exists("Work Adherence Day", name):
                frappe.db.set_value("Work Adherence Day", name, values)
            else:
                frappe.get_doc({"doctype": "Work Adherence Day", "employee": emp.name,
                                "adherence_date": day, **values}).insert(ignore_permissions=True)
            written += 1
        except Exception:
            frappe.log_error(title=f"Performance engine: adherence {emp.name} {day}",
                             message=frappe.get_traceback())
    return written


def update_goal_progress() -> int:
    modules = {m.module_id: m for m in frappe.get_all(
        "Plane Module Progress", fields=["module_id", "total_issues", "completed_issues"])}
    updated = 0
    for g in frappe.get_all("Goal", filters={"cy_plane_module": ("is", "set"), "is_group": 0},
                            fields=["name", "cy_plane_module", "progress"]):
        m = modules.get((g.cy_plane_module or "").strip())
        if not m:
            continue
        p = rules.module_progress(m.total_issues, m.completed_issues)
        if p is None or abs(p - flt(g.progress)) < 0.5:
            continue
        frappe.db.savepoint("cy_goal")
        try:
            doc = frappe.get_doc("Goal", g.name)
            doc.progress = p
            doc.save(ignore_permissions=True)
            updated += 1
        except Exception:
            frappe.db.rollback(save_point="cy_goal")
            frappe.log_error(title=f"Performance engine: goal {g.name} skipped",
                             message=frappe.get_traceback())
    return updated


def update_performance_categories() -> int:
    changed = 0
    for a in frappe.get_all("Appraisal", filters={"docstatus": ("<", 2)},
                            fields=["name", "final_score", "cy_performance_category"]):
        cat = rules.performance_category(flt(a.final_score)) or ""
        if cat != (a.cy_performance_category or ""):
            frappe.db.set_value("Appraisal", a.name, "cy_performance_category", cat, update_modified=False)
            changed += 1
    return changed
```

- [ ] **Step 3: Confirm pure tests still pass locally**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests -q`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add caryaar_hr_ext/performance/engine.py caryaar_hr_ext/performance/tests/test_integration.py
git commit -m "feat(performance): nightly engine for adherence, goal progress and rating categories"
```

---

### Task 6: Dashboard and rating distribution report

**Files:**
- Create: `caryaar_hr_ext/caryaar_hr_ext/report/__init__.py` (empty) and `report/rating_distribution/{__init__.py,rating_distribution.json,rating_distribution.py}`
- Create: `caryaar_hr_ext/fixtures/{dashboard_chart,number_card,dashboard}.json`
- Modify: `caryaar_hr_ext/hooks.py` (fixtures list)
- Test: `caryaar_hr_ext/performance/tests/test_meta.py` (extend)

**Interfaces:**
- Consumes: `Appraisal.cy_performance_category` (Task 3), `Work Adherence Day` (Task 2), `rules.BANDS`.
- Produces: Script Report "Rating Distribution" (filter `appraisal_cycle`), Dashboard "Performance and Adherence".

- [ ] **Step 1: Write the failing tests** (append to `test_meta.py`)

```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests/test_meta.py -q`
Expected: FAIL (`ModuleNotFoundError: ...report.rating_distribution`).

- [ ] **Step 3: Write the report**

```json
{
 "doctype": "Report", "name": "Rating Distribution", "report_name": "Rating Distribution",
 "ref_doctype": "Appraisal", "report_type": "Script Report", "is_standard": "Yes",
 "module": "Caryaar Hr Ext", "disabled": 0, "add_total_row": 1,
 "owner": "Administrator", "modified_by": "Administrator",
 "creation": "2026-09-26 18:00:00.000000", "modified": "2026-09-26 18:00:00.000000",
 "roles": [{"role": "HR Manager"}, {"role": "System Manager"}]
}
```

```python
# caryaar_hr_ext/caryaar_hr_ext/report/rating_distribution/rating_distribution.py
"""Company-wide rating spread for one appraisal cycle, next to the handbook's guide (spec D5)."""
from collections import Counter

GUIDE = (("Exceptional", 5), ("Excellent", 15), ("Good", 25), ("Fair", 50), ("Non-Satisfactory", 5))


def execute(filters=None):
    import frappe  # imported here so the GUIDE constant is testable without Frappe

    filters = filters or {}
    cycle = filters.get("appraisal_cycle")
    if not cycle:
        frappe.throw("Choose an appraisal cycle.")
    counts = Counter(frappe.get_all(
        "Appraisal", filters={"appraisal_cycle": cycle, "docstatus": ("<", 2),
                              "cy_performance_category": ("is", "set")},
        pluck="cy_performance_category"))
    total = sum(counts.values())
    columns = [
        {"fieldname": "category", "label": "Category", "fieldtype": "Data", "width": 170},
        {"fieldname": "people", "label": "People", "fieldtype": "Int", "width": 90},
        {"fieldname": "actual", "label": "Actual %", "fieldtype": "Percent", "width": 110},
        {"fieldname": "guide", "label": "Guide %", "fieldtype": "Percent", "width": 110},
    ]
    data = [{"category": c, "people": counts.get(c, 0),
             "actual": round(100.0 * counts.get(c, 0) / total, 1) if total else 0, "guide": g}
            for c, g in GUIDE]
    return columns, data
```

```javascript
// caryaar_hr_ext/caryaar_hr_ext/report/rating_distribution/rating_distribution.js
frappe.query_reports["Rating Distribution"] = {
  filters: [
    { fieldname: "appraisal_cycle", label: __("Appraisal cycle"), fieldtype: "Link",
      options: "Appraisal Cycle", reqd: 1 },
  ],
};
```

Counting happens in Python on purpose: this Frappe version rejects SQL aggregates written as strings in `fields` (seen live on 26-Sep).

- [ ] **Step 4: Write the dashboard fixtures**

```json
// caryaar_hr_ext/fixtures/dashboard_chart.json
[
 {"doctype": "Dashboard Chart", "name": "Rating categories", "chart_name": "Rating categories",
  "chart_type": "Group By", "document_type": "Appraisal", "group_by_type": "Count",
  "group_by_based_on": "cy_performance_category", "type": "Bar", "is_public": 1,
  "module": "Caryaar Hr Ext", "filters_json": "[[\"Appraisal\",\"docstatus\",\"<\",2]]", "timeseries": 0},
 {"doctype": "Dashboard Chart", "name": "Adherence by department", "chart_name": "Adherence by department",
  "chart_type": "Group By", "document_type": "Work Adherence Day", "group_by_type": "Average",
  "group_by_based_on": "department", "aggregate_function_based_on": "adherence_pct", "type": "Bar",
  "is_public": 1, "module": "Caryaar Hr Ext", "timeseries": 0,
  "filters_json": "[[\"Work Adherence Day\",\"checks_applicable\",\">\",0],[\"Work Adherence Day\",\"adherence_date\",\">=\",\"2026-11-01\"]]"},
 {"doctype": "Dashboard Chart", "name": "WFH days by department", "chart_name": "WFH days by department",
  "chart_type": "Group By", "document_type": "Attendance", "group_by_type": "Count",
  "group_by_based_on": "department", "type": "Bar", "is_public": 1, "module": "Caryaar Hr Ext",
  "timeseries": 0, "filters_json": "[[\"Attendance\",\"status\",\"=\",\"Work From Home\"],[\"Attendance\",\"docstatus\",\"=\",1]]"}
]
```

```json
// caryaar_hr_ext/fixtures/number_card.json
[
 {"doctype": "Number Card", "name": "WFH days this month", "label": "WFH days this month",
  "type": "Document Type", "document_type": "Attendance", "function": "Count", "is_public": 1,
  "module": "Caryaar Hr Ext", "show_percentage_stats": 0,
  "filters_json": "[[\"Attendance\",\"status\",\"=\",\"Work From Home\"],[\"Attendance\",\"docstatus\",\"=\",1],[\"Attendance\",\"attendance_date\",\"Timespan\",\"this month\"]]"},
 {"doctype": "Number Card", "name": "WFH requests waiting", "label": "WFH requests waiting",
  "type": "Document Type", "document_type": "Attendance Request", "function": "Count", "is_public": 1,
  "module": "Caryaar Hr Ext", "show_percentage_stats": 0,
  "filters_json": "[[\"Attendance Request\",\"workflow_state\",\"=\",\"Pending\"]]"}
]
```

```json
// caryaar_hr_ext/fixtures/dashboard.json
[
 {"doctype": "Dashboard", "name": "Performance and Adherence", "dashboard_name": "Performance and Adherence",
  "module": "Caryaar Hr Ext", "is_standard": 0,
  "charts": [{"chart": "Adherence by department", "width": "Half"},
             {"chart": "WFH days by department", "width": "Half"},
             {"chart": "Rating categories", "width": "Full"}],
  "cards": [{"card": "WFH days this month"}, {"card": "WFH requests waiting"}]}
]
```

Write the JSON files without the `// path` comment lines. Add to the `fixtures` list in `hooks.py`:

```python
    {"dt": "Dashboard Chart", "filters": [["module", "=", "Caryaar Hr Ext"]]},
    {"dt": "Number Card", "filters": [["module", "=", "Caryaar Hr Ext"]]},
    {"dt": "Dashboard", "filters": [["module", "=", "Caryaar Hr Ext"]]},
```

- [ ] **Step 5: Run the tests**

Run: `python3 -m pytest caryaar_hr_ext/performance/tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add caryaar_hr_ext/caryaar_hr_ext/report caryaar_hr_ext/fixtures caryaar_hr_ext/hooks.py caryaar_hr_ext/performance/tests/test_meta.py
git commit -m "feat(performance): rating distribution report and performance and adherence dashboard"
```

---

### Task 7: Verify on the staging ERP (founder go required: starts the stopped `frappe-staging` VM)

**Files:** none changed unless a defect is found (fix in the owning task's files, re-run, commit).

The staging site is a clone of production. It can send real email and once redirected logins to production, so email is muted before anything else runs.

- [ ] **Step 1: Ask the founder for go** (VM start costs money while running; the VM is stopped again at the end).
- [ ] **Step 2: Start the VM and inspect how the bench runs** (read-only):

```bash
gcloud compute instances start frappe-staging --zone=asia-south1-b --project=cy-erp
gcloud compute ssh frappe-staging --zone=asia-south1-b --project=cy-erp --tunnel-through-iap \
  --command "sudo docker ps --format '{{.Names}} {{.Image}}'; ls /home/*/gitops 2>/dev/null"
```
Expected: the Frappe containers (backend, queue-short, queue-long, scheduler, websocket) and the image tag. Record them in the plan's execution notes.
- [ ] **Step 3: Mute email and confirm the host name is not production**:

```bash
# inside the backend container, site name as found in Step 2
bench --site <site> set-config mute_emails 1
bench --site <site> get-config host_name   # must NOT be https://erp.caryaar.com
```
- [ ] **Step 4: Install this branch into every container** (the notification-relay runbook's rule: each of the 5 containers has its own venv):

```bash
# in each container: backend, queue-short, queue-long, scheduler, websocket
cd /home/frappe/frappe-bench/apps/caryaar_hr_ext && git fetch origin feat/performance-plane-wfh-program && git checkout FETCH_HEAD
/home/frappe/frappe-bench/env/bin/pip install -e /home/frappe/frappe-bench/apps/caryaar_hr_ext
# then, in backend only:
bench --site <site> migrate && bench --site <site> clear-cache
```
If the containers share one apps volume, `git checkout` once and `pip install -e` in each.
- [ ] **Step 5: Run the integration tests**:

```bash
bench --site <site> set-config allow_tests true
bench --site <site> run-tests --module caryaar_hr_ext.performance.tests.test_integration
```
Expected: all tests pass.
- [ ] **Step 6: Smoke the real path** as Administrator on staging: call `ingest_activity` with one row for a real employee email, run `bench --site <site> execute caryaar_hr_ext.performance.engine.run_nightly`, open the "Performance and Adherence" dashboard and the Rating Distribution report, and confirm the WFH approval workflow still offers "Send for Approval" on a WFH draft.
- [ ] **Step 7: Stop the VM**: `gcloud compute instances stop frappe-staging --zone=asia-south1-b --project=cy-erp`.

---

### Task 8: Deploy to production (founder go required at each step)

- [ ] **Step 1: Push first** (standing rule): merge the branch to `main` of `CarYaar/caryaar_hr_ext` and push, then confirm `git rev-list origin/main..HEAD` is empty.
- [ ] **Step 2: Inspect the production deploy path read-only** (needs a permission rule for `gcloud compute ssh caryaar-erpnext`): list containers and image, read `/home/sahaib/gitops/apps.json`, and read how `caryaar_hr_ext` is pinned (branch or commit). Present the exact rebuild or in-place update commands to the founder before running anything.
- [ ] **Step 3: Snapshot the VM disk**: `gcloud compute disks snapshot <disk> --zone=asia-south1-b --project=cy-erp --snapshot-names=erpnext-pre-perf-20261001`.
- [ ] **Step 4: Update, migrate, clear cache, restart** using the path confirmed in Step 2, in a quiet window (after 20:00 IST), then verify:
  - `GET /api/method/ping` is `pong`; an invoice list loads in Accounts (cy_billing smoke).
  - `Work Activity Day`, `Work Adherence Day`, `Plane Module Progress`, `Performance Sync Settings` open.
  - A WFH draft still offers only "Send for Approval"; the three notifications are enabled.
  - `Goal` shows "Plane module ID"; `Appraisal` shows "Performance category".
- [ ] **Step 5: Create the sync user and key**: create User `performance-sync@caryaar.com` (System User, only role `Performance Sync`, no password login), generate its API key, and store `key:secret` in Secret Manager as `erp-performance-sync-key` (project `caryaar-api-dev`). Never print the secret.
- [ ] **Step 6: Rollback** if any check fails: restore the snapshot or re-pin `caryaar_hr_ext` to the previous commit and migrate; the approval workflow stays live either way because it already exists in the database.
