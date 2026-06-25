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


def _local_timezone() -> tzinfo:
    """The system's current local timezone as a fixed-offset tzinfo.

    ``datetime.now().astimezone()`` attaches the OS local zone (with the right
    abbreviation for ``%Z``) without touching the IANA database, so it is safe on
    a bare Windows install. We guard against the rare ``None`` with a UTC default.
    """
    local = datetime.now().astimezone().tzinfo
    return local if local is not None else timezone.utc
