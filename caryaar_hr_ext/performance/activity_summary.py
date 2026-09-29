"""Pure part of the Activity Summary report (no Frappe): one row per person, department or role over a
date range, both sources side by side, columns nobody used hidden, a total row at the end. The labels
and the grouping live in activity_groups, shared with the dashboard charts."""
from __future__ import annotations

from caryaar_hr_ext.performance.activity_groups import GROUPS, LABELS, TEAM_KEYS, group_sums  # noqa: F401  (LABELS re-exported)

SNAPSHOT_KEYS: frozenset[str] = frozenset({"leads_assigned", "leads_untouched", "followups_overdue"})   # end-of-day states, never summed


def summarize(rows: list[dict], keys: tuple[str, ...], by: str = "person") -> tuple[list[dict], list[dict]]:
    """rows: Work Activity Day rows (per person, source and day, or already summed per person and
    source). Returns (columns, data) for the report: the Plane columns first, then every CY Admin key
    somebody used, then a total row. by = person (the default), department or role. The end-of-day
    snapshot keys are left out: a state summed over days means nothing. Team counts are taken once per
    group and day, so a department or the total never doubles the day's new leads."""
    keys = tuple(k for k in keys if k not in SNAPSHOT_KEYS)
    if not rows:
        return [], []
    by = by if by in GROUPS else "person"
    groups = group_sums(rows, by, keys)
    ordered = sorted(groups.items(), key=lambda kv: kv[1]["label"].lower())
    used = [k for k in keys if any(g[k] for _gid, g in ordered)]
    total = group_sums(rows, "all", keys)["Total"]
    counts = ("plane_actions", "plane_items")
    if by == "person":
        data = [{"employee": gid, "employee_name": g["label"], "department": g["department"],
                 **{k: g[k] for k in counts}, **{k: g[k] for k in used}} for gid, g in ordered]
        data.append({"employee": "", "employee_name": "Total", "department": "", **{k: total[k] for k in counts}, **{k: total[k] for k in used}})
        columns = [{"fieldname": "employee_name", "label": "Person", "fieldtype": "Data", "width": 180},
                   {"fieldname": "department", "label": "Department", "fieldtype": "Data", "width": 160}]
    else:
        data = [{"label": g["label"], **{k: g[k] for k in counts}, **{k: g[k] for k in used}} for _gid, g in ordered]
        data.append({"label": "Total", **{k: total[k] for k in counts}, **{k: total[k] for k in used}})
        columns = [{"fieldname": "label", "label": GROUPS[by], "fieldtype": "Data", "width": 240}]
    columns += [{"fieldname": "plane_actions", "label": LABELS["activity_count"], "fieldtype": "Int", "width": 110},
                {"fieldname": "plane_items", "label": LABELS["completed_count"], "fieldtype": "Int", "width": 130}]
    columns += [{"fieldname": k, "label": LABELS.get(k, k), "fieldtype": "Int", "width": 130} for k in used]
    return columns, data
