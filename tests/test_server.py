"""End-to-end smoke test of the HTTP server, fully offline.

Starts the real server on an ephemeral port against a synthetic projects dir,
monkeypatches the network call to the usage API, and checks the page + the JSON
snapshot. This is the test that proves the whole stack wires together.
"""

import json
import threading
import urllib.request
from datetime import timezone

from portmint_pulse import usage
from portmint_pulse.server import build_server


def test_endpoints_serve(tmp_path, monkeypatch):
    # Don't hit the network in tests — pretend the usage API returned no windows.
    monkeypatch.setattr(usage, "fetch_limits", lambda: {"windows": []})
    (tmp_path / "projects").mkdir()

    # Port 0 → the OS hands us a free ephemeral port (no conflicts in CI).
    httpd = build_server("127.0.0.1", 0, tz=timezone.utc, projects_dir=str(tmp_path / "projects"))
    port = httpd.server_address[1]
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        base = f"http://127.0.0.1:{port}"
        html = urllib.request.urlopen(base + "/", timeout=5).read()
        assert b"Portmint Pulse" in html

        favicon = urllib.request.urlopen(base + "/favicon.svg", timeout=5)
        assert favicon.headers.get("Content-Type") == "image/svg+xml"

        stats = json.loads(urllib.request.urlopen(base + "/api/stats", timeout=5).read())
        for key in ("today", "week", "lifetime", "range", "period", "series", "models", "projects", "limits", "generated_at", "timezone"):
            assert key in stats
        assert stats["range"] == "month"  # default
        assert len(stats["series"]) == 30  # 30 daily buckets

        # The ?range query param scopes the trend.
        wk = json.loads(urllib.request.urlopen(base + "/api/stats?range=week", timeout=5).read())
        assert wk["range"] == "week"
        assert len(wk["series"]) == 7
        day = json.loads(urllib.request.urlopen(base + "/api/stats?range=day", timeout=5).read())
        assert day["range"] == "day"
        assert len(day["series"]) == 24  # hourly
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
