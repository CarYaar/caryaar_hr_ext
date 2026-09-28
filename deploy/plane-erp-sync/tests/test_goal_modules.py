"""The one-off module creator (ops/goal_modules.py): which meters need a module, and how the
payload reaches the VM (inline in the script, never through a second stdin read)."""
import importlib.util
import pathlib

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "ops" / "goal_modules.py"
_spec = importlib.util.spec_from_file_location("goal_modules", SCRIPT)
gm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(gm)


def test_meters_that_read_a_module_need_one():
    assert gm.needs_module("Plane module", None)
    assert gm.needs_module("Ratio to target", "support_on_time_pct")
    assert not gm.needs_module("Ratio to target", "conversion_pct")
    assert not gm.needs_module("Manual", None)


def test_vm_script_carries_the_payload_inline_and_compiles():
    wanted = [{"goal": "HR-GOAL-1", "project": "p", "name": "Sprint", "dry_run": True}]
    script = gm.vm_script(wanted)
    assert "stdin" not in script and repr(wanted) in script
    compile(script, "vm-script", "exec")


def test_module_names_are_cut_on_a_word_and_never_end_in_a_space():
    long = "Lay the foundation for the next products (Roadside Assistance, WMS as SaaS) and keep the platform stable"
    name = gm.module_name(long)
    assert len(name) <= 80 and not name.endswith(" ") and name.endswith("SaaS) and")
    assert gm.module_name("  Short   name ") == "Short name"


def test_vm_script_treats_an_existing_module_name_as_the_module():
    script = gm.vm_script([{"goal": "G", "project": "p", "name": "Sprint", "dry_run": False}])
    assert "MODULE_NAME_ALREADY_EXISTS" in script and "next_cursor" in script
    assert '"module_view": True' in script          # a project with modules switched off gets them on


def test_two_people_with_the_same_goal_wording_get_their_own_module():
    goals = [{"goal": "A", "project": "hr", "name": "Run this cycle to its dates", "employee": "E1", "linked": True},
             {"goal": "B", "project": "hr", "name": "Run this cycle to its dates", "employee": "E2", "linked": False},
             {"goal": "C", "project": "dev", "name": "Run this cycle to its dates", "employee": "E3", "linked": False}]
    out = {g["goal"]: g["name"] for g in gm.dedupe_names(goals, lambda emp: {"E1": "Reema", "E2": "Melita"}[emp])}
    assert out["A"] == "Run this cycle to its dates"            # already linked: keeps its module
    assert out["B"] == "Run this cycle to its dates (Melita)"   # the collision gets the person's name
    assert out["C"] == "Run this cycle to its dates"            # another project: no collision
