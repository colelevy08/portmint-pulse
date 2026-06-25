# Contributing to Portmint Pulse

Thanks for your interest — contributions of all sizes are welcome, from typo fixes to new charts.

## Ground rules

- **Keep it standard-library.** The whole appeal is "no dependencies, no build step." New runtime
  dependencies will almost always be declined. (Dev-only tools like `pytest` are fine.)
- **Cross-platform first.** Code must run on macOS, Windows, and Linux/WSL. Avoid OS-specific paths;
  use `os.path`/`pathlib`, and gate anything platform-specific (like the macOS Keychain read) behind
  a `sys.platform` check with a graceful fallback.
- **Privacy is the product.** Don't add telemetry, analytics, remote calls, or web fonts/CDNs. The
  dashboard page must make zero outbound requests; the only network call in the whole app is the
  single usage-API request.

## Getting set up

```bash
git clone https://github.com/colelevy08/portmint-pulse.git
cd portmint-pulse
python3 -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest                      # run the test suite
python3 app.py              # run the app against your real Claude Code data
python tools/gen_demo.py    # or run it against synthetic demo data
```

## Tests

- All tests are offline and use synthetic fixtures — they never read your real `~/.claude`.
- Please add a test for any behavior change. Aggregation logic in `transcripts.py`, pricing in
  `pricing.py`, and server wiring all have existing tests to model after.
- CI runs the suite on macOS, Windows, and Linux across Python 3.9–3.13. Green CI is required to merge.

## Style

- Type hints on public functions; `from __future__ import annotations` at the top of each module.
- Comments explain *why*, in plain language. Keep functions small and focused.
- Match the surrounding style rather than introducing new patterns.

## Pull requests

1. Fork, branch (`feat/…`, `fix/…`, `docs/…`), commit with a clear message.
2. Make sure `pytest` passes locally.
3. Open the PR with a short description of the change and why. Screenshots help for UI tweaks.

By contributing, you agree your contributions are licensed under the project's [MIT License](LICENSE).
