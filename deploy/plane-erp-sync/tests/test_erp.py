import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from plane_erp_sync import erp


def _server(responses):
    """Serve the given (status, body) pairs in order; record request headers and bodies."""
    seen = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            seen.append({"ua": self.headers.get("User-Agent"), "auth": self.headers.get("Authorization"),
                         "body": json.loads(self.rfile.read(n) or b"{}")})
            status, body = responses[min(len(seen), len(responses)) - 1]
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(body).encode())

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, seen


def test_success_returns_message_and_sends_browser_ua_and_token(monkeypatch):
    monkeypatch.setattr(erp.time, "sleep", lambda s: None)
    srv, seen = _server([(200, {"message": {"accepted": 3}})])
    out = erp.call(f"http://127.0.0.1:{srv.server_port}", "k:s", "a.b.c", {"rows": []})
    assert out == {"accepted": 3}
    assert seen[0]["ua"] == "Mozilla/5.0" and seen[0]["auth"] == "token k:s"
    srv.shutdown()


def test_client_error_is_not_retried(monkeypatch):
    monkeypatch.setattr(erp.time, "sleep", lambda s: None)
    srv, seen = _server([(417, {"exception": "bad source"})])
    with pytest.raises(erp.ErpError, match="417"):
        erp.call(f"http://127.0.0.1:{srv.server_port}", "k:s", "a.b.c", {})
    assert len(seen) == 1
    srv.shutdown()


def test_server_error_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr(erp.time, "sleep", lambda s: None)
    srv, seen = _server([(502, {}), (200, {"message": {"accepted": 1}})])
    assert erp.call(f"http://127.0.0.1:{srv.server_port}", "k:s", "a.b.c", {}) == {"accepted": 1}
    assert len(seen) == 2
    srv.shutdown()
