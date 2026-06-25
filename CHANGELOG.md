# Changelog

All notable changes to Portmint Pulse are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/), and the project uses
[Semantic Versioning](https://semver.org/).

## [1.0.0] — 2026-06-25

First public release.

### Added
- Local Claude Code usage dashboard: live limit windows, Today/Week/Lifetime cards, 30-day token &
  cost trend charts, and per-model / per-project breakdowns.
- Cross-platform support for **macOS, Windows, and Linux/WSL**:
  - macOS credentials read from the login **Keychain** (with the `~/.claude/.credentials.json` file
    as the fallback on other platforms).
  - Local-timezone day bucketing by default, with a `--timezone` override; Windows pulls in `tzdata`
    automatically for named zones.
  - Terminal colors that enable VT mode on Windows and respect `NO_COLOR`.
- Installable as the `portmint-pulse` console script via `pipx` / `uv` / `pip`, or run from a checkout
  with `python3 app.py` / `python -m portmint_pulse`.
- `--projects-dir` override (and `PULSE_PROJECTS_DIR` / `PULSE_TIMEZONE` env vars).
- Offline `pytest` suite with synthetic fixtures; CI across macOS/Windows/Linux and Python 3.9–3.13.
- `tools/gen_demo.py` to preview the dashboard on fabricated data.

### Privacy
- The dashboard page makes zero outbound requests (no web fonts/CDNs).
- The OAuth token is used only for the single live-limits request to `api.anthropic.com`.
