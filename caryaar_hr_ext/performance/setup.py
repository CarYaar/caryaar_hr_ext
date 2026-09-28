"""Create the WFH approval setup (live since 26-Sep-2026) on a site where it is missing.

Runs after every migrate (hooks.after_migrate) but only inserts records that do
not exist yet, so edits HR makes in the ERP (a transition, a notification text,
switching the workflow off as a rollback) survive every deploy. Fixtures would
delete and re-insert these records on each migrate instead.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

DATA = Path(__file__).resolve().parent / "setup_data"
FILES = ("workflow", "notification", "custom_docperm")


def _key(doc: dict):
    if doc["doctype"] == "Custom DocPerm":
        # One permission row per (doctype, role, permlevel), whatever its name.
        return ("Custom DocPerm", (doc["parent"], doc["role"], int(doc.get("permlevel") or 0)))
    return (doc["doctype"], doc["name"])


def missing_docs(docs: list[dict], exists: Callable[[tuple], bool],
                 workflow_exists_for: Callable[[str], bool]) -> list[dict]:
    todo = []
    for doc in docs:
        if doc["doctype"] == "Workflow" and workflow_exists_for(doc["document_type"]):
            continue
        if not exists(_key(doc)):
            todo.append(doc)
    return todo


def load_docs() -> list[dict]:
    docs: list[dict] = []
    for name in FILES:
        docs.extend(json.loads((DATA / f"{name}.json").read_text()))
    return docs


def ensure_wfh_approval_setup() -> None:
    import frappe

    def exists(key) -> bool:
        doctype, ident = key
        if doctype == "Custom DocPerm":
            parent, role, permlevel = ident
            return bool(frappe.db.exists("Custom DocPerm", {"parent": parent, "role": role, "permlevel": permlevel}))
        return bool(frappe.db.exists(doctype, ident))

    def workflow_exists_for(doctype: str) -> bool:
        return bool(frappe.db.exists("Workflow", {"document_type": doctype}))

    for doc in missing_docs(load_docs(), exists, workflow_exists_for):
        frappe.get_doc(doc).insert(ignore_permissions=True)
    frappe.db.commit()


def ensure_goal_meters() -> int:
    """after_migrate: a Goal Meter for every goal in a live cycle whose (employee, KRA) is in
    setup_data/goal_meters.json and has no meter yet. Never updates an existing meter: the
    founders edit targets in the Goal Meter list and a deploy must not undo that."""
    import frappe

    rows = json.loads((Path(__file__).parent / "setup_data" / "goal_meters.json").read_text())
    wanted = {(r["employee"], r["kra"]): r for r in rows}
    from frappe.utils import getdate, nowdate

    from caryaar_hr_ext.performance import meter

    cycles = meter.live_cycles(getdate(nowdate()))
    if not cycles:
        return 0
    created = 0
    for g in frappe.get_all("Goal", filters={"appraisal_cycle": ("in", cycles), "is_group": 0, "status": ("!=", "Archived")},
                            fields=["name", "employee", "kra"]):
        r = wanted.get((g.employee, g.kra))
        if not r or frappe.db.exists("Goal Meter", g.name):
            continue
        frappe.get_doc({"doctype": "Goal Meter", "goal": g.name, "method": r["method"], "metric": r.get("metric"),
                        "window": r.get("window", "Cycle to date"), "target_value": r.get("target_value"),
                        "standard_value": r.get("standard_value"), "unit": r.get("unit"),
                        "direction": r.get("direction", "Higher is better"), "source_note": r.get("source_note"),
                        "active": 1}).insert(ignore_permissions=True)
        created += 1
    return created


SETTINGS_JSON = (Path(__file__).resolve().parents[1] / "caryaar_hr_ext" / "doctype" / "performance_sync_settings"
                 / "performance_sync_settings.json")


def default_review_pack_recipients() -> str:
    """The doctype's own default for review_pack_recipients: one source for the founders' list."""
    fields = json.loads(SETTINGS_JSON.read_text())["fields"]
    return next(f.get("default", "") for f in fields if f["fieldname"] == "review_pack_recipients")


def ensure_review_pack_recipients() -> bool:
    """after_migrate: a Single's field default is not stored for a Settings record that already
    exists, so the founders' list is written once when it is empty. Returns True when written."""
    import frappe

    if (frappe.db.get_single_value("Performance Sync Settings", "review_pack_recipients") or "").strip():
        return False
    frappe.db.set_single_value("Performance Sync Settings", "review_pack_recipients", default_review_pack_recipients())
    frappe.db.commit()
    return True
