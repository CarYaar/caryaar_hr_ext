# Plan C: CY Admin activity export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send each CY Admin staff member's daily calls, lead work and credited bookings (plus end-of-day lead snapshots) to the ERP intake endpoint from Plan A, hourly for today and once after midnight for yesterday.

**Architecture:** One service module in caryaar-api computes per-agent per-IST-day metrics from `voice_calls` (collapsed into sessions with the existing `collapse_call_sessions`), `lead_status_history`, `customer_notes`, `bookings` and `customers`. One Celery beat task reads in a short session, closes it, then POSTs through `FrappeClient` using a dedicated least-privilege ERP key. Dormant until a settings-panel flag is switched on.

**Tech Stack:** caryaar-api (FastAPI, SQLAlchemy async, asyncpg, Celery with beat in the worker, Asia/Kolkata crontabs), pytest with the L2 test database on port 15433.

**Spec:** `caryaar-erp/caryaar_hr_ext/docs/superpowers/specs/2026-09-26-performance-plane-wfh-program-design.md` (W4c). **Depends on:** Plan A deployed and Secret Manager secret `erp-performance-sync-key`. Work happens in `/Users/sahaib/caryaar/caryaar-api` on a branch cut from `origin/main` (local `main` is often stale), e.g. `feat/performance-activity-sync`; use superpowers:using-git-worktrees if the main checkout has other work in flight.

## Global Constraints

- Every day boundary is IST: window `[IST midnight, next IST midnight)` converted to UTC and compared as `timestamptz`. Never `created_at::date`.
- asyncpg needs every bind parameter cast (`CAST(:start AS timestamptz)`, `CAST(:ids AS uuid[])`); an uncast bind crashes at PREPARE.
- Read, close the session, then do HTTP. No transaction may stay open across an ERP call (pool is 3 + 2 on the worker).
- The flag is `get_setting("PERFORMANCE_SYNC_ENABLED", fallback=settings.PERFORMANCE_SYNC_ENABLED)`, default `False`, read inside async code as the only gate.
- The ERP key is `settings.ERP_PERFORMANCE_SYNC_KEY` (`key:secret`, from Secret Manager `erp-performance-sync-key`), added to the settings-panel secret denylist. The existing Administrator `FRAPPE_API_KEY` is never used for this.
- Payloads follow Plan A: `source="CY Admin"`, metric keys from Plan A's `METRIC_KEYS["CY Admin"]` only; snapshot metrics (`leads_assigned`, `leads_untouched`, `followups_overdue`) only in the "today" run.
- Tasks never raise; they log and return a summary dict (it lands in `task_runs.result`).
- Run tests by file name only; never a broad `pytest tests/` (dev DB rewinder hazard).

## Review Focus

1. **One phone call produces several `voice_calls` rows** (PBX leg, softphone log, Exotel ring). Expected: counted once, as the product's own call view does. Pinned in Task 2 (L2 test with two legs two minutes apart).
2. **A call just after midnight IST** (00:20 IST, still the previous UTC day). Expected: it counts for the IST day it happened in. Pinned in Task 2.
3. **A staff member with no activity.** Expected: sent with zeros so the ERP can tell "quiet" from "not synced". Pinned in Task 1.
4. **The flag is off, or the ERP key is missing.** Expected: the task returns `{"skipped": ...}` without touching the ERP and without raising. Pinned in Task 3.
5. **The nightly re-send for yesterday.** Expected: it omits the snapshot metrics so it cannot overwrite yesterday's end-of-day snapshot with a later state. Pinned in Task 1 and Plan A Task 4.

---

## File Structure

```
app/integrations/frappe/client.py          modify: optional per-client credentials
app/config/settings.py                     modify: ERP_PERFORMANCE_SYNC_KEY, PERFORMANCE_SYNC_ENABLED
app/api/v1/admin/settings.py               modify: denylist the new secret
app/services/performance/__init__.py       create (empty)
app/services/performance/agent_activity.py create: IST bounds, session bucketing, DB queries, rows
app/tasks/performance_activity_sync.py     create: task + beat entries
app/tasks/__init__.py                      modify: include + task_routes
tests/services/performance/__init__.py
tests/services/performance/test_agent_activity_pure.py
tests/services/performance/test_agent_activity_l2.py
tests/tasks/test_performance_activity_sync.py
```

---

### Task 1: Pure helpers

**Files:**
- Create: `app/services/performance/__init__.py`, `app/services/performance/agent_activity.py` (pure part)
- Test: `tests/services/performance/__init__.py`, `tests/services/performance/test_agent_activity_pure.py`

**Interfaces:**
- Produces: `METRICS_DAILY: tuple[str, ...]`, `METRICS_SNAPSHOT: tuple[str, ...]`, `ist_day_bounds(day: date) -> tuple[datetime, datetime]` (UTC-aware), `bucket_sessions(sessions: list[dict], day: date) -> dict[str, dict[str, int]]` keyed by agent user id, `build_rows(staff: dict[str, str], day: date, per_agent: dict[str, dict[str, int]], include_snapshots: bool) -> list[dict]`.

- [ ] **Step 1: Write the failing tests**

```python
# tests/services/performance/test_agent_activity_pure.py
from datetime import date, datetime, timezone

from app.services.performance import agent_activity as aa

DAY = date(2026, 10, 1)


def test_ist_day_bounds():
    start, end = aa.ist_day_bounds(DAY)
    assert start == datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)
    assert end == datetime(2026, 10, 1, 18, 30, tzinfo=timezone.utc)


def _s(agent, created, status="COMPLETED", dur=60):
    return {"agent_user_id": agent, "created_at": created, "status": status, "duration_seconds": dur}


def test_bucket_sessions_counts_by_ist_day_and_agent():
    sessions = [
        _s("u1", "2026-10-01T04:00:00+00:00"),                     # 09:30 IST 1-Oct
        _s("u1", "2026-10-01T18:50:00+00:00"),                     # 00:20 IST 2-Oct: next day
        _s("u1", "2026-09-30T18:50:00+00:00", "FAILED", 0),        # 00:20 IST 1-Oct: missed
        _s(None, "2026-10-01T05:00:00+00:00"),                     # AI-only session: ignored
        _s("u2", "2026-10-01T06:00:00+00:00", dur=125),
    ]
    out = aa.bucket_sessions(sessions, DAY)
    assert out["u1"] == {"calls_handled": 2, "calls_answered": 1, "talk_seconds": 60}
    assert out["u2"] == {"calls_handled": 1, "calls_answered": 1, "talk_seconds": 125}
    assert "None" not in out and None not in out


def test_build_rows_includes_quiet_staff_and_drops_snapshots_when_asked():
    staff = {"u1": "janhavi.nanaware@caryaar.com", "u2": "anagha.khedekar@caryaar.com"}
    per = {"u1": {"calls_handled": 3, "leads_assigned": 30}}
    today = aa.build_rows(staff, DAY, per, include_snapshots=True)
    assert len(today) == 2
    quiet = next(r for r in today if r["email"] == "anagha.khedekar@caryaar.com")
    assert quiet["metrics"]["calls_handled"] == 0 and quiet["metrics"]["leads_assigned"] == 0
    final = aa.build_rows(staff, DAY, per, include_snapshots=False)
    assert all(not set(r["metrics"]) & set(aa.METRICS_SNAPSHOT) for r in final)
    assert final[0]["date"] == "2026-10-01"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/sahaib/caryaar/caryaar-api && python3 -m pytest tests/services/performance/test_agent_activity_pure.py -q`
Expected: `ModuleNotFoundError: No module named 'app.services.performance'`.

- [ ] **Step 3: Implement the pure part**

```python
# app/services/performance/agent_activity.py
"""Per-agent daily CY Admin activity for the ERP performance program (Plan C).

Pure helpers first; the DB queries are below them. Days are IST.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from app.utils.ist import IST

METRICS_DAILY: tuple[str, ...] = ("calls_handled", "calls_answered", "talk_seconds", "dispositions",
                                  "status_moves", "notes_written", "bookings_credited")
METRICS_SNAPSHOT: tuple[str, ...] = ("leads_assigned", "leads_untouched", "followups_overdue")


def ist_day_bounds(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time(0, 0), tzinfo=IST).astimezone(timezone.utc)
    return start, start + timedelta(days=1)


def _as_utc(value) -> datetime:
    dt = datetime.fromisoformat(value) if isinstance(value, str) else value
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def bucket_sessions(sessions: list[dict], day: date) -> dict[str, dict[str, int]]:
    start, end = ist_day_bounds(day)
    out: dict[str, dict[str, int]] = {}
    for s in sessions:
        agent = s.get("agent_user_id")
        if not agent:
            continue
        when = _as_utc(s["created_at"])
        if not (start <= when < end):
            continue
        m = out.setdefault(str(agent), {"calls_handled": 0, "calls_answered": 0, "talk_seconds": 0})
        m["calls_handled"] += 1
        dur = int(s.get("duration_seconds") or 0)
        if s.get("status") == "COMPLETED" and dur > 0:
            m["calls_answered"] += 1
            m["talk_seconds"] += dur
    return out


def build_rows(staff: dict[str, str], day: date, per_agent: dict[str, dict[str, int]],
               include_snapshots: bool) -> list[dict]:
    keys = METRICS_DAILY + (METRICS_SNAPSHOT if include_snapshots else ())
    return [{"email": email, "date": day.isoformat(),
             "metrics": {k: int(per_agent.get(uid, {}).get(k, 0)) for k in keys}}
            for uid, email in sorted(staff.items(), key=lambda kv: kv[1])]
```

Confirm `app/utils/ist.py` exports `IST` as a `tzinfo` (the research found `IST` there); if it is named differently, import that name.

- [ ] **Step 4: Run to verify pass**

Run: `cd /Users/sahaib/caryaar/caryaar-api && python3 -m pytest tests/services/performance/test_agent_activity_pure.py -q`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add app/services/performance tests/services/performance
git commit -m "feat(performance): pure helpers for per-agent IST daily activity"
```

---

### Task 2: Database queries (L2)

**Files:**
- Modify: `app/services/performance/agent_activity.py` (add `compute_agent_activity`)
- Test: `tests/services/performance/test_agent_activity_l2.py`

**Interfaces:**
- Consumes: `collapse_call_sessions(rows, *, now=None, gap_seconds=300, prefer_recording_leg_transcript=False) -> list[dict]` from `app/services/contact_center/call_collapse.py:314`; `serialize_voice_call_row` from `app/api/v1/admin/bookings.py:1955`.
- Produces: `async def compute_agent_activity(session, day: date, *, include_snapshots: bool) -> list[dict]` returning Plan A rows for every active CY Admin user with an email.

- [ ] **Step 1: Read the three references before writing code**
  - `app/api/v1/admin/bookings.py:1955` (`serialize_voice_call_row`): note its parameters and the keys it returns (`call_id`, `phone`, `customer_id`, `created_at`, `ended_at`, `duration_seconds`, `status`, `source`, `direction`, `agent_user_id`, `recording_url`).
  - `app/api/v1/admin/live_ops_tower.py:1243-1269`: copy the exact "untouched" condition (lead_status NULL and no tags) so the ERP matches the product's sales report.
  - `tests/api/admin/test_job_360.py:160` and `tests/conftest.py:490-560`: the raw `INSERT INTO users` pattern and the `test_session` fixture.

- [ ] **Step 2: Write the failing L2 test**

```python
# tests/services/performance/test_agent_activity_l2.py
import uuid
from datetime import date, datetime, timezone

import pytest
from sqlalchemy import text

from app.services.performance import agent_activity as aa

pytestmark = pytest.mark.l2
DAY = date(2026, 10, 1)


@pytest.mark.asyncio
async def test_agent_day_metrics(test_session):
    uid = uuid.uuid4()
    email = f"perf.{uid.hex[:8]}@caryaar.com"
    # Seed exactly as test_job_360.py:160 does, adding user_type/status for the staff filter.
    await test_session.execute(text(
        "INSERT INTO users (id, email, name, user_type, status, role_id) "
        "VALUES (CAST(:id AS uuid), :email, 'Perf Agent', 'CY_ADMIN', 'ACTIVE', "
        "(SELECT id FROM roles WHERE name = 'SALES_AGENT'))"), {"id": str(uid), "email": email})
    phone = "+919800000001"
    legs = [datetime(2026, 10, 1, 4, 0, tzinfo=timezone.utc), datetime(2026, 10, 1, 4, 2, tzinfo=timezone.utc)]
    for i, at in enumerate(legs):  # two legs, 2 minutes apart: one session
        await test_session.execute(text(
            "INSERT INTO voice_calls (id, source, direction, status, duration_seconds, created_at, "
            "agent_user_id, outcome) VALUES (CAST(:id AS uuid), 'HUMAN_AGENT', 'OUTBOUND', 'COMPLETED', "
            ":dur, CAST(:at AS timestamptz), CAST(:uid AS uuid), :outcome)"),
            {"id": str(uuid.uuid4()), "dur": 90, "at": at.isoformat(), "uid": str(uid),
             "outcome": "INFO_PROVIDED" if i == 0 else None})
    await test_session.execute(text(  # 00:20 IST on 2-Oct: must not count for 1-Oct
        "INSERT INTO voice_calls (id, source, direction, status, duration_seconds, created_at, agent_user_id) "
        "VALUES (CAST(:id AS uuid), 'HUMAN_AGENT', 'OUTBOUND', 'COMPLETED', 30, "
        "CAST('2026-10-01T18:50:00+00:00' AS timestamptz), CAST(:uid AS uuid))"),
        {"id": str(uuid.uuid4()), "uid": str(uid)})
    await test_session.commit()
    try:
        rows = await aa.compute_agent_activity(test_session, DAY, include_snapshots=False)
        mine = next(r for r in rows if r["email"] == email)
        assert mine["metrics"]["calls_handled"] == 1
        assert mine["metrics"]["dispositions"] == 1
        assert mine["metrics"]["talk_seconds"] > 0
        assert "leads_assigned" not in mine["metrics"]
    finally:
        await test_session.execute(text("DELETE FROM users WHERE id = CAST(:id AS uuid)"), {"id": str(uid)})
        await test_session.commit()
```

Adjust the two INSERT column lists to the NOT NULL columns the schema actually requires (the Step 1 reads show them); keep the timestamps, agent and outcome exactly as written. The `phone` needed by `collapse_call_sessions` comes from `serialize_voice_call_row`; if it reads a phone column, set it to `phone` on both legs so they collapse together.

- [ ] **Step 3: Run to verify failure**

Run: `cd /Users/sahaib/caryaar/caryaar-api && docker compose -f docker-compose.test.yml up -d && TEST_DATABASE_URL=postgresql+asyncpg://caryaar_test:caryaar_test_pw@127.0.0.1:15433/caryaar_test python3 -m pytest tests/services/performance/test_agent_activity_l2.py -v`
Expected: FAIL with `AttributeError: module ... has no attribute 'compute_agent_activity'`.

- [ ] **Step 4: Implement the queries** (append to `agent_activity.py`)

```python
from sqlalchemy import select, text

from app.api.v1.admin.bookings import serialize_voice_call_row
from app.models.booking import VoiceCall  # confirm the model's import path from booking.py
from app.services.contact_center.call_collapse import collapse_call_sessions

_STAFF_SQL = text("""
    SELECT CAST(id AS text) AS id, lower(email) AS email FROM users
    WHERE user_type = 'CY_ADMIN' AND status = 'ACTIVE' AND deleted_at IS NULL
      AND email IS NOT NULL AND email <> ''
""")
_COUNT_SQL = {
    "dispositions": """SELECT CAST(agent_user_id AS text), count(*) FROM voice_calls
        WHERE source = 'HUMAN_AGENT' AND outcome IS NOT NULL AND agent_user_id IS NOT NULL
          AND created_at >= CAST(:start AS timestamptz) AND created_at < CAST(:end AS timestamptz) GROUP BY 1""",
    "status_moves": """SELECT CAST(changed_by AS text), count(*) FROM lead_status_history
        WHERE changed_by IS NOT NULL
          AND created_at >= CAST(:start AS timestamptz) AND created_at < CAST(:end AS timestamptz) GROUP BY 1""",
    "notes_written": """SELECT CAST(author_user_id AS text), count(*) FROM customer_notes
        WHERE author_user_id IS NOT NULL
          AND created_at >= CAST(:start AS timestamptz) AND created_at < CAST(:end AS timestamptz) GROUP BY 1""",
    "bookings_credited": """SELECT CAST(credited_user_id AS text), count(*) FROM bookings
        WHERE credited_user_id IS NOT NULL
          AND created_at >= CAST(:start AS timestamptz) AND created_at < CAST(:end AS timestamptz) GROUP BY 1""",
}
_SNAPSHOT_SQL = {
    "leads_assigned": """SELECT CAST(assigned_to_user_id AS text), count(*) FROM customers
        WHERE deleted_at IS NULL AND assigned_to_user_id IS NOT NULL GROUP BY 1""",
    # UNTOUCHED_CONDITION: paste the exact condition from live_ops_tower.py:1243-1269 (Step 1).
    "leads_untouched": """SELECT CAST(assigned_to_user_id AS text), count(*) FROM customers
        WHERE deleted_at IS NULL AND assigned_to_user_id IS NOT NULL AND lead_status IS NULL
          AND coalesce(cardinality(tags), 0) = 0 GROUP BY 1""",
    "followups_overdue": """SELECT CAST(assigned_to_user_id AS text), count(*) FROM customers
        WHERE deleted_at IS NULL AND assigned_to_user_id IS NOT NULL AND next_action_at IS NOT NULL
          AND next_action_at < now() GROUP BY 1""",
}
_PAD = timedelta(hours=1)


async def compute_agent_activity(session, day: date, *, include_snapshots: bool) -> list[dict]:
    start, end = ist_day_bounds(day)
    staff = {r.id: r.email for r in (await session.execute(_STAFF_SQL)).all()}
    calls = (await session.execute(
        select(VoiceCall).where(VoiceCall.created_at >= start - _PAD, VoiceCall.created_at < end + _PAD)
    )).scalars().all()
    sessions = collapse_call_sessions([serialize_voice_call_row(c) for c in calls])
    per_agent = bucket_sessions(sessions, day)
    params = {"start": start.isoformat(), "end": end.isoformat()}
    for key, sql in _COUNT_SQL.items():
        for uid, n in (await session.execute(text(sql), params)).all():
            per_agent.setdefault(uid, {})[key] = n
    if include_snapshots:
        for key, sql in _SNAPSHOT_SQL.items():
            for uid, n in (await session.execute(text(sql))).all():
                per_agent.setdefault(uid, {})[key] = n
    return build_rows(staff, day, per_agent, include_snapshots)
```

If `tags` is `jsonb` rather than an array, the Step 1 read of the sales report shows the right expression; use it instead of `cardinality(tags)`.

- [ ] **Step 5: Run to verify pass**

Run the Step 3 command again. Expected: 1 passed. Then run the pure tests again: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add app/services/performance/agent_activity.py tests/services/performance/test_agent_activity_l2.py
git commit -m "feat(performance): per-agent CY Admin activity queries with collapsed call sessions"
```

---

### Task 3: Credentials, flag and the beat task

**Files:**
- Modify: `app/integrations/frappe/client.py:176-181,199-201,228-229`, `app/config/settings.py` (near `:740-744`), `app/api/v1/admin/settings.py:87-104`, `app/tasks/__init__.py` (`include` and `task_routes`)
- Create: `app/tasks/performance_activity_sync.py`
- Test: `tests/tasks/test_performance_activity_sync.py`

**Interfaces:**
- Consumes: `compute_agent_activity` (Task 2); Plan A endpoint `caryaar_hr_ext.performance.api.ingest_activity`.
- Produces: Celery task `app.tasks.performance_activity_sync.sync_agent_activity(day: str | None = None, final: bool = False) -> dict`; beat entries `performance-activity-sync-hourly` (minute 20, today, snapshots) and `performance-activity-sync-nightly` (00:15, yesterday, no snapshots).

- [ ] **Step 1: Write the failing task tests**

```python
# tests/tasks/test_performance_activity_sync.py
import pytest

from app.tasks import celery_app
from app.tasks import performance_activity_sync as t


def test_beat_entries_registered():
    sched = celery_app.conf.beat_schedule
    assert sched["performance-activity-sync-hourly"]["task"] == "app.tasks.performance_activity_sync.sync_agent_activity"
    assert sched["performance-activity-sync-nightly"]["kwargs"] == {"final": True}


def test_module_in_celery_include():
    assert "app.tasks.performance_activity_sync" in celery_app.conf.include


@pytest.mark.asyncio
async def test_disabled_flag_skips_without_calling_erp(monkeypatch):
    async def off(key, fallback=None):
        return False
    monkeypatch.setattr(t, "get_setting", off)
    called = []
    monkeypatch.setattr(t, "_post", lambda *a, **k: called.append(a))
    out = await t._run(day=None, final=False)
    assert out == {"skipped": "PERFORMANCE_SYNC_ENABLED is off"} and not called


@pytest.mark.asyncio
async def test_missing_key_skips(monkeypatch):
    async def on(key, fallback=None):
        return True
    monkeypatch.setattr(t, "get_setting", on)
    monkeypatch.setattr(t.settings, "ERP_PERFORMANCE_SYNC_KEY", "")
    assert (await t._run(day=None, final=False))["skipped"].startswith("ERP_PERFORMANCE_SYNC_KEY")
```

- [ ] **Step 2: Run to verify failure**

Run: `cd /Users/sahaib/caryaar/caryaar-api && python3 -m pytest tests/tasks/test_performance_activity_sync.py -q`
Expected: `ModuleNotFoundError: No module named 'app.tasks.performance_activity_sync'`.

- [ ] **Step 3: Let `FrappeClient` take its own credentials** (read `client.py:160-240` first; keep every existing caller working)

```python
# client.py: _auth_headers gains optional arguments (callers like print_format.py:25 keep calling it bare)
def _auth_headers(api_key: str | None = None, api_secret: str | None = None) -> dict[str, str]:
    key = api_key if api_key is not None else settings.FRAPPE_API_KEY
    secret = api_secret if api_secret is not None else settings.FRAPPE_API_SECRET
    return {"Authorization": f"token {key}:{secret}"}

# FrappeClient.__init__
def __init__(self, api_key: str | None = None, api_secret: str | None = None) -> None:
    ...existing body...
    self._auth = _auth_headers(api_key, api_secret)

# FrappeClient._request (was: headers built from _auth_headers()): use self._auth
```

Keep the header dict the existing `_auth_headers` returns (it may also set `Accept`/`Content-Type`); only add the two optional parameters.

- [ ] **Step 4: Add settings and denylist**

```python
# app/config/settings.py, next to the FRAPPE_* block
# Least-privilege ERP key ("key:secret") of the Performance Sync user; Secret Manager erp-performance-sync-key.
ERP_PERFORMANCE_SYNC_KEY: str = ""
# Dormant by default. Panel-switchable via get_setting("PERFORMANCE_SYNC_ENABLED").
PERFORMANCE_SYNC_ENABLED: bool = False
```

Add `"ERP_PERFORMANCE_SYNC_KEY"` to `_SECRET_KEY_DENYLIST_EXACT` in `app/api/v1/admin/settings.py`.

- [ ] **Step 5: Write the task**

```python
# app/tasks/performance_activity_sync.py
"""Send per-agent CY Admin activity to the ERP performance program (Plan C).

Hourly at :20 for today (with end-of-day snapshots); 00:15 IST for yesterday
(final counts, no snapshots). Dormant until PERFORMANCE_SYNC_ENABLED is on.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from celery.schedules import crontab

from app.config.database import get_read_session, run_async_task  # match stuck_delivery_sweep.py imports
from app.config.settings import settings
from app.integrations.frappe.client import FrappeClient
from app.services.app_settings import get_setting  # match scheduled_callbacks.py:119 import
from app.services.performance.agent_activity import compute_agent_activity
from app.tasks import celery_app
from app.utils.ist import IST, ist_today

log = logging.getLogger(__name__)
METHOD = "caryaar_hr_ext.performance.api.ingest_activity"


async def _post(rows: list[dict], synced_through: str) -> dict:
    key, _, secret = settings.ERP_PERFORMANCE_SYNC_KEY.partition(":")
    client = FrappeClient(api_key=key, api_secret=secret)
    return await client.call_method(METHOD, source="CY Admin", synced_through=synced_through, rows=rows)


async def _run(day: str | None, final: bool) -> dict:
    if not await get_setting("PERFORMANCE_SYNC_ENABLED", fallback=settings.PERFORMANCE_SYNC_ENABLED):
        return {"skipped": "PERFORMANCE_SYNC_ENABLED is off"}
    if ":" not in (settings.ERP_PERFORMANCE_SYNC_KEY or ""):
        return {"skipped": "ERP_PERFORMANCE_SYNC_KEY is not configured"}
    target = date.fromisoformat(day) if day else (ist_today() - timedelta(days=1) if final else ist_today())
    stamp = datetime.now(IST).replace(microsecond=0).isoformat()
    async with get_read_session() as session:
        rows = await compute_agent_activity(session, target, include_snapshots=not final)
    try:
        out = await _post(rows, stamp)
    except Exception as e:  # never raise from a beat task
        log.exception("performance activity sync failed for %s", target)
        return {"error": str(e)[:300], "day": target.isoformat(), "rows": len(rows)}
    return {"day": target.isoformat(), "rows": len(rows), "accepted": out.get("accepted"),
            "unmapped": out.get("unmapped", [])}


@celery_app.task(name="app.tasks.performance_activity_sync.sync_agent_activity", queue="default")
def sync_agent_activity(day: str | None = None, final: bool = False) -> dict:
    return run_async_task(_run(day, final))


_existing_schedule = getattr(celery_app.conf, "beat_schedule", None) or {}
_existing_schedule.update({
    "performance-activity-sync-hourly": {
        "task": "app.tasks.performance_activity_sync.sync_agent_activity",
        "schedule": crontab(minute=20), "kwargs": {"final": False}},
    "performance-activity-sync-nightly": {
        "task": "app.tasks.performance_activity_sync.sync_agent_activity",
        "schedule": crontab(hour=0, minute=15), "kwargs": {"final": True}},
})
celery_app.conf.beat_schedule = _existing_schedule
```

Match the three import lines marked "match" to the files named; if `call_method` is synchronous in `client.py`, call it without `await` and keep the rest identical. Fix the test's `test_beat_entries_registered` to also assert `"kwargs": {"final": False}` for the hourly entry.

- [ ] **Step 6: Register the module**: add `"app.tasks.performance_activity_sync"` to `include=[...]` and `"app.tasks.performance_activity_sync.*": {"queue": "default"}` to `task_routes` in `app/tasks/__init__.py`.

- [ ] **Step 7: Run the tests**

Run: `cd /Users/sahaib/caryaar/caryaar-api && python3 -m pytest tests/tasks/test_performance_activity_sync.py tests/tasks/test_celery_includes.py tests/services/performance/test_agent_activity_pure.py -q`
Expected: all pass. Then the L2 file from Task 2 again: 1 passed.

- [ ] **Step 8: Commit**

```bash
git add app/integrations/frappe/client.py app/config/settings.py app/api/v1/admin/settings.py app/tasks/__init__.py app/tasks/performance_activity_sync.py tests/tasks/test_performance_activity_sync.py
git commit -m "feat(performance): dormant hourly and nightly CY Admin activity sync to the ERP"
```

---

### Task 4: Ship dormant, then switch on (founder go at each step)

- [ ] **Step 1: Push first**, then deploy with the usual path: `bash scripts/deploy.sh prod` (migrates, builds, deploys `caryaar-api` and `caryaar-celery-worker`). Verify `/health` `deploy_sha` equals the pushed commit.
- [ ] **Step 2: Wire the secret on the worker only** (never `--set-env-vars`):

```bash
gcloud run services update caryaar-celery-worker --region=asia-south1 --project=caryaar-api-dev \
  --update-secrets=ERP_PERFORMANCE_SYNC_KEY=erp-performance-sync-key:latest
```
- [ ] **Step 3: One manual run while still dormant must skip**: trigger `sync_agent_activity` once (e.g. `celery call` from a one-off job, or wait for :20) and confirm `task_runs.result` shows `{"skipped": "PERFORMANCE_SYNC_ENABLED is off"}`.
- [ ] **Step 4: Switch on** `PERFORMANCE_SYNC_ENABLED` in the CY Admin settings panel. After the next :20 run, confirm in the ERP: `Work Activity Day` rows with source "CY Admin" for today exist for Janhavi and Anagha, "CY Admin synced through" is recent, and `unmapped_emails` lists only non-employees. Cross-check one agent's `calls_handled` against the CY Admin calls view for the same IST day (the product's sales report team block buckets by UTC day, so compare with the calls view, not that block).
