"""Fixtures shared by the test suite.

Tests must never read or write the real `secrets/` directory: `WATCH_MAC` is
cleared for every test (so a developer's shell cannot change results) and tests
that need a device file point `watch_secrets.DEVICE_FILE` at `tmp_path`.
"""

import pytest


@pytest.fixture(autouse=True)
def _no_ambient_watch_mac(monkeypatch):
    """Keep an exported WATCH_MAC from leaking into MAC-resolution tests."""
    monkeypatch.delenv("WATCH_MAC", raising=False)
