from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request

log = logging.getLogger("plane_erp_sync.erp")


class ErpError(RuntimeError):
    pass


def call(base_url: str, token: str, method: str, body: dict, attempts: int = 3) -> dict:
    url = f"{base_url.rstrip('/')}/api/method/{method}"
    data = json.dumps(body).encode()
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(url, data=data, method="POST", headers={
            "Authorization": f"token {token}", "Content-Type": "application/json",
            "Accept": "application/json", "User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r).get("message", {})
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if 400 <= e.code < 500:
                raise ErpError(f"{method} rejected ({e.code}): {detail}") from e
            log.warning("%s attempt %s got %s: %s", method, attempt, e.code, detail)
        except (urllib.error.URLError, TimeoutError) as e:
            log.warning("%s attempt %s network error: %s", method, attempt, e)
        time.sleep(2 ** attempt)
    raise ErpError(f"{method} failed after {attempts} attempts")
