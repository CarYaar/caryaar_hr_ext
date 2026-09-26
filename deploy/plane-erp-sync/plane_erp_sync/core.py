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
