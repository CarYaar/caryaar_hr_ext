"""Pure part of the Activity Summary report (no Frappe): one row per person over a date range,
both sources side by side, columns nobody used hidden, a total row at the end."""
from __future__ import annotations

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


def summarize(rows: list[dict], keys: tuple[str, ...]) -> tuple[list[dict], list[dict]]:
    """rows: sums per (employee, source) as the SQL returns them. Returns (columns, data) for the
    report: the Plane columns first, then every CY Admin key somebody used, then a total row."""
    if not rows:
        return [], []
    people: dict[str, dict] = {}
    for r in rows:
        p = people.setdefault(r["employee"], {"employee": r["employee"], "employee_name": r.get("employee_name") or r["employee"],
                                                "department": r.get("department") or "", "plane_actions": 0, "plane_items": 0,
                                                **{k: 0 for k in keys}})
        if r.get("source") == "Plane":
            p["plane_actions"] += int(r.get("activity_count") or 0)
            p["plane_items"] += int(r.get("completed_count") or 0)
        else:
            for k in keys:
                p[k] += int(r.get(k) or 0)
    data = sorted(people.values(), key=lambda p: p["employee_name"].lower())
    used = [k for k in keys if any(p[k] for p in data)]
    total = {"employee": "", "employee_name": "Total", "department": "",
             "plane_actions": sum(p["plane_actions"] for p in data), "plane_items": sum(p["plane_items"] for p in data),
             **{k: sum(p[k] for p in data) for k in used}}
    data = [{k: v for k, v in p.items() if k in ("employee", "employee_name", "department", "plane_actions", "plane_items") or k in used}
            for p in data] + [total]
    columns = [{"fieldname": "employee_name", "label": "Person", "fieldtype": "Data", "width": 180},
               {"fieldname": "department", "label": "Department", "fieldtype": "Data", "width": 160},
               {"fieldname": "plane_actions", "label": LABELS["activity_count"], "fieldtype": "Int", "width": 110},
               {"fieldname": "plane_items", "label": LABELS["completed_count"], "fieldtype": "Int", "width": 130}]
    columns += [{"fieldname": k, "label": LABELS.get(k, k), "fieldtype": "Int", "width": 130} for k in used]
    return columns, data
