"""Unit tests for dlvp_probe.py — DLVP handle filtering and value formatting."""

import sys
from pathlib import Path

# Import from src/ via conftest sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from dlvp_probe import (
    DLVP_HANDLE_END,
    DLVP_HANDLE_START,
    MODE_JTAG,
    MODE_UART,
    format_value,
    in_dlvp_range,
)


class TestInDlvpRange:
    """in_dlvp_range() is inclusive of both DLVP handle bounds."""

    def test_below_range(self):
        assert in_dlvp_range(DLVP_HANDLE_START - 1) is False

    def test_start_boundary(self):
        assert in_dlvp_range(DLVP_HANDLE_START) is True

    def test_inside_range(self):
        assert in_dlvp_range((DLVP_HANDLE_START + DLVP_HANDLE_END) // 2) is True

    def test_end_boundary(self):
        assert in_dlvp_range(DLVP_HANDLE_END) is True

    def test_above_range(self):
        assert in_dlvp_range(DLVP_HANDLE_END + 1) is False


class TestFormatValue:
    """format_value() renders hex and names the jlink_uart_switch modes."""

    def test_no_value(self):
        assert format_value(None) == "(no read)"

    def test_uart_mode(self):
        assert format_value(bytes([MODE_UART])) == "00 (debug-UART)"

    def test_jtag_mode(self):
        assert format_value(bytes([MODE_JTAG])) == "01 (JTAG/SWD)"

    def test_other_single_byte(self):
        assert format_value(b"\x02") == "02"

    def test_multibyte(self):
        assert format_value(b"\x00\x01") == "0001"
