import json
from pathlib import Path

from scripts.goal_onepagers import build

FIX = json.loads((Path(__file__).parent / "fixture_anagha.json").read_text())


def test_page_carries_every_number_and_the_acknowledgement_link():
    html = build.render(FIX).replace("&#39;", "'")          # Jinja escapes the apostrophe in D'Souza
    for text in ("Anagha Khedekar", "Executive - Customer Experience", "01-Oct-2026", "31-Mar-2027", "15-Jan-2027",
                 "Lead to booking conversion", "5%", "CY Admin", "30%", "40%", "1.7% of assigned leads",
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
