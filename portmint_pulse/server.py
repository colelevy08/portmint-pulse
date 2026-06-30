"""The tiny HTTP server that powers the dashboard.

Standard-library only (``http.server``). It does three things:
  - serves the branded dashboard page at ``/``
  - serves a JSON snapshot of all stats at ``/api/stats``
  - serves the Portmint porthole favicon at ``/favicon.svg``

The heavy lifting (parsing transcripts, pricing, fetching live limits) lives in
the sibling modules; this file just wires them to URLs. The dashboard HTML is
loaded as packaged data via importlib.resources, so it's found whether you run
from a clone or from a ``pip``/``pipx`` install.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, tzinfo
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from . import usage
from .transcripts import PROJECTS_DIR, TranscriptStore

# The favicon is the Portmint "badge" — the porthole mark on the canonical Ink
# tile (#070b14), straight from the brand standards.
_FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Portmint">
  <defs>
    <linearGradient id="pm" x1="14" y1="12" x2="50" y2="52" gradientUnits="userSpaceOnUse">
      <stop offset="0" stop-color="#5cf0c4"/><stop offset="1" stop-color="#2bd3a6"/>
    </linearGradient>
  </defs>
  <rect width="64" height="64" rx="14" fill="#070b14"/>
  <circle cx="32" cy="32" r="21" fill="#07182c"/>
  <circle cx="32" cy="32" r="21" fill="none" stroke="url(#pm)" stroke-width="5"/>
  <g fill="#34e0b3">
    <circle cx="46" cy="32" r="2"/><circle cx="41.9" cy="41.9" r="2"/><circle cx="32" cy="46" r="2"/>
    <circle cx="22.1" cy="41.9" r="2"/><circle cx="18" cy="32" r="2"/><circle cx="22.1" cy="22.1" r="2"/>
    <circle cx="32" cy="18" r="2"/><circle cx="41.9" cy="22.1" r="2"/>
  </g>
</svg>"""


def _load_dashboard_html() -> bytes:
    """Read the packaged dashboard page (works installed or from a checkout)."""
    return (files("portmint_pulse") / "web" / "dashboard.html").read_bytes()


class _Handler(BaseHTTPRequestHandler):
    # All four set by the factory below.
    store: TranscriptStore = None  # type: ignore[assignment]
    lock: threading.Lock = None  # type: ignore[assignment]
    tz: tzinfo = None  # type: ignore[assignment]
    dashboard: bytes = b""

    # Quieter logging — drop the noisy default per-request line.
    def log_message(self, fmt: str, *args) -> None:
        return

    def _send(self, code: int, body: bytes, content_type: str) -> None:
        # A browser closing a tab mid-response is normal and would otherwise dump a
        # multi-line traceback to the console; swallow just those disconnects.
        try:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def do_GET(self) -> None:  # noqa: N802 (http.server naming)
        path = self.path.split("?", 1)[0]
        if path == "/":
            self._send(200, self.dashboard, "text/html; charset=utf-8")
        elif path == "/api/stats":
            self._serve_stats()
        elif path == "/favicon.svg":
            self._send(200, _FAVICON_SVG.encode("utf-8"), "image/svg+xml")
        else:
            self._send(404, b"Not found", "text/plain; charset=utf-8")

    def _serve_stats(self) -> None:
        # The trend range comes from ?range=<key> (day/week/month/3month/6month/
        # year/5year); the store falls back to its default for anything unknown.
        params = parse_qs(urlparse(self.path).query)
        range_key = params.get("range", [""])[0]
        # Re-scan transcripts (cheap — only changed files are re-read), pull the
        # live limits, and bundle everything into one JSON snapshot.
        with self.lock:
            self.store.refresh()
            data = self.store.aggregate(range_key)
            # 30-day API-equivalent spend (always last-30-days, independent of the
            # selected chart range) — drives the "money's worth" comparison in the UI.
            data["value_30d_usd"] = self.store.aggregate("month")["period"]["cost"]
        data["limits"] = usage.fetch_limits()
        now = datetime.now(self.tz)
        data["timezone"] = now.strftime("%Z") or "local time"
        data["generated_at"] = now.strftime("%Y-%m-%d %H:%M:%S %Z")
        body = json.dumps(data).encode("utf-8")
        self._send(200, body, "application/json; charset=utf-8")


def build_server(host: str, port: int, *, tz: tzinfo, projects_dir: str = PROJECTS_DIR) -> ThreadingHTTPServer:
    """Create the server, priming the transcript cache up front.

    We do the first (slow) full parse here, before we start serving, so the very
    first page load is instant rather than waiting on thousands of files.
    """
    store = TranscriptStore(tz=tz, projects_dir=projects_dir)
    print("Portmint Pulse — indexing your Claude Code sessions...", flush=True)
    parsed = store.refresh()
    print(f"  indexed {parsed} session transcripts.", flush=True)

    handler = type(
        "PulseHandler",
        (_Handler,),
        {"store": store, "lock": threading.Lock(), "tz": tz, "dashboard": _load_dashboard_html()},
    )
    return ThreadingHTTPServer((host, port), handler)
