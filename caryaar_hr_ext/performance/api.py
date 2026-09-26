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
