"""deploy-on-vm.sh grants the read-only role SELECT on exactly the tables the queries read:
a table the SQL needs but the GRANT misses fails every run on the VM with permission denied."""
import pathlib
import re

from plane_erp_sync import sql

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "deploy-on-vm.sh"


def test_grant_covers_every_table_the_queries_read():
    text = SCRIPT.read_text()
    m = re.search(r"GRANT SELECT ON (.*?) TO plane_erp_sync;", text, re.S)
    assert m, "GRANT SELECT line missing"
    granted = {t.strip() for t in m.group(1).replace("\n", " ").split(",") if t.strip()}
    assert set(sql.REQUIRED_COLUMNS) <= granted, sorted(set(sql.REQUIRED_COLUMNS) - granted)
