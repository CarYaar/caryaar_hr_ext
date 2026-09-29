import json
from pathlib import Path

from scripts.goal_onepagers import build

FIX = json.loads((Path(__file__).parent / "fixture_anagha.json").read_text())


def test_page_carries_every_number_and_the_acknowledgement_link():
    html = build.render(FIX).replace("&#39;", "'")          # Jinja escapes the apostrophe in D'Souza
    for text in ("Anagha Khedekar", "Executive - Customer Experience", "01-Oct-2026", "31-Mar-2027", "15-Jan-2027",
                 "Lead to booking conversion", "5%", "CY Admin", "30%", "40%", "16 of 953 leads (1.7%)",
                 "Rating from half of delivered jobs, from Jan-2027",
                 "not yet acknowledged", "erp.caryaar.com/app/goal-one-on-one/1ON1-HR-EMP-00012-2026-10-02",
                 "Joel Daniel D'Souza", "Process adherence"):
        assert text in html, text
    assert "—" not in html and "prefers-reduced-motion" in html and "gsap" in html
    assert "<title>Anagha Khedekar" in html


def test_page_states():
    acked = dict(FIX, one_on_one=dict(FIX["one_on_one"], employee_acknowledged=1, acknowledged_on="2026-10-03 11:05:00"))
    assert "acknowledged on 03-Oct-2026" in build.render(acked)
    empty = dict(FIX, goals=[])
    html = build.render(empty)
    assert "no goals" in html.lower() and "Anagha Khedekar" in html


def test_character_scale_lives_on_a_group_the_animation_never_touches():
    """29-Sep-2026: GSAP drops an SVG group's attribute transform when it takes the group over, and the
    idle hop ends on scaleX/scaleY 1. With the static scale on the idled group the hero grew to 1007px
    at a 1000px viewport (the road car by 15x). The scale group must wrap a separate rig that idles."""
    html = build.render(json.loads((Path(build.HERE) / "fixture_anagha.json").read_text()))
    for transform in ("translate(300,68) scale(0.27)", "scale(0.064)", "translate(26,44) scale(0.072)"):
        assert f'<g transform="{transform}"><g class="rig">' in html, transform
    assert 'outer + " .rig"' in html                                   # the idle helper targets the rig
    assert '"#hero-yaar .rig"' in html                                  # and so does the hero entrance
    assert '"#hero-yaar > g"' not in html and 'outer + " > g"' not in html


def test_two_goals_under_one_kra_show_the_shared_weight_once():
    """Anagha's real six goals: two sit under 'Lead to booking conversion' (30%), so each card says 15% and
    names the split; the KRA sign still says 30%."""
    html = build.render(json.loads((Path(build.HERE) / "fixture_anagha.json").read_text()))
    assert html.count("15% of your goals (30% KRA across 2 goals)") == 2
    assert "Turn my bookings into jobs" in html and "· 30% of your goals" not in html


def test_child_table_lists_name_their_parent_doctype():
    """Frappe strips every field but name from a child-table list that does not name the parent doctype
    (Appraisee answered [{'name': '2nel5a929o'}] on 29-Sep-2026 and the payload crashed on the template)."""
    erp = build.Erp.__new__(build.Erp)
    calls = []
    erp._req = lambda method, path, body=None: (calls.append(path), {"data": []})[1]
    erp.get_list("Appraisee", ["appraisal_template"], [["parent", "=", "C"]], parent="Appraisal Cycle")
    assert "parent=Appraisal+Cycle" in calls[0]
    src = Path(build.__file__).read_text()
    assert 'parent="Appraisal Cycle"' in src and 'parent="Appraisal Template"' in src
