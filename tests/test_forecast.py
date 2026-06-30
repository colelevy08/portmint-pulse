"""Tests for the time-to-limit projection — pure, reset-aware."""

from datetime import datetime, timezone

from portmint_pulse import forecast as fc


def test_record_dedups_and_handles_reset():
    h: dict = {}
    fc.record(h, "5h", 50.0, 1000)
    fc.record(h, "5h", 50.3, 1060)  # < 0.5 change → not recorded
    assert len(h["5h"]) == 1
    fc.record(h, "5h", 51.0, 1120)  # ≥ 0.5 → recorded
    assert len(h["5h"]) == 2
    fc.record(h, "5h", 5.0, 1180)   # big drop = reset → clear, then record fresh
    assert len(h["5h"]) == 1 and h["5h"][0][1] == 5.0


def test_record_trims_stale_points():
    h: dict = {}
    fc.record(h, "w", 10.0, 0.0)
    out = fc.record(h, "w", 90.0, fc._MAX_AGE_S + 100)  # the t=0 sample ages out
    assert len(out) == 1 and out[0][1] == 90.0


def test_eta_minutes_rising_flat_falling():
    # 50%→60% over 600s = 1%/60s; 40% remaining → 2400s → 40 min
    assert abs(fc.eta_minutes([(0.0, 50.0), (600.0, 60.0)], 60.0, 600.0) - 40.0) < 0.1
    assert fc.eta_minutes([(0.0, 50.0), (600.0, 50.0)], 50.0, 600.0) is None  # flat
    assert fc.eta_minutes([(0.0, 50.0)], 50.0, 0.0) is None                   # one sample
    assert fc.eta_minutes([(0.0, 60.0), (600.0, 50.0)], 50.0, 600.0) is None  # falling
    assert fc.eta_minutes([], 100.0, 0.0) == 0.0                              # already at 100


def test_minutes_to_reset_forms():
    now = 1_000_000.0
    iso = datetime.fromtimestamp(now + 3600, tz=timezone.utc).isoformat()
    assert abs(fc._minutes_to_reset(iso, now) - 60.0) < 0.2
    assert abs(fc._minutes_to_reset(now + 1800, now) - 30.0) < 0.01  # epoch seconds
    assert fc._minutes_to_reset(now - 100, now) == 0.0               # already past
    assert fc._minutes_to_reset("garbage", now) is None
    assert fc._minutes_to_reset(None, now) is None


def test_humanize():
    assert fc.humanize(None) is None
    assert fc.humanize(0.5) == "<1m"
    assert fc.humanize(45) == "45m"
    assert fc.humanize(74) == "1h14m"
    assert fc.humanize(120) == "2h"
    assert fc.humanize(1500) == "1d1h"


def test_annotate_projects_across_two_polls():
    h: dict = {}
    w1 = {"label": "5h", "utilization": 50.0, "resets_at": 3600.0}
    fc.annotate(h, {"windows": [w1]}, 0.0)
    assert w1["forecast"] is None  # only one sample so far
    w2 = {"label": "5h", "utilization": 60.0, "resets_at": 3600.0}
    fc.annotate(h, {"windows": [w2]}, 600.0)
    f = w2["forecast"]
    assert f is not None and abs(f["eta_minutes"] - 40.0) < 0.5
    assert f["hits_before_reset"] is True  # 40m eta < 50m to reset


def test_annotate_resets_before_wall():
    h: dict = {}
    fc.annotate(h, {"windows": [{"label": "w", "utilization": 50.0, "resets_at": 700.0}]}, 0.0)
    w = {"label": "w", "utilization": 51.0, "resets_at": 700.0}  # crawling up; resets very soon
    fc.annotate(h, {"windows": [w]}, 600.0)
    assert w["forecast"] is not None and w["forecast"]["hits_before_reset"] is False


def test_annotate_is_defensive():
    fc.annotate({}, None, 0.0)  # non-dict limits → no error
    h: dict = {}
    lim = {"windows": [{"label": "ok", "utilization": 5.0}, {"utilization": 5.0}, "junk", {"label": "x"}]}
    fc.annotate(h, lim, 0.0)  # missing label / util / non-dict all skipped
    assert lim["windows"][0]["forecast"] is None  # only one sample
