"""The scheduled review pack under the Frappe stand-in: who it reads, who it reaches,
and what it counts. The Frappe integration tests cover the same paths on staging."""
from datetime import date

from caryaar_hr_ext.performance.tests import _frappe_stub as stub

CYCLE = "Cycle Oct-2026"
ANAGHA, JOEL = "HR-EMP-00010", "HR-EMP-00003"


def _cycle_with_person(fake):
    stub.seed(fake, "Appraisal Cycle", name=CYCLE, status="In Progress", start_date="2026-10-01")
    stub.seed(fake, "Appraisee", name="row1", parent=CYCLE, parenttype="Appraisal Cycle", employee=ANAGHA)
    stub.seed(fake, "Employee", name=ANAGHA, employee_name="Anagha", status="Active", reports_to=JOEL,
              user_id="anagha@caryaar.test")
    stub.seed(fake, "Employee", name=JOEL, employee_name="Joel", status="Active", user_id="joel@caryaar.test")


def test_scheduled_packs_read_the_cycle_appraisees_child_table(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 15))
    from caryaar_hr_ext.performance import review_pack

    _cycle_with_person(fake)
    fake.db.singles[("Performance Sync Settings", "review_pack_recipients")] = "sahaib@caryaar.test"
    out = review_pack.send_scheduled_packs()
    assert out["sent"] == 1
    assert fake.mails[0]["recipients"] == ["joel@caryaar.test", "sahaib@caryaar.test"]


def test_pack_with_no_recipients_is_skipped_and_logged(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 15))
    from caryaar_hr_ext.performance import review_pack

    _cycle_with_person(fake)
    fake.db.store["Employee"][ANAGHA]["reports_to"] = None
    out = review_pack.send_scheduled_packs()
    assert out["sent"] == 0 and not fake.mails
    assert fake.errors and "no recipients" in fake.errors[0][0].lower()


def test_adherence_counts_only_judged_days(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 20))
    from caryaar_hr_ext.performance import review_pack

    _cycle_with_person(fake)
    stub.seed(fake, "Work Adherence Day", name="d1", employee=ANAGHA, is_working_day=1,
              adherence_date="2026-10-05", adherence_pct=100, checks_applicable=2)
    stub.seed(fake, "Work Adherence Day", name="d2", employee=ANAGHA, is_working_day=1,
              adherence_date="2026-10-20", adherence_pct=0, checks_applicable=0)   # today: not judged yet
    pack = review_pack.build_pack(ANAGHA, CYCLE, date(2026, 10, 20))
    assert pack["adherence"] == {"days": 1, "pct": 100.0}


def test_the_emailed_pack_carries_the_erp_links(monkeypatch):
    fake = stub.install(monkeypatch, date(2026, 10, 15))
    from caryaar_hr_ext.performance import review_pack

    _cycle_with_person(fake)
    fake.db.singles[("Performance Sync Settings", "review_pack_recipients")] = "sahaib@caryaar.test"
    seen = {}
    monkeypatch.setattr(review_pack.frappe, "render_template", lambda tpl, ctx: seen.update(ctx) or "<html/>")
    monkeypatch.setattr(review_pack.frappe.utils, "get_url", lambda *a, **k: "https://erp.caryaar.com", raising=False)
    review_pack.send_pack(ANAGHA, CYCLE, date(2026, 10, 15))
    assert seen["links"]["goals"].startswith("https://erp.caryaar.com/app/goal?employee=" + ANAGHA)
    assert "rows" in seen
