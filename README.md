<div align="center">

<img src="https://raw.githubusercontent.com/colelevy08/portmint-pulse/main/assets/logo.svg" width="84" alt="Portmint Pulse" />

# Portmint&nbsp;Pulse

**The live-limit instrument for Claude Code.**

Your *real* Claude Code limits — live, local, and *before* you hit the wall. Pulse reads the
actual OAuth rate-limit windows off your login token and puts them everywhere you work: a glanceable
**status line**, a desktop **warning before the wall**, and a full browser **dashboard** — plus a
*"you're getting **N× your subscription's worth**"* number priced from your real usage.

*Pure Python standard library (tzdata on Windows the lone exception). No build step. No cloud. No telemetry. Runs on macOS, Windows, and Linux/WSL.*

[![CI](https://github.com/colelevy08/portmint-pulse/actions/workflows/ci.yml/badge.svg)](https://github.com/colelevy08/portmint-pulse/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-34e0b3.svg)](https://github.com/colelevy08/portmint-pulse/blob/main/LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-2bd3a6.svg)](https://www.python.org/downloads/)
[![Platforms](https://img.shields.io/badge/platforms-macOS%20%C2%B7%20Windows%20%C2%B7%20Linux-0ea5e9.svg)](#install)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-5cf0c4.svg)](https://github.com/colelevy08/portmint-pulse/blob/main/CONTRIBUTING.md)

<img src="https://raw.githubusercontent.com/colelevy08/portmint-pulse/main/assets/screenshot.png" width="860" alt="Portmint Pulse dashboard" />

### ▶ **[Try the live demo →](https://colelevy08.github.io/portmint-pulse/)**  ·  no install, runs in your browser on fabricated data

</div>

---

## Quickstart

PyPI is on the way — until then, install straight from the repo (still one command):

```bash
pipx install git+https://github.com/colelevy08/portmint-pulse.git && portmint-pulse
```

No `pipx`? Clone and run it on a stock Python — **nothing to install** on macOS/Linux:

```bash
git clone https://github.com/colelevy08/portmint-pulse.git && cd portmint-pulse && python3 app.py
```

It opens a tab at **http://localhost:8787**. *(Once it's on PyPI: `pipx install portmint-pulse`.)*
Or skip install entirely — **[try the live demo →](https://colelevy08.github.io/portmint-pulse/)**.

---

## Why this exists

Claude Code records a wealth of usage data on your disk and meters you against hidden rate-limit
windows — but gives you no easy way to *see* either. The usual surprise is finding out you're
throttled **mid-task**. Pulse fixes that: it reads the **live OAuth limit windows** (not blocks
inferred from logs) and shows them as four glanceable surfaces, warning you *before* you hit the wall.
And it does it the lightweight way — a **visual browser dashboard** plus three terminal surfaces,
computed from the data Claude Code already writes locally. No Apple frameworks, no observability
stack, no `npm`, no database, nothing to set up.

**Why not just ccusage?** [ccusage](https://github.com/ryoppippi/ccusage) is the excellent multi-agent
CLI — reach for it if you want one tool across ~15 coding agents. Pulse is the Claude-Code-native
instrument that reads your **real live limits**, **warns you before the wall**, and needs **zero
dependencies** (pure Python stdlib, no Node). Different shape, different job.

---

## Four surfaces, one stdlib codebase

| Surface | Command | What it's for |
|---|---|---|
| 🖥️ **Dashboard** | `portmint-pulse` | *See it.* Live limit bars + token/cost trends, by-model & by-project, range Day → 5 years. |
| 📊 **Status line** | `portmint-pulse statusline` | *Glance it.* Your live limits, every turn — **no extra API call, no token cost** (reads what Claude Code already pipes in). |
| 🔔 **Watch** | `portmint-pulse watch` | *Get warned.* A desktop toast the instant any window crosses **80 / 95 / 100%** — so you're never throttled by surprise. |
| 🧾 **Summary** | `portmint-pulse summary --json` | *Pipe it.* A one-shot text or `--json` snapshot — no server, no browser. |

The killer features under the hood:

- **Live limits, no API call (status line).** The status line renders from the JSON Claude Code
  already hands it on stdin — the 5h / 7d / Opus / Sonnet windows in mint → amber → red with a reset
  countdown — so it costs **zero extra calls and zero tokens** (and falls back to context-window % when
  limits aren't present):
  ```
  [Opus] ▓▓▓▓▓░░░ 62% · 7d-opus 2h14m · $0.06
  ```
- **Warn *before* the wall + time-to-the-wall.** `watch` fires a dependency-free, cross-platform
  desktop notification (macOS `osascript`, Linux `notify-send`, Windows/WSL native PowerShell toast — no
  module) the moment a window crosses 80 / 95 / 100%, naming which one. Once it's watched your pace for
  a few minutes, it adds a ⚡ **`~2h to wall`** projection — shown *only* when you're on track to hit
  100% *before* the window resets. (It's a transparent linear projection over recent velocity, not an ML
  model.)
- **Money's-worth multiplier.** A single headline number — *"you're getting **N×** your subscription's
  worth"* — prices your last-30-days usage at API list rates against your flat Pro / Max 5× / Max 20×
  plan, computed locally and shown in the dashboard, `summary --plan`, and `--json`. *(API-equivalent
  value, not your actual bill — a flat plan is a flat fee.)*

**The moat under all of it:** stdlib-only (tzdata on Windows the lone exception), **read-only** (never
writes or deletes), **localhost-only** bind, **zero telemetry**, and exactly **one outbound call** — the
same `api.anthropic.com/api/oauth/usage` request Claude Code itself makes (cached ~180s with exponential
429 backoff). The dashboard page fetches **nothing** — no CDNs, no web fonts, no Chart.js-from-a-CDN.
Pulse also dedupes transcript records by `requestId` (Claude Code logs each request 2–10×, so a naive
summer over-counts tokens ~2.3×) — so the numbers are simply more correct.

---

## How Pulse compares

The Claude Code usage space is healthy — pick the tool whose *shape* fits you. This is an honest map
(as of 2026-06, based on each project's public README); see [the full comparison below](#the-full-comparison).

| | **Portmint Pulse** | [ccusage](https://github.com/ryoppippi/ccusage) | [Claude-Code-Usage-Monitor](https://github.com/Maciek-roboblog/Claude-Code-Usage-Monitor) |
|---|---|---|---|
| Form | **web dashboard + 3 terminal surfaces** | CLI text reports | Rich TUI |
| Live limit bars in the **status line** | **✅ (no extra API call)** | status line is beta | via official statusline rate_limits |
| Limit source | **reads live OAuth windows** | *infers* blocks from local data | reads live limits + P90 forecast |
| Warn-before-the-wall **desktop** alert | **✅ (80 / 95 / 100%)** | ❌ | ❌ (in-terminal forecast) |
| Money's-worth multiplier | **✅** | ❌ | ❌ |
| Dependencies | **stdlib only** (tzdata on Windows) | a Node toolchain | Rich + pydantic + numpy + … |
| Telemetry | **none** | none | none |
| Runs on | **macOS · Windows · Linux/WSL** | macOS · Windows · Linux | macOS · Windows · Linux |
| Language | **Python (stdlib)** | Node / npm | Python |

**Where they win, honestly:** `ccusage` is the category leader and covers ~15 agents — reach for it if
you want multi-agent breadth. `Claude-Code-Usage-Monitor` has genuine P90 limit *forecasting* in a
beautiful TUI. Pulse is Claude-Code-focused on purpose, and wins on **real live limits across four
surfaces, warn-before-the-wall, zero dependencies, and zero telemetry**.

---

## What you get

- **Usage limits** — pulled live from your Claude Code login token: the 5-hour session window,
  the 7-day all-models window, the 7-day Opus and Sonnet windows, and any pay-as-you-go credit balance.
  Bars go mint → amber → red with reset countdowns — plus, once Pulse has watched your pace for a few
  minutes, a ⚡ **time-to-the-wall** estimate on any window you're on track to hit *before* it resets.
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
line if no notifier is available. The console line also shows a **`~2h to wall`** projection once it has
tracked your pace. It reuses the cached limits poll, so it never rate-limits your token, keeps **no state
on disk** (zero telemetry), alerts once per crossing, and re-arms after a window resets.

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

## The full comparison

The quick table above, expanded — the neighbors and where each shines:

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
