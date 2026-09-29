"""Pure rules of the goal 1:1 (no Frappe): the goals table filled from the cycle, who may
acknowledge, and the state text the one-pager and the list show."""
from __future__ import annotations

from datetime import date, datetime

from caryaar_hr_ext.performance import meter_rules as mr


def goal_rows(goals: list[dict], meters: dict[str, dict], readings: dict[str, dict],
              template_weights: dict[str, float]) -> list[dict]:
    """One row per goal: weight from the person's template row for the KRA, target and source from
    the meter, progress from the latest reading; blanks, never errors, where a piece is missing."""
    rows = []
    for g in goals:
        meter = meters.get(g["name"]) or {}
        reading = readings.get(g["name"]) or {}
        rows.append({"goal": g["name"], "goal_name": g.get("goal_name") or "", "kra": g.get("kra") or "",
                     "weight": template_weights.get(g.get("kra") or ""),
                     "target_text": mr.target_text(meter) if meter else "",
                     "measured_from": mr.source_text(meter) if meter else "",
                     "progress": reading.get("progress")})
    return rows


def can_acknowledge(session_user: str, employee_user: str | None, already: bool) -> str | None:
    """Why the stamp is refused, in plain words; None when the employee's own login may acknowledge."""
    if not employee_user:
        return "This employee has no ERP login, so the acknowledgement cannot be recorded."
    if (session_user or "").strip().lower() != employee_user.strip().lower():
        return "Only the employee can acknowledge their own goals, from their own login."
    if already:
        return "These goals are already acknowledged."
    return None


def acknowledgement_state(acknowledged: bool, acknowledged_on: datetime | date | str | None) -> str:
    return f"acknowledged on {mr.fmt_day(acknowledged_on)}" if acknowledged and acknowledged_on else "not yet acknowledged"
