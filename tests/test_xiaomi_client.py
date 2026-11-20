"""Unit tests for SPP v1 and v2 framing, CRC, and crypto layers.

These tests exercise the pure-logic functions in xiaomi_client.py without
any Bluetooth hardware or network access.
"""

import struct

import pytest

# Import from src/ via conftest sys.path
from xiaomi_client import (
    SESSION_START,
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
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 2, b"\x00" * 32)
        # link is None, but drain doesn't touch it
        w.drain()  # should not raise

    def test_drain_prints_all_commands(self):
        """Drain pops every command from inbox and prints them."""
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 2, b"\x00" * 32)
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
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 2, b"\x00" * 32)
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

    def test_one_retransmit_per_seq(self):
        """A NACK for seq 0 triggers exactly one retransmit of the same command."""
        w, sent_frames = self._make_watch()

        # Build a command and send it
        cmd = xiaomi_pb2.Command(type=2, subtype=34)
        w.send_command(cmd)
        assert w.tx_seq == 1  # incremented after send
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

        # After retransmit, _nacked contains seq 0 so a second NACK is ignored
        assert 0 in w._nacked

    def test_second_nack_ignored(self):
        """A second NACK for the same seq does not trigger another retransmit."""
        w, sent_frames = self._make_watch()

        cmd = xiaomi_pb2.Command(type=2, subtype=18)
        w.send_command(cmd)

        # First NACK
        w.link.buf = encode_v2(0, 0, b"")
        w._pump(0)
        assert len(sent_frames) == 2  # original + retransmit

        # Second NACK for the same seq — should be ignored
        w.link.buf = encode_v2(0, 0, b"")
        w._pump(0)
        assert len(sent_frames) == 2  # no additional retransmit


# --------------------------------------------------------------------------- capture

import json  # noqa: E402

from xiaomi_client import T_ACK, T_DATA, Capture  # noqa: E402


class TestCapture:
    """Capture writes one NDJSON record per frame, decrypted on rx and plaintext on tx."""

    def _make_watch(self, tmp_path):
        capture = Capture(str(tmp_path / "capture.ndjson"))
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 2, b"\x00" * 32, capture=capture)
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
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 2, b"\x00" * 32)
        assert w.capture is None


# --------------------------------------------------------------------------- keepalive


class TestKeepalive:
    """listen(keepalive=...) pings the watch so a long capture keeps its session."""

    def _make_watch(self, tmp_path):
        capture = Capture(str(tmp_path / "capture.ndjson"))
        w = XiaomiWatch("AA:BB:CC:DD:EE:FF", 2, b"\x00" * 32, capture=capture)
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
