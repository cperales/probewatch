"""Unit tests for CLI argument parsing and load_key in xiaomi_client.py."""

import sys
from pathlib import Path

import pytest

# Import from src/ via conftest sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from xiaomi_client import load_key

SECRETS = Path(__file__).resolve().parent.parent / "secrets"
AUTH_KEY = SECRETS / "auth_key.txt"


class TestLoadKey:
    """load_key() reads and validates the auth key file."""

    def test_valid_key(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("0123456789abcdef0123456789abcdef\n")
        result = load_key(str(path))
        assert result == bytes.fromhex("0123456789abcdef0123456789abcdef")

    def test_valid_key_no_prefix(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("0123456789abcdef0123456789abcdef\n")
        result = load_key(str(path))
        assert len(result) == 16  # 32 hex chars = 16 bytes

    def test_valid_key_with_0x_prefix(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("0x0123456789abcdef0123456789abcdef\n")
        result = load_key(str(path))
        assert result == bytes.fromhex("0123456789abcdef0123456789abcdef")

    def test_uppercase_key(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("0123456789ABCDEF0123456789ABCDEF\n")
        result = load_key(str(path))
        assert result == bytes.fromhex("0123456789abcdef0123456789abcdef")

    def test_mixed_case_key(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("0123456789AbCdEf0123456789aBcDeF\n")
        result = load_key(str(path))
        assert result == bytes.fromhex("0123456789abcdef0123456789abcdef")

    def test_whitespace_stripped(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("  0123456789abcdef0123456789abcdef  \n")
        result = load_key(str(path))
        assert result == bytes.fromhex("0123456789abcdef0123456789abcdef")

    def test_too_short_raises(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("0123456789abcdef\n")  # only 16 hex chars
        with pytest.raises(SystemExit) as exc_info:
            load_key(str(path))
        assert "32 hex chars" in str(exc_info.value)

    def test_too_long_raises(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("0123456789abcdef0123456789abcdef01\n")  # 34 hex chars
        with pytest.raises(SystemExit) as exc_info:
            load_key(str(path))
        assert "32 hex chars" in str(exc_info.value)

    def test_invalid_hex_raises(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("gggggggggggggggggggggggggggggggg\n")
        with pytest.raises(SystemExit) as exc_info:
            load_key(str(path))
        assert "32 hex chars" in str(exc_info.value)

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("")
        with pytest.raises(SystemExit) as exc_info:
            load_key(str(path))
        assert "32 hex chars" in str(exc_info.value)

    def test_newline_only_raises(self, tmp_path):
        path = tmp_path / "key.txt"
        path.write_text("\n")
        with pytest.raises(SystemExit) as exc_info:
            load_key(str(path))
        assert "32 hex chars" in str(exc_info.value)
