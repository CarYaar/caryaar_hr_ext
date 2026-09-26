"""Export live ERP records into this app's fixture files (READ-ONLY on the ERP).

Mirrors frappe's export_json post-processing: drops per-site metadata from each
document and child row so `bench migrate` can re-apply them on any site.

Usage: set FRAPPE_URL, FRAPPE_API_KEY, FRAPPE_API_SECRET (e.g. `set -a; . ~/.config/caryaar/frappe.env; set +a`)
       python3 scripts/export_live_fixtures.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "caryaar_hr_ext"
FX = APP / "fixtures"
# The live WFH workflow, notifications and docperms are created-if-missing after
# migrate (performance/setup.py), never fixtures, so HR edits survive deploys.
SETUP = APP / "performance" / "setup_data"
SETUP_FILES = {"workflow", "notification", "custom_docperm"}
TOP_DROP = ("modified", "modified_by", "creation", "owner", "idx", "lft", "rgt",
            "_user_tags", "_comments", "_assign", "_liked_by", "_seen")
CHILD_DROP = TOP_DROP + ("docstatus", "doctype", "modified", "name")

EXPORTS = {
    "custom_field": ("Custom Field", [["fieldname", "like", "cy_%"],
                                      ["dt", "in", ["Employee", "Attendance Request"]]]),
    "workflow": ("Workflow", [["name", "=", "Attendance Request Approval"]]),
    "workflow_state": ("Workflow State", [["name", "in", ["Draft", "Cancelled"]]]),
    "workflow_action_master": ("Workflow Action Master", [["name", "in", ["Send for Approval", "Cancel"]]]),
    "notification": ("Notification", [["name", "in", ["WFH request awaiting manager approval",
                                                      "WFH request awaiting HR approval",
                                                      "WFH request decided"]]]),
    "custom_docperm": ("Custom DocPerm", [["parent", "=", "Attendance Request"]]),
}


def strip(doc: dict) -> dict:
    out = {k: v for k, v in doc.items() if k not in TOP_DROP}
    for k, v in list(out.items()):
        if isinstance(v, list):
            out[k] = [{ck: cv for ck, cv in row.items() if ck not in CHILD_DROP}
                      for row in v if isinstance(row, dict)]
    return out


def _get(path: str) -> dict:
    url = os.environ.get("FRAPPE_URL", "https://erp.caryaar.com") + path
    req = urllib.request.Request(url, headers={
        "Authorization": f"token {os.environ['FRAPPE_API_KEY']}:{os.environ['FRAPPE_API_SECRET']}",
        "User-Agent": "Mozilla/5.0", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def export(doctype: str, filters: list) -> list[dict]:
    q = urllib.parse.urlencode({"filters": json.dumps(filters), "fields": json.dumps(["name"]),
                                "limit_page_length": "500", "order_by": "name asc"})
    names = [d["name"] for d in _get(f"/api/resource/{urllib.parse.quote(doctype)}?{q}")["data"]]
    return [strip(_get(f"/api/resource/{urllib.parse.quote(doctype)}/{urllib.parse.quote(n)}")["data"])
            for n in names]


def main() -> int:
    for fname, (doctype, filters) in EXPORTS.items():
        docs = export(doctype, filters)
        if not docs:
            print(f"ERROR: nothing exported for {doctype} {filters}", file=sys.stderr)
            return 1
        ((SETUP if fname in SETUP_FILES else FX) / f"{fname}.json").write_text(json.dumps(docs, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
        print(f"{fname}.json: {len(docs)} {doctype}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
