#!/usr/bin/env python3
"""Generate a synthetic Claude-Code projects tree and serve Pulse against it.

This is a developer tool (not shipped in the package) used to produce the README
screenshot and to let anyone preview the dashboard without their own history. All
data is fabricated — no real usage, projects, or credentials are involved.

    python tools/gen_demo.py            # serve demo on http://127.0.0.1:8791
    python tools/gen_demo.py --port 9000
"""

from __future__ import annotations

import argparse
import json
import random
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make the package importable when run as `python tools/gen_demo.py` from a bare
# checkout (running a script puts tools/ — not the repo root — on sys.path).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from portmint_pulse import usage  # noqa: E402  (path set above)
from portmint_pulse.server import build_server  # noqa: E402

# Fabricated projects and the models they tend to use, with rough weightings.
_PROJECTS = ["acme-storefront", "billing-service", "ml-pipeline", "marketing-site", "infra-scripts"]
_MODELS = [
    ("claude-opus-4-8", 0.18),
    ("claude-sonnet-4-6", 0.50),
    ("claude-haiku-4-5", 0.32),
]


def _pick_model(rng: random.Random) -> str:
    r = rng.random()
    cum = 0.0
    for name, w in _MODELS:
        cum += w
        if r <= cum:
            return name
    return _MODELS[-1][0]


def _encode_cwd(project: str) -> str:
    # Claude Code encodes the cwd into the directory name; the exact scheme does
    # not matter to Pulse (it reads cwd from inside the file), so keep it simple.
    return f"-home-dev-{project}"


def generate(target: Path, *, days: int = 30, seed: int = 7) -> int:
    """Write synthetic .jsonl session files spanning the last `days` days."""
    rng = random.Random(seed)
    now = datetime.now(timezone.utc)
    files = 0
    for project in _PROJECTS:
        cwd = f"/home/dev/{project}"
        proj_dir = target / _encode_cwd(project)
        proj_dir.mkdir(parents=True, exist_ok=True)
        for day in range(days):
            # Some days a project is idle — but always populate "today" (day 0) so
            # the demo's Today card is never an unflattering $0.00.
            if day != 0 and rng.random() < 0.35:
                continue
            # An engaged daily Claude Code user (several sessions/day) — so the demo
            # reflects the real target audience and "money's worth" reads above 1×.
            sessions = rng.randint(3, 8)
            for s in range(sessions):
                when = now - timedelta(days=day, hours=rng.randint(0, 12), minutes=rng.randint(0, 59))
                records = []
                for _turn in range(rng.randint(3, 14)):
                    when += timedelta(minutes=rng.randint(1, 6))
                    model = _pick_model(rng)
                    scale = 3.0 if model == "claude-opus-4-8" else (1.4 if "sonnet" in model else 0.6)
                    records.append({
                        "type": "assistant",
                        "timestamp": when.strftime("%Y-%m-%dT%H:%M:%SZ"),
                        "cwd": cwd,
                        "message": {
                            "model": model,
                            "usage": {
                                "input_tokens": int(rng.randint(200, 1500) * scale),
                                "output_tokens": int(rng.randint(300, 2500) * scale),
                                "cache_read_input_tokens": int(rng.randint(8000, 60000) * scale),
                                "cache_creation": {
                                    "ephemeral_5m_input_tokens": int(rng.randint(1000, 9000) * scale),
                                    "ephemeral_1h_input_tokens": int(rng.randint(0, 1500) * scale),
                                },
                            },
                        },
                    })
                fpath = proj_dir / f"sess-{project}-{day}-{s}.jsonl"
                with open(fpath, "w", encoding="utf-8") as fh:
                    for r in records:
                        fh.write(json.dumps(r) + "\n")
                files += 1
    return files


# Fabricated live-limit windows so the screenshot shows the bars populated.
_DEMO_LIMITS = {
    "windows": [
        {"label": "5-hour session", "utilization": 62.0, "resets_human": "resets in 2h 14m"},
        {"label": "7-day · all models", "utilization": 38.0, "resets_human": "resets in 4d 6h"},
        {"label": "7-day · Opus", "utilization": 73.0, "resets_human": "resets in 4d 6h"},
        {"label": "7-day · Sonnet", "utilization": 41.0, "resets_human": "resets in 4d 6h"},
    ],
    "extra_usage": {"currency": "USD", "used": 12.4, "limit": 50.0, "utilization": 24.8},
}


def main() -> int:
    ap = argparse.ArgumentParser(description="Serve Portmint Pulse against synthetic demo data.")
    ap.add_argument("--port", type=int, default=8791)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="pulse-demo-"))
    n = generate(tmp)
    print(f"Generated {n} synthetic session files in {tmp}")

    # Show fabricated limits instead of calling the real usage API.
    usage.fetch_limits = lambda: _DEMO_LIMITS  # type: ignore[assignment]

    httpd = build_server(args.host, args.port, tz=timezone.utc, projects_dir=str(tmp))
    print(f"Demo live at http://{args.host}:{args.port}  (Ctrl+C to stop)", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
