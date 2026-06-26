"""Portmint Pulse — command-line entry point.

Run it any of these ways:

    portmint-pulse                  # installed console script
    python -m portmint_pulse        # module form
    python3 app.py                  # straight from a checkout

Then open the printed URL (http://127.0.0.1:8787 by default). No dependencies on
Linux/macOS; on Windows, ``tzdata`` is pulled in only if you pass --timezone.
"""

from __future__ import annotations

import argparse
import os
import sys
import threading
import webbrowser

from . import __version__
from .server import build_server
from .transcripts import PROJECTS_DIR
from .tz import resolve_timezone


def _supports_color() -> bool:
    """True if we should emit ANSI colour in the startup banner.

    Honours NO_COLOR, requires a TTY, and on Windows 10+ flips the console into
    virtual-terminal mode so the escape codes render instead of printing raw.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
            # ENABLE_VIRTUAL_TERMINAL_PROCESSING (0x4) on the stdout handle (-11).
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
            return True
        except Exception:
            return os.environ.get("WT_SESSION") is not None
    return True


def _open_browser(url: str) -> None:
    """Best-effort open a browser tab; silently no-op if none is available."""
    try:
        webbrowser.open(url)
    except Exception:
        pass  # headless box / WSL without a browser — the URL is printed anyway


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="portmint-pulse",
        description="Portmint Pulse — a local, private Claude Code usage dashboard.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind address (default 127.0.0.1; use 0.0.0.0 to expose on your LAN).")
    parser.add_argument("--port", type=int, default=8787, help="Port (default 8787).")
    parser.add_argument("--no-browser", action="store_true", help="Don't auto-open a browser tab.")
    parser.add_argument(
        "--timezone",
        default=None,
        metavar="ZONE",
        help="IANA timezone for day buckets, e.g. 'America/New_York'. Default: your machine's local timezone. (Also via PULSE_TIMEZONE.)",
    )
    parser.add_argument(
        "--projects-dir",
        default=None,
        metavar="DIR",
        help="Claude Code projects directory (default ~/.claude/projects). Also via PULSE_PROJECTS_DIR.",
    )
    parser.add_argument("--version", action="version", version=f"Portmint Pulse {__version__}")
    args = parser.parse_args(argv)

    tz = resolve_timezone(args.timezone or os.environ.get("PULSE_TIMEZONE"))
    projects_dir = args.projects_dir or os.environ.get("PULSE_PROJECTS_DIR") or PROJECTS_DIR

    # Binding to anything but loopback exposes your project names + full usage to
    # the network with no authentication — make that loud, not a footnote.
    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            f"  WARNING: binding {args.host} exposes your project names and usage to "
            f"everyone on this network — there is no authentication.",
            file=sys.stderr,
        )

    color = _supports_color()
    mint = "\033[38;2;52;224;179m" if color else ""
    dim = "\033[2m" if color else ""
    reset = "\033[0m" if color else ""

    try:
        httpd = build_server(args.host, args.port, tz=tz, projects_dir=projects_dir)
    except OSError as e:
        print(f"Could not start server on {args.host}:{args.port} — {e}", file=sys.stderr)
        print("Is something already using that port? Try --port 9000.", file=sys.stderr)
        return 1

    url = f"http://{args.host}:{args.port}"
    print(f"\n  {mint}Ψ Portmint Pulse{reset} is live at {mint}{url}{reset}")
    print(f"  {dim}Press Ctrl+C to stop.{reset}\n")

    if not args.no_browser:
        # Open the tab a beat after the server is actually accepting connections.
        threading.Timer(0.6, lambda: _open_browser(url)).start()

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Shutting down. Bye!\n")
        httpd.shutdown()
    return 0
