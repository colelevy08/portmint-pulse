<div align="center">

<img src="https://raw.githubusercontent.com/colelevy08/portmint-pulse/main/assets/logo.svg" width="84" alt="Portmint Pulse" />

# Portmint&nbsp;Pulse

**Your Claude Code usage, minted locally.**

A private, local-first dashboard for everything Claude Code is doing on this machine —
live rate-limit windows, daily / weekly / lifetime token & cost, per-model and
per-project breakdowns, and trend charts spanning a day up to 5 years.

*Pure Python standard library. No build step. No cloud. No telemetry. Runs on macOS, Windows, and Linux/WSL.*

[![CI](https://github.com/colelevy08/portmint-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/colelevy08/portmint-pulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-34e0b3.svg)](https://github.com/colelevy08/portmint-pulse/blob/main/LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-2bd3a6.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platforms-macOS%20%C2%B7%20Windows%20%C2%B7%20Linux-0ea5e9.svg)](#install)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-5cf0c4.svg)](https://github.com/colelevy08/portmint-pulse/blob/main/CONTRIBUTING.md)

<img src="https://raw.githubusercontent.com/colelevy08/portmint-pulse/main/assets/screenshot.png" width="860" alt="Portmint Pulse dashboard" />

### ▶ **[Try the live demo →](https://colelevy08.github.io/portmint-pulse/)**  ·  no install, runs in your browser on fabricated data

</div>

---

## Why this exists

Claude Code records a wealth of usage data on your disk, but gives you no easy way to *see* it.
Most tools that do are either terminal-only, macOS-only, or need a Node toolchain. Portmint Pulse is
a **visual browser dashboard** computed from the raw data Claude Code already writes locally — no
Apple frameworks, no observability stack, no `npm`, no database, nothing to set up.

| | Portmint Pulse | [claude-pulseinator](https://github.com/mikelane/claude-pulseinator) | [ccusage](https://github.com/ryoppippi/ccusage) |
|---|---|---|---|
| Form | **web dashboard** (charts, gauges) | macOS menubar | CLI text reports |
| Runs on macOS / Windows / Linux | **✅ / ✅ / ✅** | ✅ / ❌ / ❌ | ✅ / ✅ / ✅ |
| Live OAuth limit bars | ✅ 4 windows (5h, 7d all-models, 7d Opus, 7d Sonnet) + pay-as-you-go credits | ✅ | infers from local data |
| Token / cost history | ✅ computed locally, **no setup** | uses SigNoz + OpenTelemetry | ✅ |
| Per-project breakdown | ✅ visual bars | ❌ | ✅ (text) |
| Dependencies | **Python stdlib only** | a Swift toolchain | a Node toolchain |

<sub>Comparison as of 2026-06; based on each project's public README. See [How Pulse compares](#how-pulse-compares) for the fuller, honest picture.</sub>

**Privacy, in three lines** — the whole pitch:

- 🔒 **Read-only.** It only reads files Claude Code already wrote; it never writes or deletes anything.
- 📡 **One outbound call.** Your token is used in exactly one request — to `api.anthropic.com` for your
  live limits (the same call Claude Code makes). The dashboard page itself fetches **nothing** (no fonts/CDNs).
- 🏠 **Localhost only.** Binds to `127.0.0.1`; no telemetry, no analytics, no database.

---

## What you get

- **Usage limits** — pulled live from your Claude Code login token: the 5-hour session window,
  the 7-day all-models window, the 7-day Opus and Sonnet windows, and any pay-as-you-go credit balance.
  Bars go mint → amber → red with reset countdowns.
- **At a glance** — Today / This week / Lifetime cards: estimated cost, tokens, messages, sessions.
- **Usage over time** — a **range selector** (Day · Week · Month · 3M · 6M · Year · **up to 5 years**)
  drives the tokens & cost area charts, which auto-bucket to fit the window — **hourly** for a single
  day, daily, weekly, then **monthly** for multi-year views (hand-drawn SVG, hover for exact values).
- **By model** / **By project** — tokens & cost per Claude model / working directory for the selected
  range, ranked by spend.
- **Money's worth** — your last-30-days usage priced at API rates vs your flat subscription (Pro / Max 5× /
  Max 20×, remembered locally): a single *"you're getting **N× your subscription's worth**"* multiplier.
  Also in `summary --plan`.

Auto-refreshes every 60 seconds; manual **Refresh** button in the header. Days are bucketed in **your
machine's local timezone** by default (`--timezone` to override).

---

## Status line — your live limits, every turn

The dashboard is the deep-dive; the **status line** keeps Pulse always in view. Claude Code can run a
command after every turn and show its output as a status bar — and the data it pipes already includes
your **live rate-limit windows**, so Pulse renders a glanceable bar **with no extra API call and no
token cost**:

```
[Opus] ▓▓▓▓▓░░░ 62% · 7d-opus 2h14m · $0.06
```

It shows the window closest to its limit (5h / 7d / Opus / Sonnet) in mint → amber → red with a reset
countdown, plus the session cost — and falls back to **context-window %** when limits aren't available
(API-key users, or before the first response). Add this to `~/.claude/settings.json`:

```json
{
  "statusLine": { "type": "command", "command": "portmint-pulse statusline", "padding": 2 }
}
```

This uses the `portmint-pulse` command, which is on your PATH after a `pipx`/`uv`/`pip` install.
**Running from a clone instead?** Point `command` straight at the script — `"python3
/abs/path/to/portmint-pulse/app.py statusline"` (or `"python3 -m portmint_pulse statusline"` if the
package is importable) — otherwise Claude Code silently shows a blank bar. On Windows, write the path
with forward slashes (`C:/Users/you/...`) inside the JSON.

Preview it without configuring anything: `portmint-pulse statusline --demo`. *(Optional: add
`"refreshInterval": 10` to the block so the reset countdown ticks while you're idle.)*

---

## Warn me before the wall — `watch`

Run it in any terminal (or background it) and it fires a **desktop notification** the moment any limit
window crosses **80 / 95 / 100%** — naming which one — so you're never throttled mid-task by surprise:

```bash
portmint-pulse watch                 # poll every 30s; desktop notifications on
portmint-pulse watch --interval 60   # gentler cadence (5–600s)
portmint-pulse watch --no-desktop    # console only
```

Notifications are dependency-free and cross-platform — macOS (`osascript`), Linux (`notify-send`),
**Windows & WSL** (a native toast via PowerShell, no module to install) — and fall back to a console
line if no notifier is available. It reuses the cached limits poll, so it never rate-limits your token,
keeps **no state on disk** (zero telemetry), and re-arms each alert when a new window period begins.

## One-shot `summary`

A quick text (or `--json`) snapshot — no server, no browser:

```bash
portmint-pulse summary          # today / week / lifetime + live limit bars + which binds first
portmint-pulse summary --json   # the same, machine-readable
```

---

## Install

Pick whichever you like — all give you the `portmint-pulse` command (or just run from source).

> **Coming to PyPI** so it'll be a plain `pipx install portmint-pulse` / `uvx portmint-pulse`. Until
> then, install straight from this repo:

### With `pipx` (recommended — isolated, always on your PATH)

```bash
pipx install git+https://github.com/colelevy08/portmint-pulse.git
portmint-pulse
```

### With `uv`

```bash
uv tool install git+https://github.com/colelevy08/portmint-pulse.git
portmint-pulse
```

### With `pip`

```bash
pip install git+https://github.com/colelevy08/portmint-pulse.git
portmint-pulse
```

### From source (no install)

```bash
git clone https://github.com/colelevy08/portmint-pulse.git
cd portmint-pulse
python3 app.py
```

Then open **http://localhost:8787** — it auto-opens a tab. **Requirements:** Python 3.9+ and Claude
Code installed & logged in. On Linux/macOS there are *zero* third-party dependencies; on Windows a
small pure-Python `tzdata` is pulled in automatically (only used if you set `--timezone`).

### Options

```bash
portmint-pulse --port 9000                  # use a different port
portmint-pulse --no-browser                 # don't auto-open a tab
portmint-pulse --host 0.0.0.0               # expose on your LAN — see the warning below
portmint-pulse --timezone America/New_York  # bucket days in a specific zone (default: your local zone)
portmint-pulse --version
```

> ⚠️ `--host 0.0.0.0` (or any non-loopback host) serves your project names and full usage to everyone
> on the network **with no authentication**. Pulse prints a warning when you do this. Only use it on a
> network you trust.

### Keep it running

```bash
# Linux / macOS — start it in the background from your shell rc:
( portmint-pulse --no-browser & ) 2>/dev/null
```

---

## How Pulse compares

The Claude Code usage space is healthy — pick the tool whose *shape* fits you. Pulse is the
**cross-platform visual dashboard with real live limit bars**; here's an honest map of the neighbors:

- **[ccusage](https://github.com/ryoppippi/ccusage)** — the category leader. A fast CLI that prints
  daily/weekly/session token & cost reports (now across ~15 agents). Great if you want terminal text
  and multi-agent coverage; it *infers* limit blocks from local data rather than reading the live
  OAuth windows, and needs a Node toolchain.
- **[Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor)** — a
  beautiful Rich **TUI** focused on real-time burn rate and limit *prediction* (P90). Great if you live
  in the terminal and want forecasting; it's terminal-only with no charts or per-project view.
- **[claude-pulse](https://github.com/NoobyGains/claude-pulse)** (note: similar name) — a single-line
  Claude Code **status line**. Great for an always-visible glance; no dashboard or history.
- **[claude-usage](https://github.com/phuryn/claude-usage)** — the closest analog: a local **web
  dashboard** + VS Code extension backed by SQLite/Chart.js.

**Pulse is Claude Code-focused on purpose.** Want one tool across many agents? `ccusage` is excellent.
Want live limit bars + cost/project charts in a browser, on any OS, with zero dependencies and zero
setup? You're home.

---

## Where the data comes from

| Source | Used for |
|---|---|
| `~/.claude/projects/**/*.jsonl` | Token usage, cost, models, projects, history. One JSON-lines file per session; every assistant turn records its model, exact token counts, timestamp, and working directory. |
| `~/.claude/.credentials.json` (Linux/WSL/Windows) **or** the macOS **Keychain** | The OAuth token, used for one HTTPS call to `api.anthropic.com/api/oauth/usage` to fetch your live limit windows (cached ~180s with exponential 429 backoff). |

### About the cost numbers

The dollar figures are **equivalent API list-price estimates** — what your usage *would* cost at
Anthropic's published per-token API rates. They are **not** your actual subscription billing (a
Claude Max/Pro plan is a flat fee). Treat them as a measure of the *value* you're getting and a
relative gauge across models and projects.

Pricing (per million tokens) lives in one place — `portmint_pulse/pricing.py` — and uses Anthropic's
standard cache multipliers (5-minute cache write = 1.25× input, 1-hour write = 2×, cache read = 0.1×):

| Model | Input | Output |
|---|---|---|
| Opus 4.8 (incl. `[1m]`) | $5 | $25 |
| Opus 4.7 | $5 | $25 |
| Sonnet 4.6 | $3 | $15 |
| Haiku 4.5 | $1 | $5 |
| Fable 5 | $10 | $50 |

A model Pulse doesn't recognize (a brand-new release, or `<synthetic>` local messages) still has its
tokens counted, but is priced at $0 until you add it to `pricing.py`.

---

## Architecture

```
app.py                      # run-from-a-checkout shim → portmint_pulse.cli:main
portmint_pulse/
  cli.py                    # argument parsing, timezone resolution, the startup banner
  pricing.py                # per-token pricing + model-name normalization
  transcripts.py            # parse ~/.claude/projects, incremental (mtime,size) cache, aggregate
  usage.py                  # fetch live limit windows (file or macOS Keychain creds), cached + 429 backoff
  tz.py                     # local-timezone resolution: DST-aware on macOS/Linux, fixed-offset on Windows
  server.py                 # stdlib http.server: serves the page + /api/stats JSON
  web/dashboard.html        # the Portmint-branded single-page UI (inline CSS + SVG charts)
tests/                      # offline pytest suite (synthetic fixtures, no real ~/.claude needed)
tools/gen_demo.py           # generate synthetic data + serve (used for the screenshot/live demo)
```

**Flow:** the browser loads `dashboard.html`, which polls `/api/stats`. That handler re-scans your
transcripts (re-reading only files whose `(mtime, size)` changed — basically the active session),
aggregates the cached per-file summaries, fetches the live limits (served from a short cache), and
returns one JSON snapshot. The first launch indexes every session up front (≈2s for ~1,800 sessions)
so the first page load is instant.

---

## Try it without your own data

The hosted **[live demo](https://colelevy08.github.io/portmint-pulse/)** runs entirely in your browser
on fabricated data. To generate and serve your own demo locally:

```bash
git clone https://github.com/colelevy08/portmint-pulse.git
cd portmint-pulse
python tools/gen_demo.py     # serves a dashboard on fabricated data at http://127.0.0.1:8791
```

---

## How do I debug X?

- **"No Claude Code login found" / "token expired"** — run `claude` once in a terminal and sign in,
  then hit Refresh. The OAuth token expires periodically. On macOS the token lives in the Keychain.
  *(Your local usage history below the limits still works regardless.)*
- **Charts are empty / "No usage yet"** — that panel is expected on a brand-new Claude Code install;
  `~/.claude/projects/` simply has no `.jsonl` sessions yet. It fills in automatically as you use Claude Code.
- **"Could not start server… port in use"** — something's already on 8787; run with `--port 9000`.
- **A model shows up with $0 cost** — its name isn't in `pricing.py` (a brand-new model, or
  `<synthetic>` local messages). Add it to `_BASE_PER_MTOK`.
- **Windows shows the wrong day boundaries** — pass `--timezone "America/Chicago"` (or your zone).
  Windows has no system timezone database, so named zones use the bundled `tzdata`.

---

## Contributing

PRs and issues are very welcome — see [CONTRIBUTING.md](https://github.com/colelevy08/portmint-pulse/blob/main/CONTRIBUTING.md). Run the tests with:

```bash
pip install -e ".[dev]"
pytest
```

Releases (PyPI + the Pages demo) are automated — see [RELEASING.md](https://github.com/colelevy08/portmint-pulse/blob/main/RELEASING.md).

## Branding

Built to Portmint's brand standards: the mint porthole mark (`#34e0b3` on Deep Ocean Blue `#07182c`),
Portmint Ink (`#070b14`) surfaces, the mint→sky brand gradient, and Inter throughout. Port + mint. 🛟

## License

[MIT](https://github.com/colelevy08/portmint-pulse/blob/main/LICENSE) — do whatever you like with it.

<div align="center"><sub>Made by <a href="https://github.com/colelevy08">Cole Levy</a> · a <a href="https://portmint.com">Portmint</a> open-source project</sub></div>
