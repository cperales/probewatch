"""Unit tests for the OTA channel codec (0x5A segments and `0A` commands).

Pure logic only: no Bluetooth hardware and no network. The framing and command
shapes come from the official app's `HyOtaModel` / `HyOtaExecutor`; see docs/ota.md.
"""

import struct

import pytest

from xiaomi_client import (
    CH_OTA,
    OP_WRITE,
    OTA_CMD_DATA,
    OTA_CMD_PROGRESS,
    OTA_CMD_REQUIRE,
    OTA_FLAG_FIRST,
    OTA_FLAG_LAST,
    OTA_FLAG_MIDDLE,
    OTA_FLAG_SINGLE,
    OTA_MAGIC,
    OTA_MAX_SEGMENT_DATA,
    T_DATA,
    XiaomiWatch,
    crc16_arc,
    decode_ota_data,
    decode_ota_error,
    decode_ota_progress,
    decode_ota_require,
    encode_ota_command,
    encode_ota_segment,
    encode_v2,
    ota_require_segment,
    parse_ota_command,
    parse_ota_segment,
)

# --------------------------------------------------------------------------- segment framing


class TestEncodeOtaSegment:
    def test_layout(self):
        payload = b"\x0a\x00"
        seg = encode_ota_segment(payload)
        assert seg[0] == OTA_MAGIC
        assert struct.unpack_from(">H", seg, 1)[0] == len(payload) + 2
        assert seg[3] == OTA_FLAG_SINGLE
        assert seg[4] == 0
        assert seg[5:-2] == payload
        assert len(seg) == len(payload) + 7

    def test_crc_covers_everything_after_the_magic(self):
        payload = b"abc"
        seg = encode_ota_segment(payload, flag=OTA_FLAG_MIDDLE, frame_no=7)
        crc = struct.unpack_from(">H", seg, len(seg) - 2)[0]
        assert crc == crc16_arc(seg[1:-2])

    def test_flag_and_frame_number(self):
        seg = encode_ota_segment(b"x", flag=OTA_FLAG_LAST, frame_no=200)
        assert seg[3] == OTA_FLAG_LAST
        assert seg[4] == 200

    def test_oversized_payload_rejected(self):
        with pytest.raises(ValueError):
            encode_ota_segment(b"x" * (OTA_MAX_SEGMENT_DATA + 1))

    def test_require_segment_is_the_documented_probe(self):
        payload = encode_ota_command(OTA_CMD_REQUIRE)
        expected = (
            bytes([OTA_MAGIC, 0x00, 0x04, 0x00, 0x00])
            + payload
            + struct.pack(">H", crc16_arc(bytes([0x00, 0x04, 0x00, 0x00]) + payload))
        )
        assert ota_require_segment() == expected
        assert ota_require_segment().hex(" ") == expected.hex(" ")


class TestParseOtaSegment:
    def test_roundtrip(self):
        payload = b"\x0a\x02\x01hello"
        seg = encode_ota_segment(payload, flag=OTA_FLAG_FIRST, frame_no=3)
        flag, frame_no, body, used = parse_ota_segment(seg)
        assert (flag, frame_no, body) == (OTA_FLAG_FIRST, 3, payload)
        assert used == len(seg)

    def test_incomplete_returns_none(self):
        seg = encode_ota_segment(b"payload")
        for cut in (1, 3, len(seg) - 1):
            assert parse_ota_segment(seg[:cut]) is None

    def test_junk_before_magic_is_skipped(self):
        seg = encode_ota_segment(b"body")
        flag, _, body, used = parse_ota_segment(b"\x00\x01\x02" + seg)
        assert (flag, body) == (OTA_FLAG_SINGLE, b"body")
        assert used == len(seg) + 3

    def test_no_magic_consumes_the_buffer(self):
        assert parse_ota_segment(b"\x00\x01\x02") == (None, 0, b"", 3)
        assert parse_ota_segment(b"") is None

    def test_implausible_length_skips_one_byte(self):
        # length says 0, which is below the flag+frame minimum
        assert parse_ota_segment(b"\x5a\x00\x00\x00\x00") == (None, 0, b"", 1)

    def test_crc_mismatch_is_tolerated(self):
        """The official app does not verify the CRC on receive, so neither do we."""
        seg = bytearray(encode_ota_segment(b"body"))
        seg[-1] ^= 0xFF
        flag, _, body, used = parse_ota_segment(bytes(seg))
        assert (flag, body) == (OTA_FLAG_SINGLE, b"body")
        assert used == len(seg)


# --------------------------------------------------------------------------- commands


class TestCommands:
    def test_roundtrip(self):
        payload = encode_ota_command(OTA_CMD_DATA, b"\x07chunk")
        assert parse_ota_command(payload) == (OTA_CMD_DATA, b"\x07chunk")

    def test_rejects_short_or_foreign_bodies(self):
        assert parse_ota_command(b"") is None
        assert parse_ota_command(b"\x0a") is None
        assert parse_ota_command(b"\x0b\x00") is None  # wrong service id

    def test_decode_require(self):
        # page size = 128 * 32, interval = 10 * 10 ms, timeout = 50 * 100 ms
        assert decode_ota_require(b"\x80\x0a\x32") == (4096, 100, 5000)

    def test_decode_require_rejects_short(self):
        with pytest.raises(ValueError):
            decode_ota_require(b"\x80\x0a")

    def test_decode_data(self):
        args = struct.pack(">II", 4096, 8192) + b"\xff\x00"
        assert decode_ota_data(args) == (4096, 8192, b"\xff\x00")

    def test_decode_data_rejects_short(self):
        with pytest.raises(ValueError):
            decode_ota_data(b"\x00" * 7)

    def test_decode_error(self):
        assert decode_ota_error(b"\x07battery 19%") == (7, "battery 19%")

    def test_decode_progress(self):
        assert decode_ota_progress(b"\x64") == 100

    def test_decode_rejects_empty(self):
        with pytest.raises(ValueError):
            decode_ota_error(b"")
        with pytest.raises(ValueError):
            decode_ota_progress(b"")


# --------------------------------------------------------------------------- client wiring


class TestOtaWiring:
    """`_pump` and `_handle_ota` route channel-6 frames into `ota_replies`."""

    def _make_watch(self):
        watch = XiaomiWatch("AA:BB:CC:DD:EE:FF", CH_OTA, b"\x00" * 32)
        watch.sess.phone_nonce = b"\x01" * 16
        watch.sess.set_keys(b"\x02" * 16)
        watch.sess.encrypted = True
        sent: list[bytes] = []

        class FakeLink:
            def __init__(self):
                self.buf = b""

            def send(self, data: bytes):
                sent.append(data)

            def fill(self, timeout: float) -> bool:
                return False

            def close(self):
                pass

        watch.link = FakeLink()
        return watch, sent

    def test_pump_decodes_channel_6(self):
        watch, _ = self._make_watch()
        reply = encode_ota_segment(encode_ota_command(OTA_CMD_REQUIRE, b"\x80\x0a\x32"))
        body = bytes([CH_OTA, OP_WRITE]) + reply
        watch.link.buf = encode_v2(T_DATA, 0, body)
        watch.rx_expect = 0

        watch._pump(0)

        assert watch.ota_replies == [(OTA_CMD_REQUIRE, b"\x80\x0a\x32")]

    def test_multi_segment_reassembly(self):
        watch, _ = self._make_watch()
        payload = encode_ota_command(OTA_CMD_DATA, b"0123456789")
        first, middle, last = payload[:6], payload[6:8], payload[8:]

        watch._handle_ota(encode_ota_segment(first, flag=OTA_FLAG_FIRST, frame_no=0))
        watch._handle_ota(encode_ota_segment(middle, flag=OTA_FLAG_MIDDLE, frame_no=1))
        assert watch.ota_replies == []  # still incomplete
        watch._handle_ota(encode_ota_segment(last, flag=OTA_FLAG_LAST, frame_no=2))

        assert watch.ota_replies == [(OTA_CMD_DATA, b"0123456789")]
        assert watch.ota_parts == {}

    def test_single_segment_is_delivered_immediately(self):
        watch, _ = self._make_watch()
        watch._handle_ota(encode_ota_segment(encode_ota_command(OTA_CMD_PROGRESS, b"\x64")))
        assert watch.ota_replies == [(OTA_CMD_PROGRESS, b"\x64")]

    def test_garbage_is_ignored(self):
        watch, _ = self._make_watch()
        watch._handle_ota(b"\x00\x01")
        assert watch.ota_replies == []
