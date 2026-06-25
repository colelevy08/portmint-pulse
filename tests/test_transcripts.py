"""Tests for transcript parsing + aggregation, using synthetic JSONL fixtures.

These never touch a real ~/.claude directory — each test writes its own fake
projects tree into a tmp_path and points the store at it. Day bucketing uses a
fixed UTC zone so results are identical on every machine/CI runner.
"""

import json
from datetime import timezone

from portmint_pulse.transcripts import TranscriptStore, _project_label


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


def test_project_label_handles_both_separators():
    assert _project_label("/home/me/dev/proj") == "proj"
    assert _project_label("/home/me/dev/proj/") == "proj"
    assert _project_label("C:\\Users\\me\\dev\\proj") == "proj"
    assert _project_label("C:\\Users\\me\\dev\\proj\\") == "proj"
