"""Tests for transcript parsing + aggregation, using synthetic JSONL fixtures.

These never touch a real ~/.claude directory — each test writes its own fake
projects tree into a tmp_path and points the store at it. Day bucketing uses a
fixed UTC zone so results are identical on every machine/CI runner.
"""

import json
import os
from datetime import datetime, timedelta, timezone

from portmint_pulse.transcripts import TranscriptStore, _as_int, _parse_ts, _project_label


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _assistant(model, ts, cwd, **usage):
    return {
        "type": "assistant",
        "timestamp": ts,
        "cwd": cwd,
        "message": {"model": model, "usage": usage},
    }


def _ago_iso(days=0, hour=12, minute=0):
    """A UTC 'Z' timestamp `days` days before now — so range tests don't drift
    with the calendar (a hardcoded date eventually falls out of the window)."""
    dt = (datetime.now(timezone.utc) - timedelta(days=days)).replace(
        hour=hour, minute=minute, second=0, microsecond=0
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_aggregate_basic(tmp_path):
    projects = tmp_path / "projects"
    _write_jsonl(
        projects / "enc-alpha" / "s1.jsonl",
        [
            _assistant("claude-haiku-4-5", _ago_iso(1), "/home/u/dev/alpha", input_tokens=1_000_000),
            {"type": "user", "timestamp": _ago_iso(1), "cwd": "/home/u/dev/alpha"},  # ignored
        ],
    )
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    assert store.refresh() == 1

    data = store.aggregate("month")
    assert data["transcript_files"] == 1
    assert data["range"] == "month"
    assert data["lifetime"]["tokens"]["total"] == 1_000_000
    assert data["period"]["tokens"]["total"] == 1_000_000  # yesterday is within a month
    assert data["models"][0]["name"] == "claude-haiku-4-5"
    assert data["models"][0]["cost"] == 1.0
    assert data["projects"][0]["name"] == "alpha"
    assert isinstance(data["series"], list) and len(data["series"]) == 30  # 30 daily buckets


def test_incremental_reparse_only_changed(tmp_path):
    projects = tmp_path / "projects"
    f = projects / "enc" / "s1.jsonl"
    _write_jsonl(f, [_assistant("claude-opus-4-8", "2026-06-20T10:00:00Z", "/x/proj", output_tokens=10)])
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    assert store.refresh() == 1
    # No change → nothing re-parsed.
    assert store.refresh() == 0


def test_same_mtime_append_is_reparsed(tmp_path):
    # An append that doesn't move mtime still changes size — the store must notice.
    projects = tmp_path / "projects"
    f = projects / "enc" / "s.jsonl"
    _write_jsonl(f, [_assistant("claude-opus-4-8", "2026-06-20T10:00:00Z", "/x/proj", output_tokens=10)])
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    assert store.refresh() == 1
    mtime = os.path.getmtime(f)

    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(_assistant("claude-opus-4-8", "2026-06-20T10:05:00Z", "/x/proj", output_tokens=20)) + "\n")
    os.utime(f, (mtime, mtime))  # pretend the mtime never changed

    assert store.refresh() == 1  # size differs → re-parsed
    assert store.aggregate()["lifetime"]["messages"] == 2


def test_synthetic_model_counts_tokens_but_zero_cost(tmp_path):
    projects = tmp_path / "projects"
    _write_jsonl(
        projects / "enc" / "s.jsonl",
        [_assistant("<synthetic>", "2026-06-20T10:00:00Z", "/x/proj", input_tokens=500)],
    )
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store.refresh()
    data = store.aggregate()
    assert data["lifetime"]["tokens"]["total"] == 500
    assert data["lifetime"]["cost"] == 0.0


def test_missing_projects_dir_is_safe(tmp_path):
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(tmp_path / "does-not-exist"))
    assert store.refresh() == 0
    data = store.aggregate()
    assert data["transcript_files"] == 0
    assert data["lifetime"]["tokens"]["total"] == 0
    assert isinstance(data["series"], list)  # zero-filled, never missing


def test_malformed_records_do_not_crash_the_scan(tmp_path):
    # Every line here would have crashed an earlier version (ValueError on int('NaN'),
    # TypeError comparing naive vs aware, AttributeError on a non-dict message/usage,
    # or a non-object JSON line). The scan must survive and still count the good data.
    projects = tmp_path / "projects"
    f = projects / "enc" / "s.jsonl"
    f.parent.mkdir(parents=True)
    naive_ts = _ago_iso(1).rstrip("Z")  # same instant, but no offset → naive
    lines = [
        json.dumps(_assistant("claude-haiku-4-5", _ago_iso(1, hour=15), "/x/proj", input_tokens=100)),
        json.dumps(_assistant("claude-haiku-4-5", _ago_iso(1, hour=15, minute=1), "/x/proj", output_tokens="NaN")),  # bad int
        json.dumps(_assistant("claude-haiku-4-5", naive_ts, "/x/proj", input_tokens=5)),          # naive ts mixed in
        json.dumps({"type": "assistant", "timestamp": _ago_iso(1), "cwd": "/x/proj", "message": "nope"}),  # non-dict message
        json.dumps({"type": "assistant", "timestamp": _ago_iso(1), "cwd": "/x/proj", "message": {"usage": [1, 2]}}),  # non-dict usage
        "42",            # a JSON line that isn't an object
        "{ broken",      # invalid JSON
    ]
    with open(f, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")

    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    assert store.refresh() == 1            # did not raise
    data = store.aggregate()               # did not raise
    # The good record (100) and the naive-timestamp record (5) are counted; the
    # garbage ones are tolerated as zero-token rows rather than blanking the file.
    assert data["lifetime"]["tokens"]["total"] == 105
    assert data["projects"][0]["name"] == "proj"


def test_parse_ts_normalizes_naive_and_rejects_nonstring():
    aware = _parse_ts("2026-06-20T15:00:00Z")
    naive = _parse_ts("2026-06-20T15:00:00")
    assert aware is not None and naive is not None
    assert aware.tzinfo is not None and naive.tzinfo is not None  # both aware → comparable
    assert (naive < aware) or (naive == aware) or (naive > aware)  # no TypeError
    assert _parse_ts(12345) is None
    assert _parse_ts("") is None
    assert _parse_ts("not-a-date") is None


def test_as_int_coerces_garbage():
    assert _as_int("NaN") == 0
    assert _as_int(None) == 0
    assert _as_int([1, 2]) == 0
    assert _as_int("5") == 5
    assert _as_int(7) == 7


def test_range_scoping_windows(tmp_path):
    # Three records at increasing ages; period totals + breakdowns grow with the window.
    projects = tmp_path / "projects"
    _write_jsonl(projects / "enc" / "s.jsonl", [
        _assistant("claude-haiku-4-5", _ago_iso(2), "/x/recent", input_tokens=1_000_000),   # within week
        _assistant("claude-haiku-4-5", _ago_iso(40), "/x/mid", input_tokens=2_000_000),      # within 3month, not month
        _assistant("claude-haiku-4-5", _ago_iso(200), "/x/old", input_tokens=4_000_000),     # within year, not 3month
    ])
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store.refresh()

    assert store.aggregate("week")["period"]["tokens"]["total"] == 1_000_000
    assert store.aggregate("month")["period"]["tokens"]["total"] == 1_000_000
    assert store.aggregate("3month")["period"]["tokens"]["total"] == 3_000_000
    assert store.aggregate("year")["period"]["tokens"]["total"] == 7_000_000
    assert store.aggregate("week")["lifetime"]["tokens"]["total"] == 7_000_000  # range-independent
    assert {p["name"] for p in store.aggregate("week")["projects"]} == {"recent"}  # breakdown scoped


def test_hourly_series_for_day_range(tmp_path):
    projects = tmp_path / "projects"
    _write_jsonl(projects / "enc" / "s.jsonl", [
        _assistant("claude-haiku-4-5", _ago_iso(0, hour=9), "/x/proj", input_tokens=1000),
        _assistant("claude-haiku-4-5", _ago_iso(0, hour=14), "/x/proj", input_tokens=2000),
    ])
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store.refresh()
    data = store.aggregate("day")
    series = data["series"]
    assert len(series) == 24
    assert series[9]["label"] == "09:00" and series[9]["tokens"] == 1000
    assert series[14]["tokens"] == 2000
    assert data["period"]["tokens"]["total"] == 3000  # today's total


def test_hourly_series_is_memoized(tmp_path):
    projects = tmp_path / "projects"
    f = projects / "enc" / "s.jsonl"
    _write_jsonl(f, [_assistant("claude-haiku-4-5", _ago_iso(0, hour=9), "/x/proj", input_tokens=1000)])
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store.refresh()
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    a = store.hourly_series(today)
    b = store.hourly_series(today)
    assert a is b  # served from the memo — no second disk read

    # Change the active file → file signature changes → recompute.
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(_assistant("claude-haiku-4-5", _ago_iso(0, hour=10), "/x/proj", input_tokens=500)) + "\n")
    store.refresh()
    c = store.hourly_series(today)
    assert c is not a
    assert c[10]["tokens"] == 500


def test_unknown_range_defaults_to_month(tmp_path):
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(tmp_path / "none"))
    store.refresh()
    data = store.aggregate("bogus")
    assert data["range"] == "month"
    assert data["period"]["range"] == "month"


def test_long_range_uses_monthly_buckets(tmp_path):
    projects = tmp_path / "projects"
    _write_jsonl(projects / "enc" / "s.jsonl", [_assistant("claude-haiku-4-5", _ago_iso(0), "/x/proj", input_tokens=100)])
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store.refresh()
    series = store.aggregate("5year")["series"]
    assert 58 <= len(series) <= 63           # ~60 monthly buckets over 5 years
    assert "'" in series[-1]["label"]        # month labels look like "Jun '26"


def test_project_label_handles_both_separators():
    assert _project_label("/home/me/dev/proj") == "proj"
    assert _project_label("/home/me/dev/proj/") == "proj"
    assert _project_label("C:\\Users\\me\\dev\\proj") == "proj"
    assert _project_label("C:\\Users\\me\\dev\\proj\\") == "proj"
