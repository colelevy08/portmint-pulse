"""Tests for the one-shot summary formatting."""

from portmint_pulse import summary


def _block(cost, total, msgs, sess):
    return {"cost": cost, "tokens": {"total": total}, "messages": msgs, "sessions": sess}


def test_bar_and_token_formatting():
    assert summary._bar(0) == "-" * 20
    assert summary._bar(100) == "#" * 20
    assert summary._bar(50).count("#") == 10
    assert summary._bar(150) == "#" * 20  # clamped
    assert summary._fmt_tokens(2_410_000) == "2.4M"
    assert summary._fmt_tokens(6_550_000_000) == "6.55B"
    assert summary._fmt_tokens(500) == "500"


def test_text_renders_blocks_windows_and_binds_first():
    data = {
        "today": _block(1.84, 2_410_000, 38, 4),
        "week": _block(12.07, 1_000_000, 5, 2),
        "lifetime": {**_block(214.0, 4000, 100, 3), "first_session_date": "2026-01-12", "active_days": 96},
    }
    limits = {
        "windows": [
            {"label": "5-hour session", "utilization": 47, "resets_human": "in 2h"},
            {"label": "7-day · Opus", "utilization": 63, "resets_human": "in 4d"},
        ],
        "extra_usage": {"utilization": 25, "used": 12.4, "limit": 50, "currency": "USD"},
    }
    out = summary._text(data, limits, "2026-06-30 14:00:00", "EDT")
    assert "Today" in out and "$1.84" in out and "2.4M tokens" in out
    assert "binds first" in out and "7-day · Opus" in out
    assert "PAYG" in out and "since 2026-01-12" in out


def test_text_surfaces_a_limits_error():
    z = _block(0, 0, 0, 0)
    out = summary._text({"today": z, "week": z, "lifetime": z}, {"error": "not logged in"}, "x", "EDT")
    assert "not logged in" in out
