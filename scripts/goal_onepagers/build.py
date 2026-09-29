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

    def get_list(self, doctype: str, fields: list[str], filters: list, limit: int = 200) -> list[dict]:
        q = urllib.parse.urlencode({"fields": json.dumps(fields), "filters": json.dumps(filters), "limit_page_length": limit})
        return self._req("GET", f"/api/resource/{urllib.parse.quote(doctype)}?{q}")["data"]

    def call(self, method: str, **kw):
        return self._req("POST", f"/api/method/{method}", kw)["message"]


def person_payload(erp: Erp, employee: str, cycle_name: str = CYCLE["name"]) -> dict:
    emp = erp.get_list("Employee", ["name", "employee_name", "designation", "department", "reports_to", "user_id"],
                       [["name", "=", employee]])[0]
    manager_name = ""
    if emp.get("reports_to"):
        rows = erp.get_list("Employee", ["employee_name"], [["name", "=", emp["reports_to"]]])
        manager_name = rows[0]["employee_name"] if rows else ""
    template = erp.get_list("Appraisee", ["appraisal_template"], [["parent", "=", cycle_name], ["employee", "=", employee]])
    kras = []
    if template:
        kras = [{"kra": r["key_result_area"], "weight": float(r["per_weightage"] or 0)} for r in erp.get_list(
            "Appraisal Template Goal", ["key_result_area", "per_weightage"], [["parent", "=", template[0]["appraisal_template"]]])]
    weights = {k["kra"]: k["weight"] for k in kras}
    pg = erp.call("caryaar_hr_ext.performance.api.person_goals", email=emp.get("user_id") or "")
    goals = []
    for c in pg.get("cycles") or []:
        if c.get("cycle") != cycle_name:
            continue
        for g in c.get("goals") or []:
            desc = erp.get_list("Goal", ["description"], [["name", "=", g["goal"]]])
            baseline = _baseline(desc[0].get("description") if desc else "")
            goals.append({"goal": g["goal"], "goal_name": g["goal_name"], "kra": g.get("kra") or "", "weight": weights.get(g.get("kra") or ""),
                          "method": g.get("method"), "target": g.get("target") or "", "baseline": baseline, "source": g.get("source") or "",
                          "how": g.get("how") or "", "value": g.get("value"), "progress": g.get("progress"),
                          "reading_date": g.get("reading_date")})
    one = erp.get_list("Goal One on One", ["name", "meeting_date", "employee_acknowledged", "acknowledged_on"],
                       [["employee", "=", employee], ["appraisal_cycle", "=", cycle_name], ["meeting_type", "=", "Goal setting"]], limit=1)
    return {"employee": employee, "employee_name": emp["employee_name"], "designation": emp.get("designation") or "",
            "department": emp.get("department") or "", "manager_name": manager_name, "cycle": dict(CYCLE),
            "kras": kras, "goals": goals, "one_on_one": one[0] if one else None, "score": SCORE}


def _baseline(description: str) -> str:
    """The goal descriptions written on 28-Sep-2026 carry 'Baseline: ...' on their own line."""
    import re

    text = re.sub(r"<[^>]+>", "\n", description or "")
    for line in text.splitlines():
        if line.strip().lower().startswith("baseline:"):
            return line.split(":", 1)[1].strip()
    return ""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("employee", nargs="?", help="Employee id, e.g. HR-EMP-00012")
    ap.add_argument("--out", default=str(HERE / "out"))
    ap.add_argument("--fixture", action="store_true", help="render fixture_anagha.json instead of reading the ERP")
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
    path = out_dir / f"{a.employee}.html"
    path.write_text(render(person))
    print("wrote", path, "|", len(person["goals"]), "goals |", rules.acknowledgement_state(
        bool(person["one_on_one"] and person["one_on_one"]["employee_acknowledged"]),
        person["one_on_one"]["acknowledged_on"] if person["one_on_one"] else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
