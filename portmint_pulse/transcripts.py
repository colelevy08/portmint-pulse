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
default), so "today" and every trend bucket — hourly through monthly across the
selectable ranges — line up with the user's own calendar.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone, tzinfo
from typing import TypedDict

from . import archive, pricing


def _claude_config_dir() -> str:
    """Claude Code's config directory — honours CLAUDE_CONFIG_DIR like Claude
    Code itself does, so relocated installs still show their usage."""
    return os.path.expanduser(os.environ.get("CLAUDE_CONFIG_DIR") or "~/.claude")


# Where Claude Code keeps its per-session transcripts (override-able for tests).
PROJECTS_DIR = os.path.join(_claude_config_dir(), "projects")


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
    size: int
    session_id: str
    project: str
    # by_day[day_str][model] -> _Bucket
    by_day: dict[str, dict[str, _Bucket]] = field(default_factory=dict)
    first_ts: datetime | None = None
    last_ts: datetime | None = None


def _summary_to_dict(s: _FileSummary) -> dict:
    """Serialize a _FileSummary for the on-disk archive (compact arrays)."""
    return {
        "mtime": s.mtime,
        "size": s.size,
        "session_id": s.session_id,
        "project": s.project,
        "first_ts": s.first_ts.isoformat() if s.first_ts else None,
        "last_ts": s.last_ts.isoformat() if s.last_ts else None,
        "by_day": {
            day: {
                model: [b.messages, b.input, b.output, b.cache_read, b.cache_write_5m, b.cache_write_1h]
                for model, b in models.items()
            }
            for day, models in s.by_day.items()
        },
    }


def _summary_from_dict(d: dict) -> _FileSummary | None:
    """Rebuild a _FileSummary from an archived dict; None if malformed.

    Fully defensive — the archive is user-editable JSON, and one bad entry must
    not take down the whole history.
    """
    try:
        summary = _FileSummary(
            mtime=float(d.get("mtime", 0.0)),
            size=int(d.get("size", 0)),
            session_id=str(d.get("session_id", "")),
            project=str(d.get("project", "(unknown)")),
            first_ts=_parse_ts(d.get("first_ts")),
            last_ts=_parse_ts(d.get("last_ts")),
        )
        by_day = d.get("by_day")
        if not isinstance(by_day, dict):
            return None
        for day, models in by_day.items():
            if not isinstance(models, dict):
                continue
            for model, row in models.items():
                if not isinstance(row, list) or len(row) != 6:
                    continue
                summary.by_day.setdefault(str(day), {})[str(model)] = _Bucket(
                    messages=int(row[0]), input=int(row[1]), output=int(row[2]),
                    cache_read=int(row[3]), cache_write_5m=int(row[4]), cache_write_1h=int(row[5]),
                )
        return summary
    except (TypeError, ValueError):
        return None


def _parse_ts(raw: object) -> datetime | None:
    """Parse an ISO-8601 timestamp (the transcripts use a trailing 'Z').

    Always returns a timezone-AWARE datetime — if the string carries no offset we
    assume UTC — so a file that mixes naive and aware records never blows up on a
    comparison. Non-string input returns None rather than raising.
    """
    if not isinstance(raw, str) or not raw:
        return None
    try:
        # fromisoformat handles offsets; normalise the Zulu suffix first.
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _as_int(value: object) -> int:
    """Coerce a token count to int, treating missing/None/garbage as 0.

    Transcripts are files we don't control; a stray ``null``, string, or list in a
    token field must not crash the whole scan. Only the sensibly-numeric shapes
    (int/float/numeric-string) convert; everything else becomes 0.
    """
    if isinstance(value, bool):  # bool is an int subclass — count it as a number
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value or 0)
        except ValueError:
            return 0
    return 0


def _extract_record(obj: object) -> tuple[datetime, str, int, int, int, int, int] | None:
    """Pull one assistant turn's (timestamp, model, token counts) from a parsed
    JSON line, or None if it isn't a usable assistant record. Fully defensive — a
    malformed shape returns None rather than raising. Shared by the file summariser
    and the on-demand hourly pass so both treat records identically.
    """
    if not isinstance(obj, dict) or obj.get("type") != "assistant":
        return None
    ts = _parse_ts(obj.get("timestamp", ""))
    if ts is None:
        return None
    msg = obj.get("message")
    msg = msg if isinstance(msg, dict) else {}
    usage = msg.get("usage")
    usage = usage if isinstance(usage, dict) else {}
    model = msg.get("model")
    model = model if isinstance(model, str) and model else "(none)"
    inp = _as_int(usage.get("input_tokens"))
    out = _as_int(usage.get("output_tokens"))
    cr = _as_int(usage.get("cache_read_input_tokens"))
    cc = usage.get("cache_creation")
    cc = cc if isinstance(cc, dict) else {}
    cw5 = _as_int(cc.get("ephemeral_5m_input_tokens"))
    cw1 = _as_int(cc.get("ephemeral_1h_input_tokens"))
    if cw5 == 0 and cw1 == 0:
        cw5 = _as_int(usage.get("cache_creation_input_tokens"))
    return (ts, model, inp, out, cr, cw5, cw1)


# A parsed assistant turn: (timestamp, model, input, output, cache_read, cw5, cw1).
_Record = tuple[datetime, str, int, int, int, int, int]


def _request_id(obj: dict) -> str | None:
    """The id identifying one Claude request — used to dedupe repeated log entries.
    Prefers the top-level ``requestId``, falling back to ``message.id``."""
    rid = obj.get("requestId")
    if isinstance(rid, str) and rid:
        return rid
    msg = obj.get("message")
    mid = msg.get("id") if isinstance(msg, dict) else None
    return mid if isinstance(mid, str) and mid else None


def _record_total(rec: _Record) -> int:
    """Total tokens in a record (to keep the richest of duplicate log entries)."""
    return rec[2] + rec[3] + rec[4] + rec[5] + rec[6]


def _read_file(path: str) -> tuple[list[_Record], dict[str, int]]:
    """Single-pass read of one transcript file → (deduped records, cwd counter).

    Claude Code logs the SAME ``requestId`` multiple times — verified on real data
    to be *streaming partials of one turn*: input + cache tokens are constant and
    only ``output_tokens`` grows. So summing every line double-counts (≈2.3× on real
    data) — we keep ONE record per request: the one with the most tokens (the final
    partial). Do NOT change this to sum the partials; that re-introduces the bug.
    Records with no request id are kept individually (we can't tell duplicates apart).

    Scope note: dedup is PER FILE. On observed data no requestId ever spans two
    files, so this is exact; if a future Claude Code ever forks/resumes a session
    and copies a requestId into a second file, it would be counted once per file —
    revisit (dedup globally in the aggregation layer) if that's ever observed.
    Defensive against malformed lines throughout.
    """
    by_request: dict[str, _Record] = {}
    no_id: list[_Record] = []
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
                    continue
                if not isinstance(obj, dict):
                    continue
                cwd = obj.get("cwd")
                if isinstance(cwd, str) and cwd:
                    cwd_counts[cwd] += 1
                try:
                    rec = _extract_record(obj)
                    if rec is None:
                        continue
                    rid = _request_id(obj)
                    if rid is None:
                        no_id.append(rec)
                        continue
                    prev = by_request.get(rid)
                    if prev is None or _record_total(rec) > _record_total(prev):
                        by_request[rid] = rec
                except (ValueError, TypeError, AttributeError):
                    continue
    except OSError:
        # File vanished/unreadable mid-read — return whatever we gathered.
        pass
    return list(by_request.values()) + no_id, cwd_counts


class _RangeSpec(TypedDict):
    days: int   # how far back, inclusive of today
    unit: str   # chart bucket size: "hour" | "day" | "week" | "month"
    label: str  # human label for the period


# The selectable trend ranges. "5year" is the cap on how much we ever chart.
RANGES: dict[str, _RangeSpec] = {
    "day": {"days": 1, "unit": "hour", "label": "today"},
    "week": {"days": 7, "unit": "day", "label": "the last 7 days"},
    "month": {"days": 30, "unit": "day", "label": "the last 30 days"},
    "3month": {"days": 91, "unit": "day", "label": "the last 3 months"},
    "6month": {"days": 182, "unit": "week", "label": "the last 6 months"},
    "year": {"days": 365, "unit": "week", "label": "the last year"},
    "5year": {"days": 1826, "unit": "month", "label": "the last 5 years"},
}
DEFAULT_RANGE = "month"


def _bucket_label(d: datetime, unit: str) -> tuple[str, str]:
    """A (key, display-label) for the calendar day ``d`` at a chart granularity.

    Days with the same key fold into one bar. Uses only cross-platform strftime
    codes (no ``%-d``, which breaks on Windows).
    """
    if unit == "week":
        monday = d - timedelta(days=d.weekday())
        return monday.strftime("%Y-%m-%d"), monday.strftime("%m/%d")
    if unit == "month":
        return d.strftime("%Y-%m"), d.strftime("%b '%y")
    return d.strftime("%Y-%m-%d"), d.strftime("%m-%d")


def _project_label(cwd: str) -> str:
    """Turn a working-directory path into a short project name.

    Handles both POSIX and Windows separators so a transcript recorded on Windows
    (``C:\\Users\\me\\dev\\proj``) labels as ``proj`` just like ``/home/me/proj``.
    """
    trimmed = cwd.rstrip("/\\")
    # os.path.basename only knows the host separator; split on both to be safe.
    name = trimmed.replace("\\", "/").rsplit("/", 1)[-1]
    return name or cwd


def _summarise_file(path: str, mtime: float, size: int, tz: tzinfo) -> _FileSummary:
    """Read one transcript file and fold it down to a _FileSummary (deduped)."""
    session_id = os.path.splitext(os.path.basename(path))[0]
    summary = _FileSummary(mtime=mtime, size=size, session_id=session_id, project="(unknown)")
    records, cwd_counts = _read_file(path)
    for ts, model, inp, out, cr, cw5, cw1 in records:
        if summary.first_ts is None or ts < summary.first_ts:
            summary.first_ts = ts
        if summary.last_ts is None or ts > summary.last_ts:
            summary.last_ts = ts
        day = ts.astimezone(tz).strftime("%Y-%m-%d")
        bucket = summary.by_day.setdefault(day, {}).setdefault(model, _Bucket())
        bucket.messages += 1
        bucket.input += inp
        bucket.output += out
        bucket.cache_read += cr
        bucket.cache_write_5m += cw5
        bucket.cache_write_1h += cw1
    if cwd_counts:
        summary.project = _project_label(max(cwd_counts, key=lambda c: cwd_counts[c]))
    return summary


class TranscriptStore:
    """Holds the per-file cache and produces aggregated stats on demand."""

    def __init__(self, tz: tzinfo, projects_dir: str = PROJECTS_DIR, archive_path: str | None = None):
        self.tz = tz
        self.projects_dir = projects_dir
        # Where the persistent history archive lives (see archive.py). Pass "" to
        # disable archiving entirely (e.g. throwaway analysis).
        self.archive_path = archive.default_path() if archive_path is None else archive_path
        self._cache: dict[str, _FileSummary] = {}
        # Summaries of transcripts Claude Code has since DELETED (its 30-day
        # cleanup). Loaded from the archive so old usage keeps counting.
        self._archived: dict[str, _FileSummary] = {}
        if self.archive_path:
            for path, d in archive.load(self.archive_path).items():
                restored = _summary_from_dict(d)
                if restored is not None:
                    self._archived[path] = restored
        # Memo for the Day view's hourly pass: (day, file-signature) -> series, so
        # back-to-back Day refreshes don't re-read a big active session file unless
        # it actually changed.
        self._hourly_cache: tuple[str, tuple, list[dict]] | None = None

    def refresh(self) -> int:
        """Re-scan the projects directory, re-parsing only changed files.

        Returns the number of files re-parsed this pass (0 means nothing
        changed since last time).
        """
        reparsed = 0
        seen: set[str] = set()
        if not os.path.isdir(self.projects_dir):
            # No projects dir (fresh machine, or Claude Code moved) — the live
            # cache empties but archived history keeps standing in.
            self._cache.clear()
            self._persist_archive()
            return 0

        for root, _dirs, files in os.walk(self.projects_dir):
            for name in files:
                if not name.endswith(".jsonl"):
                    continue
                path = os.path.join(root, name)
                seen.add(path)
                try:
                    st = os.stat(path)
                    mtime, size = st.st_mtime, st.st_size
                except OSError:
                    continue
                cached = self._cache.get(path)
                # Key on (mtime, size): an append that doesn't bump mtime still grows
                # the file, so size catches changes a coarse mtime would miss.
                if cached is None or cached.mtime != mtime or cached.size != size:
                    self._cache[path] = _summarise_file(path, mtime, size, self.tz)
                    reparsed += 1

        # A file that vanished was pruned by Claude Code's cleanup — move its
        # summary to the archive so its usage keeps counting. With archiving
        # disabled (archive_path=""), vanished files just drop, as before.
        archived_now = 0
        for gone in set(self._cache) - seen:
            if self.archive_path:
                self._archived[gone] = self._cache.pop(gone)
                archived_now += 1
            else:
                del self._cache[gone]
        # A live file always outranks its archived twin (e.g. it was restored).
        for path in seen & set(self._archived):
            del self._archived[path]

        if reparsed or archived_now:
            self._persist_archive()
        return reparsed

    def _persist_archive(self) -> None:
        """Write every summary we know about (live + already-archived) to disk.

        Live files are included so history survives even when transcripts are
        pruned while Pulse isn't running — next launch, the missing files are
        simply served from the archive.
        """
        if not self.archive_path:
            return
        files = {p: _summary_to_dict(s) for p, s in self._archived.items()}
        files.update({p: _summary_to_dict(s) for p, s in self._cache.items()})
        archive.save(self.archive_path, files)

    def _all_summaries(self):
        """Every summary that should count: live transcripts + archived history.

        Archived entries whose path is currently live are already pruned in
        refresh(), so this never double-counts a session.
        """
        yield from self._cache.values()
        yield from self._archived.values()

    def hourly_series(self, day_str: str) -> list[dict]:
        """Token/cost per hour (0–23) for one local calendar day — for the Day view.

        Re-reads only the file(s) that touched ``day_str`` (usually just the active
        session), so we get hour resolution without storing hourly data for all of
        history.
        """
        tz = self.tz
        # Only the file(s) that touched this day matter; signature on their
        # (mtime, size) so an unchanged active session is served from the memo.
        relevant = sorted((p, s.mtime, s.size) for p, s in self._cache.items() if day_str in s.by_day)
        signature = tuple(relevant)
        if self._hourly_cache is not None and self._hourly_cache[0] == day_str and self._hourly_cache[1] == signature:
            return self._hourly_cache[2]

        hours = [{"tokens": 0, "cost": 0.0} for _ in range(24)]
        for path, _mtime, _size in relevant:
            # _read_file dedupes by requestId, so the hourly view doesn't double-count
            # the same way the daily summaries don't.
            records, _cwd = _read_file(path)
            for ts, model, inp, out, cr, cw5, cw1 in records:
                local = ts.astimezone(tz)
                if local.strftime("%Y-%m-%d") != day_str:
                    continue
                cell = hours[local.hour]
                cell["tokens"] += inp + out + cr + cw5 + cw1
                cell["cost"] += pricing.price(
                    model, input_tokens=inp, output_tokens=out,
                    cache_read=cr, cache_write_5m=cw5, cache_write_1h=cw1,
                )
        result = [{"label": f"{h:02d}:00", "tokens": hours[h]["tokens"], "cost": round(hours[h]["cost"], 4)} for h in range(24)]
        self._hourly_cache = (day_str, signature, result)
        return result

    def aggregate(self, range_key: str = DEFAULT_RANGE) -> dict:
        """Roll the cached file summaries up into the dashboard payload.

        ``range_key`` (one of RANGES) selects the trend window: it scopes the chart
        ``series``, the ``period`` totals, and the model/project breakdowns. The
        Today / This week / Lifetime cards are always all-time and ignore it.
        """
        tz = self.tz
        if range_key not in RANGES:
            range_key = DEFAULT_RANGE
        spec = RANGES[range_key]

        now = datetime.now(tz)
        today = now.strftime("%Y-%m-%d")
        days_back = spec["days"]
        start = now - timedelta(days=days_back - 1)
        window_days = {(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(days_back)}

        # All-day accumulators — drive Today/Week/Lifetime and the chart series.
        day_tokens: dict[str, dict[str, int]] = defaultdict(
            lambda: {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "messages": 0}
        )
        day_cost: dict[str, float] = defaultdict(float)
        day_sessions: dict[str, set[str]] = defaultdict(set)

        # Breakdown accumulators — only the selected window.
        model_tokens: dict[str, int] = defaultdict(int)
        model_cost: dict[str, float] = defaultdict(float)
        model_messages: dict[str, int] = defaultdict(int)
        project_tokens: dict[str, int] = defaultdict(int)
        project_cost: dict[str, float] = defaultdict(float)
        project_messages: dict[str, int] = defaultdict(int)
        project_sessions: dict[str, set[str]] = defaultdict(set)

        first_ts: datetime | None = None
        all_active_days: set[str] = set()
        # Models we couldn't price (unknown ids) — surfaced so a $0 line is a
        # visible diagnostic, not a silent lie. "<synthetic>" is Claude Code's
        # marker for locally-generated turns and is genuinely free, so skip it.
        unpriced: set[str] = set()

        for summary in self._all_summaries():
            if summary.first_ts is not None and (first_ts is None or summary.first_ts < first_ts):
                first_ts = summary.first_ts
            for day, model_buckets in summary.by_day.items():
                all_active_days.add(day)
                in_window = day in window_days
                for model, b in model_buckets.items():
                    total = b.input + b.output + b.cache_read + b.cache_write_5m + b.cache_write_1h
                    if total > 0 and model not in ("<synthetic>", "(none)") and pricing.normalize_model(model) is None:
                        unpriced.add(model)
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
                    if in_window:
                        label = pricing.normalize_model(model) or (model or "unknown")
                        model_tokens[label] += total
                        model_cost[label] += cost
                        model_messages[label] += b.messages
                        project_tokens[summary.project] += total
                        project_cost[summary.project] += cost
                        project_messages[summary.project] += b.messages
                        project_sessions[summary.project].add(summary.session_id)

        def window_totals(days: set[str]) -> dict:
            tok = {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0}
            messages = 0
            cost = 0.0
            sessions: set[str] = set()
            for d in days:
                row = day_tokens.get(d)
                if row is None:
                    continue
                for k in tok:
                    tok[k] += row[k]
                messages += row["messages"]
                cost += day_cost[d]
                sessions |= day_sessions[d]
            tok["total"] = sum(tok.values())
            return {"tokens": tok, "messages": messages, "cost": round(cost, 4), "sessions": len(sessions)}

        today_block = window_totals({today})
        today_block["date"] = today
        week_block = window_totals({(now - timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)})
        lifetime_block = window_totals(set(day_tokens.keys()))
        lifetime_block["first_session_date"] = first_ts.astimezone(tz).strftime("%Y-%m-%d") if first_ts else None
        lifetime_block["active_days"] = len(all_active_days)

        period_block = window_totals(window_days)
        period_block["range"] = range_key
        period_block["label"] = spec["label"]

        # Chart series for the selected range ---------------------------------
        unit = spec["unit"]
        if unit == "hour":
            series = self.hourly_series(today)
        else:
            buckets: dict[str, dict] = {}
            cur = datetime(start.year, start.month, start.day)
            end = datetime(now.year, now.month, now.day)
            while cur <= end:
                ds = cur.strftime("%Y-%m-%d")
                key, lbl = _bucket_label(cur, unit)
                bk = buckets.get(key)
                if bk is None:
                    bk = {"label": lbl, "tokens": 0, "cost": 0.0}
                    buckets[key] = bk
                row = day_tokens.get(ds)
                if row:
                    bk["tokens"] += row["input"] + row["output"] + row["cache_read"] + row["cache_write"]
                    bk["cost"] += day_cost.get(ds, 0.0)
                cur += timedelta(days=1)
            series = [{"label": v["label"], "tokens": v["tokens"], "cost": round(v["cost"], 4)} for v in buckets.values()]

        # Breakdowns (scoped to the window), sorted by cost then tokens -------
        models = sorted(
            (
                {"name": n, "tokens": model_tokens[n], "cost": round(model_cost[n], 4), "messages": model_messages[n]}
                for n in model_tokens
            ),
            key=lambda m: (m["cost"], m["tokens"]),
            reverse=True,
        )
        projects = sorted(
            (
                {
                    "name": n,
                    "tokens": project_tokens[n],
                    "cost": round(project_cost[n], 4),
                    "messages": project_messages[n],
                    "sessions": len(project_sessions[n]),
                }
                for n in project_tokens
            ),
            key=lambda p: (p["cost"], p["tokens"]),
            reverse=True,
        )

        return {
            "today": today_block,
            "week": week_block,
            "lifetime": lifetime_block,
            "range": range_key,
            "period": period_block,
            "series": series,
            "models": models,
            "projects": projects,
            "transcript_files": len(self._cache),
            # Sessions Claude Code has deleted but we still remember (see archive.py).
            "archived_files": len(self._archived),
            # Raw model ids we couldn't price — their tokens count, their cost is $0.
            "unpriced_models": sorted(unpriced),
        }
