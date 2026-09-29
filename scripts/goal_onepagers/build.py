"""Build one goal one-pager per employee from the ERP (spec 2026-09-29-goal-onepagers-and-acknowledgement).

Usage, from the operator's Mac with ~/.config/caryaar/frappe.env (FRAPPE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET):

    python3 -m scripts.goal_onepagers.build HR-EMP-00012                      # writes out/HR-EMP-00012.html
    python3 -m scripts.goal_onepagers.build HR-EMP-00012 --fixture             # renders the fixture, no ERP
    python3 -m scripts.goal_onepagers.build --create-1on1 HR-EMP-00012 HR-EMP-00003 2026-10-06
    python3 -m scripts.goal_onepagers.build --set-url HR-EMP-00012 https://claude.ai/artifact/...

Reads: Employee, the cycle's appraisee template and its KRA weights, person_goals(email), the Goal One on
One record for the cycle. Writes: nothing, except one_pager_url with --set-url and a new Goal One on One
with --create-1on1. Cloudflare refuses Python's default user agent, so every call sends a browser one.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from caryaar_hr_ext.performance import meter_rules as mr  # noqa: E402
from caryaar_hr_ext.performance import one_on_one_rules as rules  # noqa: E402

CYCLE = {"name": "Oct 2026 - Mar 2027", "start": "2026-10-01", "end": "2027-03-31",
         "mid_review": "2027-01-15", "final_review": "2027-03-15"}
WORDMARK = "".join(f'<path d="{d}"/>' for d in __import__("re").findall(
    r'<path class="st0" d="([^"]+)"', (HERE / "wordmark.svg").read_text()))
SCORE = [["Goals", 50], ["Competencies", 20], ["Behaviour and culture", 12.5], ["Process adherence", 7.5],
         ["Initiative and innovation", 10]]


def _num(x) -> str:
    if x is None:
        return ""
    return f"{int(x)}" if float(x).is_integer() else f"{x}"


def render(person: dict, generated_on: date | None = None) -> str:
    env = Environment(loader=FileSystemLoader(str(HERE)), autoescape=select_autoescape(["html"]))
    env.filters["day"] = mr.fmt_day
    env.filters["num"] = _num
    one = person.get("one_on_one") or None
    ack = rules.acknowledgement_state(bool(one and one.get("employee_acknowledged")), one.get("acknowledged_on") if one else None)
    return env.get_template("template.html").render(
        p=person, cycle=person.get("cycle") or CYCLE, kras=person.get("kras") or [], goals=person.get("goals") or [],
        one_on_one=one, ack_state=ack, score=person.get("score") or SCORE, generated_on=generated_on or date.today(),
        WORDMARK=WORDMARK)


# ─── the ERP, read only except the two named writes ───────────────────────────

def _env() -> dict:
    out = {}
    for line in open(os.path.expanduser("~/.config/caryaar/frappe.env")):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            out[k] = v.strip().strip('"').strip("'")
    return out


class Erp:
    def __init__(self):
        e = _env()
        self.base = e["FRAPPE_URL"].rstrip("/")
        self.headers = {"Authorization": f"token {e['FRAPPE_API_KEY']}:{e['FRAPPE_API_SECRET']}",
                        "Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}

    def _req(self, method: str, path: str, body: dict | None = None):
        data = json.dumps(body).encode() if body is not None else None
        r = urllib.request.Request(self.base + path, data=data, headers=self.headers, method=method)
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read().decode())

    def get_list(self, doctype: str, fields: list[str], filters: list, limit: int = 200, parent: str | None = None) -> list[dict]:
        """A child table must name its parent doctype, or Frappe strips every field but name from the rows."""
        q = {"fields": json.dumps(fields), "filters": json.dumps(filters), "limit_page_length": limit}
        if parent:
            q["parent"] = parent
        return self._req("GET", f"/api/resource/{urllib.parse.quote(doctype)}?{urllib.parse.urlencode(q)}")["data"]

    def call(self, method: str, **kw):
        return self._req("POST", f"/api/method/{method}", kw)["message"]


def person_payload(erp: Erp, employee: str, cycle_name: str = CYCLE["name"]) -> dict:
    """Everything the page needs, read straight from the records (Goal, Goal Meter, the latest reading,
    the template weights) through the same rules the 1:1 record uses, so the page and the record agree."""
    emp = erp.get_list("Employee", ["name", "employee_name", "designation", "department", "reports_to", "user_id", "company_email"],
                       [["name", "=", employee]])[0]
    manager_name = ""
    if emp.get("reports_to"):
        rows = erp.get_list("Employee", ["employee_name"], [["name", "=", emp["reports_to"]]])
        manager_name = rows[0]["employee_name"] if rows else ""
    template = erp.get_list("Appraisee", ["appraisal_template"], [["parent", "=", cycle_name], ["employee", "=", employee]],
                            parent="Appraisal Cycle")
    kras = []
    if template:
        kras = [{"kra": r["key_result_area"], "weight": float(r["per_weightage"] or 0)} for r in erp.get_list(
            "Appraisal Template Goal", ["key_result_area", "per_weightage"], [["parent", "=", template[0]["appraisal_template"]]],
            parent="Appraisal Template")]
    weights = {k["kra"]: k["weight"] for k in kras}
    goal_rows = erp.get_list("Goal", ["name", "goal_name", "kra", "description"],
                             [["employee", "=", employee], ["appraisal_cycle", "=", cycle_name], ["is_group", "=", 0], ["status", "!=", "Archived"]])
    names = [g["name"] for g in goal_rows]
    meters = {m["goal"]: {"method": m["method"], "metric": m["metric"], "target": m["target_value"], "unit": m["unit"],
                          "standard": m["standard_value"], "direction": m["direction"]}
              for m in erp.get_list("Goal Meter", ["goal", "method", "metric", "target_value", "unit", "standard_value", "direction"],
                                    [["goal", "in", names]])} if names else {}
    readings: dict[str, dict] = {}
    if names:
        for r in sorted(erp.get_list("Goal Meter Reading", ["goal", "progress", "value", "reading_date"], [["goal", "in", names]], limit=2000),
                        key=lambda r: str(r["reading_date"]), reverse=True):
            readings.setdefault(r["goal"], r)
    goals = []
    for row, g in zip(rules.goal_rows(goal_rows, meters, readings, weights), goal_rows):
        meter = meters.get(g["name"]) or {}
        reading = readings.get(g["name"]) or {}
        goals.append({"goal": g["name"], "goal_name": g["goal_name"], "kra": row["kra"], "weight": row["weight"],
                      "kra_weight": row["kra_weight"], "kra_goals": row["kra_goals"],
                      "method": meter.get("method") or "", "target": row["target_text"], "baseline": row["baseline"],
                      "source": mr.source_name(meter) if meter else "", "how": mr.describe_meter(meter) if meter else "",
                      "value": reading.get("value"), "progress": row["progress"], "reading_date": reading.get("reading_date")})
    one = erp.get_list("Goal One on One", ["name", "meeting_date", "employee_acknowledged", "acknowledged_on"],
                       [["employee", "=", employee], ["appraisal_cycle", "=", cycle_name], ["meeting_type", "=", "Goal setting"]], limit=1)
    return {"employee": employee, "employee_name": emp["employee_name"], "designation": emp.get("designation") or "",
            "department": emp.get("department") or "", "manager_name": manager_name, "cycle": dict(CYCLE),
            "kras": kras, "goals": goals, "one_on_one": one[0] if one else None, "score": SCORE,
            "login": emp.get("user_id") or emp.get("company_email") or ""}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("employee", nargs="?", help="Employee id, e.g. HR-EMP-00012")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--fixture", action="store_true", help="render fixture_anagha.json instead of reading the ERP")
    ap.add_argument("--allow-empty", action="store_true", help="write a page even when the person has no goals yet")
    ap.add_argument("--set-url", nargs=2, metavar=("EMPLOYEE", "URL"), help="write one_pager_url on the person's goal setting 1:1")
    ap.add_argument("--create-1on1", nargs=3, metavar=("EMPLOYEE", "MANAGER", "YYYY-MM-DD"), help="create the goal setting 1:1")
    a = ap.parse_args(argv)
    out_dir = Path(a.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    if a.fixture:
        person = json.loads((HERE / "fixture_anagha.json").read_text())
        path = out_dir / "fixture_anagha.html"
        path.write_text(render(person))
        print("wrote", path)
        return 0
    erp = Erp()
    if a.create_1on1:
        employee, manager, day = a.create_1on1
        doc = erp.call("frappe.client.insert", doc={"doctype": "Goal One on One", "employee": employee, "manager": manager,
                                                    "appraisal_cycle": CYCLE["name"], "meeting_date": day, "meeting_type": "Goal setting"})
        print("created", doc["name"])
        return 0
    if a.set_url:
        employee, url = a.set_url
        one = erp.get_list("Goal One on One", ["name"], [["employee", "=", employee], ["appraisal_cycle", "=", CYCLE["name"]],
                                                          ["meeting_type", "=", "Goal setting"]], limit=1)
        if not one:
            print("no goal setting 1:1 for", employee)
            return 1
        erp.call("frappe.client.set_value", doctype="Goal One on One", name=one[0]["name"], fieldname="one_pager_url", value=url)
        print("set one_pager_url on", one[0]["name"])
        return 0
    if not a.employee:
        ap.print_help()
        return 2
    person = person_payload(erp, a.employee)
    if not person["goals"] and not a.allow_empty:
        print(f"{a.employee} has no live goals in {CYCLE['name']}; nothing written (use --allow-empty for a page that says so)")
        return 1
    path = out_dir / f"{a.employee}.html"
    path.write_text(render(person))
    print("wrote", path, "|", len(person["goals"]), "goals |", rules.acknowledgement_state(
        bool(person["one_on_one"] and person["one_on_one"]["employee_acknowledged"]),
        person["one_on_one"]["acknowledged_on"] if person["one_on_one"] else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
