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
