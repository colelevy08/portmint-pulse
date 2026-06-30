"""``portmint-pulse watch`` — warn you BEFORE you hit a Claude limit.

A small foreground loop that polls your live rate-limit windows and fires a desktop
notification the moment any window crosses 80 / 95 / 100% — naming which one — so a
mid-session wall never surprises you. It reuses ``usage.fetch_limits()`` (180s cache
+ 429 backoff), so the network is touched only ~once per 180s no matter the poll
cadence. State is in memory only (zero telemetry, no files).
"""

from __future__ import annotations

import argparse
import signal
import threading
import time
from datetime import datetime

_THRESHOLDS = (80, 95, 100)


def _windows_from(limits: dict) -> list[dict]:
    """Flatten fetch_limits() output into a list of {label, utilization, resets_at,
    resets_human}, including the pay-as-you-go credit bucket as one more window."""
    out: list[dict] = []
    if not isinstance(limits, dict):
        return out
    for w in limits.get("windows", []) or []:
        if isinstance(w, dict) and isinstance(w.get("utilization"), (int, float)) and w.get("label"):
            out.append(w)
    extra = limits.get("extra_usage")
    if isinstance(extra, dict) and isinstance(extra.get("utilization"), (int, float)):
        out.append({"label": "Extra-usage credits", "utilization": extra["utilization"], "resets_at": None, "resets_human": None})
    return out


def evaluate(windows: list[dict], latched: set) -> tuple[list[dict], set]:
    """Pure: given current windows + the set of already-alerted (label, threshold)
    pairs, return (alerts, new_latched).

    Edge-triggered — alert only the FIRST time a window crosses a threshold, and
    re-arm when it drops back below (which is exactly what a real reset does:
    utilisation falls to ~0). We deliberately do NOT key off ``resets_at`` — on a
    rolling window it can drift slightly every poll, which would re-fire the alert
    on every tick. This is the difference between "warn me once" and notification spam.
    """
    latched = set(latched)
    alerts: list[dict] = []
    for w in windows:
        label = w.get("label")
        util = w.get("utilization")
        if not label or not isinstance(util, (int, float)):
            continue
        for th in _THRESHOLDS:
            key = (label, th)
            if util >= th and key not in latched:
                alerts.append({"label": label, "threshold": th, "utilization": float(util), "resets_human": w.get("resets_human")})
                latched.add(key)
            elif util < th and key in latched:
                latched.discard(key)  # dropped back below → re-arm for the next climb
    return alerts, latched


def _status_line(windows: list[dict]) -> str:
    """A compact one-line view of every window + which binds first (and, if it's
    projected to hit 100% before it resets, a rough time-to-the-wall)."""
    if not windows:
        return "no active limit windows"
    parts = []
    for w in windows:
        util = w.get("utilization", 0)
        mark = " ⚠" if util >= 80 else ""
        parts.append(f"{w['label']} {util:.0f}%{mark}")
    binds = max(windows, key=lambda w: w.get("utilization", 0))
    line = " · ".join(parts) + f"   (binds: {binds['label']} {binds.get('utilization', 0):.0f}%)"
    fc = binds.get("forecast")
    if isinstance(fc, dict) and fc.get("hits_before_reset") and fc.get("eta_human"):
        line += f" · ~{fc['eta_human']} to wall"
    return line


def _alert_text(alert: dict) -> tuple[str, str]:
    """Branded (title) + detailed (body) text for one alert."""
    th = alert["threshold"]
    level = "Limit reached" if th >= 100 else "Almost out" if th >= 95 else "Approaching limit"
    when = f" · resets {alert['resets_human']}" if alert.get("resets_human") else ""
    title = "Portmint Pulse"
    body = f"Claude {alert['label']} at {alert['utilization']:.0f}% — {level}{when}"
    return title, body


def main(argv: list[str] | None = None) -> int:
    from . import forecast, usage  # local import keeps the path light

    parser = argparse.ArgumentParser(prog="portmint-pulse watch", description="Warn before you hit a Claude rate limit.")
    parser.add_argument("--interval", type=int, default=30, help="Poll seconds (default 30; clamped 5–600).")
    parser.add_argument("--no-desktop", action="store_true", help="Console only — don't send desktop notifications.")
    args = parser.parse_args(argv if argv is not None else [])
    interval = max(5, min(600, args.interval))

    stop = threading.Event()

    def _handle(*_a):
        stop.set()

    signal.signal(signal.SIGINT, _handle)
    try:
        signal.signal(signal.SIGTERM, _handle)  # may be absent on some platforms
    except (ValueError, AttributeError, OSError):
        pass

    print(f"\n  Ψ Portmint Pulse — watching your Claude limits (every {interval}s). Ctrl+C to stop.\n", flush=True)

    latched: set = set()
    fc_history: dict = {}
    while not stop.is_set():
        limits = usage.fetch_limits()
        if isinstance(limits, dict) and limits.get("error"):
            print(f"  {datetime.now().strftime('%H:%M:%S')}  limits unavailable — {limits['error']}", flush=True)
        else:
            windows = _windows_from(limits if isinstance(limits, dict) else {})
            forecast.annotate(fc_history, {"windows": windows}, time.time())  # adds ~time-to-wall
            print(f"  {datetime.now().strftime('%H:%M:%S')}  {_status_line(windows)}", flush=True)
            alerts, latched = evaluate(windows, latched)
            for alert in alerts:
                title, body = _alert_text(alert)
                print(f"  🔔 {title} — {body}", flush=True)
                if not args.no_desktop:
                    from .notify import notify

                    notify(title, body, urgency="critical" if alert["threshold"] >= 95 else "normal")
        stop.wait(interval)

    print("\n  Pulse watch stopped. Bye!\n", flush=True)
    return 0
