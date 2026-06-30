"""Project time-to-limit from observed utilisation — pure, standard library only.

Given a rate-limit window's utilisation sampled over time, estimate how long until
it reaches 100% at the recent pace, and whether that lands *before* the window
resets. This is what turns "you're at 80%" into "at this pace, ~2h to the wall".

Used by the dashboard server (which sees utilisation across polls) and by ``watch``
(which polls in a loop). A tiny in-memory sample store + stateless math — nothing is
ever written to disk (zero telemetry, like everything else in Pulse).
"""

from __future__ import annotations

from datetime import datetime, timezone

_MAX_AGE_S = 45 * 60  # only the last 45 minutes of trajectory inform the pace
_MAX_POINTS = 24
_MIN_SAMPLES = 2
_RESET_DROP = 1.0     # a utilisation fall this big = the window reset
_MIN_STEP = 0.5       # only record a new sample on a change this big


def record(history: dict, label: str, util: float, now: float) -> list:
    """Append a timestamped sample for ``label`` (handling resets + de-dup) and
    return that window's age/count-trimmed sample list."""
    hist = history.setdefault(label, [])
    if hist and util < hist[-1][1] - _RESET_DROP:
        hist.clear()  # window reset → start a fresh trajectory
    if not hist or abs(util - hist[-1][1]) >= _MIN_STEP:
        hist.append((now, util))
    trimmed = [s for s in hist if s[0] >= now - _MAX_AGE_S][-_MAX_POINTS:]
    hist[:] = trimmed
    return trimmed


def eta_minutes(hist: list, util: float, now: float) -> float | None:
    """Minutes until this window reaches 100% at the recent pace, or None if it
    isn't rising or there isn't enough history yet."""
    if util >= 100:
        return 0.0
    pts = [s for s in hist if s[0] >= now - _MAX_AGE_S]
    if len(pts) < _MIN_SAMPLES:
        return None
    (t0, u0), (t1, u1) = pts[0], pts[-1]
    dt = t1 - t0
    if dt <= 0:
        return None
    rate = (u1 - u0) / dt  # utilisation %/second
    if rate <= 0:
        return None  # flat or falling → not approaching the wall
    return ((100.0 - util) / rate) / 60.0


def _minutes_to_reset(resets_at: object, now: float) -> float | None:
    """Minutes until ``resets_at`` (ISO string, epoch seconds, or epoch ms), or None."""
    if isinstance(resets_at, str):
        try:
            when = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
        except ValueError:
            return None
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        secs = when.timestamp() - now
    elif isinstance(resets_at, (int, float)) and not isinstance(resets_at, bool):
        ts = resets_at / 1000 if resets_at > 1e12 else resets_at
        secs = ts - now
    else:
        return None
    return secs / 60.0 if secs > 0 else 0.0


def humanize(minutes: float | None) -> str | None:
    """A short human duration, e.g. '2h14m', '45m', '<1m'."""
    if minutes is None:
        return None
    if minutes <= 1:
        return "<1m"
    m = int(round(minutes))
    if m < 60:
        return f"{m}m"
    h, mm = divmod(m, 60)
    if h < 24:
        return f"{h}h{mm}m" if mm else f"{h}h"
    d, hh = divmod(h, 24)
    return f"{d}d{hh}h" if hh else f"{d}d"


def annotate(history: dict, limits: object, now: float) -> None:
    """Mutate each window in ``limits`` to add a ``forecast`` of
    ``{eta_minutes, eta_human, hits_before_reset}`` — or ``None`` when the window
    isn't rising fast enough (or there's not enough history) to project."""
    if not isinstance(limits, dict):
        return
    for w in limits.get("windows", []) or []:
        if not isinstance(w, dict):
            continue
        util = w.get("utilization")
        label = w.get("label")
        if not isinstance(util, (int, float)) or not label:
            continue
        hist = record(history, label, float(util), now)
        em = eta_minutes(hist, float(util), now)
        if em is None:
            w["forecast"] = None
            continue
        ttr = _minutes_to_reset(w.get("resets_at"), now)
        w["forecast"] = {
            "eta_minutes": round(em, 1),
            "eta_human": humanize(em),
            # If you'd hit 100% before the window resets, it's actionable; otherwise
            # you'll reset first and never actually hit the wall this period.
            "hits_before_reset": ttr is None or em < ttr,
        }
