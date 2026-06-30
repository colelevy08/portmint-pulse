"""``portmint-pulse summary`` — a one-shot text (or ``--json``) view of your usage
and live limits, with no server and no browser. Reads local transcripts (no token
cost) plus one live-limits call; great for scripts or a quick terminal glance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime


def _fmt_tokens(n: float) -> str:
    n = n or 0
    if n >= 1e9:
        return f"{n / 1e9:.2f}B"
    if n >= 1e6:
        return f"{n / 1e6:.1f}M"
    if n >= 1e3:
        return f"{n / 1e3:.1f}K"
    return str(int(n))


def _bar(util: float, width: int = 20) -> str:
    util = max(0.0, min(100.0, util))
    filled = round(util / 100 * width)
    return "#" * filled + "-" * (width - filled)


def _row(label: str, block: dict, extra: str = "") -> str:
    total = block.get("tokens", {}).get("total", 0)
    return (
        f"  {label:8} ${block.get('cost', 0):.2f}  {_fmt_tokens(total)} tokens  "
        f"{block.get('messages', 0)} msgs  {block.get('sessions', 0)} sessions{extra}"
    )


def _text(data: dict, limits: dict, generated_at: str, tzname: str) -> str:
    today, week, life = data["today"], data["week"], data["lifetime"]
    lines = [f"Portmint Pulse — usage summary  ({generated_at}, {tzname})", ""]
    lines.append(_row("Today", today))
    lines.append(_row("Week", week))
    since = f"  (since {life['first_session_date']}, {life['active_days']} active days)" if life.get("first_session_date") else ""
    lines.append(
        f"  Lifetime ${life.get('cost', 0):.2f}  {_fmt_tokens(life.get('tokens', {}).get('total', 0))} tokens  {life.get('messages', 0)} msgs{since}"
    )
    lines.append("")

    if isinstance(limits, dict) and limits.get("error"):
        lines.append(f"  Rate-limit windows: {limits['error']}")
        return "\n".join(lines)

    windows = limits.get("windows", []) if isinstance(limits, dict) else []
    extra = limits.get("extra_usage") if isinstance(limits, dict) else None
    binds = max(windows, key=lambda w: w.get("utilization", 0)) if windows else None
    lines.append("  Rate-limit windows (live):")
    if not windows:
        lines.append("    (none reported)")
    for w in windows:
        util = w.get("utilization", 0)
        mark = "   <- binds first" if binds is not None and w is binds else ""
        lines.append(f"    {w.get('label', ''):20} [{_bar(util)}] {util:4.0f}%   {w.get('resets_human') or ''}{mark}")
    if isinstance(extra, dict):
        util = extra.get("utilization", 0)
        limit = extra.get("limit")
        cap = f"{extra.get('used')} of {limit} {extra.get('currency', '')}".strip() if limit is not None else str(extra.get("used"))
        lines.append(f"    {'PAYG credits':20} [{_bar(util)}] {util:4.0f}%   {cap}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    from . import usage
    from .transcripts import PROJECTS_DIR, TranscriptStore
    from .tz import resolve_timezone

    parser = argparse.ArgumentParser(prog="portmint-pulse summary", description="One-shot usage + live-limits summary.")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of text.")
    parser.add_argument("--timezone", default=None, metavar="ZONE", help="IANA timezone (default: local; also PULSE_TIMEZONE).")
    parser.add_argument("--projects-dir", default=None, metavar="DIR", help="Override ~/.claude/projects (also PULSE_PROJECTS_DIR).")
    args = parser.parse_args(argv if argv is not None else [])

    tz = resolve_timezone(args.timezone or os.environ.get("PULSE_TIMEZONE"))
    projects_dir = args.projects_dir or os.environ.get("PULSE_PROJECTS_DIR") or PROJECTS_DIR
    store = TranscriptStore(tz=tz, projects_dir=projects_dir)
    store.refresh()
    data = store.aggregate("week")
    limits = usage.fetch_limits()

    now = datetime.now(tz)
    tzname = now.strftime("%Z") or "local time"
    if args.json:
        out = {
            "generated_at": now.isoformat(),
            "timezone": tzname,
            "today": data["today"],
            "week": data["week"],
            "lifetime": data["lifetime"],
            "limits": limits,
        }
        sys.stdout.write(json.dumps(out, indent=2) + "\n")
    else:
        sys.stdout.write(_text(data, limits, now.strftime("%Y-%m-%d %H:%M:%S"), tzname) + "\n")
    return 0
