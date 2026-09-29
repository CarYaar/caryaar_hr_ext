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


_SINGLE = "Performance Sync Settings"


def _stamp(field: str):
    # An unset Datetime single reads back as 0001-01-01, not None.
    return rules.stored_stamp(frappe.db.get_single_value(_SINGLE, field))


def _set(field: str, value) -> None:
    # Single-value writes: no full-document save, so no Version row per sync call
    # and no timestamp clash with someone editing the settings form.
    frappe.db.set_single_value(_SINGLE, field, value)


@frappe.whitelist(methods=["POST"])
def ingest_activity(source=None, synced_through=None, rows=None, covers_from=None):
    frappe.only_for(("Performance Sync", "System Manager"))
    try:
        batch = rules.validate_activity_payload(source, synced_through, rows, covers_from)
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

    field = _SYNC_FIELD[batch.source]
    current = _stamp(field)
    stamp = rules.advance_stamp(current, batch.synced_through, batch.covers_from)
    if stamp != current:
        _set(field, stamp)
    if unmapped:
        known = set(filter(None, (frappe.db.get_single_value(_SINGLE, "unmapped_emails") or "").split("\n")))
        _set("unmapped_emails", "\n".join(sorted(known | unmapped)))
    return {"accepted": accepted, "unmapped": sorted(unmapped),
            "synced_through": stamp.isoformat() if stamp else None}


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
    current = _stamp("plane_modules_synced_through")
    if not current or when > current:
        _set("plane_modules_synced_through", when)
    return {"accepted": len(rows)}



@frappe.whitelist(methods=["POST"])
def ingest_work_items(synced_through=None, items=None, full_pass=0):
    """Every Plane project's work items, upserted by issue id. A deleted or archived
    item arrives flagged and stays flagged: the review pack shows what happened to it.
    Chunk calls carry a 1970 placeholder stamp; only the sender's final call moves it."""
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
                  "module_id": r.module_id, "module_ids": ",".join(r.module_ids), "labels": ",".join(r.labels),
                  "start_date": r.start_date, "target_date": r.target_date, "completed_at": r.completed_at,
                  "created_at": r.created_at, "updated_at": r.updated_at, "is_deleted": 1 if r.is_deleted else 0,
                  "is_archived": 1 if r.is_archived else 0, "synced_at": now_datetime()}
        if frappe.db.exists("Plane Work Item", r.issue_id):
            frappe.db.set_value("Plane Work Item", r.issue_id, values, update_modified=False)
        else:
            frappe.get_doc({"doctype": "Plane Work Item", "issue_id": r.issue_id, **values}).insert(ignore_permissions=True)
        accepted += 1
    current = _stamp("plane_items_synced_through")
    if when.year > 1971 and (not current or when > current):
        _set("plane_items_synced_through", when)
    if int(full_pass or 0):
        _set("plane_items_full_pass_on", when.date())
    if unmapped:
        known = set(filter(None, (frappe.db.get_single_value(_SINGLE, "unmapped_emails") or "").split("\n")))
        _set("unmapped_emails", "\n".join(sorted(known | unmapped)))
    stamp = _stamp("plane_items_synced_through")
    return {"accepted": accepted, "unmapped": sorted(unmapped), "synced_through": stamp.isoformat() if stamp else None}

@frappe.whitelist(methods=["GET", "POST"])
def person_goals(email: str = "") -> dict:
    """For CY Admin's home screen: one person's goals in each live cycle, how each is measured,
    the latest reading, the Plane items counted and the next review date. Read by caryaar-api
    with the Performance Sync key on behalf of the signed-in user; the email is theirs."""
    frappe.only_for(("Performance Sync", "System Manager"))
    from frappe.utils import getdate, nowdate

    from caryaar_hr_ext.performance import meter, meter_rules as mr, review_pack

    emp = _email_map().get((email or "").strip().lower())
    if not emp:
        return {"employee": None, "employee_name": None, "cycles": []}
    today = getdate(nowdate())
    cycles = meter.live_cycles(today, started_only=True)
    out = []
    for cycle in cycles:
        pack = review_pack.build_pack(emp, cycle, today)
        if not pack["goals"]:
            continue          # a live cycle the person has no goals in (the previous one, until it ends)
        review_on = frappe.db.get_value("Appraisal", {"employee": emp, "appraisal_cycle": cycle, "docstatus": ("<", 2)},
                                        "cy_next_review_on")
        out.append(mr.person_view(pack, str(review_on) if review_on else None))
    return {"employee": emp, "employee_name": frappe.db.get_value("Employee", emp, "employee_name"), "cycles": out}


@frappe.whitelist(methods=["GET", "POST"])
def get_sync_state():
    """Each source's "synced through" stamp, so a sender can backfill from it."""
    frappe.only_for(("Performance Sync", "System Manager"))
    state = {src: (_stamp(field).isoformat() if _stamp(field) else None) for src, field in _SYNC_FIELD.items()}
    items = _stamp("plane_items_synced_through")
    state["Plane items"] = items.isoformat() if items else None
    full = frappe.db.get_single_value(_SINGLE, "plane_items_full_pass_on")
    state["Plane items full pass"] = str(full) if full else None
    return state


@frappe.whitelist(methods=["POST"])
def recompute(from_date=None, to_date=None):
    """Recompute Work Adherence Day for a date range (at most 62 days), e.g. after
    leave was approved late or attendance was corrected."""
    frappe.only_for(("HR Manager", "System Manager"))
    from caryaar_hr_ext.performance import engine

    try:
        days = rules.recompute_days(from_date, to_date)
    except ValueError as e:
        frappe.throw(str(e), exc=frappe.ValidationError)
    written = sum(engine.run_day(d) for d in days)
    return {"days": len(days), "rows": written}


@frappe.whitelist(methods=["POST"])
def acknowledge_goals(name: str = "") -> dict:
    """The employee acknowledges the goals on their own Goal One on One record. Any logged-in user
    may call it; the rule decides, and only the employee's own login passes. The row is locked
    while it is stamped, so two clicks cannot both write."""
    from frappe.utils import now_datetime

    from caryaar_hr_ext.performance import one_on_one_rules as o2o

    doc = frappe.get_doc("Goal One on One", name, for_update=True)
    employee_user, employee_name = frappe.db.get_value("Employee", doc.employee, ["user_id", "employee_name"]) or (None, None)
    problem = o2o.can_acknowledge(frappe.session.user, employee_user, bool(doc.get("employee_acknowledged")))
    if problem:
        frappe.throw(problem)
    stamp = now_datetime()
    doc.db_set({"employee_acknowledged": 1, "acknowledged_on": stamp, "acknowledged_by": frappe.session.user}, notify=True)
    doc.add_comment("Info", f"Goals acknowledged by {employee_name or doc.employee}")
    return {"ok": True, "acknowledged_on": str(stamp)}
