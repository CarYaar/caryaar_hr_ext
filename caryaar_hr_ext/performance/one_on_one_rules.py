"""Pure rules of the goal 1:1 (no Frappe): the goals table filled from the cycle, who may
acknowledge, and the state text the one-pager and the list show."""
from __future__ import annotations

import html
import re
from datetime import date, datetime

from caryaar_hr_ext.performance import meter_rules as mr

_BLOCK_END = re.compile(r"</p>|<br\s*/?>|</li>|</div>|</h[1-6]>", re.I)
_TAG = re.compile(r"<[^>]+>")


def description_field(description: str | None, label: str) -> str:
    """The goal descriptions written on 27-Sep-2026 are paragraphs of '<b>Label:</b> text'. Paragraph
    ends become line ends, inline tags vanish, so the value stays on the label's own line."""
    text = html.unescape(_TAG.sub("", _BLOCK_END.sub("\n", description or "")))
    for line in text.splitlines():
        line = line.strip()
        if line.lower().startswith(label.lower() + ":"):
            return line.split(":", 1)[1].strip()
    return ""


def goal_rows(goals: list[dict], meters: dict[str, dict], readings: dict[str, dict],
              template_weights: dict[str, float]) -> list[dict]:
    """One row per goal: weight from the person's template row for the KRA, shared equally when several
    goals sit under the same KRA (HRMS averages their progress and applies the KRA weight once), target
    and source from the meter (a manual goal's target comes from the 'Target:' line of its description),
    the baseline from the description, progress from the latest reading; blanks, never errors, where a
    piece is missing. kra_weight and kra_goals carry the split so a page can say '15% (30% KRA across 2 goals)'."""
    under_kra: dict[str, int] = {}
    for g in goals:
        under_kra[g.get("kra") or ""] = under_kra.get(g.get("kra") or "", 0) + 1
    rows = []
    for g in goals:
        meter = meters.get(g["name"]) or {}
        reading = readings.get(g["name"]) or {}
        kra = g.get("kra") or ""
        kra_weight = template_weights.get(kra)
        n = under_kra[kra]
        rows.append({"goal": g["name"], "goal_name": g.get("goal_name") or "", "kra": kra,
                     "weight": None if kra_weight is None else round(float(kra_weight) / n, 1),
                     "kra_weight": kra_weight, "kra_goals": n,
                     "target_text": (mr.target_text(meter) if meter else "") or description_field(g.get("description"), "target"),
                     "baseline": description_field(g.get("description"), "baseline"),
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
