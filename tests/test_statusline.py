"""Tests for the status-line renderer — pure, defensive, never blank/crash."""

import io
import json
from datetime import datetime, timedelta, timezone

from portmint_pulse import statusline as sl


def _epoch(seconds_from_now):
    return int((datetime.now(timezone.utc) + timedelta(seconds=seconds_from_now)).timestamp())


def test_picks_highest_window_and_renders_segments():
    blob = {
        "model": {"display_name": "Opus"},
        "cost": {"total_cost_usd": 0.0562},
        "rate_limits": {
            "five_hour": {"used_percentage": 47.0, "resets_at": _epoch(8000)},
            "seven_day": {"used_percentage": 41.2},
            "seven_day_opus": {"used_percentage": 62.5, "resets_at": _epoch(8000)},
        },
    }
    out = sl.render(blob, use_color=False)
    assert "[Opus]" in out
    assert "62%" in out          # the highest window (opus), not 47/41
    assert "7d-opus" in out
    assert "$0.06" in out


def test_color_severity_thresholds():
    def at(p):
        return sl.render({"rate_limits": {"five_hour": {"used_percentage": p}}}, use_color=True)
    assert sl._MINT in at(40)
    assert sl._AMBER in at(70)
    assert sl._RED in at(92)


def test_no_color_emits_no_ansi():
    assert "\033" not in sl.render(sl._DEMO_BLOB, use_color=False)


def test_context_fallback_when_no_rate_limits():
    out = sl.render({"model": {"display_name": "Opus"}, "context_window": {"used_percentage": 34}}, use_color=False)
    assert "ctx" in out and "34%" in out


def test_context_fallback_computes_from_tokens():
    out = sl.render({"context_window": {"total_input_tokens": 20000, "context_window_size": 200000}}, use_color=False)
    assert "10%" in out


def test_nan_window_does_not_hide_the_binding_window():
    # json.loads accepts NaN; a NaN in five_hour must NOT mask a real 80% seven_day.
    blob = {"rate_limits": {"five_hour": {"used_percentage": float("nan")},
                            "seven_day": {"used_percentage": 80}}}
    out = sl.render(blob, use_color=False)
    assert "80%" in out and "nan" not in out.lower()


def test_displayed_percentage_is_clamped():
    over = sl.render({"rate_limits": {"five_hour": {"used_percentage": 9999}}}, use_color=False)
    assert "100%" in over and "9999" not in over
    under = sl.render({"rate_limits": {"five_hour": {"used_percentage": -50}}}, use_color=False)
    assert "0%" in under and "-50" not in under


def test_pathological_huge_values_stay_compact():
    blob = {"model": {"display_name": "Opus"}, "cost": {"total_cost_usd": 1e308},
            "rate_limits": {"five_hour": {"used_percentage": 1e308}}}
    out = sl.render(blob, use_color=False, columns=80)
    assert len(out) < 60 and "e+" not in out  # clamped pct + dropped absurd cost


def test_never_blank_or_crash_on_bad_input():
    for bad in [None, {}, [], "x", 5, {"model": 123, "rate_limits": "nope", "cost": []}]:
        out = sl.render(bad, use_color=False)
        assert out and isinstance(out, str)


def test_model_name_string_or_object_and_strips_claude():
    assert sl._model_name({"model": {"display_name": "Claude Opus 4.8"}}) == "Opus 4.8"
    assert sl._model_name({"model": "Sonnet"}) == "Sonnet"
    assert sl._model_name({"model": {"id": "claude-opus-4-8"}}) == "claude-opus-4-8"
    assert sl._model_name({}) == ""


def test_reset_countdown_type_sniff():
    assert sl._humanize_reset(_epoch(3700)).startswith("1h")             # epoch seconds
    ms = int((datetime.now(timezone.utc) + timedelta(days=2)).timestamp() * 1000)
    assert sl._humanize_reset(ms) in ("2d", "1d23h")                     # epoch milliseconds (>1e12)
    iso = (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat()
    assert sl._humanize_reset(iso) in ("30m", "29m")                     # ISO string
    assert sl._humanize_reset(_epoch(-100)) == "now"
    assert sl._humanize_reset("garbage") is None
    assert sl._humanize_reset(None) is None


def test_narrow_columns_drops_cost_and_label():
    blob = {"model": {"display_name": "Opus"}, "cost": {"total_cost_usd": 1.0},
            "rate_limits": {"five_hour": {"used_percentage": 50}}}
    wide = sl.render(blob, use_color=False, columns=80)
    narrow = sl.render(blob, use_color=False, columns=40)
    assert "$1.00" in wide and "5h" in wide
    assert "$1.00" not in narrow and "5h" not in narrow   # both trimmed under width


def test_main_reads_stdin_and_exits_zero(monkeypatch, capsys):
    blob = {"model": {"display_name": "Opus"}, "rate_limits": {"five_hour": {"used_percentage": 50}}}
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(blob)))
    monkeypatch.setenv("NO_COLOR", "1")
    assert sl.main([]) == 0
    out = capsys.readouterr().out
    assert "[Opus]" in out and "50%" in out and out.endswith("\n")


def test_main_demo_and_empty_never_blank(monkeypatch, capsys):
    monkeypatch.setenv("NO_COLOR", "1")
    assert sl.main(["--demo"]) == 0
    assert "[Opus]" in capsys.readouterr().out

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert sl.main([]) == 0
    assert capsys.readouterr().out.strip()  # never blank
