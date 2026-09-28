#!/usr/bin/env python3
"""Create one Plane module per Plane-measured goal and link it to the goal (Task 9).

Run from the operator's Mac:  python3 goal_modules.py [--dry-run]
  1. reads active Goal Meters that need a module (method "Plane module", or a metric computed over the module)
     whose goal has no cy_plane_module (ERP REST, ~/.config/caryaar/frappe.env)
  2. creates a module named after the goal in the person's department project, through the cy-automation token ON the
     Plane VM (gcloud compute ssh caryaar-plane ... python3 -), skipping a module of that name that already exists
  3. writes the module id to Goal.cy_plane_module
Idempotent: a goal with a module set, or a module already named after it, is left alone."""
from __future__ import annotations

import json
import os
import subprocess
import sys

PROJECTS = {"DEV": "257911e1-8d3e-430a-89ad-bf02a6cf9d06", "MKT": "51a28d51-484e-4aae-8d58-6a73d5253c7e",
            "OPS": "23a1dc7e-820c-480d-88a2-874165adc4e8", "WR": "1f82b49a-1667-4fca-8201-31b3a108903a",
            "PARTNER": "299ab26a-d79c-4622-acdd-1ae853787c92", "FINANCE": "0d03f705-65c8-4115-b557-1cf4c9b3cbc8",
            "HR": "737a2409-5035-4ce1-989c-bedc7e59d45e", "CORP": "23de6828-fe38-4c97-a27f-c3ca4a6b014c"}
BY_EMPLOYEE = {"HR-EMP-00008": "DEV", "HR-EMP-00011": "DEV", "HR-EMP-00014": "MKT", "HR-EMP-00012": "OPS",
               "HR-EMP-00010": "OPS", "HR-EMP-00006": "WR", "HR-EMP-00005": "PARTNER", "HR-EMP-00007": "FINANCE",
               "HR-EMP-00004": "HR", "HR-EMP-00016": "HR", "HR-EMP-00001": "CORP", "HR-EMP-00002": "CORP", "HR-EMP-00003": "CORP"}
TECH_KRAS = {"Technology Development", "Technology Maintained"}   # the founders' tech goals live in DEV
MODULE_METRICS = ("support_on_time_pct",)   # Ratio meters whose metric reads the goal's module (meter.py)


def module_name(goal_name: str) -> str:
    """The module is named after the goal, cut at 80 characters on a word and stripped, the way
    Plane stores names (it strips whitespace, so a name ending in a space never matches again)."""
    name = " ".join((goal_name or "").split())
    if len(name) <= 80:
        return name
    cut = name[:80]
    return (cut[:cut.rfind(" ")] if " " in cut else cut).rstrip(" ,;:")


def needs_module(method: str | None, metric: str | None) -> bool:
    """Plane-module meters, plus any meter whose metric is computed over the goal's module."""
    return method == "Plane module" or (metric or "") in MODULE_METRICS


def env():
    out = {}
    for line in open(os.path.expanduser("~/.config/caryaar/frappe.env")):
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1); out[k] = v.strip().strip('"').strip("'")
    return out


def erp(e, method, path, **kw):
    import requests

    h = {"Authorization": f"token {e['FRAPPE_API_KEY']}:{e['FRAPPE_API_SECRET']}", "User-Agent": "Mozilla/5.0"}
    r = requests.request(method, f"{e['FRAPPE_URL']}{path}", headers=h, timeout=60, **kw); r.raise_for_status()
    return r.json()


VM_SCRIPT = r'''
import json, subprocess, urllib.error, urllib.request
T = subprocess.check_output(["sudo", "cat", "/opt/plane-chat-app/plane_token"]).decode().strip()
BASE = "http://127.0.0.1:8080/api/v1/workspaces/caryaar/projects/"
def req(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method,
                               headers={"X-Api-Key": T, "Host": "pitstop.mycaryaar.com", "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(r, timeout=60) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise SystemExit(f"Plane {method} {path} -> {e.code}: {e.read().decode()[:400]} (body {json.dumps(body)[:200]})")
def key(name):
    return " ".join(name.split()).lower()
def modules(pid):
    found, cursor = {}, None
    while True:
        page = req("GET", f"{pid}/modules/?per_page=100" + (f"&cursor={cursor}" if cursor else "")) or {}
        for m in page.get("results", []):
            found[key(m["name"])] = m["id"]
        if not page.get("next_page_results"):
            return found
        cursor = page.get("next_cursor")
WANTED = __WANTED__
out, cache = {}, {}
for w in WANTED:
    pid = w["project"]
    if pid not in cache:
        cache[pid] = modules(pid)
    mid = cache[pid].get(key(w["name"]))
    if not mid and not w.get("dry_run"):
        try:
            mid = req("POST", f"{pid}/modules/", {"name": w["name"]})["id"]
        except SystemExit as e:
            if "MODULE_NAME_ALREADY_EXISTS" in str(e):
                cache[pid] = modules(pid)
                mid = cache[pid].get(key(w["name"]))
            elif "Modules are not enabled" in str(e):
                # HR, WR and PARTNER were created with the modules view off; a goal module needs it on
                req("PATCH", f"{pid}/", {"module_view": True})
                mid = req("POST", f"{pid}/modules/", {"name": w["name"]})["id"]
            else:
                raise
        cache[pid][key(w["name"])] = mid
    out[w["goal"]] = mid
print(json.dumps(out))
'''


def vm_script(wanted: list[dict]) -> str:
    """The script that runs on the VM, with the payload inline as a Python literal: the whole
    of stdin is the script, so nothing is read from stdin a second time."""
    return VM_SCRIPT.replace("__WANTED__", repr(wanted))


def plane_create_modules(wanted: list[dict]) -> dict:
    """Runs on the VM: for each {project, name} returns the module id (existing or created)."""
    cmd = ["gcloud", "compute", "ssh", "caryaar-plane", "--zone", "asia-south1-a", "--project", "caryaar-api-dev",
           "--tunnel-through-iap", "--quiet", "--command", "python3 -"]
    proc = subprocess.run(cmd, input=vm_script(wanted), capture_output=True, text=True, timeout=300)
    lines = [l for l in proc.stdout.splitlines() if l.startswith("{")]
    if proc.returncode != 0 or not lines:
        raise SystemExit(f"Plane call failed: {proc.stderr[-400:]}")
    return json.loads(lines[-1])


def main(argv) -> int:
    dry = "--dry-run" in argv
    e = env()
    meters = erp(e, "GET", "/api/resource/Goal Meter", params={"filters": json.dumps([["active", "=", 1]]),
                                                                  "fields": json.dumps(["goal", "employee", "method", "metric"]),
                                                                  "limit_page_length": 200})["data"]
    wanted = []
    for m in meters:
        if not needs_module(m.get("method"), m.get("metric")):
            continue
        g = erp(e, "GET", f"/api/resource/Goal/{m['goal']}")["data"]
        if g.get("cy_plane_module"):
            continue
        proj = "DEV" if g["kra"] in TECH_KRAS else BY_EMPLOYEE.get(g["employee"], "CORP")
        wanted.append({"goal": g["name"], "project": PROJECTS[proj], "name": module_name(g["goal_name"]), "dry_run": dry})
    print(f"{len(wanted)} goals need a module" + (" (dry run)" if dry else ""))
    for w in wanted:
        print("  ", w["goal"], "->", [k for k, v in PROJECTS.items() if v == w["project"]][0], "|", w["name"])
    if not wanted:
        return 0
    ids = plane_create_modules(wanted)
    for w in wanted:
        mid = ids.get(w["goal"])
        if mid and not dry:
            erp(e, "POST", "/api/method/frappe.client.set_value", json={"doctype": "Goal", "name": w["goal"], "fieldname": "cy_plane_module", "value": mid})
        print("  ", w["goal"], "module", mid or "(would create)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
