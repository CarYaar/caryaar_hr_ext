"""Pure rules behind the department and role views of activity (no Frappe): which numbers each
department is read by, the founder's four periods, grouping of day-level Work Activity Day rows by
person, department or role, and the bar chart one department gets on the dashboard.

Team counts (the day's new leads by channel) are stamped on every marketing person, so a group takes
them once per day (the max across its people) while personal counts add up across people."""
from __future__ import annotations

from datetime import date, timedelta

LABELS: dict[str, str] = {
    "activity_count": "Plane actions", "completed_count": "Plane items completed",
    "calls_handled": "Calls handled", "calls_answered": "Calls answered", "talk_seconds": "Talk time (seconds)",
    "dispositions": "Calls with an outcome", "status_moves": "Lead status changes", "notes_written": "Notes written",
    "bookings_credited": "Bookings credited", "leads_assigned": "Leads assigned (end of day)",
    "leads_untouched": "Leads untouched (end of day)", "followups_overdue": "Follow-ups overdue (end of day)",
    "leads_assigned_new": "Leads assigned that day", "bookings_within_7d": "Bookings within 7 days",
    "followups_due": "Follow-ups due", "followups_done_on_time": "Follow-ups done on the day",
    "leads_statused_48h": "Leads statused within 48 h",
    "jobs_from_bookings": "Jobs from bookings", "jobs_from_bookings_paid": "Jobs from bookings, paid",
    "campaigns_sent": "Campaigns sent", "campaign_leads_reached": "Leads reached by campaigns",
    "pr_campaigns_sent": "PR campaigns sent", "pr_replies": "PR replies", "creatives_rendered": "Creatives rendered",
    "creatives_approved": "Creatives approved", "leads_meta": "New leads: Meta (team)", "leads_google": "New leads: Google (team)",
    "leads_whatsapp": "New leads: WhatsApp (team)", "leads_web": "New leads: web (team)",
    "jobs_moved": "Job status moves", "estimates_created": "Estimates created", "partner_changes": "Service Partner changes",
    "sweep_items_closed": "Sweep items closed", "partners_created": "Service Partners created",
    "partners_verified": "Service Partners verified", "partners_activated": "Service Partners activated",
    "partner_documents": "Documents uploaded or verified", "agreements_created": "Agreements created",
    "agreements_approved": "Agreements approved", "agreements_signed": "Agreements signed",
    "partner_checkins_closed": "Check-ins closed", "payouts_triggered": "Payouts triggered by hand",
    "payments_collected_offline": "Offline payments recorded", "unpaid_cleared": "Ready-unpaid items closed",
    "plane_items_completed": "Plane items completed (CY Admin mirror)",
}

TEAM_KEYS: frozenset[str] = frozenset({"leads_meta", "leads_google", "leads_whatsapp", "leads_web"})
PLANE_KEYS: dict[str, str] = {"plane_items": "completed_count", "plane_actions": "activity_count"}   # chart key -> Plane row field

# Which numbers a department is read by, in the order the chart shows them. Keyed by the part of the
# ERP department name before " - " (Operations - CAPL -> Operations) so a company suffix never matters.
DEPARTMENT_METRICS: dict[str, tuple[str, ...]] = {
    "Operations": ("calls_handled", "followups_done_on_time", "leads_statused_48h", "bookings_credited", "jobs_from_bookings"),
    "Marketing": ("campaign_leads_reached", "campaigns_sent", "creatives_approved", "leads_meta", "leads_google", "leads_whatsapp", "leads_web"),
    "Technology": ("plane_items", "plane_actions", "jobs_moved", "sweep_items_closed"),
    "Finance & Accounts": ("payouts_triggered", "payments_collected_offline", "unpaid_cleared", "plane_items"),
    "Workshop Relations": ("partners_activated", "partners_verified", "agreements_signed", "partner_checkins_closed", "partner_documents"),
    "Partnerships": ("plane_items", "plane_actions", "partners_created"),
    "Human Resources": ("plane_items", "plane_actions"),
    "Corporate Management": ("plane_items", "plane_actions"),
}
DEFAULT_METRICS: tuple[str, ...] = ("plane_items", "plane_actions")
PERIODS: tuple[str, ...] = ("This month", "Last month", "Last 7 days", "Last 30 days", "Custom")
GROUPS: dict[str, str] = {"person": "Person", "department": "Department", "role": "Role"}


def department_key(name: str | None) -> str:
    return (name or "").split(" - ")[0].strip()


def metrics_for(department: str | None) -> tuple[str, ...]:
    return DEPARTMENT_METRICS.get(department_key(department), DEFAULT_METRICS)


def period_bounds(period: str | None, today: date, from_date: date | None = None, to_date: date | None = None) -> tuple[date, date]:
    """The founder's four windows; Custom takes the two dates given, anything else reads this month."""
    if period == "Last month":
        last_of_previous = today.replace(day=1) - timedelta(days=1)
        return last_of_previous.replace(day=1), last_of_previous
    if period == "Last 7 days":
        return today - timedelta(days=6), today
    if period == "Last 30 days":
        return today - timedelta(days=29), today
    if period == "Custom" and from_date and to_date:
        return from_date, to_date
    return today.replace(day=1), today


def _group_of(row: dict, by: str) -> tuple[str, str]:
    if by == "person":
        return row["employee"], row.get("employee_name") or row["employee"]
    if by == "department":
        d = row.get("department") or ""
        return d, d
    if by == "role":
        r = row.get("role") or row.get("designation") or ""
        return r, r
    return "Total", "Total"


def group_sums(rows: list[dict], by: str, keys: tuple[str, ...]) -> dict[str, dict]:
    """rows are Work Activity Day rows (one per person, source and day; rows without a date count as
    one day). Returns {group id: {label, department, plane_actions, plane_items, key...}}. Personal
    keys add up; TEAM_KEYS are taken once per group and day, as the max across the group's people."""
    groups: dict[str, dict] = {}
    team: dict[tuple[str, str, str], int] = {}
    for r in rows:
        gid, label = _group_of(r, by)
        g = groups.get(gid)
        if g is None:
            g = groups[gid] = {"label": label, "department": r.get("department") or "", "plane_actions": 0, "plane_items": 0,
                               **{k: 0 for k in keys}}
        elif g["department"] != (r.get("department") or ""):
            g["department"] = ""
        if r.get("source") == "Plane":
            g["plane_actions"] += int(r.get("activity_count") or 0)
            g["plane_items"] += int(r.get("completed_count") or 0)
            continue
        for k in keys:
            v = int(r.get(k) or 0)
            if k in TEAM_KEYS:
                bucket = (gid, str(r.get("activity_date") or ""), k)
                team[bucket] = max(team.get(bucket, 0), v)
            else:
                g[k] += v
    for (gid, _day, k), v in team.items():
        groups[gid][k] += v
    return groups


def department_chart(department: str | None, rows: list[dict]) -> dict:
    """The dashboard bar chart of one department: its metrics in order, over whatever rows are given."""
    metrics = metrics_for(department)
    sums = group_sums(rows, "all", tuple(k for k in metrics if k not in PLANE_KEYS)).get("Total") or {}
    values = [int(sums.get(k, 0) or 0) for k in metrics]
    labels = [LABELS[PLANE_KEYS[k]] if k in PLANE_KEYS else LABELS[k] for k in metrics]
    return {"labels": labels, "datasets": [{"name": department_key(department) or "Everyone", "values": values}], "type": "bar"}
