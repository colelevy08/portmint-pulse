"""Shared test setup.

Every test gets PULSE_DATA_DIR pointed at its own temp directory so the
persistent usage archive (portmint_pulse.archive) never reads from or writes
to the developer's real per-user data directory.
"""

import pytest


@pytest.fixture(autouse=True)
def _isolate_archive(tmp_path, monkeypatch):
    monkeypatch.setenv("PULSE_DATA_DIR", str(tmp_path / "pulse-data"))
