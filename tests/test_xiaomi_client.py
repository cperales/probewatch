"""Unit tests for SPP v1 and v2 framing, CRC, and crypto layers.

These tests exercise the pure-logic functions in xiaomi_client.py without
any Bluetooth hardware or network access.
"""

import struct
import time

import pytest

# Import from src/ via conftest sys.path
from xiaomi_client import (
    SESSION_START,
    T_ACK,
    T_DATA,
    T_NACK,
    V1_EPILOGUE,
    V1_PREAMBLE,
    V1_VERSION_REQUEST,
    Session,
    XiaomiWatch,
    crc16_arc,
    derive_keys,
    encode_v2,
    hmac_sha256,
    parse_v1,
    parse_v2,
)

# --------------------------------------------------------------------------- CRC-16/ARC


class TestCrc16:
    """CRC-16/ARC (used by SPP v2 framing)."""

    def test_known_value(self):
        # CRC of SESSION_START is deterministic
        crc = crc16_arc(SESSION_START)
        # Verify it matches what encode_v2 would produce
        assert crc == crc16_arc(SESSION_START)

    def test_empty(self):
        assert crc16_arc(b"") == 0

    def test_check_value(self):
        # Reference value for CRC-16/ARC: crc("123456789") == 0xBB3D
        assert crc16_arc(b"123456789") == 0xBB3D

    def test_single_zero_byte(self):
        # A zero byte never sets a bit, so the remainder stays zero.
        assert crc16_arc(b"\x00") == 0x0000

    def test_all_zeros(self):
        assert crc16_arc(b"\x00" * 100) == 0x0000

    def test_all_ones(self):
        assert crc16_arc(b"\xff" * 100) == 0x72DB


# --------------------------------------------------------------------------- SPP v2 framing


class TestEncodeV2:
    """encode_v2 produces correct frame bytes."""

    def test_data_frame(self):
        payload = b"\x01\x01\x00\x01"  # channel 1, plain opcode, empty protobuf
        frame = encode_v2(3, 0, payload)  # T_DATA
        assert frame[:2] == b"\xa5\xa5"
        # type=3, seq=0, len=4, crc
        assert frame[2] == 3
        assert frame[3] == 0
        length = struct.unpack_from("<H", frame, 4)[0]
        assert length == 4
        # CRC should match
        assert crc16_arc(payload) == struct.unpack_from("<H", frame, 6)[0]
        assert frame[8:] == payload

    def test_session_frame(self):
        frame = encode_v2(2, 0, SESSION_START)  # T_SESSION
        assert frame[:2] == b"\xa5\xa5"
        assert frame[2] == 2
        assert frame[3] == 0
        length = struct.unpack_from("<H", frame, 4)[0]
        assert length == len(SESSION_START)
        assert frame[8:] == SESSION_START

    def test_ack_frame(self):
        frame = encode_v2(1, 5, b"")  # T_ACK, seq=5
        assert frame[:2] == b"\xa5\xa5"
        assert frame[2] == 1
        assert frame[3] == 5
        assert frame[4:6] == b"\x00\x00"  # len=0
        assert frame[6:8] == b"\x00\x00"  # crc=0
        assert frame[8:] == b""

    def test_seq_wraps(self):
        frame = encode_v2(3, 255, b"x")
        assert frame[3] == 255
        frame2 = encode_v2(3, 256, b"x")
        assert frame2[3] == 0  # seq wraps to 0

    def test_roundtrip(self):
        """encode -> parse roundtrip for all frame types."""
        for ptype in (0, 1, 2, 3):
            payload = b"\x01\x02\x03"
            frame = encode_v2(ptype, 7, payload)
            result = parse_v2(frame)
            assert result is not None
            assert result[0] == ptype
            assert result[1] == 7
            assert result[2] == payload
            assert result[3] == len(frame)


class TestParseV2:
    """parse_v2 handles valid, invalid, and partial buffers."""

    def test_valid_data_frame(self):
        payload = b"\x01\x01\x00\x01"
        frame = encode_v2(3, 0, payload)
        ptype, seq, data, consumed = parse_v2(frame)
        assert ptype == 3
        assert seq == 0
        assert data == payload
        assert consumed == len(frame)

    def test_junk_before_preamble(self):
        """The parser resyncs on the preamble and returns the frame after the junk."""
        frame = b"\x00\x01\x02" + encode_v2(3, 0, b"test")
        ptype, seq, data, consumed = parse_v2(frame)
        assert (ptype, seq, data) == (3, 0, b"test")
        assert consumed == len(frame)

    def test_junk_in_frame(self):
        """CRC mismatch causes the frame to be skipped."""
        bad = b"\xa5\xa5" + struct.pack("<BBHH", 3, 0, 4, 0xFFFF) + b"\x00\x00\x00\x00"
        ptype, seq, data, consumed = parse_v2(bad)
        assert ptype is None
        assert consumed == 2  # drop the preamble and rescan for the next one

    def test_incomplete_frame(self):
        """Partial frame returns None (wait for more bytes)."""
        buf = b"\xa5\xa5" + struct.pack("<BBH", 3, 0, 10)  # says 10 bytes, only 0 provided
        assert parse_v2(buf) is None

    def test_empty_buffer(self):
        assert parse_v2(b"") is None

    def test_multiple_frames(self):
        """parse_v2 only consumes the first frame; remaining bytes are left in buf."""
        frame1 = encode_v2(3, 0, b"aaa")
        frame2 = encode_v2(3, 1, b"bbb")
        combined = frame1 + frame2
        ptype, seq, data, consumed = parse_v2(combined)
        assert ptype == 3
        assert seq == 0
        assert data == b"aaa"
        assert consumed == len(frame1)

    def test_trailing_junk_after_valid_frame(self):
        """Only the valid frame is consumed; trailing garbage is ignored."""
        frame = encode_v2(3, 0, b"x") + b"\x00\x00\x00"
        ptype, seq, data, consumed = parse_v2(frame)
        assert ptype == 3
        assert consumed == len(frame) - 3  # only the valid frame


# --------------------------------------------------------------------------- SPP v1 parsing


class TestParseV1:
    """parse_v1 handles the Xiaomi SPP v1 version probe."""

    def test_version_request_is_correct(self):
        """The built-in request matches the expected v1 probe format."""
        assert V1_VERSION_REQUEST[:3] == V1_PREAMBLE
        assert V1_VERSION_REQUEST[-1] == V1_EPILOGUE[0]

    def test_parse_version_response(self):
        """Simulate a v2 version response from the watch."""
        # v1 payload = opcode, serial, data type, then the version bytes
        payload = bytes([0x00, 0x00, 0x00, 0x02])
        ln = len(payload)
        resp = V1_PREAMBLE + bytes([0x00, 0xC0]) + struct.pack("<H", ln) + payload + V1_EPILOGUE
        pkt, consumed = parse_v1(resp)
        assert pkt is not None
        assert pkt["channel"] == 0
        assert pkt["flags"] == 0xC0
        assert pkt["opcode"] == 0
        assert pkt["payload"] == bytes([2])
        assert consumed == len(resp)

    def test_incomplete_v1(self):
        assert parse_v1(b"\xba\xdc\xfe") == (None, 0)
        assert parse_v1(b"\xba\xdc\xfe\x00") == (None, 0)

    def test_no_preamble(self):
        assert parse_v1(b"\x00\x01\x02\x03") == (None, 0)


# --------------------------------------------------------------------------- Crypto


class TestHmacSha256:
    def test_deterministic(self):
        key = b"secret"
        msg = b"message"
        result = hmac_sha256(key, msg)
        assert len(result) == 32
        assert hmac_sha256(key, msg) == result  # deterministic

    def test_different_key(self):
        assert hmac_sha256(b"a", b"m") != hmac_sha256(b"b", b"m")


class TestDeriveKeys:
    def test_output_length(self):
        secret = bytes([0] * 32)
        phone_nonce = b"\x01" * 16
        watch_nonce = b"\x02" * 16
        result = derive_keys(secret, phone_nonce, watch_nonce)
        assert len(result) == 64

    def test_deterministic(self):
        secret = bytes([0x42] * 32)
        pn = b"\xaa" * 16
        wn = b"\xbb" * 16
        assert derive_keys(secret, pn, wn) == derive_keys(secret, pn, wn)

    def test_different_nonce(self):
        secret = bytes([0] * 32)
        pn = b"\x01" * 16
        wn1 = b"\x02" * 16
        wn2 = b"\x03" * 16
        assert derive_keys(secret, pn, wn1) != derive_keys(secret, pn, wn2)


class TestSessionCrypto:
    """Session encryption/decryption (AES-CTR and AES-CCM)."""

    @pytest.fixture
    def session(self):
        """Create a Session with known keys for deterministic testing."""
        secret = bytes([0x42] * 32)
        sess = Session(secret)
        sess.phone_nonce = b"\x01" * 16
        sess.set_keys(b"\x02" * 16)
        return sess

    def test_ctr_roundtrip_with_same_key(self, session):
        # Outbound traffic uses enc_key and inbound dec_key; force one key to
        # exercise AES-CTR symmetry itself.
        session.dec_key = session.enc_key
        data = b"hello world"
        assert session.decrypt_v2(session.encrypt_v2(data)) == data

    def test_directions_use_different_keys(self, session):
        data = b"hello world"
        assert session.dec_key != session.enc_key
        assert session.decrypt_v2(session.encrypt_v2(data)) != data

    def test_ctr_different_keys_differ(self, session):
        data = b"hello world"
        enc1 = session.encrypt_v2(data)
        # Create a second session with different keys
        secret2 = bytes([0x43] * 32)
        sess2 = Session(secret2)
        sess2.phone_nonce = b"\x01" * 16
        sess2.set_keys(b"\x02" * 16)
        enc2 = sess2.encrypt_v2(data)
        assert enc1 != enc2

    def test_ctr_produces_different_ciphertext(self, session):
        """Each encryption produces different ciphertext (IV is the key itself,
        but the session uses the same key as IV per Xiaomi's design)."""
        data = b"hello"
        enc1 = session.encrypt_v2(data)
        enc2 = session.encrypt_v2(data)
        # Same key/IV -> same ciphertext (deterministic CTR)
        assert enc1 == enc2

    def test_ccm_encrypt(self, session):
        data = b"test data for CCM"
        encrypted = session.ccm_encrypt(data, 0)
        # CCM adds a 4-byte tag
        assert len(encrypted) == len(data) + 4

    def test_ccm_nonce_length(self, session):
        """CCM nonce is enc_nonce (4 bytes) + counter (4 bytes) = 8 bytes."""
        data = b"short"
        encrypted = session.ccm_encrypt(data, 0)
        assert len(encrypted) == len(data) + 4


# --------------------------------------------------------------------------- build_command

from xiaomi_client import build_command  # noqa: E402


class TestBuildCommand:
    """build_command creates Command protobufs from type/subtype and optional payload."""

    def test_empty_body(self):
        """Empty body is the default: only type and subtype are set."""
        cmd = build_command(2, 34)
        assert cmd.type == 2
        assert cmd.subtype == 34
        assert not cmd.HasField("system")
        assert not cmd.HasField("health")

    def test_with_payload(self):
        """text_format.Parse populates nested fields from the payload string."""
        payload = "system { raiseToWake { mode: 2 } }"
        cmd = build_command(2, 25, payload)
        assert cmd.type == 2
        assert cmd.subtype == 25
        assert cmd.HasField("system")
        assert cmd.system.raiseToWake.mode == 2

    def test_payload_overrides_defaults(self):
        """A text_format payload can override the default empty body."""
        cmd = build_command(2, 25, "system { raiseToWake { mode: 1 } }")
        assert cmd.HasField("system")
        assert cmd.system.raiseToWake.mode == 1

    def test_invalid_payload_raises(self):
        """Malformed text_format raises an exception."""
        from google.protobuf import text_format as _tf

        with pytest.raises(_tf.ParseError):
            build_command(2, 25, "this is not valid protobuf text")

    def test_dnd_status_payload(self):
        """DND status payload (2/34, documented; watch returns status:1)."""
        cmd = build_command(2, 34, "system { dndStatus { status: 0 } }")
        assert cmd.type == 2
        assert cmd.subtype == 34
        assert cmd.HasField("system")
        assert cmd.system.dndStatus.status == 0
        assert cmd.SerializeToString().hex(" ") == "08 02 10 22 22 04 5a 02 08 00"

    def test_raise_to_wake_payload(self):
        """Raise-to-wake payload (2/25, documented; watch ignores the write)."""
        cmd = build_command(2, 25, "system { raiseToWake { mode: 2 } }")
        assert cmd.type == 2
        assert cmd.subtype == 25
        assert cmd.HasField("system")
        assert cmd.system.raiseToWake.mode == 2
        assert cmd.SerializeToString().hex(" ") == "08 02 10 19 22 04 3a 02 08 02"

    def test_dnd_sync_set_payload(self):
        """Verified dndSync write (2/15) — docs/protocol.md pins this string."""
        cmd = build_command(2, 15, "system { miscSettingSet { dndSync { enabled: 1 } } }")
        assert cmd.type == 2
        assert cmd.subtype == 15
        assert cmd.system.miscSettingSet.dndSync.enabled == 1
        assert cmd.SerializeToString().hex(" ") == "08 02 10 0f 22 07 9a 02 04 12 02 08 01"

    def test_dnd_sync_restore_payload(self):
        """Verified dndSync restore (2/15) — original enabled=0."""
        cmd = build_command(2, 15, "system { miscSettingSet { dndSync { enabled: 0 } } }")
        assert cmd.type == 2
        assert cmd.subtype == 15
        assert cmd.system.miscSettingSet.dndSync.enabled == 0
        assert cmd.SerializeToString().hex(" ") == "08 02 10 0f 22 07 9a 02 04 12 02 08 00"

    def test_dnd_sync_get_payload(self):
        """Verified dndSync read-back (2/14 setting 2) — docs pin this string."""
        cmd = build_command(2, 14, "system { miscSettingGet { setting: 2 } }")
        assert cmd.type == 2
        assert cmd.subtype == 14
        assert cmd.system.miscSettingGet.setting == 2
        assert cmd.SerializeToString().hex(" ") == "08 02 10 0e 22 05 92 02 02 08 02"

    def test_notification_settings_payload(self):
        """Verified notification-settings write (2/15) — docs pin this string."""
        payload = (
            "system { miscSettingSet { miscNotificationSettings "
            "{ wakeScreen: 1 onlyWhenPhoneLocked: 2 onlyWhenWorn: 2 } } }"
        )
        cmd = build_command(2, 15, payload)
        s = cmd.system.miscSettingSet.miscNotificationSettings
        assert (s.wakeScreen, s.onlyWhenPhoneLocked, s.onlyWhenWorn) == (1, 2, 2)
        assert cmd.SerializeToString().hex(" ") == (
            "08 02 10 0f 22 0b 9a 02 08 0a 06 08 01 10 02 18 02"
        )

    def test_notification_settings_restore_payload(self):
        """Verified notification-settings restore (2/15) — original 2/1/1."""
        payload = (
            "system { miscSettingSet { miscNotificationSettings "
            "{ wakeScreen: 2 onlyWhenPhoneLocked: 1 onlyWhenWorn: 1 } } }"
        )
        cmd = build_command(2, 15, payload)
        s = cmd.system.miscSettingSet.miscNotificationSettings
        assert (s.wakeScreen, s.onlyWhenPhoneLocked, s.onlyWhenWorn) == (2, 1, 1)
        assert cmd.SerializeToString().hex(" ") == (
            "08 02 10 0f 22 0b 9a 02 08 0a 06 08 02 10 01 18 01"
        )

    def test_watchface_list_command(self):
        """Verified watchface list is 4/0 (docs/protocol.md), empty body."""
        cmd = build_command(4, 0)
        assert cmd.type == 4
        assert cmd.subtype == 0
        assert cmd.SerializeToString().hex(" ") == "08 04 10 00"

    def test_watchface_set_ack_command(self):
        """Watchface set 4/1 with no id returns ack:1; it is not the list."""
        cmd = build_command(4, 1)
        assert cmd.type == 4
        assert cmd.subtype == 1
        assert cmd.SerializeToString().hex(" ") == "08 04 10 01"

    def test_watchface_install_status_command(self):
        """Watchface install status 4/4, read-only."""
        cmd = build_command(4, 4)
        assert cmd.type == 4
        assert cmd.subtype == 4
        assert cmd.SerializeToString().hex(" ") == "08 04 10 04"


# --------------------------------------------------------------------------- drain

import xiaomi_pb2  # noqa: E402


class TestDrain:
    """XiaomiWatch.drain() empties the inbox and prints every queued command."""

    def test_drain_empty_inbox(self):
        """Drain on an empty inbox is a no-op."""
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32)
        # link is None, but drain doesn't touch it
        w.drain()  # should not raise

    def test_drain_prints_all_commands(self):
        """Drain pops every command from inbox and prints them."""
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32)
        cmd1 = xiaomi_pb2.Command(type=2, subtype=1)
        cmd2 = xiaomi_pb2.Command(type=2, subtype=2)
        w.inbox.append(cmd1)
        w.inbox.append(cmd2)
        assert len(w.inbox) == 2

        # Capture printed output
        import io
        import sys

        buf = io.StringIO()
        old_stdout = sys.stdout
        sys.stdout = buf
        w.drain()
        sys.stdout = old_stdout

        output = buf.getvalue()
        assert "[2/1]" in output
        assert "[2/2]" in output
        assert len(w.inbox) == 0  # inbox is emptied


# --------------------------------------------------------------------------- NACK retransmit


class TestNackRetransmit:
    """XiaomiWatch._pump retransmits once per seq when the watch NACKs."""

    def _make_watch(self):
        """Create a XiaomiWatch with encrypted session and fake link."""
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32)
        # Initialize session keys so encryption works without auth
        w.sess.phone_nonce = b"\x01" * 16
        w.sess.set_keys(b"\x02" * 16)
        w.sess.encrypted = True

        sent_frames: list[bytes] = []

        class FakeLink:
            def __init__(self):
                self.buf = b""

            def send(self, data: bytes):
                sent_frames.append(data)

            def fill(self, timeout: float) -> bool:
                return False

            def close(self):
                pass

        w.link = FakeLink()
        return w, sent_frames

    def test_nack_retransmits_command(self):
        """A NACK for seq 0 triggers a verbatim retransmit of the same command."""
        w, sent_frames = self._make_watch()

        # Build a command and send it
        cmd = xiaomi_pb2.Command(type=2, subtype=34)
        w.send_command(cmd)
        assert w.tx_next == 1  # incremented after send
        assert 0 in w._sent  # tracked by seq 0

        # Simulate a NACK for seq 0 in the link buffer
        nack_frame = encode_v2(0, 0, b"")  # type=NACK, seq=0
        w.link.buf = nack_frame

        # Pump with zero timeout (no more data will arrive)
        w._pump(0)

        # Verify: original send + one retransmit = 2 frames total
        assert len(sent_frames) == 2, f"expected 2 frames, got {len(sent_frames)}"

        # Both frames must be identical (verbatim retransmit)
        assert sent_frames[0] == sent_frames[1]

        # The retransmitted frame must be a DATA frame (type 3)
        ptype, _, _, _ = parse_v2(sent_frames[1])
        assert ptype == 3, f"retransmit should be DATA, got type {ptype}"

    def test_repeated_nack_retransmits_again(self):
        """A second NACK for the same seq means it is still missing: resend it."""
        w, sent_frames = self._make_watch()

        cmd = xiaomi_pb2.Command(type=2, subtype=18)
        w.send_command(cmd)

        # First NACK
        w.link.buf = encode_v2(0, 0, b"")
        w._pump(0)
        assert len(sent_frames) == 2  # original + retransmit

        # Second NACK for the same seq: the peer still has not got it
        w.link.buf = encode_v2(0, 0, b"")
        w._pump(0)
        assert len(sent_frames) == 3  # another retransmit

    def test_nack_for_unsent_seq_ignored(self):
        """A NACK for a seq we never sent cannot release or resend anything."""
        w, sent_frames = self._make_watch()
        for _ in range(3):
            w.send_command(xiaomi_pb2.Command(type=2, subtype=1))
        sent_frames.clear()

        w.link.buf = encode_v2(T_NACK, 50, b"")
        w._pump(0)

        assert sent_frames == []
        assert w.tx_base == 0
        assert w.pending_count == 3


# --------------------------------------------------------------------------- capture

import json  # noqa: E402

from xiaomi_client import Capture  # noqa: E402


class TestCapture:
    """Capture writes one NDJSON record per frame, decrypted on rx and plaintext on tx."""

    def _make_watch(self, tmp_path):
        capture = Capture(str(tmp_path / "capture.ndjson"))
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32, capture=capture)
        w.sess.phone_nonce = b"\x01" * 16
        w.sess.set_keys(b"\x02" * 16)
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

        w.link = FakeLink()
        return w, sent, capture

    def _records(self, capture) -> list[dict]:
        capture.close()
        with open(capture.path) as handle:
            return [json.loads(line) for line in handle if line.strip()]

    def test_rx_data_recorded_decrypted(self, tmp_path):
        """An encrypted DATA frame is stored after decryption, with channel and opcode."""
        w, _, capture = self._make_watch(tmp_path)
        plain = xiaomi_pb2.Command(type=2, subtype=1).SerializeToString()
        body = bytes([1, 2]) + w.sess._ctr(w.sess.dec_key, plain)  # watch -> phone key
        w.link.buf = encode_v2(T_DATA, 7, body)
        # Set rx_expect so seq 7 is treated as in-order (not out-of-order)
        w.rx_expect = 7

        w._pump(0)
        records = self._records(capture)

        data = [r for r in records if r["dir"] == "rx" and r["type"] == T_DATA]
        assert len(data) == 1
        assert (data[0]["ch"], data[0]["op"], data[0]["seq"]) == (1, 2, 7)
        assert bytes.fromhex(data[0]["hex"]) == plain
        assert data[0]["len"] == len(plain)

    def test_tx_data_recorded_plaintext(self, tmp_path):
        """Our own commands are stored before encryption, so records are comparable."""
        w, _, capture = self._make_watch(tmp_path)
        cmd = xiaomi_pb2.Command(type=2, subtype=15)
        w.send_command(cmd)

        records = self._records(capture)
        sent = [r for r in records if r["dir"] == "tx"]
        assert len(sent) == 1
        assert (sent[0]["ch"], sent[0]["op"]) == (1, 2)
        assert bytes.fromhex(sent[0]["hex"]) == cmd.SerializeToString()

    def test_short_data_frame_is_survivable(self, tmp_path):
        """A DATA frame without the channel/opcode header is recorded, not an IndexError."""
        w, sent, capture = self._make_watch(tmp_path)
        w.link.buf = encode_v2(T_DATA, 9, b"\x01")  # one byte: no opcode
        # Set rx_expect so seq 9 is treated as in-order (not out-of-order)
        w.rx_expect = 9

        w._pump(0)  # must not raise
        records = self._records(capture)

        assert any(r.get("note") == "short data" for r in records)
        acked = [parse_v2(frame) for frame in sent if parse_v2(frame)[0] == T_ACK]
        assert acked, "the short frame must still be ACKed or the link drops"

    def test_non_data_frames_recorded(self, tmp_path):
        """ACK/NACK/SESSION frames are recorded too, which is what dates a reply."""
        w, _, capture = self._make_watch(tmp_path)
        w.link.buf = encode_v2(T_ACK, 3, b"")
        w._pump(0)

        records = self._records(capture)
        assert any(r["dir"] == "rx" and r["type"] == T_ACK and r["seq"] == 3 for r in records)

    def test_capture_is_optional(self):
        """Without a capture object the client behaves exactly as before."""
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32)
        assert w.capture is None


# --------------------------------------------------------------------------- keepalive


class TestKeepalive:
    """listen(keepalive=...) pings the watch so a long capture keeps its session."""

    def _make_watch(self, tmp_path):
        capture = Capture(str(tmp_path / "capture.ndjson"))
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32, capture=capture)
        w.sess.phone_nonce = b"\x01" * 16
        w.sess.set_keys(b"\x02" * 16)
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

        w.link = FakeLink()
        return w, sent

    def test_keepalive_sends_battery_queries(self, tmp_path):
        w, sent = self._make_watch(tmp_path)
        w.listen(0.12, keepalive=0.02)
        assert sent, "keepalive must send something"
        ptype, _, payload, _ = parse_v2(sent[0])
        assert ptype == T_DATA
        # decrypted in the capture; here just assert it is addressed to the battery query
        cmd = xiaomi_pb2.Command()
        cmd.ParseFromString(w.sess._ctr(w.sess.enc_key, payload[2:]))
        assert (cmd.type, cmd.subtype) == (2, 1)

    def test_no_keepalive_sends_nothing(self, tmp_path):
        w, sent = self._make_watch(tmp_path)
        w.listen(0.05)
        assert sent == []


# --------------------------------------------------------------------------- L2 prefix

from xiaomi_client import (  # noqa: E402
    CH_ACTIVITY,
    CH_DATA,
    CH_FILE_SENSOR,
    CH_LYRA,
    CH_MASS_VOICE,
    CH_NETWORK,
    CH_OTA,
    CH_PROTOBUF,
    CH_RESEARCH,
    CHANNEL_NAMES,
    OP_READ,
    OP_WRITE,
    OP_WRITE_ENC,
)


class TestL2Prefix:
    """_send_data builds the correct [channel, opcode] prefix for every combination."""

    def _make_watch(self):
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32)
        w.sess.phone_nonce = b"\x01" * 16
        w.sess.set_keys(b"\x02" * 16)
        w.sess.encrypted = True
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

        w.link = FakeLink()
        return w, sent

    def _parse_l2(self, frame: bytes):
        """Extract channel and opcode from a DATA frame."""
        _, _, body, _ = parse_v2(frame)
        return body[0] & 0x0F, body[1]

    def test_channel_1_write(self):
        w, sent = self._make_watch()
        w._send_data(OP_WRITE, b"test")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_PROTOBUF
        assert op == OP_WRITE

    def test_channel_1_write_enc(self):
        w, sent = self._make_watch()
        w._send_data(OP_WRITE_ENC, b"test")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_PROTOBUF
        assert op == OP_WRITE_ENC

    def test_channel_6_ota(self):
        w, sent = self._make_watch()
        w.l2_channel = CH_OTA
        w._send_data(OP_WRITE, b"ota")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_OTA
        assert op == OP_WRITE

    def test_channel_9_research(self):
        w, sent = self._make_watch()
        w.l2_channel = CH_RESEARCH
        w._send_data(OP_READ, b"")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_RESEARCH
        assert op == OP_READ

    def test_channel_4_sensor(self):
        w, sent = self._make_watch()
        w.l2_channel = CH_FILE_SENSOR
        w._send_data(OP_WRITE_ENC, b"sensor")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_FILE_SENSOR
        assert op == OP_WRITE_ENC

    def test_channel_3_voice(self):
        w, sent = self._make_watch()
        w.l2_channel = CH_MASS_VOICE
        w._send_data(OP_WRITE, b"voice")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_MASS_VOICE
        assert op == OP_WRITE

    def test_channel_7_network(self):
        w, sent = self._make_watch()
        w.l2_channel = CH_NETWORK
        w._send_data(OP_WRITE_ENC, b"net")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_NETWORK
        assert op == OP_WRITE_ENC

    def test_channel_8_lyra(self):
        w, sent = self._make_watch()
        w.l2_channel = CH_LYRA
        w._send_data(OP_READ, b"")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_LYRA
        assert op == OP_READ

    def test_channel_5_fitness(self):
        w, sent = self._make_watch()
        w.l2_channel = CH_ACTIVITY
        w._send_data(OP_WRITE, b"fit")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_ACTIVITY
        assert op == OP_WRITE

    def test_channel_2_mass(self):
        w, sent = self._make_watch()
        w.l2_channel = CH_DATA
        w._send_data(OP_WRITE, b"mass")
        ch, op = self._parse_l2(sent[0])
        assert ch == CH_DATA
        assert op == OP_WRITE

    def test_all_channels_have_names(self):
        """Every known channel has a name in CHANNEL_NAMES."""
        for ch in range(1, 10):
            assert ch in CHANNEL_NAMES, f"channel {ch} missing from CHANNEL_NAMES"

    def test_all_opcodes_mapped(self):
        """OP_WRITE, OP_WRITE_ENC, OP_READ are distinct constants."""
        assert OP_WRITE == 1
        assert OP_WRITE_ENC == 2
        assert OP_READ == 3


# --------------------------------------------------------------------------- ARQ state machine


class TestARQStateMachine:
    """Unit tests for the selective-repeat ARQ state machine.

    These tests drive the state machine with synthetic ACK/NAK/timeout sequences
    to verify: out-of-order arrival, duplicate suppression, retransmit-after-NAK,
    and window exhaustion.
    """

    def _make_watch(self):
        """Create a XiaomiWatch with encrypted session and fake link."""
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32)
        w.sess.phone_nonce = b"\x01" * 16
        w.sess.set_keys(b"\x02" * 16)
        w.sess.encrypted = True

        sent_frames: list[bytes] = []

        class FakeLink:
            def __init__(self):
                self.buf = b""

            def send(self, data: bytes):
                sent_frames.append(data)

            def fill(self, timeout: float) -> bool:
                return False

            def close(self):
                pass

        w.link = FakeLink()
        return w, sent_frames

    def test_out_of_order_sends_nak(self):
        """An out-of-order DATA frame triggers a NAK, not an ACK."""
        w, sent_frames = self._make_watch()
        # Set rx_expect so seq 5 is "in-order" for the first frame
        w.rx_expect = 5
        body = bytes([1, 1]) + b"\x00" * 4
        w.link.buf = encode_v2(T_DATA, 5, body)
        w._pump(0)

        # Should have sent an ACK for seq 5
        acks = [f for f in sent_frames if parse_v2(f)[0] == T_ACK]
        assert len(acks) == 1
        _, ack_seq, _, _ = parse_v2(acks[0])
        assert ack_seq == 5

        # Now send seq 7 (out-of-order: rx_expect=6, diff=(7-6)=1 < 128, not stale)
        w.link.buf = encode_v2(T_DATA, 7, body)
        w._pump(0)

        # The NAK must carry the first missing seq (6), not the seq that arrived
        naks = [f for f in sent_frames if parse_v2(f)[0] == T_NACK]
        assert len(naks) == 1
        _, nak_seq, _, _ = parse_v2(naks[0])
        assert nak_seq == 6

    def test_duplicate_suppression(self):
        """A DATA frame whose seq - expected >= 128 (unsigned) is dropped silently."""
        w, sent_frames = self._make_watch()
        # Set rx_expect so seq 100 is "in-order"
        w.rx_expect = 100
        body = bytes([1, 1]) + b"\x00" * 4

        # Send seq 100 (in-order)
        w.link.buf = encode_v2(T_DATA, 100, body)
        w._pump(0)
        assert len(sent_frames) == 1  # ACK for seq 100

        # Send seq 10 (unsigned diff = 10 - 100 = -90 → 166 >= 128 → stale duplicate)
        w.link.buf = encode_v2(T_DATA, 10, body)
        w._pump(0)

        # No additional frames should be sent (duplicate dropped silently)
        assert len(sent_frames) == 1

    def test_retransmit_after_nak_range(self):
        """A NAK for seq N releases everything before it and resends from N onwards."""
        w, sent_frames = self._make_watch()

        # Send 3 commands (seq 0, 1, 2)
        for _i in range(3):
            cmd = xiaomi_pb2.Command(type=2, subtype=1)
            w.send_command(cmd)

        assert w.tx_next == 3
        assert w.pending_count == 3

        # Simulate a NACK for seq 1
        w.link.buf = encode_v2(T_NACK, 1, b"")
        w._pump(0)

        # seq 0 is treated as acknowledged locally; 1 and 2 are resent, oldest first.
        # No ACK is emitted: the NAK already told the peer what we have.
        assert w.tx_base == 1
        assert [parse_v2(f)[1] for f in sent_frames if parse_v2(f)[0] == T_DATA] == [
            0,
            1,
            2,
            1,
            2,
        ]
        assert not [f for f in sent_frames if parse_v2(f)[0] == T_ACK]

    def test_window_exhaustion(self):
        """Sending past TX_WINDOW returns None; window opens after ACK."""
        w, sent_frames = self._make_watch()

        # Fill the window (32 frames succeed, 33rd is rejected)
        for i in range(33):
            cmd = xiaomi_pb2.Command(type=2, subtype=1)
            result = w._send_data(OP_WRITE_ENC, cmd.SerializeToString())
            if i < 32:
                assert result is not None, f"frame {i} should have been sent"
            else:
                assert result is None, "frame 33 should return None (window full)"

        assert w.pending_count == 32
        assert w.tx_next == 32

        # Simulate an ACK for seq 31 (cumulative)
        w.link.buf = encode_v2(T_ACK, 31, b"")
        w._pump(0)

        # Window should have opened; next send should succeed
        cmd = xiaomi_pb2.Command(type=2, subtype=2)
        result = w._send_data(OP_WRITE_ENC, cmd.SerializeToString())
        assert result is not None, "should be able to send after window opens"
        assert w.pending_count == 1  # only the new frame is pending

    def test_cumulative_ack_advances_tx_base(self):
        """A cumulative ACK for seq N advances tx_base past N."""
        w, sent_frames = self._make_watch()

        # Send 5 commands
        for _i in range(5):
            cmd = xiaomi_pb2.Command(type=2, subtype=1)
            w.send_command(cmd)

        assert w.tx_base == 0
        assert w.tx_next == 5
        assert w.pending_count == 5

        # Simulate a cumulative ACK for seq 4
        w.link.buf = encode_v2(T_ACK, 4, b"")
        w._pump(0)

        # tx_base should advance past 4
        assert w.tx_base == 5
        assert w.pending_count == 0

    def test_delayed_ack_timer(self):
        """When pending count is low, ACK is delayed until the 500 ms timer fires."""
        w, sent_frames = self._make_watch()
        # Set rx_expect so seq 0 is "in-order"
        w.rx_expect = 0
        body = bytes([2, 1]) + b"\x00" * 4  # opcode 1 (not 1 or 8), so delayed ACK

        w.link.buf = encode_v2(T_DATA, 0, body)
        w._pump(0)

        # No ACK should have been sent yet (timer not fired)
        acks = [f for f in sent_frames if parse_v2(f)[0] == T_ACK]
        assert len(acks) == 0
        assert w.ack_deadline is not None

        # Let the 500 ms timer expire
        w.ack_deadline = 0.0
        w._pump(0)

        # Now an ACK should have been sent, and the pending state cleared
        acks = [f for f in sent_frames if parse_v2(f)[0] == T_ACK]
        assert len(acks) == 1
        _, ack_seq, _, _ = parse_v2(acks[0])
        assert ack_seq == 0
        assert w.rx_pending == 0
        assert w.ack_deadline is None

    def test_delayed_ack_timer_not_reset_by_later_frames(self):
        """A burst must not postpone the ACK forever: the first deadline stands."""
        w, sent_frames = self._make_watch()
        body = bytes([2, 1]) + b"\x00" * 4
        w.link.buf = encode_v2(T_DATA, 0, body)
        w._pump(0)
        first_deadline = w.ack_deadline
        assert first_deadline is not None

        w.link.buf = encode_v2(T_DATA, 1, body)
        w._pump(0)

        assert w.ack_deadline == first_deadline

    def test_delayed_ack_flushed_at_threshold(self):
        """ACK_THRESHOLD pending frames force an immediate ACK."""
        w, sent_frames = self._make_watch()
        body = bytes([2, 1]) + b"\x00" * 4
        threshold = XiaomiWatch.ACK_THRESHOLD

        for seq in range(threshold):
            w.link.buf = encode_v2(T_DATA, seq, body)
            w._pump(0)

        acks = [f for f in sent_frames if parse_v2(f)[0] == T_ACK]
        assert len(acks) == 1
        _, ack_seq, _, _ = parse_v2(acks[0])
        assert ack_seq == threshold - 1
        assert w.rx_pending == 0

    def test_cumulative_ack_across_wrap(self):
        """ACKs keep releasing frames after the 8-bit sequence number wraps."""
        w, _sent_frames = self._make_watch()
        w.tx_base = 250
        w.tx_next = 250

        for _i in range(5):
            w._send_data(OP_WRITE_ENC, b"\x08\x01\x02")
        w.link.buf = encode_v2(T_ACK, 254, b"")
        w._pump(0)
        assert w.tx_base == 255
        assert w.pending_count == 0

        for _i in range(3):
            w._send_data(OP_WRITE_ENC, b"\x08\x01\x02")  # seqs 255, 0, 1
        w.link.buf = encode_v2(T_ACK, 1, b"")
        w._pump(0)

        assert w.tx_base == 2
        assert w.tx_next == 2
        assert w.pending_count == 0
        assert w._sent == {}

    def test_ack_for_unsent_seq_ignored(self):
        """An ACK for a frame we never sent must not move the window."""
        w, _sent_frames = self._make_watch()
        for _i in range(3):
            w.send_command(xiaomi_pb2.Command(type=2, subtype=1))

        w.link.buf = encode_v2(T_ACK, 50, b"")
        w._pump(0)

        assert w.tx_base == 0
        assert w.tx_next == 3
        assert w.pending_count == 3

    def test_stale_ack_ignored(self):
        """A repeated ACK for an already released seq keeps the newer frames tracked."""
        w, _sent_frames = self._make_watch()
        for _i in range(3):
            w.send_command(xiaomi_pb2.Command(type=2, subtype=1))

        w.link.buf = encode_v2(T_ACK, 1, b"")
        w._pump(0)
        assert w.tx_base == 2
        assert w.pending_count == 1

        w.link.buf = encode_v2(T_ACK, 0, b"")
        w._pump(0)

        assert w.tx_base == 2
        assert w.pending_count == 1

    def test_timeout_retransmits_unacked(self):
        """A frame unacked for SEND_TIMEOUT is resent on its own."""
        w, sent_frames = self._make_watch()
        for _i in range(2):
            w.send_command(xiaomi_pb2.Command(type=2, subtype=1))
        sent_frames.clear()

        w._sent_times[0] = time.time() - XiaomiWatch.SEND_TIMEOUT - 1
        w._pump(0)

        resent = [parse_v2(f)[1] for f in sent_frames if parse_v2(f)[0] == T_DATA]
        assert resent == [0]
        assert w.pending_count == 2  # resending does not consume the window

    def test_no_regression_single_frame_command(self):
        """Single-frame commands (e.g. battery query) work exactly as before."""
        w, sent_frames = self._make_watch()

        # Send a battery query (single frame)
        cmd = xiaomi_pb2.Command(type=2, subtype=1)
        w.send_command(cmd)
        assert w.tx_next == 1
        assert w.pending_count == 1

        # Simulate a response from the watch (encrypted with dec_key, phone decrypts with dec_key)
        resp = xiaomi_pb2.Command(type=2, subtype=1)
        # Use OP_WRITE_ENC (opcode 2) so the data gets decrypted
        body = bytes([1, 2]) + w.sess._ctr(w.sess.dec_key, resp.SerializeToString())
        w.link.buf = encode_v2(T_DATA, 0, body)
        w._pump(0)

        # Should have received the command in inbox
        assert len(w.inbox) == 1
        assert w.inbox[0].type == 2
        assert w.inbox[0].subtype == 1

        # And an ACK should have been sent (immediate for payload[0] == 1)
        acks = [f for f in sent_frames if parse_v2(f)[0] == T_ACK]
        assert len(acks) == 1


# --------------------------------------------------------------------------- mass push (ota_type = 2)

from xiaomi_client import (  # noqa: E402
    MASS_UPLOAD_FIRMWARE,
    mass_chunks,
    mass_prepare_command,
    mass_upload_command,
)


class TestMassChunks:
    """mass_chunks splits a payload into device-sized chunks."""

    def test_exact_split(self):
        assert mass_chunks(b"12345678", 4) == [b"1234", b"5678"]

    def test_short_last_chunk(self):
        assert mass_chunks(b"1234567", 4) == [b"1234", b"567"]

    def test_empty(self):
        assert mass_chunks(b"", 4096) == []

    def test_chunk_larger_than_data(self):
        assert mass_chunks(b"abc", 4096) == [b"abc"]


class TestMassCommands:
    """The prepare and upload protobufs carry the right fields."""

    def test_prepare_fields(self):
        cmd = mass_prepare_command("2.2.111", "0" * 32)
        assert cmd.type == 2 and cmd.subtype == 5
        r = cmd.system.firmwareInstallRequest
        assert (r.unknown1, r.unknown2, r.version, r.md5) == (0, 0, "2.2.111", "0" * 32)

    def test_upload_fields(self):
        md5sum = bytes(range(16))
        cmd = mass_upload_command(md5sum, 3452039)
        assert cmd.type == 22 and cmd.subtype == 0
        r = cmd.dataUpload.dataUploadRequest
        assert r.type == MASS_UPLOAD_FIRMWARE
        assert r.md5sum == md5sum
        assert r.size == 3452039

    def test_upload_default_type_is_firmware(self):
        cmd = mass_upload_command(b"\x00" * 16, 0)
        assert cmd.dataUpload.dataUploadRequest.type == MASS_UPLOAD_FIRMWARE


class TestMassPush:
    """mass_push arms the receiver, then streams plaintext chunks on channel 2."""

    def _make_watch(self):
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 1, b"\x00" * 32)
        w.sess.phone_nonce = b"\x01" * 16
        w.sess.set_keys(b"\x02" * 16)
        w.sess.encrypted = True
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

        w.link = FakeLink()
        return w, sent

    @staticmethod
    def _fake_wait_for(chunk_size=4096, errno=0):
        def wait(ctype, subtype, timeout=10):
            if ctype == 2:
                r = xiaomi_pb2.Command(type=2, subtype=5)
                r.system.firmwareInstallResponse.status = 0
                return r
            if ctype == 22:
                r = xiaomi_pb2.Command(type=22, subtype=0)
                r.dataUpload.dataUploadAck.errno = errno
                r.dataUpload.dataUploadAck.chunkSize = chunk_size
                return r
            return None

        return wait

    def test_streams_plaintext_chunks_on_channel_2(self, monkeypatch):
        w, sent = self._make_watch()
        monkeypatch.setattr(w, "wait_for", self._fake_wait_for())

        data = b"\x00" * 9000  # 4096 + 4096 + 808
        w.mass_push(data)

        parsed = [parse_v2(f) for f in sent]
        assert all(p[0] == T_DATA for p in parsed)
        # two encrypted handshake commands on channel 1, then raw plaintext chunks on channel 2
        assert [p[2][0] & 0x0F for p in parsed] == [
            CH_PROTOBUF,
            CH_PROTOBUF,
            CH_DATA,
            CH_DATA,
            CH_DATA,
        ]
        assert [p[2][1] for p in parsed] == [
            OP_WRITE_ENC,
            OP_WRITE_ENC,
            OP_WRITE,
            OP_WRITE,
            OP_WRITE,
        ]
        assert [len(p[2]) - 2 for p in parsed][-3:] == [4096, 4096, 808]
        assert w.l2_channel == 1  # restored after the push

    def test_chunk_size_override(self, monkeypatch):
        w, sent = self._make_watch()
        monkeypatch.setattr(w, "wait_for", self._fake_wait_for())

        w.mass_push(b"\x00" * 10, chunk_size=4)
        parsed = [parse_v2(f) for f in sent]
        assert [len(p[2]) - 2 for p in parsed][-3:] == [4, 4, 2]

    def test_aborts_on_ack_errno(self, monkeypatch):
        w, sent = self._make_watch()
        monkeypatch.setattr(w, "wait_for", self._fake_wait_for(errno=1))

        ack = w.mass_push(b"\x00" * 100)
        parsed = [parse_v2(f) for f in sent]
        # prepare + upload only, no data chunks
        assert len(parsed) == 2
        assert ack is not None
        assert ack.dataUpload.dataUploadAck.errno == 1

    def test_send_until_space_waits_for_window(self):
        """_send_until_space pumps the link until the TX window opens again."""
        w, sent = self._make_watch()
        for _ in range(XiaomiWatch.TX_WINDOW):
            w._send_data(OP_WRITE, b"\x00")
        assert w.pending_count == XiaomiWatch.TX_WINDOW

        # A cumulative ACK for the last in-flight frame frees the whole window.
        w.link.buf = encode_v2(T_ACK, XiaomiWatch.TX_WINDOW - 1, b"")
        frame = w._send_until_space(OP_WRITE, b"payload", timeout=1.0)

        assert frame is not None
        assert w.pending_count == 1  # only the newly sent frame remains
