"""Unit tests for a2dp_probe.py — AVDTP codec decoding logic."""

import sys
from pathlib import Path

# Import from src/ via conftest sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from a2dp_probe import (
    AVDTP_PSM,
    CATEGORIES,
    CODECS,
    MSG_TYPES,
    VENDOR_CODECS,
    bits,
    decode_codec,
)


class TestBits:
    """bits() converts an integer to a comma-separated list of bit names."""

    def test_single_bit(self):
        assert bits(1, ["A", "B", "C"]) == "C"

    def test_multiple_bits(self):
        assert bits(5, ["A", "B", "C"]) == "A, C"  # bits 0 and 2

    def test_all_bits(self):
        assert bits(7, ["A", "B", "C"]) == "A, B, C"

    def test_no_bits(self):
        assert bits(0, ["A", "B", "C"]) == "-"

    def test_middle_bit(self):
        assert bits(2, ["A", "B", "C"]) == "B"


class TestDecodeCodec:
    """decode_codec() formats codec data into human-readable strings."""

    def test_sbc_codec(self):
        # AVDTP media codec capability: data[0] >> 4 = media, data[1] = codec,
        # data[2:] = codec info. SBC info: sampling+channels, blocks+subbands+alloc,
        # min bitpool, max bitpool.
        #   0x72 -> sampling 0b0111 (32/44.1/48 kHz), channels 0b0010 (Stereo)
        #   0x8E -> blocks 0b1000 (4), subbands 0b11 (8, 4), alloc 0b10 (SNR)
        #   0x0D, 0x00 -> bitpool 13..0
        data = bytes([0x00, 0x00, 0x72, 0x8E, 0x0D, 0x00])
        result = decode_codec(data)
        assert "Audio / SBC" in result
        assert "sampling: 32 kHz, 44.1 kHz, 48 kHz" in result
        assert "channels: Stereo" in result
        assert "blocks:   4" in result
        assert "subbands: 8, 4" in result
        assert "alloc:    SNR" in result
        assert "bitpool:  13..0" in result

    def test_aac_codec(self):
        # data[0] >> 4 = media (0=Audio), data[1] = codec (0x02=AAC)
        # info[0] = 0x00 = MPEG-2 LC (bit 0), info[1:3] = sampling, info[2] = channels
        data = bytes([0x00, 0x02, 0x00, 0x00, 0x00, 0x00])
        result = decode_codec(data)
        assert "AAC" in result

    def test_vendor_codec(self):
        # data[1] = 0xFF (vendor codec); info[0:4] = vendor ID, info[4:6] = codec ID,
        # both little-endian: 0x0000012D + 0x00AA is Sony LDAC.
        data = bytes([0x00, 0xFF, 0x2D, 0x01, 0x00, 0x00, 0xAA, 0x00])
        result = decode_codec(data)
        assert "LDAC" in result

    def test_unknown_codec(self):
        data = bytes([0x00, 0x99, 0x00, 0x00, 0x00, 0x00])
        result = decode_codec(data)
        assert "0x99" in result

    def test_sbc_short_info(self):
        """Codec with insufficient info bytes — should not crash."""
        data = bytes([0x00, 0x00, 0x00])
        result = decode_codec(data)
        assert "SBC" in result

    def test_vendor_short_info(self):
        """Vendor codec with insufficient info — should not crash."""
        data = bytes([0x00, 0xFF, 0x00])
        result = decode_codec(data)
        assert "Vendor" in result or "vendor" in result

    def test_raw_hex_included(self):
        data = bytes([0x00, 0x00, 0x00, 0x00, 0x00])
        result = decode_codec(data)
        assert "raw:" in result or "raw :" in result


class TestConstants:
    """Verify protocol constants are correct."""

    def test_avdtp_psm(self):
        assert AVDTP_PSM == 25

    def test_msg_types(self):
        assert MSG_TYPES[0] == "command"
        assert MSG_TYPES[1] == "general reject"
        assert MSG_TYPES[2] == "accept"
        assert MSG_TYPES[3] == "reject"

    def test_categories(self):
        assert CATEGORIES[1] == "Media Transport"
        assert CATEGORIES[7] == "Media Codec"

    def test_codecs(self):
        assert CODECS[0x00] == "SBC"
        assert CODECS[0x01] == "MPEG-1,2 Audio (MP3)"
        assert CODECS[0x02] == "MPEG-2,4 AAC"

    def test_vendor_codecs(self):
        assert VENDOR_CODECS[(0x012D, 0x00AA)] == "Sony LDAC"
        assert VENDOR_CODECS[(0x004F, 0x0001)] == "aptX"
