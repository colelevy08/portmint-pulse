"""Tests for the watch alert logic — pure, edge-triggered, drift-immune."""

from portmint_pulse.watch import _alert_text, _status_line, _windows_from, evaluate


def W(label, util, resets="r1"):
    return {"label": label, "utilization": util, "resets_at": resets, "resets_human": "in 2h"}


def test_edge_triggered_alert_fires_once():
    a1, latched = evaluate([W("5h", 85)], set())
    assert [a["threshold"] for a in a1] == [80]
    a2, latched = evaluate([W("5h", 86)], latched)  # still ≥80
    assert a2 == []  # no re-alert


def test_crossing_a_higher_threshold_alerts_again():
    a1, latched = evaluate([W("5h", 85)], set())
    a2, latched = evaluate([W("5h", 96)], latched)
    assert [a["threshold"] for a in a2] == [95]


def test_hitting_100_fires_all_thresholds_once():
    a, _ = evaluate([W("5h", 100)], set())
    assert sorted(x["threshold"] for x in a) == [80, 95, 100]


def test_resets_at_drift_does_not_respam():
    # The bug that caused the spam: a rolling window whose resets_at shifts each poll
    # must NOT re-fire the alert. (We no longer key off resets_at.)
    a1, latched = evaluate([W("5h", 85, resets="t1")], set())
    assert len(a1) == 1
    a2, latched = evaluate([W("5h", 85, resets="t2")], latched)  # resets_at drifted
    assert a2 == []
    a3, _ = evaluate([W("5h", 85, resets="t3")], latched)
    assert a3 == []  # still silent — only one alert per crossing


def test_dropping_below_rearms_the_alert():
    # A real reset drops utilisation → re-arm → next climb alerts again.
    _, latched = evaluate([W("5h", 85)], set())
    _, latched = evaluate([W("5h", 5)], latched)   # reset
    a, _ = evaluate([W("5h", 85)], latched)
    assert len(a) == 1


def test_windows_from_includes_extra_usage_and_filters_junk():
    limits = {
        "windows": [{"label": "5h", "utilization": 10, "resets_at": None}, {"label": "bad", "utilization": None}, "nope"],
        "extra_usage": {"utilization": 25, "used": 12.4, "limit": 50},
    }
    w = _windows_from(limits)
    assert [x["label"] for x in w] == ["5h", "Extra-usage credits"]
    assert w[1]["utilization"] == 25


def test_status_line_marks_and_names_binding_window():
    line = _status_line([W("5h", 85), W("7d", 30)])
    assert "5h 85% ⚠" in line and "binds: 5h 85%" in line


def test_alert_text_is_branded_and_detailed():
    title, body = _alert_text({"label": "5-hour session", "threshold": 95, "utilization": 96.0, "resets_human": "in 14m"})
    assert title == "Portmint Pulse"
    assert "5-hour session" in body and "96%" in body and "Almost out" in body and "in 14m" in body


def test_empty_is_safe():
    assert evaluate([], set()) == ([], set())
    assert "no active" in _status_line([])
