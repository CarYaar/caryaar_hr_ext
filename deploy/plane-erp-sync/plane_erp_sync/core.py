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


MAX_DAYS_BACK = 31


def days_back(today: date, stamp_day: date | None, cap: int = MAX_DAYS_BACK) -> int:
    """How many days before today to re-send: back to the ERP's stamp day after an
    outage, at least yesterday, at most `cap` (older gaps need a manual backfill)."""
    if stamp_day is None:
        return 1
    return max(1, min(cap, (today - stamp_day).days))


EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)
FULL_PASS_HOUR_IST = 0


def work_item_rows(rows) -> list[dict]:
    out = []
    for (iid, pid, seq, title, start, target, done, created, updated, state, deleted, email, module, labels) in rows:
        out.append({"issue_id": str(iid), "project_identifier": pid or "", "sequence_id": int(seq or 0),
                    "title": (title or "")[:140], "assignee_email": (email or "").lower() or None,
                    "state_group": state, "module_id": str(module) if module else None,
                    "labels": [x for x in (labels or "").split(",") if x],
                    "start_date": start.isoformat() if start else None,
                    "target_date": target.isoformat() if target else None,
                    "completed_at": done.astimezone(timezone.utc).isoformat() if done else None,
                    "created_at": created.astimezone(timezone.utc).isoformat(),
                    "updated_at": updated.astimezone(timezone.utc).isoformat(), "is_deleted": bool(deleted)})
    return out


def work_items_since(now_utc: datetime, stamp: str | None, full_pass_on: str | None) -> tuple[datetime, bool]:
    """Incremental from the ERP stamp minus one day; a full pass on the first run and once a day
    in the first IST hour, so a missed edit or a soft delete always heals within a day."""
    today = now_utc.astimezone(IST).date()
    first_hour = now_utc.astimezone(IST).hour == FULL_PASS_HOUR_IST
    if not stamp or (first_hour and (not full_pass_on or date.fromisoformat(full_pass_on) < today)):
        return EPOCH, True
    return datetime.fromisoformat(stamp).astimezone(timezone.utc) - timedelta(days=1), False
