"""Timezone resolution that works the same on Linux, macOS, and Windows.

Why this module exists: the dashboard buckets usage into days, and "a day" only
means something in a timezone. The original tool hardcoded America/New_York. For
a tool other people run, that's wrong — someone in Tokyo or Berlin should see
*their* days. So by default we use the machine's local timezone, and let the user
override it with ``--timezone "America/New_York"``.

There's also a portability trap: ``zoneinfo.ZoneInfo("America/New_York")`` raises
on a stock Windows Python because Windows ships no IANA timezone database. We
avoid that entirely on the default path (local time needs no database), and when
the user explicitly names a zone we rely on the ``tzdata`` package (declared as a
Windows dependency) and fall back gracefully if it still can't be found.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timezone, tzinfo


def resolve_timezone(name: str | None) -> tzinfo:
    """Return a tzinfo for ``name`` (an IANA key), or the machine's local zone.

    Passing ``None`` (the default) yields the local timezone, which needs no
    external database and therefore works everywhere out of the box.
    """
    if name:
        try:
            from zoneinfo import ZoneInfo  # local import: only needed when overriding

            return ZoneInfo(name)
        except Exception:
            # Unknown zone, or Windows without tzdata installed. Warn and fall
            # back to local rather than crashing the whole dashboard.
            print(
                f"  ! Unknown timezone {name!r} (is 'tzdata' installed on Windows?) "
                f"— using local time instead.",
                file=sys.stderr,
            )
    return _local_timezone()


def _detect_iana_name() -> str | None:
    """Best-effort discovery of the system IANA timezone name on POSIX.

    Prefers the ``TZ`` env var, then resolves the ``/etc/localtime`` symlink
    (e.g. ``/usr/share/zoneinfo/America/New_York`` → ``America/New_York``). Returns
    None on Windows or when nothing is discoverable.
    """
    tzenv = os.environ.get("TZ")
    if tzenv and "/" in tzenv:
        # A path-like TZ value is an IANA name (including the Etc/GMT±N family).
        # A POSIX rule like "EST5EDT,M3.2.0/2" can also contain "/", but ZoneInfo
        # will simply reject it and the caller falls back — so don't over-filter.
        return tzenv.lstrip(":")
    try:
        target = os.readlink("/etc/localtime")
        marker = "zoneinfo/"
        idx = target.find(marker)
        if idx != -1:
            return target[idx + len(marker):]
    except (OSError, ValueError):
        pass
    # Debian/Ubuntu/WSL keep the name here even when /etc/localtime is a plain copy.
    try:
        with open("/etc/timezone", encoding="utf-8") as fh:
            name = fh.read().strip()
            if name and "/" in name:
                return name
    except OSError:
        pass
    return None


def _local_timezone() -> tzinfo:
    """The system's current local timezone.

    On POSIX we resolve the real IANA zone so day bucketing stays correct across any
    DST transition within the charted window (which spans up to 5 years) — a single
    frozen offset would be wrong on one side of a boundary. If the IANA name can't
    be found — notably on a
    bare Windows install with no timezone database — we fall back to
    ``datetime.now().astimezone()``, a fixed-offset zone that still works everywhere.
    """
    name = _detect_iana_name()
    if name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:
            pass
    local = datetime.now().astimezone().tzinfo
    return local if local is not None else timezone.utc
