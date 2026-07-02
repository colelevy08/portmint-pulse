"""Persistent usage archive — keeps your history when Claude Code deletes it.

Claude Code prunes old session transcripts (the ``cleanupPeriodDays`` setting,
30 days by default). Without an archive, every pruned transcript silently
erases part of your usage history — the dashboard's "lifetime" numbers shrink
over time. This module fixes that: every time Pulse summarises a transcript it
also writes the compact per-file summary here, and when the transcript later
disappears from disk the archived summary keeps standing in for it. Your
history survives as long as you've run Pulse at least once while the
transcripts still existed.

The archive is one JSON file in the platform's per-user data directory
(override with ``PULSE_DATA_DIR``). It stores only the same tiny digests the
in-memory cache holds — day/model token counts, session id, project name —
never message content. Writes are atomic (write-to-temp + rename) so a crash
can't corrupt existing history.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile

# Bump when the on-disk shape changes; unknown versions are ignored (fresh start).
_FORMAT_VERSION = 1


def default_dir() -> str:
    """The per-user data directory for Pulse, following platform conventions.

    ``PULSE_DATA_DIR`` overrides everything (used by tests, and by anyone who
    wants the archive somewhere specific, e.g. a synced folder).
    """
    override = os.environ.get("PULSE_DATA_DIR")
    if override:
        return os.path.expanduser(override)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        return os.path.join(base, "portmint-pulse")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/portmint-pulse")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "portmint-pulse")


def default_path() -> str:
    """Full path of the archive JSON file."""
    return os.path.join(default_dir(), "archive.json")


def load(path: str) -> dict[str, dict]:
    """Read the archive → {transcript path: summary dict}, or {} if absent/bad.

    A corrupt or future-versioned file returns {} rather than raising — the
    archive is a best-effort safety net, never a reason Pulse won't start.
    """
    try:
        with open(path, "r", encoding="utf-8") as fh:
            blob = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(blob, dict) or blob.get("version") != _FORMAT_VERSION:
        return {}
    files = blob.get("files")
    if not isinstance(files, dict):
        return {}
    # Keep only well-shaped entries; one bad row must not poison the rest.
    return {p: s for p, s in files.items() if isinstance(p, str) and isinstance(s, dict)}


def save(path: str, files: dict[str, dict]) -> bool:
    """Atomically write the archive. Returns False (never raises) on failure.

    Written to a temp file in the same directory then renamed, so a crash
    mid-write leaves the previous archive intact.
    """
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        payload = {"version": _FORMAT_VERSION, "files": files}
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".archive-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, separators=(",", ":"))
            os.replace(tmp, path)
        finally:
            # If the rename happened, the temp file is gone; otherwise clean up.
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    except OSError:
        return False
