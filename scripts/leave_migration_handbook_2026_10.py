"""Move every active employee onto the handbook leave policy (HR-LPOL-2026-00002).

Casual 10, Sick 5, Earned 12 a financial year (Apr to Mar), credited monthly from the
date of joining (Employee Handbook 9.5.3 and 10). Renames Privilege Leave to Earned Leave.

HRMS refuses to cancel an allocation that approved leave was taken against, and it
refuses overlapping allocations. So this year's approved leave applications are set
aside (cancelled), the hand-entered allocations and old calendar-year assignments are
cancelled, the handbook policy is assigned (which credits each person's months so far),
and every set-aside application is re-submitted as an amended copy with the same dates.
Leave emails are switched off for the run and restored after.

Usage inside the backend container (cwd sites):
  python leave_migration_handbook_2026_10.py report  [AS_OF]    read-only balances
  python leave_migration_handbook_2026_10.py apply   [AS_OF]    make the change (AS_OF defaults to today)
  python leave_migration_handbook_2026_10.py yearsim            staging only: credit Oct to Mar, show year end
"""
import json
import os
import sys
from datetime import date, datetime

os.chdir("/home/frappe/frappe-bench/sites")
import frappe  # noqa: E402
from frappe.utils import flt  # noqa: E402

MODE = sys.argv[1] if len(sys.argv) > 1 else "report"
AS_OF = date.fromisoformat(sys.argv[2]) if len(sys.argv) > 2 else date.today()
POLICY, OLD_POLICY = "HR-LPOL-2026-00002", "HR-LPOL-2026-00001"
FY_FROM, FY_TO = date(2026, 4, 1), date(2027, 3, 31)
OLD_PL, NEW_PL = "Privilege Leave", "Earned Leave"

frappe.init(site="erp.caryaar.com", sites_path=".")
frappe.connect()
frappe.set_user("Administrator")
from hrms.hr.doctype.leave_application.leave_application import get_leave_balance_on  # noqa: E402


def types():
    return ["Casual Leave", "Sick Leave", NEW_PL if frappe.db.exists("Leave Type", NEW_PL) else OLD_PL]


emps = frappe.get_all("Employee", filters={"status": "Active"},
                      fields=["name", "employee_name", "date_of_joining"], order_by="date_of_joining")
active = [e.name for e in emps]


def table(title, on):
    T = types()
    print(f"\n== {title} (balance on {on})")
    print(f"{'person':10} {'joined':10} | " + " | ".join(f"{t.split()[0][:6]:>6} credited/used/bal" for t in T))
    for e in emps:
        cells = []
        for t in T:
            alloc = sum(a.total_leaves_allocated for a in frappe.get_all(
                "Leave Allocation", filters={"employee": e.name, "leave_type": t, "docstatus": 1,
                                             "from_date": ("<=", FY_TO), "to_date": (">=", FY_FROM)},
                fields=["total_leaves_allocated"]))
            used = sum(a.total_leave_days for a in frappe.get_all(
                "Leave Application", filters={"employee": e.name, "leave_type": t, "docstatus": 1,
                                              "status": "Approved", "from_date": (">=", FY_FROM)},
                fields=["total_leave_days"]))
            bal = get_leave_balance_on(e.name, t, on) if alloc else 0
            cells.append(f"{alloc:5.1f}/{used:4.1f}/{bal:5.1f}")
        print(f"{e.employee_name.split()[0]:10} {str(e.date_of_joining):10} | " + " | ".join(cells))


if MODE == "report":
    table("current", AS_OF)
    frappe.destroy()
    sys.exit(0)

if MODE == "yearsim":  # staging only: run the real monthly job at each month end, Oct to Mar
    # this credits six months of leave early; refuse anywhere the scheduler and emails are live (prod)
    if not (frappe.conf.get("pause_scheduler") and frappe.conf.get("mute_emails")):
        frappe.destroy()
        sys.exit("yearsim runs only on staging: this site's scheduler is not paused or its emails are not muted")
    from hrms.hr.utils import allocate_earned_leaves
    for d in (date(2026, 10, 31), date(2026, 11, 30), date(2026, 12, 31), date(2027, 1, 31),
              date(2027, 2, 28), date(2027, 3, 31)):
        frappe.flags.current_date = d
        allocate_earned_leaves()
        frappe.db.commit()
    errs = frappe.get_all("Error Log", filters={"creation": (">=", frappe.utils.add_to_date(None, minutes=-10))},
                          fields=["method"])
    print("errors logged during the simulated year:", [e.method[:80] for e in errs])
    table("year end, after every monthly credit (simulated)", date(2027, 3, 31))
    # independent check: handbook pro-rata from the date of joining (part of the joining month, then whole months)
    import calendar
    annual = {d.leave_type: d.annual_allocation for d in frappe.get_doc("Leave Policy", POLICY).leave_policy_details}
    doj = {e.name: e.date_of_joining for e in emps}

    def expected(t, joined):
        if joined <= FY_FROM:
            return annual[t]
        days = calendar.monthrange(joined.year, joined.month)[1]
        months = (days - joined.day + 1) / days + (FY_TO.year - joined.year) * 12 + FY_TO.month - joined.month
        return annual[t] / 12 * months

    allocs = frappe.get_all("Leave Allocation", filters={"docstatus": 1, "leave_policy": POLICY},
                            fields=["employee", "employee_name", "leave_type", "total_leaves_allocated"])
    off = [(a.employee_name, a.leave_type, a.total_leaves_allocated, round(expected(a.leave_type, doj[a.employee]), 3))
           for a in allocs if abs(a.total_leaves_allocated - round(expected(a.leave_type, doj[a.employee]), 3)) > 0.0015]
    print(f"year-end check: {len(allocs) - len(off)} of {len(allocs)} allocations match the handbook pro-rata to 3 decimals")
    for o in off:
        print("  MISMATCH:", o)
    frappe.destroy()
    sys.exit(0)

frappe.flags.current_date = AS_OF
print("run as of", AS_OF)

# 0. snapshot everything we are about to replace
fy_apps = frappe.get_all("Leave Application", filters={"docstatus": 1, "employee": ("in", active),
                                                        "from_date": (">=", FY_FROM)},
                         fields=["name", "employee", "employee_name", "leave_type", "from_date", "to_date",
                                 "total_leave_days", "status"], order_by="from_date")
snap = {"allocations": frappe.get_all("Leave Allocation", filters={"docstatus": 1, "to_date": (">=", FY_FROM)}, fields=["*"]),
        "assignments": frappe.get_all("Leave Policy Assignment", filters={"docstatus": 1}, fields=["*"]),
        "applications": fy_apps}
# timestamped so a second run can never overwrite the snapshot of the original state
path = f"/home/frappe/frappe-bench/sites/erp.caryaar.com/private/backups/leave_snapshot_{datetime.now():%Y%m%d_%H%M%S}.json"
open(path, "w").write(json.dumps(snap, default=str))
print("snapshot:", path, len(snap["allocations"]), "allocations,", len(snap["assignments"]), "assignments,",
      len(fy_apps), "applications")

# 1. rename Privilege Leave to Earned Leave; handbook 10.2 carry forward limit 45
if frappe.db.exists("Leave Type", OLD_PL) and not frappe.db.exists("Leave Type", NEW_PL):
    frappe.rename_doc("Leave Type", OLD_PL, NEW_PL, force=True)
    print("renamed", OLD_PL, "->", NEW_PL)
frappe.db.set_value("Leave Type", NEW_PL, "maximum_carry_forwarded_leaves", 45)
T = types()
# exact monthly credit (0.83 / 0.42 / 1.0): rounding each month to 0.5 over-credits joiners
# and makes full-year allocations overflow the annual cap in the last months
for t in T:
    frappe.db.set_value("Leave Type", t, "rounding", "")
frappe.db.commit()

# 2. no leave emails during the swap
notify = frappe.db.get_single_value("HR Settings", "send_leave_notification")
frappe.db.set_single_value("HR Settings", "send_leave_notification", 0)
frappe.db.commit()
try:
    # 3. set aside this year's approved applications (their On Leave attendance is cancelled with them)
    for a in fy_apps:
        frappe.get_doc("Leave Application", a.name).cancel()
    frappe.db.commit()
    print("set aside", len(fy_apps), "applications")
    # 4. cancel old assignments and this year's hand-entered allocations
    for n in frappe.get_all("Leave Policy Assignment", filters={"docstatus": 1, "employee": ("in", active)}, pluck="name"):
        frappe.get_doc("Leave Policy Assignment", n).cancel()
    for n in frappe.get_all("Leave Allocation", filters={"docstatus": 1, "employee": ("in", active), "leave_type": ("in", T),
                                                          "from_date": ("<=", FY_TO), "to_date": (">=", FY_FROM)}, pluck="name"):
        frappe.get_doc("Leave Allocation", n).cancel()
    frappe.db.commit()
    print("cancelled old assignments and allocations")
    # 5. handbook policy for everyone; submitting credits each person's months so far
    for e in emps:
        lpa = frappe.get_doc({"doctype": "Leave Policy Assignment", "employee": e.name, "leave_policy": POLICY,
                              "effective_from": FY_FROM, "effective_to": FY_TO, "carry_forward": 0})
        lpa.insert()
        lpa.submit()
        frappe.db.commit()
    print("assigned", POLICY, "to", len(emps), "employees")
    # 5b. the monthly job credits each scheduled month rounded to the allocation's precision
    # (3 decimals): 5/12 goes in as 0.417, so a full year of Sick Leave would reach 5.002 and
    # HRMS refuses the whole last month; 10/12 goes in as 0.833, so Casual Leave ends at 9.998
    # and the tenth day cannot be taken. Set the last pending month so that, after the job's
    # rounding, each allocation ends exactly on its intended total (never above the policy figure).
    # The intended total is what the ledger already credited plus the exact months still to come:
    # for someone who joined mid-year the schedule's first row is not their whole opening credit.
    annual = {d.leave_type: d.annual_allocation for d in frappe.get_doc("Leave Policy", POLICY).leave_policy_details}
    lpas = frappe.get_all("Leave Policy Assignment", filters={"docstatus": 1, "leave_policy": POLICY,
                                                              "employee": ("in", active)}, pluck="name")
    trimmed = 0
    for al in frappe.get_all("Leave Allocation", filters={"docstatus": 1, "leave_policy_assignment": ("in", lpas)},
                             pluck="name"):
        doc = frappe.get_doc("Leave Allocation", al)
        p = doc.precision("total_leaves_allocated")
        rows = frappe.get_all("Earned Leave Schedule", filters={"parent": al},
                              fields=["name", "number_of_leaves", "is_allocated", "attempted"], order_by="allocation_date")
        pending = [r for r in rows if not r.is_allocated and not r.attempted]
        if not pending:
            continue
        credited = flt(doc.get_existing_leave_count(), p)
        target = min(flt(credited + sum(r.number_of_leaves for r in pending), p), flt(annual.get(doc.leave_type, 0), p))
        before_last = flt(credited + sum(flt(r.number_of_leaves, p) for r in pending[:-1]), p)
        last = flt(target - before_last, p)
        if last <= 0:
            print("  CHECK BY HAND: last month would be", last, "on", al, doc.employee, doc.leave_type)
            continue
        if last != flt(pending[-1].number_of_leaves, p):
            frappe.db.set_value("Earned Leave Schedule", pending[-1].name, "number_of_leaves", last)
            trimmed += 1
    frappe.db.commit()
    print("set the last scheduled month on", trimmed, "allocations so each ends on its exact total")
    # 6. put every set-aside application back as an amended copy
    failed = []
    for a in fy_apps:
        old = frappe.get_doc("Leave Application", a.name)
        new = frappe.copy_doc(old)
        new.amended_from = old.name
        new.status = "Approved"
        try:
            new.insert()
            new.submit()
            frappe.db.commit()
        except Exception as ex:
            frappe.db.rollback()
            # an attachment that cannot be copied must not keep approved leave off the books:
            # re-submit without the amend link and say where it came from
            try:
                new = frappe.copy_doc(old)
                new.amended_from = None
                new.status = "Approved"
                new.description = (old.description or "") + f"\nRe-submitted from {old.name} during the 01-Oct-2026 move to the handbook leave policy."
                new.insert()
                new.submit()
                frappe.db.commit()
                print("  re-submitted without amend link:", old.name, "->", new.name, "|", str(ex)[:80])
            except Exception as ex2:  # keep going; report every one that did not go back
                frappe.db.rollback()
                failed.append((a.name, a.employee_name, a.leave_type, str(ex2)[:160]))
    print("re-submitted", len(fy_apps) - len(failed), "of", len(fy_apps), "applications")
    for f in failed:
        print("  NOT RE-SUBMITTED:", f)
finally:
    frappe.db.set_single_value("HR Settings", "send_leave_notification", notify)
    frappe.db.commit()
    print("leave emails setting restored to", notify)

# 7. the old calendar-year policy is no longer used
old_policy = frappe.get_doc("Leave Policy", OLD_POLICY)
if old_policy.docstatus == 1 and not frappe.db.exists("Leave Policy Assignment", {"leave_policy": OLD_POLICY, "docstatus": 1}):
    old_policy.cancel()
    frappe.db.commit()
    print("cancelled old policy", OLD_POLICY)

table("after the change", AS_OF)
frappe.destroy()
