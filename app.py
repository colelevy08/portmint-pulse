#!/usr/bin/env python3
"""Portmint Pulse — run-from-a-checkout shim.

This lets you start the dashboard without installing anything:

    python3 app.py                 # serves on http://127.0.0.1:8787
    python3 app.py --port 9000     # pick a different port
    python3 app.py --no-browser    # don't auto-open a browser tab
    python3 app.py --timezone America/New_York   # bucket days in a specific zone

All the real logic lives in the ``portmint_pulse`` package (entry point
``portmint_pulse.cli:main``); this file is just a friendly front door for people
who cloned the repo instead of running ``pip install``.
"""

import sys

# Fail fast with a clear message instead of a confusing ImportError deep in the
# stdlib (zoneinfo / importlib.resources.files are both 3.9+).
if sys.version_info < (3, 9):
    raise SystemExit(
        "Portmint Pulse needs Python 3.9 or newer (found %d.%d)." % sys.version_info[:2]
    )

from portmint_pulse.cli import main  # noqa: E402  (guarded import below the check)

if __name__ == "__main__":
    raise SystemExit(main())
