"""Reads Claude Code's local session transcripts and turns them into stats.

Claude Code writes one JSON-lines file per session under
``~/.claude/projects/<encoded-cwd>/<session-id>.jsonl``. Every assistant turn in
that file records the model used, the exact token usage (input, output, and the
three flavours of cache token), a timestamp, and the working directory. That is
everything we need to reconstruct usage, cost, and per-project breakdowns —
locally, with no cloud telemetry and no platform-specific files.

Performance note: there can be thousands of these files. We parse each one once
and remember a tiny per-file summary keyed by the file's modification time. On
every refresh we only re-read files that actually changed (in practice, just the
session you're using right now). Aggregation then sums the cached summaries,
which is instant.

Day/hour bucketing is done in the timezone passed in (the machine's local zone by
default), so "today" and the 30-day chart line up with the user's own calendar.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

from . import pricing

# Where Claude Code keeps its per-session transcripts (override-able for tests).
PROJECTS_DIR = os.path.expanduser("~/.claude/projects")


@dataclass
class _Bucket:
    """Token counts for one (day, model) cell within a single session file."""

    messages: int = 0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write_5m: int = 0
    cache_write_1h: int = 0


@dataclass
class _FileSummary:
    """The compact, cached digest of one transcript file."""

    mtime: float
    session_id: str
    project: str
    # by_day[day_str][model] -> _Bucket
    by_day: dict[str, dict[str, _Bucket]] = field(default_factory=dict)
    first_ts: datetime | None = None
    last_ts: datetime | None = None


def _parse_ts(raw: str) -> datetime | None:
    """Parse an ISO-8601 timestamp (the transcripts use a trailing 'Z')."""
    if not raw:
        return None
    try:
        # fromisoformat handles offsets; normalise the Zulu suffix first.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _project_label(cwd: str) -> str:
    """Turn a working-directory path into a short project name.

    Handles both POSIX and Windows separators so a transcript recorded on Windows
    (``C:\\Users\\me\\dev\\proj``) labels as ``proj`` just like ``/home/me/proj``.
    """
    trimmed = cwd.rstrip("/\\")
    # os.path.basename only knows the host separator; split on both to be safe.
    name = trimmed.replace("\\", "/").rsplit("/", 1)[-1]
    return name or cwd


def _summarise_file(path: str, mtime: float, tz: tzinfo) -> _FileSummary:
    """Read one transcript file and fold it down to a _FileSummary."""
    session_id = os.path.splitext(os.path.basename(path))[0]
    summary = _FileSummary(mtime=mtime, session_id=session_id, project="(unknown)")
    # We pick the project label from the most common working directory seen.
    cwd_counts: dict[str, int] = defaultdict(int)

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    # A half-written final line in the active session is normal —
                    # skip it rather than failing the whole file.
                    continue

                cwd = obj.get("cwd")
                if cwd:
                    cwd_counts[cwd] += 1

                if obj.get("type") != "assistant":
                    continue

                ts = _parse_ts(obj.get("timestamp", ""))
                if ts is None:
                    continue
                if summary.first_ts is None or ts < summary.first_ts:
                    summary.first_ts = ts
                if summary.last_ts is None or ts > summary.last_ts:
                    summary.last_ts = ts

                msg = obj.get("message", {}) or {}
                usage = msg.get("usage", {}) or {}
                model = msg.get("model")

                # Pull the token counts, defaulting anything missing to zero.
                inp = int(usage.get("input_tokens", 0) or 0)
                out = int(usage.get("output_tokens", 0) or 0)
                cr = int(usage.get("cache_read_input_tokens", 0) or 0)
                # Prefer the precise 5m/1h split when present; otherwise treat the
                # lump-sum cache-creation total as a 5-minute write.
                cc = usage.get("cache_creation", {}) or {}
                cw5 = int(cc.get("ephemeral_5m_input_tokens", 0) or 0)
                cw1 = int(cc.get("ephemeral_1h_input_tokens", 0) or 0)
                if cw5 == 0 and cw1 == 0:
                    cw5 = int(usage.get("cache_creation_input_tokens", 0) or 0)

                day = ts.astimezone(tz).strftime("%Y-%m-%d")
                day_models = summary.by_day.setdefault(day, {})
                bucket = day_models.setdefault(model or "(none)", _Bucket())
                bucket.messages += 1
                bucket.input += inp
                bucket.output += out
                bucket.cache_read += cr
                bucket.cache_write_5m += cw5
                bucket.cache_write_1h += cw1
    except OSError:
        # File vanished or is unreadable — return whatever we have.
        return summary

    if cwd_counts:
        top_cwd = max(cwd_counts, key=cwd_counts.get)
        summary.project = _project_label(top_cwd)
    return summary


class TranscriptStore:
    """Holds the per-file cache and produces aggregated stats on demand."""

    def __init__(self, tz: tzinfo, projects_dir: str = PROJECTS_DIR):
        self.tz = tz
        self.projects_dir = projects_dir
        self._cache: dict[str, _FileSummary] = {}

    def refresh(self) -> int:
        """Re-scan the projects directory, re-parsing only changed files.

        Returns the number of files re-parsed this pass (0 means nothing
        changed since last time).
        """
        reparsed = 0
        seen: set[str] = set()
        if not os.path.isdir(self.projects_dir):
            self._cache.clear()
            return 0

        for root, _dirs, files in os.walk(self.projects_dir):
            for name in files:
                if not name.endswith(".jsonl"):
                    continue
                path = os.path.join(root, name)
                seen.add(path)
                try:
                    mtime = os.path.getmtime(path)
                except OSError:
                    continue
                cached = self._cache.get(path)
                if cached is None or cached.mtime != mtime:
                    self._cache[path] = _summarise_file(path, mtime, self.tz)
                    reparsed += 1

        # Drop cache entries for files that have been deleted.
        for gone in set(self._cache) - seen:
            del self._cache[gone]
        return reparsed

    def aggregate(self) -> dict:
        """Roll the cached file summaries up into the dashboard payload."""
        tz = self.tz
        # Accumulators -------------------------------------------------------
        # day -> totals (and the set of session ids active that day)
        day_tokens: dict[str, dict[str, int]] = defaultdict(
            lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "messages": 0}
        )
        day_cost: dict[str, float] = defaultdict(float)
        day_sessions: dict[str, set[str]] = defaultdict(set)

        model_tokens: dict[str, int] = defaultdict(int)
        model_cost: dict[str, float] = defaultdict(float)
        model_messages: dict[str, int] = defaultdict(int)

        project_tokens: dict[str, int] = defaultdict(int)
        project_cost: dict[str, float] = defaultdict(float)
        project_sessions: dict[str, set[str]] = defaultdict(set)
        project_messages: dict[str, int] = defaultdict(int)

        first_ts: datetime | None = None
        all_active_days: set[str] = set()

        for summary in self._cache.values():
            if summary.first_ts is not None:
                if first_ts is None or summary.first_ts < first_ts:
                    first_ts = summary.first_ts
            for day, models in summary.by_day.items():
                all_active_days.add(day)
                for model, b in models.items():
                    total = (
                        b.input + b.output + b.cache_read + b.cache_write_5m + b.cache_write_1h
                    )
                    cost = pricing.price(
                        model,
                        input_tokens=b.input,
                        output_tokens=b.output,
                        cache_read=b.cache_read,
                        cache_write_5m=b.cache_write_5m,
                        cache_write_1h=b.cache_write_1h,
                    )

                    dt = day_tokens[day]
                    dt["input"] += b.input
                    dt["output"] += b.output
                    dt["cache_read"] += b.cache_read
                    dt["cache_write"] += b.cache_write_5m + b.cache_write_1h
                    dt["messages"] += b.messages
                    day_cost[day] += cost
                    day_sessions[day].add(summary.session_id)

                    label = pricing.normalize_model(model) or (model or "unknown")
                    model_tokens[label] += total
                    model_cost[label] += cost
                    model_messages[label] += b.messages

                    project_tokens[summary.project] += total
                    project_cost[summary.project] += cost
                    project_sessions[summary.project].add(summary.session_id)
                    project_messages[summary.project] += b.messages

        # Windows ------------------------------------------------------------
        now = datetime.now(tz)
        today = now.strftime("%Y-%m-%d")
        week_days = {(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)}

        def window_totals(days: set[str]) -> dict:
            tok = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
            messages = 0
            cost = 0.0
            sessions: set[str] = set()
            for d in days:
                if d not in day_tokens:
                    continue
                for k in tok:
                    tok[k] += day_tokens[d][k]
                messages += day_tokens[d]["messages"]
                cost += day_cost[d]
                sessions |= day_sessions[d]
            tok["total"] = sum(tok.values())
            return {"tokens": tok, "messages": messages, "cost": round(cost, 4), "sessions": len(sessions)}

        today_block = window_totals({today})
        today_block["date"] = today
        week_block = window_totals(week_days)

        # Lifetime -----------------------------------------------------------
        life_tokens = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
        life_messages = 0
        life_cost = 0.0
        life_sessions: set[str] = set()
        for d in day_tokens:
            for k in life_tokens:
                life_tokens[k] += day_tokens[d][k]
            life_messages += day_tokens[d]["messages"]
            life_cost += day_cost[d]
            life_sessions |= day_sessions[d]
        life_tokens["total"] = sum(life_tokens.values())

        lifetime_block = {
            "tokens": life_tokens,
            "messages": life_messages,
            "cost": round(life_cost, 4),
            "sessions": len(life_sessions),
            "first_session_date": first_ts.astimezone(tz).strftime("%Y-%m-%d") if first_ts else None,
            "active_days": len(all_active_days),
        }

        # 30-day daily series (ascending) for the charts ---------------------
        daily = []
        for i in range(29, -1, -1):
            d = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            dt = day_tokens.get(d)
            if dt:
                tokens = dt["input"] + dt["output"] + dt["cache_read"] + dt["cache_write"]
                daily.append({
                    "date": d,
                    "tokens": tokens,
                    "cost": round(day_cost[d], 4),
                    "messages": dt["messages"],
                })
            else:
                daily.append({"date": d, "tokens": 0, "cost": 0.0, "messages": 0})

        # Model + project breakdowns (sorted by cost, then tokens) -----------
        models = sorted(
            (
                {
                    "name": name,
                    "tokens": model_tokens[name],
                    "cost": round(model_cost[name], 4),
                    "messages": model_messages[name],
                }
                for name in model_tokens
            ),
            key=lambda m: (m["cost"], m["tokens"]),
            reverse=True,
        )
        projects = sorted(
            (
                {
                    "name": name,
                    "tokens": project_tokens[name],
                    "cost": round(project_cost[name], 4),
                    "messages": project_messages[name],
                    "sessions": len(project_sessions[name]),
                }
                for name in project_tokens
            ),
            key=lambda p: (p["cost"], p["tokens"]),
            reverse=True,
        )

        return {
            "today": today_block,
            "week": week_block,
            "lifetime": lifetime_block,
            "daily": daily,
            "models": models,
            "projects": projects,
            "transcript_files": len(self._cache),
        }
