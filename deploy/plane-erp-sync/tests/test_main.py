from contextlib import contextmanager
from datetime import datetime, timedelta

from plane_erp_sync import core

from plane_erp_sync import main


def test_real_stamp_is_sent_only_after_every_row_chunk(monkeypatch, tmp_path):
    key = tmp_path / "erp_key"
    key.write_text("k:s")
    monkeypatch.setenv("ERP_KEY_FILE", str(key))
    rows = [{"email": f"u{i}@caryaar.com", "date": "2026-10-01",
             "metrics": {"activity_count": 0, "completed_count": 0}} for i in range(4500)]

    @contextmanager
    def fake_conn():
        yield object()

    monkeypatch.setattr(main, "connect", fake_conn)
    monkeypatch.setattr(main, "check_schema", lambda conn: None)
    monkeypatch.setattr(main, "collect", lambda conn, slug, now, days_back: (rows, [{"module_id": "m"}]))
    calls = []
    monkeypatch.setattr(main.erp, "call", lambda base, token, method, body: calls.append((method, body)) or {})

    out = main.run_once(dry_run=False)

    activity = [b for m, b in calls if m == main.ACTIVITY_METHOD]
    assert [len(b["rows"]) for b in activity] == [2000, 2000, 500, 0]
    assert all(b["synced_through"].startswith("1970-") for b in activity[:3])
    assert not activity[3]["synced_through"].startswith("1970-")
    assert calls[-1][0] == main.MODULES_METHOD
    assert out["rows"] == 4500


def test_a_failed_chunk_never_sends_the_real_stamp(monkeypatch, tmp_path):
    key = tmp_path / "erp_key"
    key.write_text("k:s")
    monkeypatch.setenv("ERP_KEY_FILE", str(key))

    @contextmanager
    def fake_conn():
        yield object()

    monkeypatch.setattr(main, "connect", fake_conn)
    monkeypatch.setattr(main, "check_schema", lambda conn: None)
    monkeypatch.setattr(main, "collect", lambda conn, slug, now, days_back: ([{"email": "a@caryaar.com", "date": "2026-10-01",
                                                                   "metrics": {}}], []))
    stamps = []

    def boom(base, token, method, body):
        if method == main.STATE_METHOD:
            return {}
        stamps.append(body.get("synced_through"))
        raise main.erp.ErpError("ERP down")

    monkeypatch.setattr(main.erp, "call", boom)
    try:
        main.run_once(dry_run=False)
    except main.erp.ErpError:
        pass
    assert all(s.startswith("1970-") for s in stamps)


def test_run_backfills_from_the_erp_stamp_and_sends_covers_from(monkeypatch, tmp_path):
    key = tmp_path / "erp_key"
    key.write_text("k:s")
    monkeypatch.setenv("ERP_KEY_FILE", str(key))
    seen = {}

    @contextmanager
    def fake_conn():
        yield object()

    def fake_collect(conn, slug, now, days_back):
        seen["days_back"] = days_back
        return [], []

    monkeypatch.setattr(main, "connect", fake_conn)
    monkeypatch.setattr(main, "check_schema", lambda conn: None)
    monkeypatch.setattr(main, "collect", fake_collect)
    stamp_day = (datetime.now(core.IST) - timedelta(days=3)).date()
    calls = []

    def fake_call(base, token, method, body):
        calls.append((method, body))
        return {"Plane": f"{stamp_day.isoformat()}T10:00:00"} if method == main.STATE_METHOD else {}

    monkeypatch.setattr(main.erp, "call", fake_call)
    main.run_once(dry_run=False)
    assert seen["days_back"] == 3
    activity = [b for m, b in calls if m == main.ACTIVITY_METHOD]
    assert activity and all(b["covers_from"] == stamp_day.isoformat() for b in activity)
