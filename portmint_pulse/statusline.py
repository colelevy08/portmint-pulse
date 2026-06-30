"""Render the Claude Code status line from the JSON blob it pipes on stdin.

Claude Code can run a command after every turn and show its first stdout line as a
status bar (``statusLine`` in settings.json). That blob already carries your live
subscription rate-limit windows, session cost, model, and context usage — so this
renders a glanceable limit bar **with no OAuth call and no token cost**, right where
you work.

Hard rules for a status-line command (all honored here):
  - **Never blank, never crash, always exit 0.** A non-zero exit or empty output
    hides the bar, so every path prints *something* and returns 0.
  - **stdout only** (stderr is dropped), **no network**, fast (it runs often).
  - Honor ``NO_COLOR``; adapt to ``COLUMNS`` (a real TTY isn't detectable here).

Pure standard library; imports nothing heavy so it starts fast on every turn.
"""

from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timezone

# 256-colour ANSI (widely supported). Severity: mint → amber → red.
_RESET = "\033[0m"
_DIM = "\033[2m"
_MINT = "\033[38;5;43m"
_AMBER = "\033[38;5;214m"
_RED = "\033[38;5;196m"
_CYAN = "\033[38;5;87m"

# Rate-limit windows to consider, with short labels. The last two aren't in the
# official docs but Claude Code emits them (claude-pulse reads exactly these four).
_WINDOWS = [
    ("five_hour", "5h"),
    ("seven_day", "7d"),
    ("seven_day_opus", "7d-opus"),
    ("seven_day_sonnet", "7d-sonnet"),
]


def _num(v: object) -> float | None:
    """A finite real number (not bool, not NaN/inf), else None.

    json.loads accepts NaN/Infinity by default; a NaN here would both print 'nan%'
    and — because NaN compares False in max() — mask the truly-binding window. Drop
    non-finite values so the bar always points at a real number.
    """
    if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v):
        return float(v)
    return None


def _color_for(pct: float) -> str:
    """Severity colour for a 0–100 utilisation."""
    return _RED if pct >= 85 else (_AMBER if pct >= 60 else _MINT)


def _bar(pct: float, width: int, color: str, use_color: bool) -> str:
    """A width-char block bar for a 0–100 percentage."""
    pct = max(0.0, min(100.0, pct))
    filled = max(0, min(width, round(pct / 100 * width)))
    body = "▓" * filled + "░" * (width - filled)
    return f"{color}{body}{_RESET}" if use_color else body


def _model_name(blob: dict) -> str:
    """Short model label. Handles `model` being an object OR a bare string, and
    strips a leading 'Claude ' the way real consumers do."""
    m = blob.get("model")
    if isinstance(m, dict):
        name = m.get("display_name") or m.get("id") or ""
    elif isinstance(m, str):
        name = m
    else:
        name = ""
    name = str(name).strip()
    if name.startswith("Claude "):
        name = name[len("Claude ") :]
    return name


def _humanize_reset(resets_at: object) -> str | None:
    """Countdown to a reset time. Type-sniffs: ISO string, epoch seconds, or epoch
    milliseconds (>1e12) — defends against the documented stdin/changelog mismatch."""
    when: datetime | None = None
    if isinstance(resets_at, str):
        try:
            when = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
    elif isinstance(resets_at, (int, float)) and not isinstance(resets_at, bool):
        ts = resets_at / 1000 if resets_at > 1e12 else resets_at
        try:
            when = datetime.fromtimestamp(ts, tz=timezone.utc)
        except (ValueError, OSError, OverflowError):
            return None
    if when is None:
        return None
    secs = int((when - datetime.now(timezone.utc)).total_seconds())
    if secs <= 0:
        return "now"
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"{days}d{hours}h" if hours else f"{days}d"
    if hours:
        return f"{hours}h{mins}m" if mins else f"{hours}h"
    return f"{mins}m" if mins else "<1m"


def _pick_window(rate_limits: object) -> tuple[str, float, object] | None:
    """The most-used present rate-limit window → (label, pct, resets_at), or None.

    Picking the highest-utilisation window answers 'which limit blocks me first',
    the whole point of the bar.
    """
    if not isinstance(rate_limits, dict):
        return None
    present: list[tuple[str, float, object]] = []
    for key, label in _WINDOWS:
        w = rate_limits.get(key)
        if isinstance(w, dict):
            pct = _num(w.get("used_percentage"))
            if pct is not None:
                present.append((label, pct, w.get("resets_at")))
    return max(present, key=lambda x: x[1]) if present else None


def _context_pct(blob: dict) -> float | None:
    """Context-window % used (0–100): the pre-calculated field, or computed from
    input tokens / window size as a fallback."""
    cw = blob.get("context_window")
    if not isinstance(cw, dict):
        return None
    pct = _num(cw.get("used_percentage"))
    if pct is not None:
        return pct
    tot = _num(cw.get("total_input_tokens"))
    size = _num(cw.get("context_window_size"))
    if tot is not None and size:
        return tot / size * 100
    return None


def render(blob: object, *, use_color: bool = True, columns: int = 80) -> str:
    """Build the one-line status string. Pure + defensive — any odd input still
    yields a sensible, non-empty line."""
    if not isinstance(blob, dict):
        blob = {}
    sep = f" {_DIM}·{_RESET} " if use_color else " · "
    bar_w = 4 if columns < 60 else 8
    segs: list[str] = []

    # 1) model
    name = _model_name(blob) or "claude"
    segs.append(f"{_CYAN}[{name}]{_RESET}" if use_color else f"[{name}]")

    # 2/3) the live limit bar (headline) — or context% if limits aren't present.
    win = _pick_window(blob.get("rate_limits"))
    if win is not None:
        label, pct, resets_at = win
        pct = max(0.0, min(100.0, pct))  # clamp the DISPLAYED number too (the bar already clamps)
        color = _color_for(pct)
        pctstr = f"{color}{pct:.0f}%{_RESET}" if use_color else f"{pct:.0f}%"
        segs.append(f"{_bar(pct, bar_w, color, use_color)} {pctstr}")
        if columns >= 60:
            reset = _humanize_reset(resets_at)
            wl = f"{label} {reset}" if reset else label
            segs.append(f"{_DIM}{wl}{_RESET}" if use_color else wl)
    else:
        cpct = _context_pct(blob)
        if cpct is not None:
            cpct = max(0.0, min(100.0, cpct))
            color = _color_for(cpct)
            pctstr = f"{color}{cpct:.0f}%{_RESET}" if use_color else f"{cpct:.0f}%"
            segs.append(f"ctx {_bar(cpct, bar_w, color, use_color)} {pctstr}")

    # 4) session cost (dropped first when space is tight)
    cost_obj = blob.get("cost")
    cost = _num(cost_obj.get("total_cost_usd")) if isinstance(cost_obj, dict) else None
    # Bound the cost segment so a pathological huge value can't blow the one-line budget.
    if cost is not None and 0 <= cost < 1e9 and columns >= 50:
        c = f"${cost:.2f}"
        segs.append(f"{_DIM}{c}{_RESET}" if use_color else c)

    return sep.join(segs)


# A representative blob (from the verified schema) for `--demo` and tests.
_DEMO_BLOB: dict = {
    "model": {"id": "claude-opus-4-8", "display_name": "Opus"},
    "cost": {"total_cost_usd": 0.0562},
    "context_window": {"total_input_tokens": 15500, "context_window_size": 200000, "used_percentage": 8},
    "rate_limits": {
        "five_hour": {"used_percentage": 47.0, "resets_at": None},
        "seven_day": {"used_percentage": 41.2, "resets_at": None},
        "seven_day_opus": {"used_percentage": 62.5, "resets_at": None},
        "seven_day_sonnet": None,
    },
}


def main(argv: list[str] | None = None) -> int:
    """Read the blob from stdin (or `--demo`), print one status line, exit 0."""
    args = sys.argv[1:] if argv is None else argv
    if "--demo" in args:
        # Give the headline window a live reset time so the preview shows a countdown.
        soon = int(datetime.now(timezone.utc).timestamp()) + 8100  # ~2h15m
        blob: object = {
            **_DEMO_BLOB,
            "rate_limits": {**_DEMO_BLOB["rate_limits"], "seven_day_opus": {"used_percentage": 62.5, "resets_at": soon}},
        }
    else:
        try:
            raw = sys.stdin.read()
            blob = json.loads(raw) if raw.strip() else {}
        except Exception:
            blob = {}

    use_color = os.environ.get("NO_COLOR") is None
    try:
        columns = int(os.environ.get("COLUMNS", "80"))
    except (ValueError, TypeError):
        columns = 80

    try:
        line = render(blob, use_color=use_color, columns=columns)
    except Exception:
        # Absolute last resort — never blank, never non-zero.
        line = "[claude]"
    sys.stdout.write(line + "\n")
    return 0
