"""Tests for usage.py: credential resolution + caching/backoff. Fully offline —
the network is monkeypatched, so no real token or API call is ever used.
"""

import json
import urllib.error
import urllib.request

import pytest

from portmint_pulse import usage


class _Resp:
    """Minimal stand-in for an http response usable with `json.load`/`with`."""

    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def read(self, *_a):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *_a):
        return False


@pytest.fixture(autouse=True)
def _clear_cache():
    usage.reset_cache()
    yield
    usage.reset_cache()


def test_token_shadowing_falls_through_to_keychain(monkeypatch):
    # File parses but has no usable token; the Keychain has the real one.
    monkeypatch.setattr(usage, "_read_credentials_file", lambda: {"claudeAiOauth": {}})
    monkeypatch.setattr(usage, "_read_keychain_blob", lambda: {"claudeAiOauth": {"accessToken": "K"}})
    assert usage._read_access_token() == "K"


def test_token_from_file_wins_when_present(monkeypatch):
    monkeypatch.setattr(usage, "_read_credentials_file", lambda: {"claudeAiOauth": {"accessToken": "F"}})
    monkeypatch.setattr(usage, "_read_keychain_blob", lambda: {"claudeAiOauth": {"accessToken": "K"}})
    assert usage._read_access_token() == "F"


def test_no_login_returns_error(monkeypatch):
    monkeypatch.setattr(usage, "_read_access_token", lambda: None)
    out = usage.fetch_limits()
    assert "error" in out and "login" in out["error"].lower()


def test_success_then_429_serves_last_good(monkeypatch):
    monkeypatch.setattr(usage, "_read_access_token", lambda: "tok")
    payload = {"five_hour": {"utilization": 50, "resets_at": None}}
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Resp(payload))

    first = usage.fetch_limits()
    assert first["windows"][0]["label"] == "5-hour session"
    assert first["windows"][0]["utilization"] == 50.0

    # Force the TTL to look expired so the next call hits the network again...
    usage._state["good_ts"] = 0.0

    # ...but now the API 429s. We should still get the last-good windows, not an error.
    def _boom(*_a, **_k):
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _boom)
    second = usage.fetch_limits()
    assert "error" not in second
    assert second["windows"][0]["utilization"] == 50.0


def test_cold_429_sets_backoff_and_stops_calling(monkeypatch):
    # A first-ever fetch that is rate-limited (no cached good value) must set a
    # backoff and NOT keep hitting the endpoint on the next call.
    monkeypatch.setattr(usage, "_read_access_token", lambda: "tok")
    calls = {"n": 0}

    def _429(*_a, **_k):
        calls["n"] += 1
        raise urllib.error.HTTPError("u", 429, "Too Many Requests", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _429)
    out1 = usage.fetch_limits()
    assert "error" in out1 and "rate-limit" in out1["error"].lower()
    assert calls["n"] == 1

    out2 = usage.fetch_limits()  # within backoff window
    assert "error" in out2
    assert calls["n"] == 1  # did NOT re-hit the rate-limited endpoint


def test_expired_token_message(monkeypatch):
    monkeypatch.setattr(usage, "_read_access_token", lambda: "tok")

    def _401(*_a, **_k):
        raise urllib.error.HTTPError("u", 401, "Unauthorized", {}, None)

    monkeypatch.setattr(urllib.request, "urlopen", _401)
    out = usage.fetch_limits()
    assert "error" in out and "expired" in out["error"].lower()
