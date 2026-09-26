# Plan B: Plane to ERP sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every 15 minutes, send each Plane member's daily actions and completed tasks, and every Plane module's progress, to the ERP intake endpoints built in Plan A.

**Architecture:** A small Python container on the Plane VM (`caryaar-plane`), on the `plane-app_default` Docker network, reads Plane's Postgres (`plane-db:5432`) inside read-only transactions, turns rows into the Plan A payloads with pure functions, and POSTs them to `https://erp.caryaar.com/api/method/...` through the ERP's `/api` Cloudflare bypass. Same deploy pattern as the existing Google Chat app on that VM, but committed to git.

**Tech Stack:** Python 3.12, psycopg 3.2 (binary), urllib, Docker, pytest (local, pure functions only).

**Spec:** `docs/superpowers/specs/2026-09-26-performance-plane-wfh-program-design.md` (W4a). **Depends on:** Plan A deployed (intake endpoints live) and Secret Manager secret `erp-performance-sync-key` (Plan A Task 8 Step 5).

## Global Constraints

- Plane's database is read-only for this service: every session runs with `default_transaction_read_only=on`. Never INSERT, UPDATE or DELETE in Plane.
- Days are IST: `(ts AT TIME ZONE 'Asia/Kolkata')::date`, windows computed as IST midnight converted to UTC.
- Exclude from every count: deleted rows (`deleted_at IS NULL` on every table except `users`), drafts (`issues.is_draft`), bots (`users.is_bot`), Plane automation rows (`field='archived_at' AND new_value='archive'`; `field='state' AND comment LIKE 'Plane updated the state to %'`), and the Yaar Space copies (`issues.external_source = 'yaar-space'`).
- Payloads follow Plan A exactly: `source="Plane"`, metrics `activity_count` and `completed_count` only, at most 2000 rows per call.
- ERP calls send `User-Agent: Mozilla/5.0` (Cloudflare 403s the urllib default) and the `Performance Sync` user's key. Never the Administrator key.
- Secrets live in files under `/opt/plane-erp-sync/secrets/` (mode 600) mounted read-only; never in `docker run -e`.

## Review Focus

1. **A person has no Plane activity today.** Expected: they are still sent with zeros so a count that fell (a deleted task) is corrected in the ERP. Pinned in Task 1.
2. **A run fails halfway (ERP down, DB restart).** Expected: `synced_through` is only sent on a fully successful run, so the ERP never believes stale data is current; the next run resends absolute counts. Pinned in Task 1 and Task 3.
3. **Midnight.** Expected: each run covers yesterday and today, so the last actions before midnight land in yesterday once the day closes. Pinned in Task 1.
4. **Actions taken through the shared `cy-automation` token** (Google Chat `/task`, admin scripts) are booked to the token owner. Expected: documented and visible; not silently counted as someone else's. Covered in Task 4's verification (compare against the Plane UI) and noted in the README.
5. **Plane upgrade changes a column.** Expected: the service fails loudly at startup with the missing column named, instead of sending zeros. Pinned in Task 2.

---

## File Structure

```
deploy/plane-erp-sync/
  README.md                 runbook: what it does, deploy, logs, rollback
  Dockerfile
  requirements.txt          psycopg[binary]==3.2.3
  deploy-on-vm.sh           scp'd and run on the VM
  plane_erp_sync/
    __init__.py
    core.py                 pure: IST windows, member x day grid, chunking, payloads
    sql.py                  the four SQL statements and the schema check list
    erp.py                  POST with retries
    main.py                 loop, DB reads, --once and --dry-run
  tests/
    test_core.py
```

---

### Task 1: Pure core

**Files:**
- Create: `deploy/plane-erp-sync/plane_erp_sync/__init__.py` (empty), `deploy/plane-erp-sync/plane_erp_sync/core.py`
- Test: `deploy/plane-erp-sync/tests/test_core.py`

**Interfaces:**
- Produces: `IST`, `ist_window(now_utc: datetime, days_back: int = 1) -> tuple[datetime, datetime, list[date]]`; `activity_rows(members: list[str], activity: dict[tuple[str, date], int], completed: dict[tuple[str, date], int], days: list[date]) -> list[dict]`; `module_rows(rows: list[tuple]) -> list[dict]`; `chunks(items: list, size: int = 2000) -> list[list]`; `synced_through(now_utc: datetime) -> str`.

- [ ] **Step 1: Write the failing tests**

```python
# deploy/plane-erp-sync/tests/test_core.py
from datetime import date, datetime, timezone

from plane_erp_sync import core


def test_window_covers_yesterday_and_today_in_ist():
    now = datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc)  # 00:30 IST on 2-Oct
    start, end, days = core.ist_window(now)
    assert days == [date(2026, 10, 1), date(2026, 10, 2)]
    assert start == datetime(2026, 9, 30, 18, 30, tzinfo=timezone.utc)  # 1-Oct 00:00 IST
    assert end == now


def test_every_member_gets_a_row_for_every_day_even_with_zeros():
    days = [date(2026, 10, 1), date(2026, 10, 2)]
    rows = core.activity_rows(["a@caryaar.com", "b@caryaar.com"],
                              {("a@caryaar.com", days[1]): 5}, {("a@caryaar.com", days[1]): 1}, days)
    assert len(rows) == 4
    a2 = next(r for r in rows if r["email"] == "a@caryaar.com" and r["date"] == "2026-10-02")
    assert a2["metrics"] == {"activity_count": 5, "completed_count": 1}
    b1 = next(r for r in rows if r["email"] == "b@caryaar.com" and r["date"] == "2026-10-01")
    assert b1["metrics"] == {"activity_count": 0, "completed_count": 0}


def test_activity_for_non_members_is_still_sent():
    days = [date(2026, 10, 2)]
    rows = core.activity_rows([], {("x@caryaar.com", days[0]): 2}, {}, days)
    assert rows == [{"email": "x@caryaar.com", "date": "2026-10-02",
                     "metrics": {"activity_count": 2, "completed_count": 0}}]


def test_module_rows_shape_and_clamping():
    rows = core.module_rows([("m1", "DEV", "Q4 reliability", 10, 4), ("m2", "OPS", None, 0, 0)])
    assert rows[0] == {"module_id": "m1", "project_identifier": "DEV", "module_name": "Q4 reliability",
                       "total_issues": 10, "completed_issues": 4}
    assert rows[1]["module_name"] == ""


def test_chunks():
    assert [len(c) for c in core.chunks(list(range(4500)))] == [2000, 2000, 500]
    assert core.chunks([]) == []


def test_synced_through_is_iso_with_ist_offset():
    s = core.synced_through(datetime(2026, 10, 1, 19, 0, tzinfo=timezone.utc))
    assert s == "2026-10-02T00:30:00+05:30"
```

- [ ] **Step 2: Run to verify failure**

Run: `cd deploy/plane-erp-sync && python3 -m pytest tests -q`
Expected: `ModuleNotFoundError: No module named 'plane_erp_sync.core'`.

- [ ] **Step 3: Implement**

```python
# deploy/plane-erp-sync/plane_erp_sync/core.py
"""Pure helpers: IST windows, the member x day grid and payload shapes (Plan A contract)."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))


def ist_window(now_utc: datetime, days_back: int = 1) -> tuple[datetime, datetime, list[date]]:
    today = now_utc.astimezone(IST).date()
    first = today - timedelta(days=days_back)
    start = datetime.combine(first, time(0, 0), tzinfo=IST).astimezone(timezone.utc)
    days = [first + timedelta(days=i) for i in range(days_back + 1)]
    return start, now_utc, days


def activity_rows(members, activity, completed, days) -> list[dict]:
    emails = sorted(set(members) | {e for e, _ in activity} | {e for e, _ in completed})
    return [{"email": e, "date": d.isoformat(),
             "metrics": {"activity_count": int(activity.get((e, d), 0)),
                         "completed_count": int(completed.get((e, d), 0))}}
            for e in emails for d in days]


def module_rows(rows) -> list[dict]:
    return [{"module_id": str(mid), "project_identifier": pid or "", "module_name": (name or "")[:140],
             "total_issues": int(total), "completed_issues": min(int(done), int(total))}
            for mid, pid, name, total, done in rows]


def chunks(items: list, size: int = 2000) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def synced_through(now_utc: datetime) -> str:
    return now_utc.astimezone(IST).replace(microsecond=0).isoformat()
```

- [ ] **Step 4: Run to verify pass**

Run: `cd deploy/plane-erp-sync && python3 -m pytest tests -q`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add deploy/plane-erp-sync/plane_erp_sync deploy/plane-erp-sync/tests
git commit -m "feat(plane-sync): pure core for IST windows, member day grid and payloads"
```

---

### Task 2: SQL and schema check

**Files:**
- Create: `deploy/plane-erp-sync/plane_erp_sync/sql.py`
- Test: `deploy/plane-erp-sync/tests/test_core.py` (extend)

**Interfaces:**
- Produces: `MEMBERS_SQL`, `ACTIVITY_SQL`, `COMPLETED_SQL`, `MODULES_SQL` (psycopg named parameters `%(slug)s`, `%(start)s`, `%(end)s`), `REQUIRED_COLUMNS: dict[str, set[str]]`, `SCHEMA_SQL`.

- [ ] **Step 1: Write the failing tests**

```python
from plane_erp_sync import sql


def test_every_query_excludes_the_yaar_space_copies_and_deleted_rows():
    for q in (sql.ACTIVITY_SQL, sql.COMPLETED_SQL):
        assert "external_source" in q and "yaar-space" in q
        assert "deleted_at IS NULL" in q
    assert "is_bot" in sql.ACTIVITY_SQL and "Plane updated the state to" in sql.ACTIVITY_SQL


def test_queries_bucket_days_in_ist():
    for q in (sql.ACTIVITY_SQL, sql.COMPLETED_SQL):
        assert "AT TIME ZONE 'Asia/Kolkata'" in q


def test_required_columns_cover_every_table_used():
    assert {"issue_activities", "issues", "issue_assignees", "users", "states", "modules",
            "module_issues", "projects", "workspaces", "workspace_members"} <= set(sql.REQUIRED_COLUMNS)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd deploy/plane-erp-sync && python3 -m pytest tests -q`
Expected: `ImportError: cannot import name 'sql'`.

- [ ] **Step 3: Implement**

```python
# deploy/plane-erp-sync/plane_erp_sync/sql.py
"""Read-only queries against Plane v1.3.1's Postgres (models under apps/api/plane/db/models)."""

REQUIRED_COLUMNS = {
    "issue_activities": {"issue_id", "actor_id", "field", "new_value", "comment", "created_at", "deleted_at", "workspace_id"},
    "issues": {"id", "state_id", "completed_at", "is_draft", "external_source", "deleted_at", "workspace_id"},
    "issue_assignees": {"issue_id", "assignee_id", "deleted_at"},
    "users": {"id", "email", "is_bot", "is_active"},
    "states": {"id", "group"},
    "modules": {"id", "name", "project_id", "workspace_id", "archived_at", "deleted_at"},
    "module_issues": {"module_id", "issue_id", "deleted_at"},
    "projects": {"id", "identifier", "deleted_at"},
    "workspaces": {"id", "slug"},
    "workspace_members": {"member_id", "workspace_id", "is_active", "deleted_at"},
}

SCHEMA_SQL = """
SELECT table_name, column_name FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = ANY(%(tables)s)
"""

MEMBERS_SQL = """
SELECT lower(u.email)
FROM workspace_members wm
JOIN workspaces w ON w.id = wm.workspace_id AND w.slug = %(slug)s
JOIN users u ON u.id = wm.member_id
WHERE wm.deleted_at IS NULL AND wm.is_active AND u.is_active AND NOT u.is_bot
"""

ACTIVITY_SQL = """
SELECT lower(u.email) AS email, (a.created_at AT TIME ZONE 'Asia/Kolkata')::date AS day, count(*) AS n
FROM issue_activities a
JOIN users u ON u.id = a.actor_id
JOIN issues i ON i.id = a.issue_id AND i.deleted_at IS NULL
JOIN workspaces w ON w.id = a.workspace_id AND w.slug = %(slug)s
WHERE a.deleted_at IS NULL
  AND NOT u.is_bot
  AND a.created_at >= %(start)s AND a.created_at < %(end)s
  AND coalesce(i.external_source, '') <> 'yaar-space'
  AND NOT (coalesce(a.field, '') = 'archived_at' AND coalesce(a.new_value, '') = 'archive')
  AND NOT (coalesce(a.field, '') = 'state' AND coalesce(a.comment, '') LIKE 'Plane updated the state to %%')
GROUP BY 1, 2
"""

COMPLETED_SQL = """
SELECT lower(u.email) AS email, (i.completed_at AT TIME ZONE 'Asia/Kolkata')::date AS day,
       count(DISTINCT i.id) AS n
FROM issues i
JOIN issue_assignees ia ON ia.issue_id = i.id AND ia.deleted_at IS NULL
JOIN users u ON u.id = ia.assignee_id
JOIN states s ON s.id = i.state_id AND s."group" = 'completed'
JOIN workspaces w ON w.id = i.workspace_id AND w.slug = %(slug)s
WHERE i.deleted_at IS NULL AND NOT i.is_draft AND NOT u.is_bot
  AND i.completed_at >= %(start)s AND i.completed_at < %(end)s
  AND coalesce(i.external_source, '') <> 'yaar-space'
GROUP BY 1, 2
"""

MODULES_SQL = """
SELECT m.id::text, p.identifier, m.name,
       count(i.id) FILTER (WHERE s."group" <> 'cancelled') AS total,
       count(i.id) FILTER (WHERE s."group" = 'completed') AS done
FROM modules m
JOIN projects p ON p.id = m.project_id AND p.deleted_at IS NULL
JOIN workspaces w ON w.id = m.workspace_id AND w.slug = %(slug)s
LEFT JOIN module_issues mi ON mi.module_id = m.id AND mi.deleted_at IS NULL
LEFT JOIN issues i ON i.id = mi.issue_id AND i.deleted_at IS NULL AND NOT i.is_draft
LEFT JOIN states s ON s.id = i.state_id
WHERE m.deleted_at IS NULL AND m.archived_at IS NULL
GROUP BY m.id, p.identifier, m.name
"""
```

- [ ] **Step 4: Run to verify pass**

Run: `cd deploy/plane-erp-sync && python3 -m pytest tests -q`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add deploy/plane-erp-sync/plane_erp_sync/sql.py deploy/plane-erp-sync/tests/test_core.py
git commit -m "feat(plane-sync): read-only queries for activity, completions, members and modules"
```

---

### Task 3: ERP client and runner

**Files:**
- Create: `deploy/plane-erp-sync/plane_erp_sync/erp.py`, `deploy/plane-erp-sync/plane_erp_sync/main.py`, `deploy/plane-erp-sync/requirements.txt`, `deploy/plane-erp-sync/Dockerfile`

**Interfaces:**
- Consumes: `core.*`, `sql.*`; Plan A endpoints `caryaar_hr_ext.performance.api.ingest_activity` and `ingest_module_progress`.
- Produces: `python -m plane_erp_sync.main [--once] [--dry-run]`; env `PLANE_WORKSPACE_SLUG` (default `caryaar`), `PLANE_DB_HOST` (default `plane-db`), `PLANE_DB_NAME`/`PLANE_DB_USER` (default `plane`), `PLANE_DB_PASSWORD_FILE`, `ERP_URL` (default `https://erp.caryaar.com`), `ERP_KEY_FILE` (contents `key:secret`), `INTERVAL_SECONDS` (default 900).

- [ ] **Step 1: Write `erp.py`**

```python
# deploy/plane-erp-sync/plane_erp_sync/erp.py
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger("plane_erp_sync.erp")


class ErpError(RuntimeError):
    pass


def call(base_url: str, token: str, method: str, body: dict, attempts: int = 3) -> dict:
    url = f"{base_url.rstrip('/')}/api/method/{method}"
    data = json.dumps(body).encode()
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": f"token {token}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r).get("message", {})
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if 400 <= e.code < 500:
                raise ErpError(f"{method} rejected ({e.code}): {detail}") from e
            log.warning("%s attempt %s got %s: %s", method, attempt, e.code, detail)
        except (urllib.error.URLError, TimeoutError) as e:
            log.warning("%s attempt %s network error: %s", method, attempt, e)
        time.sleep(2 ** attempt)
    raise ErpError(f"{method} failed after {attempts} attempts")
```

- [ ] **Step 2: Write `main.py`**

```python
# deploy/plane-erp-sync/plane_erp_sync/main.py
"""Plane to ERP sync: every INTERVAL_SECONDS, send yesterday's and today's per-person
activity and every module's progress to the ERP (Plan A intake). Read-only on Plane."""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg

from plane_erp_sync import core, erp, sql

log = logging.getLogger("plane_erp_sync")
ACTIVITY_METHOD = "caryaar_hr_ext.performance.api.ingest_activity"
MODULES_METHOD = "caryaar_hr_ext.performance.api.ingest_module_progress"


def _read(path_env: str) -> str:
    return Path(os.environ[path_env]).read_text().strip()


def connect() -> psycopg.Connection:
    return psycopg.connect(
        host=os.environ.get("PLANE_DB_HOST", "plane-db"), port=5432,
        dbname=os.environ.get("PLANE_DB_NAME", "plane"), user=os.environ.get("PLANE_DB_USER", "plane"),
        password=_read("PLANE_DB_PASSWORD_FILE"), options="-c default_transaction_read_only=on",
        connect_timeout=10)


def check_schema(conn) -> None:
    rows = conn.execute(sql.SCHEMA_SQL, {"tables": list(sql.REQUIRED_COLUMNS)}).fetchall()
    have: dict[str, set[str]] = defaultdict(set)
    for table, column in rows:
        have[table].add(column)
    missing = {t: sorted(c - have[t]) for t, c in sql.REQUIRED_COLUMNS.items() if c - have[t]}
    if missing:
        raise SystemExit(f"Plane schema changed, refusing to sync. Missing columns: {missing}")


def collect(conn, slug: str, now_utc: datetime):
    start, end, days = core.ist_window(now_utc)
    p = {"slug": slug, "start": start, "end": end}
    members = [r[0] for r in conn.execute(sql.MEMBERS_SQL, p).fetchall()]
    activity = {(e, d): n for e, d, n in conn.execute(sql.ACTIVITY_SQL, p).fetchall()}
    completed = {(e, d): n for e, d, n in conn.execute(sql.COMPLETED_SQL, p).fetchall()}
    modules = conn.execute(sql.MODULES_SQL, p).fetchall()
    return core.activity_rows(members, activity, completed, days), core.module_rows(modules)


def run_once(dry_run: bool) -> dict:
    now = datetime.now(timezone.utc)
    slug = os.environ.get("PLANE_WORKSPACE_SLUG", "caryaar")
    with connect() as conn:
        check_schema(conn)
        rows, modules = collect(conn, slug, now)
    stamp = core.synced_through(now)
    if dry_run:
        print(json.dumps({"synced_through": stamp, "rows": rows, "modules": modules}, indent=1, default=str))
        return {"rows": len(rows), "modules": len(modules), "dry_run": True}
    base, token = os.environ.get("ERP_URL", "https://erp.caryaar.com"), _read("ERP_KEY_FILE")
    unmapped: set[str] = set()
    for part in core.chunks(rows):
        # synced_through goes out only after every row chunk; earlier chunks carry the
        # previous stamp's meaning via rows only (see Review Focus 2).
        out = erp.call(base, token, ACTIVITY_METHOD,
                       {"source": "Plane", "synced_through": "1970-01-01T00:00:00+05:30", "rows": part})
        unmapped |= set(out.get("unmapped", []))
    erp.call(base, token, ACTIVITY_METHOD, {"source": "Plane", "synced_through": stamp, "rows": []})
    for part in core.chunks(modules):
        erp.call(base, token, MODULES_METHOD, {"synced_through": stamp, "modules": part})
    return {"rows": len(rows), "modules": len(modules), "unmapped": sorted(unmapped)}


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    interval = int(os.environ.get("INTERVAL_SECONDS", "900"))
    while True:
        try:
            log.info("sync ok %s", run_once(args.dry_run))
        except SystemExit:
            raise
        except Exception:
            log.exception("sync failed; will retry next interval")
        if args.once or args.dry_run:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
```

Plan A's `_advance` only moves `synced_through` forward, so the placeholder `1970-01-01` stamp on row chunks never moves it; the final empty-rows call carries the real stamp. That keeps Review Focus 2 true without a second endpoint.

- [ ] **Step 3: Write `requirements.txt` and `Dockerfile`**

```text
psycopg[binary]==3.2.3
```

```dockerfile
# deploy/plane-erp-sync/Dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY plane_erp_sync ./plane_erp_sync
RUN useradd -r -u 10001 sync && chown -R sync /app
USER sync
CMD ["python", "-m", "plane_erp_sync.main"]
```

- [ ] **Step 4: Run the pure tests and a syntax check**

Run: `cd deploy/plane-erp-sync && python3 -m pytest tests -q && python3 -m py_compile plane_erp_sync/*.py`
Expected: 9 passed, no compile errors.

- [ ] **Step 5: Commit**

```bash
git add deploy/plane-erp-sync
git commit -m "feat(plane-sync): runner, ERP client and container image"
```

---

### Task 4: Deploy on the Plane VM (founder go required)

**Files:**
- Create: `deploy/plane-erp-sync/deploy-on-vm.sh`, `deploy/plane-erp-sync/README.md`

- [ ] **Step 1: Write the deploy script**

```bash
#!/usr/bin/env bash
# deploy/plane-erp-sync/deploy-on-vm.sh: run ON caryaar-plane after scp'ing this folder to /opt/plane-erp-sync/src
set -euo pipefail
PROJECT=caryaar-api-dev
APP=/opt/plane-erp-sync
sudo mkdir -p "$APP/secrets"
echo "=== secrets -> $APP/secrets (600)"
gcloud secrets versions access latest --secret=PLANE_POSTGRES_PASSWORD --project="$PROJECT" | sudo tee "$APP/secrets/pg_password" >/dev/null
gcloud secrets versions access latest --secret=erp-performance-sync-key --project="$PROJECT" | sudo tee "$APP/secrets/erp_key" >/dev/null
sudo chown -R 10001 "$APP/secrets" && sudo chmod 600 "$APP/secrets/"*
DB=$(sudo docker ps --format '{{.Names}}' | grep -E 'plane-db' | head -1)
[ -n "$DB" ] || { echo "FATAL: plane-db container not found"; exit 1; }
echo "=== build"
sudo docker build -t plane-erp-sync:latest "$APP/src"
echo "=== dry run (read-only, prints payload counts)"
sudo docker run --rm --network plane-app_default -e PLANE_DB_HOST="$DB" \
  -e PLANE_DB_PASSWORD_FILE=/run/secrets/pg_password -e ERP_KEY_FILE=/run/secrets/erp_key \
  -v "$APP/secrets:/run/secrets:ro" plane-erp-sync:latest python -m plane_erp_sync.main --dry-run | tail -5
if [ "${1:-}" != "--start" ]; then echo "Dry run only. Re-run with --start to launch."; exit 0; fi
sudo docker rm -f plane-erp-sync 2>/dev/null || true
sudo docker run -d --name plane-erp-sync --restart unless-stopped --network plane-app_default \
  -e PLANE_DB_HOST="$DB" -e PLANE_DB_PASSWORD_FILE=/run/secrets/pg_password -e ERP_KEY_FILE=/run/secrets/erp_key \
  -v "$APP/secrets:/run/secrets:ro" --log-opt max-size=10m --log-opt max-file=3 plane-erp-sync:latest
sudo docker logs --tail 20 plane-erp-sync
```

- [ ] **Step 2: Write the README** (runbook): what it sends and how often, the exclusions from Global Constraints, the `cy-automation` token caveat (actions through it are booked to the token's owner; move automation to a dedicated bot user later), how to read logs (`sudo docker logs -f plane-erp-sync`), how to stop it (`sudo docker rm -f plane-erp-sync`), and how to check freshness (ERP, Performance Sync Settings, "Plane activity synced through").

- [ ] **Step 3: Ask the founder for go, then deploy the dry run**

```bash
gcloud compute scp --recurse deploy/plane-erp-sync caryaar-plane:/tmp/plane-erp-sync --zone=asia-south1-a --project=caryaar-api-dev --tunnel-through-iap
gcloud compute ssh caryaar-plane --zone=asia-south1-a --project=caryaar-api-dev --tunnel-through-iap \
  --command "sudo mkdir -p /opt/plane-erp-sync && sudo rm -rf /opt/plane-erp-sync/src && sudo mv /tmp/plane-erp-sync /opt/plane-erp-sync/src && bash /opt/plane-erp-sync/src/deploy-on-vm.sh"
```
Expected: schema check passes; dry run prints a row count equal to members x 2 plus any non-member actors, and a module count.

- [ ] **Step 4: Cross-check two numbers against the Plane UI** (Shiwans's completed tasks today; one module's done/total) before starting. If they differ, stop and fix the SQL.

- [ ] **Step 5: Start it**: re-run the ssh command with `deploy-on-vm.sh --start`. Then confirm in the ERP that "Plane activity synced through" is within the last 15 minutes and `Work Activity Day` has today's Plane rows.

- [ ] **Step 6: Commit the deploy files**

```bash
git add deploy/plane-erp-sync/deploy-on-vm.sh deploy/plane-erp-sync/README.md
git commit -m "feat(plane-sync): VM deploy script with dry run and runbook"
```
