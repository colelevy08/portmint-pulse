"""Tests for the persistent usage archive — history must survive Claude Code
deleting old transcripts (its 30-day cleanup), including deletions that happen
while Pulse isn't running."""

import json
import os
from datetime import datetime, timedelta, timezone

from portmint_pulse import archive
from portmint_pulse.transcripts import TranscriptStore


def _write_jsonl(path, records):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r) + "\n")


def _assistant(model, ts, cwd, rid=None, **usage):
    obj = {
        "type": "assistant",
        "timestamp": ts,
        "cwd": cwd,
        "message": {"model": model, "usage": usage},
    }
    if rid is not None:
        obj["requestId"] = rid
    return obj


def _ago_iso(days=0, hour=12):
    dt = (datetime.now(timezone.utc) - timedelta(days=days)).replace(
        hour=hour, minute=0, second=0, microsecond=0
    )
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_archive_roundtrip(tmp_path):
    path = str(tmp_path / "nested" / "archive.json")
    files = {"/a/b.jsonl": {"mtime": 1.0, "size": 2, "session_id": "b", "project": "p", "by_day": {}}}
    assert archive.save(path, files)
    assert archive.load(path) == files


def test_archive_load_tolerates_garbage(tmp_path):
    path = tmp_path / "archive.json"
    path.write_text("not json at all", encoding="utf-8")
    assert archive.load(str(path)) == {}
    path.write_text(json.dumps({"version": 999, "files": {}}), encoding="utf-8")
    assert archive.load(str(path)) == {}
    assert archive.load(str(tmp_path / "missing.json")) == {}


def test_deleted_transcript_history_survives(tmp_path):
    # A transcript is parsed, then Claude Code prunes it — its usage must keep counting.
    projects = tmp_path / "projects"
    f = projects / "enc" / "s1.jsonl"
    _write_jsonl(f, [_assistant("claude-haiku-4-5", _ago_iso(1), "/x/proj", input_tokens=1_000_000)])

    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store.refresh()
    assert store.aggregate("month")["lifetime"]["tokens"]["total"] == 1_000_000

    os.unlink(f)  # simulate Claude Code's cleanupPeriodDays pruning
    store.refresh()
    data = store.aggregate("month")
    assert data["lifetime"]["tokens"]["total"] == 1_000_000  # history retained
    assert data["archived_files"] == 1
    assert data["transcript_files"] == 0
    # Cost and project attribution survive too.
    assert data["models"][0]["name"] == "claude-haiku-4-5"
    assert data["models"][0]["cost"] == 1.0
    assert data["projects"][0]["name"] == "proj"


def test_history_survives_pruning_while_pulse_was_not_running(tmp_path):
    # Store A sees the file and persists its summary. The file is deleted while
    # nothing is running. A brand-new store B must still count it.
    projects = tmp_path / "projects"
    f = projects / "enc" / "s1.jsonl"
    _write_jsonl(f, [_assistant("claude-haiku-4-5", _ago_iso(1), "/x/proj", input_tokens=500)])

    store_a = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store_a.refresh()

    os.unlink(f)

    store_b = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store_b.refresh()
    data = store_b.aggregate("month")
    assert data["lifetime"]["tokens"]["total"] == 500
    assert data["archived_files"] == 1


def test_live_file_outranks_its_archived_twin(tmp_path):
    # If a path exists both on disk and in the archive, the live parse wins —
    # no double counting.
    projects = tmp_path / "projects"
    f = projects / "enc" / "s1.jsonl"
    _write_jsonl(f, [_assistant("claude-haiku-4-5", _ago_iso(1), "/x/proj", input_tokens=100)])

    store_a = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store_a.refresh()  # persists the summary while the file is still live

    store_b = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store_b.refresh()  # file still exists → live parse, archived twin dropped
    data = store_b.aggregate("month")
    assert data["lifetime"]["tokens"]["total"] == 100  # not 200
    assert data["archived_files"] == 0


def test_missing_projects_dir_still_serves_archived_history(tmp_path):
    projects = tmp_path / "projects"
    f = projects / "enc" / "s1.jsonl"
    _write_jsonl(f, [_assistant("claude-haiku-4-5", _ago_iso(1), "/x/proj", input_tokens=42)])

    store_a = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store_a.refresh()

    os.unlink(f)
    os.rmdir(projects / "enc")
    os.rmdir(projects)  # whole tree gone

    store_b = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store_b.refresh()
    assert store_b.aggregate("month")["lifetime"]["tokens"]["total"] == 42


def test_archiving_disabled_with_empty_path(tmp_path):
    projects = tmp_path / "projects"
    f = projects / "enc" / "s1.jsonl"
    _write_jsonl(f, [_assistant("claude-haiku-4-5", _ago_iso(1), "/x/proj", input_tokens=7)])

    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects), archive_path="")
    store.refresh()
    os.unlink(f)
    store.refresh()
    # No archive → deleting the transcript really does drop the history.
    assert store.aggregate("month")["lifetime"]["tokens"]["total"] == 0
    assert not os.path.exists(archive.default_path())


def test_unpriced_models_are_surfaced(tmp_path):
    projects = tmp_path / "projects"
    _write_jsonl(projects / "enc" / "s1.jsonl", [
        _assistant("some-future-model-9", _ago_iso(1), "/x/proj", input_tokens=10),
        _assistant("<synthetic>", _ago_iso(1), "/x/proj", input_tokens=10),
    ])
    store = TranscriptStore(tz=timezone.utc, projects_dir=str(projects))
    store.refresh()
    data = store.aggregate("month")
    assert data["unpriced_models"] == ["some-future-model-9"]  # synthetic excluded
    assert data["lifetime"]["tokens"]["total"] == 20  # tokens still counted
