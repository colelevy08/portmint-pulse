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
