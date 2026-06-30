# Changelog

All notable changes to Portmint Pulse are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project uses
[Semantic Versioning](https://semver.org/).

## [1.1.0] — 2026-06-29

### Added
- **Status line** (`portmint-pulse statusline`) — renders the Claude Code status line from the JSON
  blob Claude Code pipes on stdin every turn. Shows the rate-limit window closest to its limit
  (5h / 7d / Opus / Sonnet) as a mint→amber→red bar with a reset countdown, plus session cost — with
  **no extra API call and no token cost** — and falls back to context-window % when limits aren't
  present. Defensive (never blank, never non-zero exit, no network); preview with `--demo`. Configure
  via one `statusLine` block in `~/.claude/settings.json`.

## [1.0.0] — 2026-06-25

First public release.

### Added
- Local Claude Code usage dashboard: live limit windows, Today/Week/Lifetime cards, token & cost
  trend charts, and per-model / per-project breakdowns.
- **Selectable time range** (Day · Week · Month · 3M · 6M · Year · up to **5 years**) driving the trend
  charts, the period summary, and the breakdowns. The chart auto-buckets to the window — **hourly** for
  the Day view (read on demand), daily, weekly, then **monthly** for multi-year views. Served via
  `/api/stats?range=<key>`.
- Cross-platform support for **macOS, Windows, and Linux/WSL**:
  - Credentials read from the `~/.claude/.credentials.json` file on all platforms, with the macOS
    login **Keychain** as the fallback when the file is absent or has no usable token.
  - Local-timezone day bucketing by default, with a `--timezone` override; Windows pulls in `tzdata`
    automatically for named zones.
  - Terminal colors that enable VT mode on Windows and respect `NO_COLOR`.
- Installable as the `portmint-pulse` console script via `pipx` / `uv` / `pip`, or run from a checkout
  with `python3 app.py` / `python -m portmint_pulse`.
- `--projects-dir` override (and `PULSE_PROJECTS_DIR` / `PULSE_TIMEZONE` env vars).
- Offline `pytest` suite with synthetic fixtures; CI across macOS/Windows/Linux and Python 3.9–3.13.
- `tools/gen_demo.py` to preview the dashboard on fabricated data, and `tools/build_static_demo.py`
  + a hosted **GitHub Pages live demo** (synthetic data, runs entirely in the browser).
- Live limits are cached (~180s TTL) with **429 backoff** and last-good fallback, so the bars stay
  steady and `/api/stats` never blocks on a slow/rate-limited usage API.
- DST-aware local-timezone resolution on macOS/Linux (resolves the IANA zone); Windows falls back to
  a fixed-offset zone — use `--timezone` there for a named zone. The dashboard labels the zone it's
  actually using (no more hardcoded Eastern).
- Friendly **empty-state** panel for a brand-new install, amber callouts for limit errors, and
  HTML-escaped project/model names.
- Transcript cache keyed on `(mtime, size)` so same-mtime appends aren't missed; macOS Keychain is
  consulted even when a tokenless credentials file exists.
- A loud warning when binding a non-loopback `--host`.

### Accuracy & reliability
- **Dedupe transcript records by `requestId`.** Claude Code logs the same request
  multiple times (often 2–10×, sometimes with 0/1-token placeholders), so naive
  summing over-counted tokens & cost ~2.3× on real data. Pulse now counts each
  request once (keeping its richest usage), in both the daily and hourly views.
- Raise the live-limits poll TTL to **180s** with **exponential 429 backoff**
  (180→360→720s, capped 15 min), so a fast dashboard refresh never risks
  rate-limiting your real Claude token.

### Privacy
- The dashboard page makes zero outbound requests (no web fonts/CDNs).
- The OAuth token is used only for the single live-limits request to `api.anthropic.com`.
