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

from plane_erp_sync import core, erp, sql

log = logging.getLogger("plane_erp_sync")
ACTIVITY_METHOD = "caryaar_hr_ext.performance.api.ingest_activity"
MODULES_METHOD = "caryaar_hr_ext.performance.api.ingest_module_progress"


def _read(path_env: str) -> str:
    return Path(os.environ[path_env]).read_text().strip()


def connect():
    import psycopg  # imported here so the pure run logic is testable without the driver

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
