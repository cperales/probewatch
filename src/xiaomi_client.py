# SPDX-License-Identifier: AGPL-3.0-or-later
"""Talk to the Redmi Watch 5 Active over Xiaomi's SPP protocol, from Linux.

Python port of the relevant parts of Gadgetbridge, modified for this repository in
November 2026. Gadgetbridge is AGPL-3.0-or-later:
https://codeberg.org/Freeyourgadget/Gadgetbridge

  service/devices/xiaomi/XiaomiSppSupport.java     (version probe, protocol switch)
  service/devices/xiaomi/XiaomiSppPacketV1/V2.java (framing)
  service/devices/xiaomi/XiaomiSppProtocolV2.java  (session, acks)
  service/devices/xiaomi/XiaomiAuthService.java    (handshake, crypto)

Prerequisites:
  * watch bound to Mi Fitness (that is what creates the auth key) and paired
    with this PC at Bluetooth level (src/pair_watch.py --direct)
  * phone Bluetooth OFF (the watch talks to one client at a time)
  * auth key (32 hex chars) in secrets/auth_key.txt

Console usage:
  uv run python src/xiaomi_client.py --send 2 34                 # empty get
  uv run python src/xiaomi_client.py --send 2 25 \\
      --payload 'type: 2 subtype: 25 system { raiseToWake { mode: 2 } }'
  uv run python src/xiaomi_client.py --send 2 18 --listen 10     # find-device, then listen
  uv run python src/xiaomi_client.py --send 2 18 --channel 6     # send on channel 6 (OTA)
  uv run python src/xiaomi_client.py --send 2 18 --opcode read   # query opcode
  uv run python src/xiaomi_client.py --ota-require               # read-only OTA handshake
  uv run python src/xiaomi_client.py --mass-push FW.bin         # ota_type=2 mass-channel push
  uv run python src/xiaomi_client.py --listen 30                 # connect, dump unsolicited
  uv run python src/xiaomi_client.py --capture                   # record every frame, NDJSON

Legacy usage (hardcoded queries):
  uv run python src/xiaomi_client.py [MAC] [--channel 2] [-v]
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import hashlib
import hmac
import json
import locale
import os
import secrets
import select
import socket
import struct
import sys
import time

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESCCM
from google.protobuf import text_format

from watch_secrets import resolve_mac

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "xiaomi_pb"))
import xiaomi_pb2  # noqa: E402  (generated from proto/ with grpc_tools.protoc)
from xiaomi import wear_account_pb2  # noqa: E402

KEY_FILE = os.path.join(ROOT, "secrets", "auth_key.txt")
VERBOSE = False


def log(*a):
    if VERBOSE:
        print("   ·", *a)


# --------------------------------------------------------------------------- capture
CAPTURE_DIR = os.path.join(ROOT, "captures")


def default_capture_path() -> str:
    return os.path.join(CAPTURE_DIR, time.strftime("%Y%m%dT%H%M%S") + ".ndjson")


class Capture:
    """Record every SPP frame, both directions, as one JSON object per line.

    RX payloads are stored after decryption and TX payloads before encryption, so a
    record always holds the protobuf bytes and never the ciphertext: records are
    comparable regardless of the opcode a frame used. Timestamps are relative to the
    moment the file was opened, which is what makes reply-vs-periodic analysis possible.
    """

    def __init__(self, path: str):
        directory = os.path.dirname(os.path.abspath(path))
        os.makedirs(directory, exist_ok=True)
        self.path = path
        self._fh = open(path, "w", encoding="utf-8")  # noqa: SIM115 - kept open for the run
        self._start = time.time()

    def frame(
        self,
        direction: str,
        ftype: int,
        seq: int,
        channel: int | None = None,
        opcode: int | None = None,
        data: bytes = b"",
        note: str | None = None,
    ):
        record = {"t": round(time.time() - self._start, 3), "dir": direction, "type": ftype}
        if channel is not None:
            record["ch"] = channel
        if opcode is not None:
            record["op"] = opcode
        record["seq"] = seq
        record["len"] = len(data)
        record["hex"] = data.hex()
        if note:
            record["note"] = note
        self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()  # a crash must not cost the frames captured so far

    def close(self):
        self._fh.close()


# --------------------------------------------------------------------------- RFCOMM
# Opened through libc rather than socket.socket: sockaddr_rc keeps the MAC byte-reversed
# in an explicit, auditable struct, and this path works even on interpreters without
# socket.AF_BLUETOOTH (CPython builds downloaded by uv have no Bluetooth support).
AF_BLUETOOTH, BTPROTO_RFCOMM = 31, 3


class _SockaddrRc(ctypes.Structure):
    _fields_ = [
        ("family", ctypes.c_ushort),
        ("bdaddr", ctypes.c_ubyte * 6),
        ("channel", ctypes.c_ubyte),
    ]


class Rfcomm:
    def __init__(self, mac: str, channel: int, timeout: float = 20):
        libc = ctypes.CDLL(None, use_errno=True)
        fd = libc.socket(AF_BLUETOOTH, socket.SOCK_STREAM, BTPROTO_RFCOMM)
        if fd < 0:
            raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
        bd = bytes(reversed(bytes.fromhex(mac.replace(":", ""))))
        addr = _SockaddrRc(AF_BLUETOOTH, (ctypes.c_ubyte * 6)(*bd), channel)
        if libc.connect(fd, ctypes.byref(addr), ctypes.sizeof(addr)) != 0:
            err = ctypes.get_errno()
            os.close(fd)
            raise OSError(err, f"RFCOMM connect to {mac} ch{channel}: {os.strerror(err)}")
        self.fd = fd
        self.buf = b""

    def send(self, data: bytes):
        log("TX", data.hex(" "))
        # A 64 KiB (MPS) frame can exceed what one os.write accepts; write it all.
        view = memoryview(data)
        while view:
            written = os.write(self.fd, view)
            view = view[written:]

    def fill(self, timeout: float) -> bool:
        r, _, _ = select.select([self.fd], [], [], timeout)
        if not r:
            return False
        chunk = os.read(self.fd, 4096)
        if not chunk:
            raise ConnectionError("watch closed the connection")
        log("RX", chunk.hex(" "))
        self.buf += chunk
        return True

    def close(self):
        os.close(self.fd)


# --------------------------------------------------------------------------- SPP v1 (only the version probe)
V1_PREAMBLE, V1_EPILOGUE = b"\xba\xdc\xfe", b"\xef"
# channel 0 (version), flags 0xC0 (flag | needsResponse), len 3, opcode READ, serial 0, plain
V1_VERSION_REQUEST = (
    V1_PREAMBLE + bytes([0x00, 0xC0]) + struct.pack("<H", 3) + bytes([0, 0, 0]) + V1_EPILOGUE
)


def parse_v1(buf: bytes):
    """Return (packet_dict, consumed) or (None, 0) if incomplete."""
    i = buf.find(V1_PREAMBLE)
    if i < 0 or len(buf) - i < 11:
        return None, 0
    ch, flags, ln = buf[i + 3], buf[i + 4], struct.unpack_from("<H", buf, i + 5)[0]
    total = 7 + ln + 1
    if len(buf) - i < total:
        return None, 0
    opcode, serial, dtype = buf[i + 7], buf[i + 8], buf[i + 9]
    payload = buf[i + 10 : i + 7 + ln]
    return dict(
        channel=ch & 0x0F, flags=flags, opcode=opcode, serial=serial, dtype=dtype, payload=payload
    ), i + total


# --------------------------------------------------------------------------- SPP v2 framing
V2_PREAMBLE = b"\xa5\xa5"
T_NACK, T_ACK, T_SESSION, T_DATA = 0, 1, 2, 3

# Channels (from Gadgetbridge's L2Packet.Channel / ChannelType)
CH_PROTOBUF, CH_DATA, CH_ACTIVITY = 1, 2, 5
CH_MASS_VOICE, CH_FILE_SENSOR, CH_OTA = 3, 4, 6
CH_NETWORK, CH_LYRA, CH_RESEARCH = 7, 8, 9

# Channel name table for display and capture
CHANNEL_NAMES: dict[int, str] = {
    1: "PB",
    2: "MASS",
    3: "VOICE",
    4: "SENSOR",
    5: "FITNESS",
    6: "OTA",
    7: "NET",
    8: "LYRA",
    9: "RESEARCH",
}

OP_WRITE, OP_WRITE_ENC, OP_READ = 1, 2, 3

# Sending anything resets the watch's ~20 s idle timer, so a long listen needs a ping.
KEEPALIVE_COMMAND = (2, 1)  # battery: read-only, cheap, always answered

# Session config captured from the official app (see XiaomiSppPacketV2.SessionConfigPacket)
SESSION_START = bytes(
    [
        1,  # opcode START_SESSION_REQUEST
        1,
        0x03,
        0x00,
        0x01,
        0x00,
        0x00,  # version 1.0.0
        2,
        0x02,
        0x00,
        0x00,
        0xFC,  # max packet size 0xfc00
        3,
        0x02,
        0x00,
        0x20,
        0x00,  # tx window 32
        4,
        0x02,
        0x00,
        0x10,
        0x27,  # send timeout 10000 ms
    ]
)


def crc16_arc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


def encode_v2(ptype: int, seq: int, payload: bytes) -> bytes:
    return (
        V2_PREAMBLE
        + struct.pack("<BBHH", ptype & 0x0F, seq & 0xFF, len(payload), crc16_arc(payload))
        + payload
    )


def parse_v2(buf: bytes):
    """Return (ptype, seq, payload, consumed) / (None, ..., consumed>0 to skip junk) / None if incomplete."""
    i = buf.find(V2_PREAMBLE)
    if i < 0:
        return (None, 0, b"", len(buf)) if buf else None
    if len(buf) - i < 8:
        return None
    flags_type, seq, ln, crc = struct.unpack_from("<BBHH", buf, i + 2)
    if len(buf) - i < 8 + ln:
        return None
    payload = buf[i + 8 : i + 8 + ln]
    if crc16_arc(payload) != crc:
        log(f"bad CRC, skipping frame at {i}")
        return None, 0, b"", i + 2
    return flags_type & 0x0F, seq, payload, i + 8 + ln


def parse_session_config(payload: bytes) -> dict[int, bytes]:
    """Parse a SESSION config payload: ``[opcode][type][len u16 LE][value]...``.

    The watch answers SESSION_START with its own limits; config type 3 is TX_WIN, the
    number of DATA frames it can hold in flight. Sending past it overflows its buffer.
    """
    cfg: dict[int, bytes] = {}
    i = 1  # skip the opcode byte
    while i + 3 <= len(payload):
        kind = payload[i]
        ln = struct.unpack_from("<H", payload, i + 1)[0]
        cfg[kind] = payload[i + 3 : i + 3 + ln]
        i += 3 + ln
    return cfg


# --------------------------------------------------------------------------- OTA channel (0x5A framing)
# The app's `HyOtaExecutor` (product `ota_type == 1`) frames channel-6 payloads itself:
# `0x5A`, a big-endian length, a segment flag/frame number, and a CRC-16/ARC over everything
# after the magic. The body is `[SERVICE_ID][command][args]`. All integers here are
# big-endian, unlike the L1 header. See docs/ota.md.
OTA_MAGIC = 0x5A
OTA_SERVICE_ID = 10
OTA_FLAG_SINGLE, OTA_FLAG_FIRST, OTA_FLAG_MIDDLE, OTA_FLAG_LAST = 0, 1, 2, 3

OTA_CMD_REQUIRE = 0
OTA_CMD_START = 1
OTA_CMD_DATA = 2
OTA_CMD_ERROR = 3
OTA_CMD_RESET = 4
OTA_CMD_PROGRESS = 5
OTA_CMD_SILENT_START = 6
OTA_CMD_SILENT_PAUSE = 7

OTA_CMD_NAMES: dict[int, str] = {
    0: "REQUIRE",
    1: "START",
    2: "DATA",
    3: "ERROR",
    4: "RESET",
    5: "PROGRESS",
    6: "SILENT_START",
    7: "SILENT_PAUSE",
}

OTA_MAX_SEGMENT_DATA = 4217  # HyOtaModel.MAX_SEGMENT_DATA_SIZE


def encode_ota_segment(payload: bytes, flag: int = OTA_FLAG_SINGLE, frame_no: int = 0) -> bytes:
    """Wrap *payload* in one 0x5A segment (big-endian length and CRC)."""
    if len(payload) > OTA_MAX_SEGMENT_DATA:
        raise ValueError(f"OTA payload is {len(payload)} B, max {OTA_MAX_SEGMENT_DATA}")
    body = bytes([flag & 0xFF, frame_no & 0xFF]) + payload
    head = bytes([OTA_MAGIC]) + struct.pack(">H", len(body))
    return head + body + struct.pack(">H", crc16_arc(head[1:] + body))


def parse_ota_segment(buf: bytes):
    """Return (flag, frame_no, payload, consumed) for the first complete segment.

    ``None`` means "wait for more bytes"; ``(None, 0, b"", consumed)`` means junk was
    skipped and the caller should retry at *consumed*. A CRC mismatch is logged but
    accepted, because the official app does not verify it on receive either.
    """
    i = buf.find(bytes([OTA_MAGIC]))
    if i < 0:
        return (None, 0, b"", len(buf)) if buf else None
    if len(buf) - i < 5:
        return None
    length = struct.unpack_from(">H", buf, i + 1)[0]
    if length < 2 or length > OTA_MAX_SEGMENT_DATA + 2:
        return None, 0, b"", i + 1  # implausible length: skip this magic byte
    total = length + 5
    if len(buf) - i < total:
        return None
    flag, frame_no = buf[i + 3], buf[i + 4]
    payload = buf[i + 5 : i + 3 + length]
    crc = struct.unpack_from(">H", buf, i + 3 + length)[0]
    if crc16_arc(buf[i + 1 : i + 3 + length]) != crc:
        log("bad OTA segment CRC (accepted anyway, the app ignores it)")
    return flag, frame_no, payload, i + total


def encode_ota_command(cmd: int, body: bytes = b"") -> bytes:
    """Build `[SERVICE_ID][command][body]`."""
    return bytes([OTA_SERVICE_ID, cmd & 0xFF]) + body


def parse_ota_command(payload: bytes) -> tuple[int, bytes] | None:
    """Split a segment body into (command, args), or None if it is not ours."""
    if len(payload) < 2 or payload[0] != OTA_SERVICE_ID:
        return None
    return payload[1], payload[2:]


def ota_require_segment() -> bytes:
    """The read-only `CMD_REQUIRE` probe: one segment with an empty body."""
    return encode_ota_segment(encode_ota_command(OTA_CMD_REQUIRE))


def decode_ota_require(args: bytes) -> tuple[int, int, int]:
    """Return (page_size, interval_ms, timeout_ms) from a REQUIRE reply."""
    if len(args) < 3:
        raise ValueError(f"REQUIRE reply is {len(args)} B, expected 3")
    return args[0] * 32, args[1] * 10, args[2] * 100


def decode_ota_data(args: bytes) -> tuple[int, int, bytes]:
    """Return (offset, length, page bitmap) from a DATA reply."""
    if len(args) < 8:
        raise ValueError(f"DATA reply is {len(args)} B, expected at least 8")
    offset, length = struct.unpack_from(">II", args, 0)
    return offset, length, args[8:]


def decode_ota_error(args: bytes) -> tuple[int, str]:
    """Return (code, description) from an ERROR reply."""
    if not args:
        raise ValueError("ERROR reply needs a code byte")
    return args[0], args[1:].decode("utf-8", "replace")


def decode_ota_progress(args: bytes) -> int:
    """Return the percent from a PROGRESS reply."""
    if not args:
        raise ValueError("PROGRESS reply needs a percent byte")
    return args[0]


# --------------------------------------------------------------------------- mass channel (2) push
# `ota_type = 2` (this watch) updates firmware over the mass channel: a channel-1 protobuf
# handshake arms the receiver, then the raw SiFli package is streamed on channel 2 as plaintext
# OP_WRITE chunks of the device-advertised chunkSize (4096). See docs/mass-channel.md.
MASS_UPLOAD_FIRMWARE = 32  # DataUploadRequest.type for a firmware image
MASS_DEFAULT_CHUNK = 4096  # DataUploadAck.chunkSize measured on this watch


def mass_chunks(data: bytes, chunk_size: int) -> list[bytes]:
    """Split *data* into *chunk_size* pieces; the last may be short."""
    return [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]


def mass_prepare_command(version: str, md5_hex: str) -> xiaomi_pb2.Command:
    """Build the firmware prepare ``Command{2,5}`` (battery-gated; version/md5 not compared)."""
    cmd = xiaomi_pb2.Command(type=2, subtype=5)
    cmd.system.firmwareInstallRequest.unknown1 = 0
    cmd.system.firmwareInstallRequest.unknown2 = 0
    cmd.system.firmwareInstallRequest.version = version
    cmd.system.firmwareInstallRequest.md5 = md5_hex
    return cmd


def mass_upload_command(
    md5sum: bytes, size: int, upload_type: int = MASS_UPLOAD_FIRMWARE
) -> xiaomi_pb2.Command:
    """Build the ``Command{22,0}`` DataUploadRequest that arms the mass-channel receiver."""
    cmd = xiaomi_pb2.Command(type=22, subtype=0)
    cmd.dataUpload.dataUploadRequest.type = upload_type
    cmd.dataUpload.dataUploadRequest.md5sum = md5sum
    cmd.dataUpload.dataUploadRequest.size = size
    return cmd


# --------------------------------------------------------------------------- crypto (XiaomiAuthService)
def hmac_sha256(key: bytes, msg: bytes) -> bytes:
    return hmac.new(key, msg, hashlib.sha256).digest()


def derive_keys(secret: bytes, phone_nonce: bytes, watch_nonce: bytes) -> bytes:
    """HKDF-SHA256(salt = phone_nonce||watch_nonce, ikm = secret, info = 'miwear-auth', L = 64)."""
    prk = hmac_sha256(phone_nonce + watch_nonce, secret)
    out, t, i = b"", b"", 1
    while len(out) < 64:
        t = hmac_sha256(prk, t + b"miwear-auth" + bytes([i]))
        out += t
        i += 1
    return out[:64]


class Session:
    def __init__(self, secret: bytes):
        self.secret = secret
        self.phone_nonce = secrets.token_bytes(16)
        self.enc_key = self.dec_key = self.enc_nonce = self.dec_nonce = None
        self.encrypted = False

    def set_keys(self, watch_nonce: bytes):
        k = derive_keys(self.secret, self.phone_nonce, watch_nonce)
        self.dec_key, self.enc_key = k[0:16], k[16:32]
        self.dec_nonce, self.enc_nonce = k[32:36], k[36:40]

    def ccm_encrypt(self, data: bytes, counter: int = 0) -> bytes:
        nonce = self.enc_nonce + struct.pack("<II", 0, counter)
        return AESCCM(self.enc_key, tag_length=4).encrypt(nonce, data, None)

    @staticmethod
    def _ctr(key: bytes, data: bytes) -> bytes:  # Xiaomi uses the key itself as IV, per message
        c = Cipher(algorithms.AES(key), modes.CTR(key)).encryptor()
        return c.update(data) + c.finalize()

    def encrypt_v2(self, data: bytes) -> bytes:
        return self._ctr(self.enc_key, data)

    def decrypt_v2(self, data: bytes) -> bytes:
        return self._ctr(self.dec_key, data)


# --------------------------------------------------------------------------- client
class XiaomiWatch:
    """SPP v2 client with selective-repeat ARQ (window 32, 10 s retransmit).

    The peer runs a real selective-repeat ARQ on top of the ``A5 A5`` framing.
    This class tracks a send window, delays ACKs, detects duplicates, and
    retransmits on NAK or timeout.
    """

    # ARQ parameters (from Gadgetbridge's SAR_DEFAULT_* constants)
    TX_WINDOW: int = 32  # max unacked DATA frames in flight
    REMOTE_WINDOW: int = 4  # peer's advertised window
    SEND_TIMEOUT: float = 10.0  # retransmit unacked DATA after this many seconds
    CUM_ACK_TIMEOUT: float = 0.5  # flush a delayed ACK after a quiet burst
    ACK_THRESHOLD: int = TX_WINDOW * 2 // 3  # pending ACKs that force an immediate ACK

    def __init__(self, mac: str, l2_channel: int, secret: bytes, capture: Capture | None = None):
        self.mac, self.l2_channel = mac, l2_channel
        self.sess = Session(secret)
        self.tx_base: int = 0  # oldest unacked seq
        self.tx_next: int = 0  # next seq to send
        self.rx_expect: int = 0  # next expected incoming seq
        self.rx_pending: int = 0  # in-order DATA frames received since the last ACK
        self.ack_deadline: float | None = None  # when to flush the delayed ACK
        self.inbox: list[xiaomi_pb2.Command] = []
        self.link: Rfcomm | None = None
        self.capture = capture
        # Insertion-ordered: oldest unacked first. An ACK releases every entry up to its seq.
        self._sent: dict[int, bytes] = {}  # seq -> encoded DATA frame
        self._sent_times: dict[int, float] = {}  # seq -> last send timestamp
        self.ota_parts: dict[int, bytes] = {}  # frame_no -> payload of a multi-segment body
        self.ota_replies: list[tuple[int, bytes]] = []  # decoded channel-6 commands
        self.peer_window: int | None = None  # watch's advertised TX_WIN (from SESSION config)

    @property
    def pending_count(self) -> int:
        """Number of DATA frames sent but not ACKed yet."""
        return len(self._sent)

    @property
    def send_window(self) -> int:
        """Max DATA frames in flight.

        The watch advertises TX_WIN 3, but pacing to it collapses throughput (the ACK is
        delayed ~500 ms, so 3 frames/cycle is ~16 KB/s); the ARQ tolerates the 32-frame
        window and reaches ~150 KB/s, so keep TX_WINDOW.
        """
        return self.TX_WINDOW

    # -- low level
    def _send_data(self, opcode: int, payload: bytes) -> bytes | None:
        """Build and send a DATA frame, returning the full encoded frame for retransmit.

        Returns ``None`` when the send window is full; the caller should pump
        the link until space opens.
        """
        if self.pending_count >= self.send_window:
            log(f"window full ({self.pending_count}/{self.send_window}), cannot send")
            return None

        body = bytes([self.l2_channel & 0x0F, opcode]) + (
            self.sess.encrypt_v2(payload) if opcode == OP_WRITE_ENC else payload
        )
        seq = self.tx_next
        frame = encode_v2(T_DATA, seq, body)
        self.link.send(frame)
        self.tx_next = (seq + 1) & 0xFF
        self._sent[seq] = frame
        self._sent_times[seq] = time.time()
        if self.capture:
            self.capture.frame("tx", T_DATA, seq, self.l2_channel, opcode, payload)
        return frame

    def _send_until_space(self, opcode: int, payload: bytes, timeout: float = 30.0) -> bytes | None:
        """Send a DATA frame, pumping the link until the TX window opens.

        Returns the encoded frame, or ``None`` if the window never opened within *timeout*.
        Pumps in short slices so an ACK that arrives mid-wait is acted on at once instead
        of after the whole timeout: with the watch's delayed ACKs this is the difference
        between ~80 KB/s and a push that fits inside the ~25 s session.
        """
        deadline = time.time() + timeout
        frame = self._send_data(opcode, payload)
        while frame is None and time.time() < deadline:
            self._pump(min(0.02, deadline - time.time()))
            frame = self._send_data(opcode, payload)
        return frame

    def send_command(self, cmd: xiaomi_pb2.Command):
        log("send cmd", cmd.type, cmd.subtype)
        if cmd.type == 1:  # auth -> plaintext on the protobuf channel
            self._send_data(OP_WRITE, cmd.SerializeToString())
        else:
            self._send_data(OP_WRITE_ENC, cmd.SerializeToString())

    def _send_ack(self, seq: int) -> None:
        """Send an ACK frame for *seq*."""
        self.link.send(encode_v2(T_ACK, seq, b""))
        log("ack", seq)

    def _send_nak(self, seq: int) -> None:
        """Ask the peer to retransmit from *seq* (the first frame we are missing)."""
        self.link.send(encode_v2(T_NACK, seq, b""))
        log("nak, watch expects", seq)

    def _retransmit(self, seq: int) -> None:
        """Resend a tracked DATA frame verbatim and restart its timeout."""
        frame = self._sent.get(seq)
        if frame is None:
            return
        log("retransmitting seq", seq)
        self.link.send(frame)
        self._sent_times[seq] = time.time()

    def _ack_received(self, seq: int) -> None:
        """Release every tracked frame up to and including *seq*.

        Sequence numbers are 8 bit and wrap, so *seq* is looked up in the
        insertion-ordered ``_sent`` map instead of being compared numerically:
        an ACK for a frame we never sent releases nothing.
        """
        if seq not in self._sent:
            log(f"ack for untracked seq {seq}, ignoring")
            return
        released = 0
        for s in list(self._sent):
            del self._sent[s]
            self._sent_times.pop(s, None)
            released += 1
            if s == seq:
                break
        self.tx_base = (seq + 1) & 0xFF
        log(f"ack {seq} ({released} released, {self.pending_count} pending)")

    def _ack_now(self, seq: int) -> None:
        """Send the cumulative ACK for *seq* and drop any pending delayed ACK."""
        self._send_ack(seq & 0xFF)
        self.rx_pending = 0
        self.ack_deadline = None

    def _flush_due(self) -> None:
        """Fire the delayed ACK and any per-frame retransmit timers that are due."""
        now = time.time()
        if self.ack_deadline is not None and now >= self.ack_deadline:
            # rx_expect is the first missing seq, so this ACKs everything before it.
            self._ack_now(self.rx_expect - 1)
        for seq, sent_at in list(self._sent_times.items()):
            if now - sent_at >= self.SEND_TIMEOUT:
                self._retransmit(seq)

    def _pump(self, timeout: float):
        """Read and handle frames until ``timeout`` seconds pass without a complete frame.

        Implements the SAR selective-repeat ARQ:
        - Delayed ACKs: immediate for payload[0] in {1, 8} or after
          ``ACK_THRESHOLD`` pending frames, otherwise after 500 ms of quiet.
        - Duplicate suppression (unsigned diff >= 128 → drop silently).
        - Out-of-order NAK carrying the first missing seq.
        - Retransmit on timeout (10 s, per frame) and on NAK (range retransmit).
        - Window accounting (refuse to send past 32 unacked frames).
        """
        end = time.time() + timeout
        while True:
            self._flush_due()

            res = parse_v2(self.link.buf)
            if res is None:
                now = time.time()
                remaining = end - now
                if remaining <= 0:
                    return
                # Never sleep past a timer: cap the read by the next deadline so the
                # delayed ACK and retransmits fire even when the peer is quiet.
                wait = remaining
                ack_due = self.ack_deadline
                if ack_due is not None:
                    wait = min(wait, max(0.0, ack_due - now))
                retransmit_due = None
                if self._sent_times:
                    retransmit_due = min(self._sent_times.values()) + self.SEND_TIMEOUT
                    wait = min(wait, max(0.0, retransmit_due - now))
                if self.link.fill(wait):
                    continue
                now = time.time()
                if now >= end:
                    return
                if (ack_due is not None and now >= ack_due) or (
                    retransmit_due is not None and now >= retransmit_due
                ):
                    continue  # a timer was the reason the read ended; service it
                return

            ptype, seq, payload, used = res
            self.link.buf = self.link.buf[used:]
            if ptype is None:
                continue

            if ptype != T_DATA and self.capture:
                self.capture.frame("rx", ptype, seq, data=payload)

            if ptype == T_ACK:
                self._ack_received(seq)

            elif ptype == T_NACK:
                log("nack, watch expects", seq)
                # The peer ACKs whatever it already had: release up to seq-1 first.
                previous = (seq - 1) & 0xFF
                if previous in self._sent:
                    self._ack_received(previous)
                if not self._sent or next(iter(self._sent)) != seq:
                    log(f"nack for seq {seq}, which is not the oldest unacked, ignoring")
                    continue
                # Retransmit every unacked frame from seq onwards, oldest first.
                for s in list(self._sent):
                    self._retransmit(s)

            elif ptype == T_SESSION:
                cfg = parse_session_config(payload)
                if cfg.get(3):
                    self.peer_window = struct.unpack_from("<H", cfg[3])[0]
                log(
                    "session config from watch",
                    {k: v.hex() for k, v in cfg.items()},
                    "peer_window",
                    self.peer_window,
                )
                self.session_ok = True

            elif ptype == T_DATA:
                # Duplicate detection (unsigned arithmetic)
                diff = (seq - self.rx_expect) & 0xFF
                if diff >= 128:
                    log(f"stale duplicate seq {seq}, dropping")
                    continue

                # Out-of-order: NAK the first missing seq so the peer resends from there.
                if seq != self.rx_expect:
                    log(f"out-of-order seq {seq}, expected {self.rx_expect}, sending NAK")
                    if self.rx_pending:
                        self._ack_now(self.rx_expect - 1)
                    self._send_nak(self.rx_expect)
                    continue

                # In-order: process
                self.rx_expect = (seq + 1) & 0xFF
                self.rx_pending += 1

                # Immediate for "control" channels 1 and 8, or once enough ACKs are pending;
                # otherwise a 500 ms timer (armed once, not reset by every frame) flushes it.
                if (
                    len(payload) < 2
                    or payload[0] in (1, 8)
                    or self.rx_pending >= self.ACK_THRESHOLD
                ):
                    self._ack_now(seq)
                elif self.ack_deadline is None:
                    self.ack_deadline = time.time() + self.CUM_ACK_TIMEOUT

                if len(payload) < 2:  # a DATA frame needs the channel/opcode header
                    if self.capture:
                        self.capture.frame("rx", ptype, seq, data=payload, note="short data")
                    log(f"short DATA frame ({len(payload)} bytes), ignored")
                    continue

                ch, op, data = payload[0] & 0x0F, payload[1], payload[2:]
                if op == OP_WRITE_ENC:
                    data = self.sess.decrypt_v2(data)
                if self.capture:
                    self.capture.frame("rx", ptype, seq, ch, op, data)
                name = CHANNEL_NAMES.get(ch, f"CH{ch}")
                if op == OP_READ:
                    verb = "read"
                elif op == OP_WRITE_ENC:
                    verb = "write_enc"
                else:
                    verb = "write"
                print(f"  [{name}] ch{ch} {verb} {len(data)} B")
                if ch == CH_PROTOBUF:
                    cmd = xiaomi_pb2.Command()
                    try:
                        cmd.ParseFromString(data)
                    except Exception as e:  # noqa: BLE001
                        print(f"!! could not parse protobuf ({e}): {data.hex()}")
                        continue
                    log("recv cmd", cmd.type, cmd.subtype)
                    self.inbox.append(cmd)
                elif ch == CH_OTA:
                    self._handle_ota(data)
                else:
                    log(f"data on channel {ch} ({len(data)} bytes) ignored")

    def _handle_ota(self, data: bytes) -> None:
        """Decode one channel-6 payload (0x5A segment) and record its `0A` command."""
        res = parse_ota_segment(data)
        if res is None:
            log("incomplete OTA segment")
            return
        flag, frame_no, payload, _used = res
        if flag is None:
            log("junk before OTA segment")
            return
        if flag == OTA_FLAG_SINGLE:
            self._deliver_ota(payload)
            return
        if flag == OTA_FLAG_FIRST:
            self.ota_parts = {frame_no: payload}
            return
        self.ota_parts[frame_no] = payload
        if flag == OTA_FLAG_LAST:
            joined = b"".join(self.ota_parts[k] for k in sorted(self.ota_parts))
            self.ota_parts = {}
            self._deliver_ota(joined)

    def _deliver_ota(self, payload: bytes) -> None:
        """Record and print one reassembled OTA body."""
        parsed = parse_ota_command(payload)
        if parsed is None:
            print(f"  [OTA] undecodable body {payload.hex()}")
            return
        cmd, args = parsed
        self.ota_replies.append((cmd, args))
        name = OTA_CMD_NAMES.get(cmd, f"cmd{cmd}")
        try:
            if cmd == OTA_CMD_REQUIRE:
                page, interval, timeout = decode_ota_require(args)
                print(f"  [OTA] {name}: page={page} B interval={interval} ms timeout={timeout} ms")
            elif cmd == OTA_CMD_DATA:
                offset, length, bitmap = decode_ota_data(args)
                print(f"  [OTA] {name}: offset={offset} length={length} bitmap={bitmap.hex()}")
            elif cmd == OTA_CMD_ERROR:
                code, desc = decode_ota_error(args)
                print(f"  [OTA] {name}: code={code} desc={desc!r}")
            elif cmd == OTA_CMD_PROGRESS:
                print(f"  [OTA] {name}: {decode_ota_progress(args)}%")
            else:
                print(f"  [OTA] {name}: args={args.hex()}")
        except ValueError as e:
            print(f"  [OTA] {name}: malformed reply ({e}): {args.hex()}")

    def wait_for(
        self, ctype: int, subtype: int | None, timeout: float = 10
    ) -> xiaomi_pb2.Command | None:
        end = time.time() + timeout
        while time.time() < end:
            for c in self.inbox:
                if c.type == ctype and (subtype is None or c.subtype == subtype):
                    self.inbox.remove(c)
                    return c
            self._pump(min(1.0, end - time.time()))
        return None

    # -- connection steps
    def connect(self):
        print(f"[1] RFCOMM connect {self.mac} channel 2 (SPP) ...")
        self.link = Rfcomm(self.mac, 2)

        print("[2] SPP version probe ...")
        self.link.send(V1_VERSION_REQUEST)
        version = None
        end = time.time() + 5
        while time.time() < end and version is None:
            pkt, used = parse_v1(self.link.buf)
            if pkt:
                self.link.buf = self.link.buf[used:]
                if pkt["channel"] == 0:
                    version = pkt["payload"]
                continue
            self.link.fill(end - time.time())
        print(f"    SPP protocol version: {version.hex(' ') if version else 'no answer'}")
        if not version or version[0] < 2:
            raise RuntimeError("watch did not report SPP v2; only v2 is implemented here")

        print("[3] start SPPv2 session ...")
        self.session_ok = False
        self.link.send(encode_v2(T_SESSION, 0, SESSION_START))
        end = time.time() + 5
        while time.time() < end and not self.session_ok:
            self._pump(1)
        if not self.session_ok:
            raise RuntimeError("no session config response")

        # Auth commands always go on channel 1 (PB)
        saved_ch = self.l2_channel
        self.l2_channel = CH_PROTOBUF

        print("[4] auth step 1: send phone nonce ...")
        c = xiaomi_pb2.Command(type=1, subtype=26)
        c.auth.appVerify.nonce = self.sess.phone_nonce
        self.send_command(c)
        r = self.wait_for(1, None, 10)
        if r is None:
            raise RuntimeError("no answer to auth step 1")
        if not r.auth.HasField("deviceVerify"):
            raise RuntimeError(
                f"watch refused auth step 1: {text_format.MessageToString(r, as_one_line=True)}"
            )

        print("[5] auth step 2: verify watch, derive session keys ...")
        wn = r.auth.deviceVerify.nonce
        self.sess.set_keys(wn)
        expected = hmac_sha256(self.sess.dec_key, wn + self.sess.phone_nonce)
        if not hmac.compare_digest(expected, r.auth.deviceVerify.hmac):
            raise RuntimeError("watch HMAC mismatch -> wrong auth key")
        print("    watch proved it knows the same key ✓")

        lang = (locale.getlocale()[0] or os.environ.get("LANG", "en"))[:2].upper()
        info = wear_account_pb2.CompanionDevice(
            unknown1=0, phoneApiLevel=34, phoneName="Linux PC", unknown3=224, region=lang
        )
        c = xiaomi_pb2.Command(type=1, subtype=27)
        c.auth.appConfirm.encryptedNonces = hmac_sha256(
            self.sess.enc_key, self.sess.phone_nonce + wn
        )
        c.auth.appConfirm.encryptedDeviceInfo = self.sess.ccm_encrypt(info.SerializeToString(), 0)
        print("[6] auth step 3: send our proof ...")
        self.send_command(c)
        r = self.wait_for(1, 27, 10)
        if r is None:
            raise RuntimeError("no answer to auth step 3")
        print("    AUTHENTICATED ✓  " + text_format.MessageToString(r.auth, as_one_line=True))
        self.sess.encrypted = True

        # Restore the user-specified L2 channel
        self.l2_channel = saved_ch

    def request(self, ctype: int, subtype: int, timeout: float = 8):
        self.send_command(xiaomi_pb2.Command(type=ctype, subtype=subtype))
        return self.wait_for(ctype, subtype, timeout)

    def send_command_with_retransmit(
        self, cmd: xiaomi_pb2.Command, timeout: float = 8
    ) -> xiaomi_pb2.Command | None:
        """Send a command and wait for response, with one NACK retransmit.

        ``send_command`` stores the full encoded DATA frame by sequence number so
        ``_pump`` can resend it verbatim when the watch sends a NACK.
        """
        self.send_command(cmd)
        return self.wait_for(cmd.type, cmd.subtype, timeout)

    def _reconnect(self, attempts: int = 3, delay: float = 2.0) -> None:
        """Tear down and re-run connect/auth, clearing ARQ/session state.

        A dropped mass session leaves stale sequence numbers and a closed socket; the watch
        re-arms from a ``DataUploadRequest`` after auth, so the state must start clean.
        """
        self.close()
        self.link = None
        self.tx_base = 0
        self.tx_next = 0
        self.rx_expect = 0
        self.rx_pending = 0
        self.ack_deadline = None
        self._sent.clear()
        self._sent_times.clear()
        self.inbox.clear()
        self.session_ok = False
        self.peer_window = None
        for attempt in range(attempts):
            try:
                self.connect()
                return
            except OSError as e:
                if attempt == attempts - 1:
                    raise
                print(f"[mass] reconnect failed ({e}); retrying ...")
                time.sleep(delay)

    def mass_pause(self) -> bytes | None:
        """Send the app's ``22/1`` pause control (``DataUpload.dataUploadControl {a=1, b=47}``).

        The vendored proto has no ``DataUpload`` field 3 (the control), so the ``Command`` is
        hand-built: ``type=22, subtype=1, dataUpload{control{a=1, b=47}}``. Sent encrypted on
        channel 1, like any non-auth command.
        """
        raw = bytes.fromhex("08161001c201061a040801102f")
        saved = self.l2_channel
        self.l2_channel = CH_PROTOBUF
        try:
            return self._send_until_space(OP_WRITE_ENC, raw, timeout=5.0)
        finally:
            self.l2_channel = saved

    def mass_push(
        self,
        data: bytes,
        chunk_size: int | None = None,
        fw_version: str = "",
        upload_type: int = MASS_UPLOAD_FIRMWARE,
        max_reconnects: int = 8,
        reconnect_delay: float = 1.0,
    ) -> xiaomi_pb2.Command | None:
        """Push a file over the mass channel (2), the ``ota_type = 2`` path.

        Mirrors the official app: send the battery-gated prepare (``2/5``) once, then per
        session arm the receiver with a ``DataUploadRequest`` (``22/0``) and stream the raw
        bytes as plaintext ``OP_WRITE`` segments of the advertised ``chunkSize``. The watch
        drops the SPP session at ~20 s, so a dropped session reconnects and resumes from
        ``DataUploadAck.resumePosition``. Returns the last ``DataUploadAck`` command.
        """
        md5 = hashlib.md5(data).digest()
        print(f"[mass] {len(data)} B, md5 {md5.hex()}")

        if upload_type == MASS_UPLOAD_FIRMWARE:
            self.send_command(mass_prepare_command(fw_version, md5.hex()))
            r = self.wait_for(2, 5)
            if r is not None and r.system.HasField("firmwareInstallResponse"):
                print(f"[mass] prepare status {r.system.firmwareInstallResponse.status}")

        offset = 0
        reconnects = 0
        ack = None
        while True:
            # Arm the receiver for this session and learn where to resume from.
            self.send_command(mass_upload_command(md5, len(data), upload_type))
            ack = self.wait_for(22, 0)
            chunk = chunk_size or MASS_DEFAULT_CHUNK
            resume = 0
            if ack is not None and ack.dataUpload.HasField("dataUploadAck"):
                a = ack.dataUpload.dataUploadAck
                print(
                    f"[mass] ack errno {a.errno} chunkSize {a.chunkSize} resume {a.resumePosition}"
                )
                if a.errno != 0:
                    print(f"[mass] receiver not ready (errno {a.errno}), aborting")
                    return ack
                if chunk_size is None and a.chunkSize:
                    chunk = a.chunkSize
                resume = a.resumePosition
            elif ack is None:
                print("[mass] no DataUploadAck; pushing with the default chunk size")
            if resume != offset:
                print(f"[mass] resuming at {resume} B (local offset {offset})")
                offset = resume

            saved = self.l2_channel
            self.l2_channel = CH_DATA
            try:
                while offset < len(data):
                    piece = data[offset : offset + chunk]
                    if self._send_until_space(OP_WRITE, piece, timeout=40.0) is None:
                        print(f"[mass] window stalled at {offset} B; reconnecting")
                        break
                    offset += len(piece)
                    if offset % (chunk * 32) < chunk:
                        print(f"[mass] {offset}/{len(data)} B")
            except (OSError, ConnectionError) as e:
                print(f"[mass] session dropped at {offset} B: {e}")
            finally:
                self.l2_channel = saved

            if offset >= len(data):
                print(f"[mass] pushed {offset}/{len(data)} B")
                return ack

            reconnects += 1
            if reconnects > max_reconnects:
                print(f"[mass] giving up after {max_reconnects} reconnects")
                return ack
            print(f"[mass] reconnecting ({reconnects}/{max_reconnects}) ...")
            time.sleep(reconnect_delay)
            self._reconnect()

    def listen(self, seconds: float, keepalive: float = 0) -> None:
        """Listen for unsolicited frames for *seconds* seconds, printing each.

        ``keepalive`` sends a read-only battery query every that many seconds: the watch
        closes an idle SPP session after roughly 20 s, so a longer capture needs the ping.
        """
        start = time.time()
        end = start + seconds
        next_ping = start + keepalive if keepalive else None
        while time.time() < end:
            if next_ping is not None and time.time() >= next_ping:
                ctype, subtype = KEEPALIVE_COMMAND
                self.send_command(xiaomi_pb2.Command(type=ctype, subtype=subtype))
                print(f"  keepalive at t+{time.time() - start:.0f}s")
                next_ping = time.time() + keepalive
            self._pump(min(1.0, end - time.time()))
            while self.inbox:
                cmd = self.inbox.pop(0)
                print(
                    f"[{cmd.type}/{cmd.subtype}] {text_format.MessageToString(cmd, as_one_line=True)}"
                )
            if VERBOSE:
                print(
                    f"  [window] tx_base={self.tx_base} tx_next={self.tx_next} "
                    f"rx_expect={self.rx_expect} pending={self.pending_count}",
                    file=sys.stderr,
                )

    def drain(self) -> None:
        """Drain the inbox and print every queued command."""
        while self.inbox:
            cmd = self.inbox.pop(0)
            print(
                f"[{cmd.type}/{cmd.subtype}] {text_format.MessageToString(cmd, as_one_line=True)}"
            )

    def close(self):
        if self.link:
            self.link.close()


def load_key(path: str) -> bytes:
    try:
        with open(path) as f:
            k = f.read().strip().lower().removeprefix("0x")
    except OSError as e:
        raise SystemExit(f"cannot read auth key {path}: {e}") from e
    if len(k) != 32 or any(c not in "0123456789abcdef" for c in k):
        raise SystemExit(f"auth key in {path} must be 32 hex chars")
    return bytes.fromhex(k)


def build_command(ctype: int, subtype: int, payload_text: str | None = None) -> xiaomi_pb2.Command:
    """Build a Command protobuf from type/subtype and optional text_format payload.

    ``payload_text`` is parsed with ``text_format.Parse`` so the user names the
    field explicitly — nothing is inferred or guessed.
    """
    cmd = xiaomi_pb2.Command(type=ctype, subtype=subtype)
    if payload_text:
        text_format.Parse(payload_text, cmd)
    return cmd


def main():
    global VERBOSE
    p = argparse.ArgumentParser(
        description="Console for Xiaomi SPP v2: send commands, listen for responses."
    )
    p.add_argument(
        "mac", nargs="?", default=None, help="watch MAC (default: secrets/device.md or $WATCH_MAC)"
    )
    p.add_argument(
        "--channel",
        type=int,
        default=1,
        dest="l2_channel",
        help="L2 channel (default 1 = protobuf)",
    )
    p.add_argument("--key-file", default=KEY_FILE)
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument(
        "--opcode",
        type=str,
        default="write",
        choices=["write", "write_enc", "read"],
        help="L2 opcode for --send (default write)",
    )
    p.add_argument(
        "--ota-require",
        action="store_true",
        help="Send the read-only OTA REQUIRE handshake on channel 6 and print the reply",
    )
    p.add_argument(
        "--mass-push",
        type=str,
        default=None,
        metavar="PATH",
        help="Push a firmware file over the mass channel (2): prepare + DataUpload + raw push",
    )
    p.add_argument(
        "--fw-version",
        type=str,
        default="",
        metavar="VER",
        help="Version string for the --mass-push prepare (not compared; battery gate only)",
    )
    p.add_argument(
        "--send",
        nargs=2,
        type=int,
        action="append",
        metavar=("TYPE", "SUBTYPE"),
        help="Send a command (type subtype), repeatable; empty body is the default",
    )
    p.add_argument(
        "--payload",
        default=None,
        help="Payload as text_format string (overrides empty body for --send)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=8,
        metavar="SECONDS",
        help="Per-command wait for a response (default 8)",
    )
    p.add_argument(
        "--listen",
        type=float,
        default=None,
        metavar="SECONDS",
        help="After connect (and optional --send), listen for SECONDS and dump frames",
    )
    p.add_argument(
        "--keepalive",
        type=float,
        default=0,
        metavar="SECONDS",
        help="During --listen, send a read-only query every SECONDS to keep the session alive",
    )
    p.add_argument(
        "--capture",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="Record every frame to PATH as NDJSON (default: captures/<timestamp>.ndjson)",
    )
    a = p.parse_args()
    VERBOSE = a.verbose

    # Validate: a body only makes sense for exactly one --send
    if a.payload and not a.send:
        p.error("--payload requires --send")
    if a.payload and len(a.send) > 1:
        p.error("--payload applies to a single --send")

    # Resolve opcode string to constant
    opcode_map = {"write": OP_WRITE, "write_enc": OP_WRITE_ENC, "read": OP_READ}
    opcode = opcode_map[a.opcode]

    capture = None
    mac = resolve_mac(a.mac)  # validate before creating a capture file
    key = load_key(a.key_file)
    if a.capture is not None:
        capture = Capture(a.capture or default_capture_path())
        print(f"Capturing every frame to {capture.path}")

    w = XiaomiWatch(mac, a.l2_channel, key, capture=capture)
    try:
        w.connect()

        # --send: one or more commands, each waiting for its response
        for ctype, subtype in a.send or []:
            cmd = build_command(ctype, subtype, a.payload)
            print(f"Sending command {ctype}/{subtype} on ch{a.l2_channel} ({a.opcode}) ...")
            frame = w._send_until_space(opcode, cmd.SerializeToString(), a.timeout)
            if frame is None:
                print("send window still full, skipping this command")
                continue
            r = w.wait_for(ctype, subtype, a.timeout)
            if r is None:
                print("(no answer)")
                if len(a.send) == 1 and not a.listen:
                    sys.exit(1)  # a lone send that expects an answer failed
                continue
            print(f"Response: {text_format.MessageToString(r, as_one_line=True)}")

        # --ota-require: the read-only HyperOS OTA handshake (channel 6, 0x5A framing)
        if a.ota_require:
            print("Sending OTA REQUIRE (5A 0A 00) on channel 6 ...")
            w.l2_channel = CH_OTA
            frame = w._send_until_space(OP_WRITE, ota_require_segment(), a.timeout)
            if frame is None:
                print("send window still full, aborting the OTA probe")
            else:
                end = time.time() + a.timeout
                while time.time() < end and not w.ota_replies:
                    w._pump(min(1.0, end - time.time()))
                if not w.ota_replies:
                    print("(no OTA reply)")
                    if not a.listen:
                        sys.exit(1)

        # --mass-push: the ota_type = 2 file push (prepare + DataUpload + raw channel-2 bytes)
        if a.mass_push:
            print(f"Pushing {a.mass_push} over the mass channel ...")
            with open(a.mass_push, "rb") as fh:
                w.mass_push(fh.read(), fw_version=a.fw_version)

        # --listen: connect and listen for unsolicited frames
        if a.listen:
            print(f"Listening for {a.listen} seconds ...")
            w.listen(a.listen, a.keepalive)

    except ConnectionResetError:
        # The watch closes an SPP session after roughly 25 s; a capture keeps what it got.
        print("\nconnection reset by the watch (session lifetime is ~25 s), keeping the capture")
    except OSError as e:
        if e.errno != errno.EHOSTDOWN:
            raise
        print("\nwatch refused the connection (EHOSTDOWN): wait a few seconds and retry")
    finally:
        w.close()
        if capture:
            capture.close()
            print(f"Capture written to {capture.path}")


if __name__ == "__main__":
    main()
