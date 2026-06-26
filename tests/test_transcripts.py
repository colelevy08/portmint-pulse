"""Tests for transcript parsing + aggregation, using synthetic JSONL fixtures.

These never touch a real ~/.claude directory — each test writes its own fake
projects tree into a tmp_path and points the store at it. Day bucketing uses a
fixed UTC zone so results are identical on every machine/CI runner.
"""

import json
import os
from datetime import timezone

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


def test_aggregate_basic(tmp_path):
    projects = tmp_path / "projects"
    _write_jsonl(
        projects / "enc-alpha" / "s1.jsonl",
        [
            _assistant("claude-haiku-4-5", "2026-06-20T15:00:00Z", "/home/u/dev/alpha", input_tokens=1_000_000),
            {"type": "user", "timestamp": "2026-06-20T15:00:01Z", "cwd": "/home/u/dev/alpha"},  # ignored
        ],
    )
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    assert store.refresh() == 1

    data = store.aggregate()
    assert data["transcript_files"] == 1
    assert data["lifetime"]["tokens"]["total"] == 1_000_000
    assert data["models"][0]["name"] == "claude-haiku-4-5"
    assert data["models"][0]["cost"] == 1.0
    assert data["projects"][0]["name"] == "alpha"
    assert len(data["daily"]) == 30  # always a 30-day series


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


def test_malformed_records_do_not_crash_the_scan(tmp_path):
    # Every line here would have crashed an earlier version (ValueError on int('NaN'),
    # TypeError comparing naive vs aware, AttributeError on a non-dict message/usage,
    # or a non-object JSON line). The scan must survive and still count the good data.
    projects = tmp_path / "projects"
    f = projects / "enc" / "s.jsonl"
    f.parent.mkdir(parents=True)
    lines = [
        json.dumps(_assistant("claude-haiku-4-5", "2026-06-20T15:00:00Z", "/x/proj", input_tokens=100)),
        json.dumps(_assistant("claude-haiku-4-5", "2026-06-20T15:01:00Z", "/x/proj", output_tokens="NaN")),  # bad int
        json.dumps(_assistant("claude-haiku-4-5", "2026-06-20T15:02:00", "/x/proj", input_tokens=5)),          # naive ts mixed in
        json.dumps({"type": "assistant", "timestamp": "2026-06-20T15:03:00Z", "cwd": "/x/proj", "message": "nope"}),  # non-dict message
        json.dumps({"type": "assistant", "timestamp": "2026-06-20T15:04:00Z", "cwd": "/x/proj", "message": {"usage": [1, 2]}}),  # non-dict usage
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


def test_project_label_handles_both_separators():
    assert _project_label("/home/me/dev/proj") == "proj"
    assert _project_label("/home/me/dev/proj/") == "proj"
    assert _project_label("C:\\Users\\me\\dev\\proj") == "proj"
    assert _project_label("C:\\Users\\me\\dev\\proj\\") == "proj"
