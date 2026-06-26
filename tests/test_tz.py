"""Tests for timezone resolution (local default + named override + fallback)."""

from datetime import tzinfo

from portmint_pulse.tz import resolve_timezone


def test_local_default_returns_tzinfo():
    assert isinstance(resolve_timezone(None), tzinfo)


def test_named_zone_resolves():
    tz = resolve_timezone("America/New_York")
    assert isinstance(tz, tzinfo)
    # tzname should be an Eastern abbreviation (EST or EDT depending on the date).
    import datetime as _dt

    assert tz.tzname(_dt.datetime(2026, 6, 1)) in {"EST", "EDT"}


def test_bad_zone_falls_back_to_local(capsys):
    tz = resolve_timezone("Not/AZone")
    assert isinstance(tz, tzinfo)
    err = capsys.readouterr().err
    assert "Unknown timezone" in err


def test_named_zone_is_dst_aware():
    import datetime as _dt

    tz = resolve_timezone("America/New_York")
    jan = tz.utcoffset(_dt.datetime(2026, 1, 15))
    jul = tz.utcoffset(_dt.datetime(2026, 7, 15))
    assert jan != jul  # EST vs EDT — proves it's a real zone, not a frozen offset


def test_local_default_is_dst_aware_via_tz_env(monkeypatch):
    import datetime as _dt

    # With TZ set to an IANA name, the local-default path should resolve a real,
    # DST-aware zone (needs tzdata on Windows, which the package depends on there).
    monkeypatch.setenv("TZ", "America/New_York")
    tz = resolve_timezone(None)
    jan = tz.utcoffset(_dt.datetime(2026, 1, 15))
    jul = tz.utcoffset(_dt.datetime(2026, 7, 15))
    assert jan != jul
