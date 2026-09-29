"""Who sees and edits a Goal One on One. HR Manager and System Manager: everything. Anyone else:
read when they are the employee or the manager on it; create and write only when they are the
manager and the employee reports to them; never delete. The hook decides, and both Link fields
skip Frappe's user-permission check, so a manager's self-scoped Employee user permission does not
hide their reports' records."""
from __future__ import annotations

import frappe

WIDE = {"HR Manager", "System Manager"}


def _own_employee(user: str) -> str | None:
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"}, "name")


def query_conditions(user: str | None = None) -> str:
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & WIDE:
        return ""
    emp = _own_employee(user)
    if not emp:
        return "1=0"
    return (f"(`tabGoal One on One`.employee = {frappe.db.escape(emp)} "
            f"or `tabGoal One on One`.manager = {frappe.db.escape(emp)})")


def has_permission(doc, ptype: str = "read", user: str | None = None) -> bool:
    user = user or frappe.session.user
    if set(frappe.get_roles(user)) & WIDE:
        return True
    if ptype == "delete":
        return False
    emp = _own_employee(user)
    if not emp:
        return False
    if ptype == "read":
        return emp in (doc.get("employee"), doc.get("manager"))
    if doc.get("manager") != emp:
        return False
    return frappe.db.get_value("Employee", doc.get("employee"), "reports_to") == emp
