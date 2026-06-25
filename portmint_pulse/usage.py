"""Fetches your live Claude usage limits straight from the OAuth API.

Claude Code stores its login token differently per platform:
  - Linux / WSL / Windows: a JSON file at ``~/.claude/.credentials.json``
  - macOS: the login Keychain (service "Claude Code-credentials")

This module reads whichever applies, then calls Anthropic's usage endpoint with
that token — the same call Claude Code itself makes — to learn how much of each
rolling limit you've used: the 5-hour session window, the 7-day all-models
window, per-model 7-day windows, and any pay-as-you-go credit balance.

Everything here is read-only and runs locally. The token never leaves your
machine except in the one HTTPS request to api.anthropic.com.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# macOS Keychain service name that Claude Code stores its credentials blob under.
_MAC_KEYCHAIN_SERVICE = "Claude Code-credentials"

# Friendly labels for the rolling-limit windows the API returns. Anything not in
# this map (or whose utilisation is null) is simply not shown.
_WINDOW_LABELS = {
    "five_hour": "5-hour session",
    "seven_day": "7-day · all models",
    "seven_day_opus": "7-day · Opus",
    "seven_day_sonnet": "7-day · Sonnet",
}
# The order we want the bars to appear in.
_WINDOW_ORDER = ["five_hour", "seven_day", "seven_day_opus", "seven_day_sonnet"]


def _read_credentials_blob() -> dict | None:
    """Load Claude Code's credentials JSON from the file or the macOS Keychain."""
    # 1) The plain file (Linux, WSL, and Windows installs).
    try:
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        pass

    # 2) macOS stores the same JSON in the login Keychain instead of a file.
    if sys.platform == "darwin":
        try:
            out = subprocess.run(
                ["security", "find-generic-password", "-s", _MAC_KEYCHAIN_SERVICE, "-w"],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            if out.returncode == 0 and out.stdout.strip():
                return json.loads(out.stdout.strip())
        except (OSError, json.JSONDecodeError, subprocess.SubprocessError):
            pass

    return None


def _read_access_token() -> str | None:
    """Pull the current OAuth access token out of the credentials blob."""
    creds = _read_credentials_blob()
    if not isinstance(creds, dict):
        return None
    oauth = creds.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None
    return oauth.get("accessToken")


def _humanize_reset(resets_at: str | None) -> str | None:
    """Turn an ISO reset timestamp into a friendly 'resets in 2h 14m' string."""
    if not resets_at:
        return None
    try:
        when = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = when - datetime.now(timezone.utc)
    secs = int(delta.total_seconds())
    if secs <= 0:
        return "resetting now"
    hours, rem = divmod(secs, 3600)
    minutes = rem // 60
    days, hours = divmod(hours, 24)
    if days:
        return f"resets in {days}d {hours}h"
    if hours:
        return f"resets in {hours}h {minutes}m"
    return f"resets in {minutes}m"


def fetch_limits() -> dict:
    """Return the parsed usage limits, or an ``error`` describing why we can't.

    The shape is intentionally simple so the front-end can render it directly:
    a list of windows (each with a 0-100 utilisation and a reset countdown) plus
    an optional pay-as-you-go ``extra_usage`` block.
    """
    token = _read_access_token()
    if not token:
        hint = "log in with the Claude app (Keychain)" if sys.platform == "darwin" else "~/.claude/.credentials.json missing"
        return {"error": f"No Claude Code login found ({hint})."}

    req = urllib.request.Request(
        USAGE_URL,
        headers={
            "Authorization": f"Bearer {token}",
            "anthropic-beta": "oauth-2025-04-20",
            "User-Agent": "claude-code/2.0.32",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return {"error": "Login token expired — run `claude` once to refresh it."}
        return {"error": f"Usage API returned HTTP {e.code}."}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return {"error": f"Couldn't reach the usage API ({type(e).__name__})."}

    windows = []
    for key in _WINDOW_ORDER:
        block = data.get(key)
        if not isinstance(block, dict):
            continue
        util = block.get("utilization")
        if util is None:
            continue
        windows.append({
            "label": _WINDOW_LABELS.get(key, key),
            # The API reports utilisation as a 0-100 percentage already.
            "utilization": round(float(util), 1),
            "resets_at": block.get("resets_at"),
            "resets_human": _humanize_reset(block.get("resets_at")),
        })

    result: dict = {"windows": windows}

    # Pay-as-you-go overage credits, if the account has them enabled.
    extra = data.get("extra_usage")
    if isinstance(extra, dict) and extra.get("is_enabled"):
        places = extra.get("decimal_places", 2) or 0
        scale = 10 ** places
        limit_raw = extra.get("monthly_limit")
        used_raw = extra.get("used_credits")
        limit = (limit_raw / scale) if isinstance(limit_raw, (int, float)) else None
        used = (used_raw / scale) if isinstance(used_raw, (int, float)) else 0.0
        util = (used / limit * 100) if (limit and limit > 0) else 0.0
        result["extra_usage"] = {
            "currency": extra.get("currency", "USD"),
            "used": round(used, places),
            "limit": round(limit, places) if limit is not None else None,
            "utilization": round(util, 1),
        }

    return result
