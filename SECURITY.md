# Security Policy

Portmint Pulse is local-first and read-only, but it does handle your Claude Code login token, so we
take reports seriously.

## What Pulse does with sensitive data

- It **reads** your Claude Code OAuth token from `~/.claude/.credentials.json` (or the macOS Keychain)
  and sends it in exactly **one** request: to `https://api.anthropic.com/api/oauth/usage`, over HTTPS,
  to fetch your live limit windows. This is the same call Claude Code itself makes.
- The token is **never** written anywhere, logged, or sent to any other host.
- The dashboard binds to `127.0.0.1` by default. The `/api/stats` payload contains usage numbers and
  your local project directory names — keep that in mind before using `--host 0.0.0.0` on an untrusted
  network.
- The dashboard page itself makes **no** outbound requests (no fonts, analytics, or CDNs).

## Reporting a vulnerability

Please **do not** open a public issue for a security problem. Instead, use GitHub's
[private vulnerability reporting](https://github.com/colelevy08/portmint-pulse/security/advisories/new)
or email the maintainer. Include steps to reproduce and the impact you see. You'll get an
acknowledgement within a few days.

## Supported versions

This is a young project; security fixes land on `main` and in the latest release.
