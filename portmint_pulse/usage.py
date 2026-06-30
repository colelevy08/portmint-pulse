"""Fetches your live Claude usage limits straight from the OAuth API.

Claude Code stores its login token in a JSON file at ``~/.claude/.credentials.json``
on Linux / WSL / Windows, and in the login Keychain (service "Claude Code-credentials")
on macOS. We read the **file first on every platform** and fall back to the macOS
Keychain when the file is absent or has no usable token.

With that token this module calls Anthropic's usage endpoint — the same call
Claude Code itself makes — to learn how much of each
rolling limit you've used: the 5-hour session window, the 7-day all-models
window, per-model 7-day windows, and any pay-as-you-go credit balance.

The OAuth usage endpoint rate-limits aggressively, so results are cached for a
short TTL and a 429 backs off while serving the last-good values rather than
flapping the bars. Everything here is read-only and runs locally. The token
never leaves your machine except in the one HTTPS request to api.anthropic.com.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

CREDENTIALS_PATH = os.path.expanduser("~/.claude/.credentials.json")
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"

# macOS Keychain service name that Claude Code stores its credentials blob under.
_MAC_KEYCHAIN_SERVICE = "Claude Code-credentials"

# How long a successful result is reused before we hit the network again, and how
# long we wait after a 429 before trying again. The /api/oauth/usage endpoint
# rate-limits aggressively PER TOKEN and is only safe at ~>=180s intervals, so the
# TTL is 180s — the dashboard's faster local refresh is served from cache and the
# network is only touched ~once per window, well clear of 429-ing the real token.
_TTL_SECONDS = 180.0
# Exponential backoff after a 429: 180s, 360s, 720s, capped at 900s (15 min).
_BACKOFF_BASE_SECONDS = 180.0
_BACKOFF_CAP_SECONDS = 900.0

# Cache of the last *successful* fetch, so transient errors keep showing real bars.
# "fails" counts consecutive 429s to grow the backoff; reset on any success.
_state: dict = {"good": None, "good_ts": 0.0, "backoff_until": 0.0, "fails": 0}

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


def reset_cache() -> None:
    """Clear the in-memory limit cache (used by tests)."""
    _state["good"] = None
    _state["good_ts"] = 0.0
    _state["backoff_until"] = 0.0
    _state["fails"] = 0


def _token_from_blob(blob: object) -> str | None:
    """Extract the OAuth access token from a parsed credentials blob, if present."""
    if not isinstance(blob, dict):
        return None
    oauth = blob.get("claudeAiOauth")
    if not isinstance(oauth, dict):
        return None
    tok = oauth.get("accessToken")
    return tok if isinstance(tok, str) and tok else None


def _read_credentials_file() -> object | None:
    """Load the credentials JSON file (Linux / WSL / Windows), or None."""
    try:
        with open(CREDENTIALS_PATH, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _read_keychain_blob() -> object | None:
    """Load Claude Code's credentials JSON from the macOS login Keychain, or None."""
    if sys.platform != "darwin":
        return None
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
    """Return the OAuth access token from the file or macOS Keychain.

    Important: we fall through to the Keychain whenever the *file* didn't yield a
    usable token — not only when it's missing. On macOS the file can exist but be
    tokenless (older installs), and the real token lives in the Keychain; reading
    the file first must not shadow it.
    """
    tok = _token_from_blob(_read_credentials_file())
    if tok:
        return tok
    return _token_from_blob(_read_keychain_blob())


def _humanize_reset(resets_at: str | None) -> str | None:
    """Turn an ISO reset timestamp into a friendly 'resets in 2h 14m' string."""
    if not resets_at:
        return None
    try:
        when = datetime.fromisoformat(resets_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    delta = when - datetime.now(timezone.utc)
    secs = round(delta.total_seconds())
    if secs <= 0:
        return "resetting now"
    hours, rem = divmod(secs, 3600)
    minutes = rem // 60
    days, hours = divmod(hours, 24)
    if days:
        return f"resets in {days}d {hours}h"
    if hours:
        return f"resets in {hours}h {minutes}m"
    if minutes:
        return f"resets in {minutes}m"
    return "resets in <1m"


def _parse_payload(data: dict) -> dict:
    """Shape the raw usage-API response into the front-end's simple structure."""
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
        # Distinguish a missing/null decimal_places (default to 2) from a real 0,
        # so a null never silently mis-scales the dollar amount by 100×.
        dp = extra.get("decimal_places")
        places = dp if isinstance(dp, int) and dp >= 0 else 2
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


def fetch_limits() -> dict:
    """Return the parsed usage limits (cached), or an ``error`` describing why not.

    Serves a recent successful result from cache without touching the network,
    backs off after a 429, and on any error prefers the last-good windows over
    flashing an error in the UI.
    """
    now = time.monotonic()
    good = _state["good"]

    # Fresh enough? Serve cache, no network call.
    if good is not None and (now - _state["good_ts"]) < _TTL_SECONDS:
        return good
    # In a post-429 cooldown? Don't touch the network — even with no cached value
    # yet (a first launch that got rate-limited). Serve last-good if we have it,
    # otherwise a clear "rate-limited" message, but never re-hit the endpoint.
    if now < _state["backoff_until"]:
        return good if good is not None else {"error": "Usage API is rate-limiting (429) — retrying shortly."}

    token = _read_access_token()
    if not token:
        if good is not None:
            return good
        hint = "run `claude` and sign in" if sys.platform == "darwin" else "run `claude` to sign in"
        return {"error": f"No Claude Code login found — {hint}, then hit Refresh."}

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
            return good if good is not None else {"error": "Login token expired — run `claude` once to refresh it."}
        if e.code == 429:
            _state["fails"] += 1
            backoff = min(_BACKOFF_CAP_SECONDS, _BACKOFF_BASE_SECONDS * (2 ** (_state["fails"] - 1)))
            _state["backoff_until"] = now + backoff
            return good if good is not None else {"error": "Usage API is rate-limiting (429) — retrying shortly."}
        return good if good is not None else {"error": f"Usage API returned HTTP {e.code}."}
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return good if good is not None else {"error": f"Couldn't reach the usage API ({type(e).__name__})."}

    result = _parse_payload(data)
    _state["good"] = result
    _state["good_ts"] = now
    _state["backoff_until"] = 0.0
    _state["fails"] = 0
    return result
