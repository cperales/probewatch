"""Unit tests for watch_secrets.py — MAC resolution logic.

Every test that needs a device file points `watch_secrets.DEVICE_FILE` at a
`tmp_path`; nothing here reads or writes the real git-ignored `secrets/` directory.
"""

import pytest

import watch_secrets
from watch_secrets import MAC_LINE, default_mac, resolve_mac


@pytest.fixture
def device_file(tmp_path, monkeypatch):
    """A throwaway device.md, wired into watch_secrets for the test."""
    path = tmp_path / "device.md"
    monkeypatch.setattr(watch_secrets, "DEVICE_FILE", path)
    return path


class TestDefaultMac:
    """default_mac() reads from env or file."""

    def test_from_env(self, device_file, monkeypatch):
        device_file.write_text("- MAC: 11:22:33:44:55:66\n")
        monkeypatch.setenv("WATCH_MAC", "aa:bb:cc:dd:ee:ff")
        assert default_mac() == "AA:BB:CC:DD:EE:FF"

    def test_from_file(self, device_file):
        device_file.write_text("- MAC: 11:22:33:44:55:66\n")
        assert default_mac() == "11:22:33:44:55:66"

    def test_from_file_uppercase(self, device_file):
        device_file.write_text("- MAC: AA:BB:CC:DD:EE:FF\n")
        assert default_mac() == "AA:BB:CC:DD:EE:FF"

    def test_from_file_with_prefix(self, device_file):
        device_file.write_text("# Comment\n- MAC: 11:22:33:44:55:66\n")
        assert default_mac() == "11:22:33:44:55:66"

    def test_empty_when_no_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(watch_secrets, "DEVICE_FILE", tmp_path / "missing.md")
        assert default_mac() == ""

    def test_empty_when_file_has_no_mac(self, device_file):
        device_file.write_text("# Just a comment\n")
        assert default_mac() == ""

    def test_env_overrides_file(self, device_file, monkeypatch):
        device_file.write_text("- MAC: 11:22:33:44:55:66\n")
        monkeypatch.setenv("WATCH_MAC", "aa:bb:cc:dd:ee:ff")
        assert default_mac() == "AA:BB:CC:DD:EE:FF"


class TestResolveMac:
    """resolve_mac() returns the MAC or exits."""

    def test_explicit_value(self):
        assert resolve_mac("AA:BB:CC:DD:EE:FF") == "AA:BB:CC:DD:EE:FF"

    def test_explicit_value_lowercase_is_preserved(self):
        # Only default_mac() uppercases what it reads from the environment/file.
        assert resolve_mac("aa:bb:cc:dd:ee:ff") == "aa:bb:cc:dd:ee:ff"

    def test_none_uses_default(self, device_file):
        device_file.write_text("- MAC: 11:22:33:44:55:66\n")
        assert resolve_mac(None) == "11:22:33:44:55:66"

    def test_empty_raises(self, device_file):
        device_file.write_text("# no MAC here\n")
        with pytest.raises(SystemExit) as exc_info:
            resolve_mac(None)
        assert "no watch MAC" in str(exc_info.value)

    def test_whitespace_stripped(self, device_file):
        device_file.write_text("- MAC:   11:22:33:44:55:66  \n")
        assert resolve_mac(None) == "11:22:33:44:55:66"


class TestMacRegex:
    """MAC_LINE regex matches valid MACs and rejects invalid ones."""

    def test_colon_separated(self):
        assert MAC_LINE.search("MAC: AA:BB:CC:DD:EE:FF") is not None

    def test_with_prefix(self):
        assert MAC_LINE.search("- MAC: AA:BB:CC:DD:EE:FF") is not None

    def test_with_asterisk_prefix(self):
        assert MAC_LINE.search("**MAC**: AA:BB:CC:DD:EE:FF") is not None

    def test_lowercase(self):
        assert MAC_LINE.search("MAC: aa:bb:cc:dd:ee:ff") is not None

    def test_mixed_case(self):
        assert MAC_LINE.search("MAC: Aa:Bb:Cc:Dd:Ee:Ff") is not None

    def test_invalid_too_few_octets(self):
        assert MAC_LINE.search("MAC: AA:BB:CC") is None

    def test_invalid_letters(self):
        assert MAC_LINE.search("MAC: GG:HH:II:JJ:KK:LL") is None

    def test_invalid_no_colons(self):
        assert MAC_LINE.search("MAC: AABBCCDDEEFF") is None
