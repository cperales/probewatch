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
  uv run python src/xiaomi_client.py --listen 30                 # connect, dump unsolicited
  uv run python src/xiaomi_client.py --send 2 18 --listen 10     # find-device, then listen
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
        os.write(self.fd, data)

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
CH_PROTOBUF, CH_DATA, CH_ACTIVITY = 1, 2, 5
OP_PLAIN, OP_ENCRYPTED = 1, 2

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
    def __init__(self, mac: str, channel: int, secret: bytes, capture: Capture | None = None):
        self.mac, self.channel = mac, channel
        self.sess = Session(secret)
        self.tx_seq = 0
        self.inbox: list[xiaomi_pb2.Command] = []
        self.link: Rfcomm | None = None
        self.capture = capture
        self._sent: dict[int, bytes] = {}  # seq -> encoded DATA frame for NACK retransmit
        self._nacked: set[int] = set()  # seqs we already retransmitted

    # -- low level
    def _send_data(self, channel: int, opcode: int, payload: bytes) -> bytes:
        """Build and send a DATA frame, returning the full encoded frame for retransmit."""
        body = bytes([channel & 0x0F, opcode]) + (
            self.sess.encrypt_v2(payload) if opcode == OP_ENCRYPTED else payload
        )
        seq = self.tx_seq
        frame = encode_v2(T_DATA, seq, body)
        self.link.send(frame)
        self.tx_seq = (seq + 1) & 0xFF
        if self.capture:
            self.capture.frame("tx", T_DATA, seq, channel, opcode, payload)
        return frame

    def send_command(self, cmd: xiaomi_pb2.Command):
        log("send cmd", cmd.type, cmd.subtype)
        seq = self.tx_seq  # capture before _send_data increments it
        if cmd.type == 1:  # auth -> plaintext on the protobuf channel
            frame = self._send_data(CH_PROTOBUF, OP_PLAIN, cmd.SerializeToString())
        else:
            frame = self._send_data(CH_PROTOBUF, OP_ENCRYPTED, cmd.SerializeToString())
        self._sent[seq] = frame  # track full encoded frame for NACK retransmit

    def _pump(self, timeout: float):
        """Read and handle frames until `timeout` seconds pass without a complete frame."""
        end = time.time() + timeout
        while True:
            res = parse_v2(self.link.buf)
            if res is None:
                remaining = end - time.time()
                if remaining <= 0 or not self.link.fill(remaining):
                    return
                continue
            ptype, seq, payload, used = res
            self.link.buf = self.link.buf[used:]
            if ptype is None:
                continue
            if ptype != T_DATA and self.capture:
                self.capture.frame("rx", ptype, seq, data=payload)
            if ptype == T_ACK:
                log("ack", seq)
            elif ptype == T_NACK:
                log("nack, watch expects", seq)
                if seq in self._sent and seq not in self._nacked:
                    log("retransmitting command for seq", seq)
                    self.link.send(self._sent[seq])  # verbatim DATA body
                    self._nacked.add(seq)
            elif ptype == T_SESSION:
                log("session config from watch, opcode", payload[:1].hex(), payload.hex(" "))
                self.session_ok = True
            elif ptype == T_DATA:
                self.link.send(encode_v2(T_ACK, seq, b""))  # ACK first: never delay it
                if len(payload) < 2:  # a DATA frame needs the channel/opcode header
                    if self.capture:
                        self.capture.frame("rx", ptype, seq, data=payload, note="short data")
                    log(f"short DATA frame ({len(payload)} bytes), ignored")
                    continue
                ch, op, data = payload[0] & 0x0F, payload[1], payload[2:]
                if op == OP_ENCRYPTED:
                    data = self.sess.decrypt_v2(data)
                if self.capture:
                    self.capture.frame("rx", ptype, seq, ch, op, data)
                if ch == CH_PROTOBUF:
                    cmd = xiaomi_pb2.Command()
                    try:
                        cmd.ParseFromString(data)
                    except Exception as e:  # noqa: BLE001
                        print(f"!! could not parse protobuf ({e}): {data.hex()}")
                        continue
                    log("recv cmd", cmd.type, cmd.subtype)
                    self.inbox.append(cmd)
                else:
                    log(f"data on channel {ch} ({len(data)} bytes) ignored")

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
        print(f"[1] RFCOMM connect {self.mac} channel {self.channel} ...")
        self.link = Rfcomm(self.mac, self.channel)

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
    p.add_argument("--channel", type=int, default=2)
    p.add_argument("--key-file", default=KEY_FILE)
    p.add_argument("-v", "--verbose", action="store_true")
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

    capture = None
    mac = resolve_mac(a.mac)  # validate before creating a capture file
    key = load_key(a.key_file)
    if a.capture is not None:
        capture = Capture(a.capture or default_capture_path())
        print(f"Capturing every frame to {capture.path}")

    w = XiaomiWatch(mac, a.channel, key, capture=capture)
    try:
        w.connect()

        # --send: one or more commands, each waiting for its response
        for ctype, subtype in a.send or []:
            cmd = build_command(ctype, subtype, a.payload)
            print(f"Sending command {ctype}/{subtype} ...")
            r = w.send_command_with_retransmit(cmd, a.timeout)
            if r is None:
                print("(no answer)")
                if len(a.send) == 1 and not a.listen:
                    sys.exit(1)  # a lone send that expects an answer failed
                continue
            print(f"Response: {text_format.MessageToString(r, as_one_line=True)}")

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
