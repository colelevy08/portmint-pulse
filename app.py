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

from portmint_pulse.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
