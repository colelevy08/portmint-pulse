"""Best-effort desktop notifications — standard library only, no pip packages.

One ``notify(title, body)`` call picks the right native tool per platform and
falls back to a console line if no GUI notifier is available. Never raises.

  - macOS:   ``osascript`` (an `on run argv` handler, so titles can't inject AppleScript)
  - Linux:   ``notify-send`` (libnotify; absent on headless/server/WSL boxes)
  - Windows: a dep-free WinRT toast via ``powershell.exe`` (NOT BurntToast, which is a module)
  - WSL:     the same Windows toast through powershell.exe interop — because notify-send
             does NOT work in WSL (no notification daemon), WSL must be detected BEFORE Linux.

Delivery is best-effort everywhere: even a zero exit doesn't guarantee the banner
was shown (Do Not Disturb / Focus). The caller treats it as fire-and-forget.
"""

from __future__ import annotations

import base64
import os
import shutil
import subprocess
import sys

# App id the Windows toast is shown under (best-effort source label).
_APP_ID = "Portmint Pulse"


def _ps_toast(title: str, body: str) -> str:
    """A WinRT toast PowerShell command, with title/body embedded as base64.

    base64 is used (not $env:) on purpose: WSL does NOT pass environment variables
    across to a Windows process, so $env:PULSE_TITLE would arrive empty (blank toast).
    base64 lives in the -Command ARGS, which DO cross the WSL→Windows boundary, and is
    pure [A-Za-z0-9+/=] so it can't break the quoting or inject anything.
    """
    t = base64.b64encode(title.encode("utf-8")).decode("ascii")
    b = base64.b64encode(body.encode("utf-8")).decode("ascii")
    return (
        "$ErrorActionPreference='Stop';"
        f"$T=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{t}'));"
        f"$B=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b}'));"
        "[void][Windows.UI.Notifications.ToastNotificationManager,Windows.UI.Notifications,ContentType=WindowsRuntime];"
        "$x=[Windows.UI.Notifications.ToastNotificationManager]::GetTemplateContent([Windows.UI.Notifications.ToastTemplateType]::ToastText02);"
        "$n=$x.GetElementsByTagName('text');"
        "[void]$n.Item(0).AppendChild($x.CreateTextNode($T));"
        "[void]$n.Item(1).AppendChild($x.CreateTextNode($B));"
        "$o=[Windows.UI.Notifications.ToastNotification]::new($x);"
        f"[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('{_APP_ID}').Show($o)"
    )


def _is_wsl() -> bool:
    """True inside WSL — which reports platform 'linux' but has no notify daemon."""
    if os.environ.get("WSL_INTEROP") or os.environ.get("WSL_DISTRO_NAME"):
        return True
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as fh:
            v = fh.read().lower()
        return "microsoft" in v or "wsl" in v
    except OSError:
        return False


def _detect_backend() -> str:
    """The notification backend to use (checked once at import)."""
    if _is_wsl():
        return "wsl"
    if sys.platform == "win32":
        return "windows"
    if sys.platform == "darwin":
        return "macos"
    if sys.platform.startswith("linux"):
        return "linux"
    return "console"


_BACKEND = _detect_backend()


def _command(backend: str, title: str, body: str, urgency: str) -> tuple[list[str] | None, dict[str, str] | None]:
    """The argv (and any env overrides) for a backend, or (None, None) for console.

    Always argv lists (shell=False) with a literal ``--`` before user text on Linux,
    so labels with spaces or a leading '-' can't be misparsed or injected.
    """
    if backend == "macos":
        script = "on run argv\ndisplay notification (item 1 of argv) with title (item 2 of argv)\nend run"
        return ["osascript", "-e", script, body, title], None
    if backend == "linux":
        u = "critical" if urgency == "critical" else "normal"
        return ["notify-send", "--app-name", "Portmint Pulse", "--urgency", u, "--", title, body], None
    if backend in ("windows", "wsl"):
        # Title/body are base64-embedded in the command (env vars don't cross WSL).
        return (
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _ps_toast(title, body)],
            None,
        )
    return None, None


def notify(title: str, body: str, *, urgency: str = "normal") -> bool:
    """Show a desktop notification. Returns True if a GUI notifier ran, False if it
    fell back to the console. Never raises."""
    argv, env_over = _command(_BACKEND, title, body, urgency)
    if argv and shutil.which(argv[0]):
        try:
            env = {**os.environ, **(env_over or {})}
            timeout = 10 if _BACKEND in ("windows", "wsl") else 5
            result = subprocess.run(argv, env=env, capture_output=True, timeout=timeout, check=False)
            if result.returncode == 0:
                return True
        except (OSError, subprocess.SubprocessError):
            pass
    # Fallback: print it (also the path on headless Linux / unknown OS).
    print(f"  🔔 {title} — {body}", flush=True)
    return False
