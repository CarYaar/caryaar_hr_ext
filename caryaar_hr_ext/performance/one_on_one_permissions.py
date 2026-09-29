"""Who sees a Goal One on One: HR and System Managers everything; everyone else their own
records, as the employee or as the manager. The hook decides, so the self-scoped Employee
user permissions some managers carry do not hide their reports' records."""
from __future__ import annotations

import frappe

WIDE = {"HR Manager", "System Manager"}


def _own_employee(user: str) -> str | None:
    return frappe.db.get_value("Employee", {"user_id": user}, "name")


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
    return bool(emp) and emp in (doc.get("employee"), doc.get("manager"))
