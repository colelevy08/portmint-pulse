<!-- Thanks for contributing to Portmint Pulse! -->

## What & why

<!-- What does this change, and why? Link any related issue (e.g. "Closes #12"). -->

## Checklist

- [ ] Tests pass (`pytest`) and I added/updated tests for any new behavior
- [ ] `ruff check portmint_pulse tools tests` and `mypy portmint_pulse` are clean
- [ ] **No new runtime dependencies** — Pulse is standard-library only (`tzdata` on Windows is the lone exception)
- [ ] It stays **local, read-only, and zero-telemetry** (no new outbound calls beyond the existing OAuth usage fetch)
- [ ] Updated `CHANGELOG.md` if the change is user-facing
