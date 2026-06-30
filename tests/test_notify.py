"""Tests for the desktop-notification abstraction — per-OS argv + safe fallback."""

import base64

from portmint_pulse import notify


def test_command_per_backend():
    argv, env = notify._command("macos", "Title", "Body", "normal")
    assert argv[0] == "osascript" and "Title" in argv and "Body" in argv and env is None

    argv, env = notify._command("linux", "Title", "Body", "critical")
    assert argv[0] == "notify-send" and "--" in argv and "critical" in argv

    for be in ("windows", "wsl"):
        argv, env = notify._command(be, "Title", "Body", "normal")
        # Title/body are base64-embedded in the command (env vars don't cross WSL).
        assert argv[0] == "powershell.exe" and env is None
        cmd = argv[-1]
        assert base64.b64encode(b"Title").decode() in cmd
        assert base64.b64encode(b"Body").decode() in cmd

    assert notify._command("console", "T", "B", "normal") == (None, None)


def test_fallback_to_console_when_tool_missing(monkeypatch, capsys):
    monkeypatch.setattr(notify, "_BACKEND", "macos")
    monkeypatch.setattr(notify.shutil, "which", lambda _x: None)
    assert notify.notify("T", "B") is False
    assert "T" in capsys.readouterr().out  # printed instead


def test_returns_true_on_successful_delivery(monkeypatch):
    class _R:
        returncode = 0

    monkeypatch.setattr(notify, "_BACKEND", "macos")
    monkeypatch.setattr(notify.shutil, "which", lambda x: "/usr/bin/" + x)
    monkeypatch.setattr(notify.subprocess, "run", lambda *a, **k: _R())
    assert notify.notify("T", "B") is True


def test_never_raises_falls_back_on_subprocess_error(monkeypatch, capsys):
    monkeypatch.setattr(notify, "_BACKEND", "macos")
    monkeypatch.setattr(notify.shutil, "which", lambda x: "/usr/bin/" + x)

    def _boom(*_a, **_k):
        raise OSError("nope")

    monkeypatch.setattr(notify.subprocess, "run", _boom)
    assert notify.notify("T", "B") is False
    assert "T" in capsys.readouterr().out
