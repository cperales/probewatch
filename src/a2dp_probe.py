"""Ask the watch's A2DP service which audio endpoints and codecs it has.

Read-only: sends only AVDTP DISCOVER and GET_CAPABILITIES signalling commands
over L2CAP PSM 25. No audio stream is opened.

Needs a Python built with Bluetooth support (socket.AF_BLUETOOTH). The distro
/usr/bin/python3 has it; CPython builds downloaded by uv do not, which is why the
venv is created from the system interpreter (see README "Setup").

Usage: uv run python src/a2dp_probe.py [MAC]
"""

import argparse
import socket

from watch_secrets import resolve_mac

AVDTP_PSM = 25
DISCOVER, GET_CAPABILITIES = 0x01, 0x02
MSG_TYPES = {0: "command", 1: "general reject", 2: "accept", 3: "reject"}
CATEGORIES = {
    1: "Media Transport",
    2: "Reporting",
    3: "Recovery",
    4: "Content Protection",
    5: "Header Compression",
    6: "Multiplexing",
    7: "Media Codec",
    8: "Delay Reporting",
}
CODECS = {
    0x00: "SBC",
    0x01: "MPEG-1,2 Audio (MP3)",
    0x02: "MPEG-2,4 AAC",
    0x04: "ATRAC",
    0xFF: "Vendor-specific",
}
VENDOR_CODECS = {
    (0x012D, 0x00AA): "Sony LDAC",
    (0x004F, 0x0001): "aptX",
    (0x00D7, 0x0024): "aptX HD",
    (0x0075, 0x0102): "Samsung Scalable",
    (0x027D, 0x0001): "LHDC",
}


def bits(value: int, names: list[str]) -> str:
    """names[0] is the most significant bit of the field."""
    n = len(names)
    return ", ".join(name for i, name in enumerate(names) if value & (1 << (n - 1 - i))) or "-"


def decode_codec(data: bytes) -> str:
    media, codec, info = data[0] >> 4, data[1], data[2:]
    out = f"{'Audio' if media == 0 else f'media {media}'} / {CODECS.get(codec, hex(codec))}"
    if codec == 0x00 and len(info) >= 4:  # SBC
        out += (
            f"\n        sampling: {bits(info[0] >> 4, ['16 kHz', '32 kHz', '44.1 kHz', '48 kHz'])}"
            f"\n        channels: {bits(info[0] & 0xF, ['Mono', 'Dual', 'Stereo', 'Joint stereo'])}"
            f"\n        blocks:   {bits(info[1] >> 4, ['4', '8', '12', '16'])}"
            f"\n        subbands: {bits((info[1] >> 2) & 3, ['4', '8'][::-1])}"
            f"\n        alloc:    {bits(info[1] & 3, ['SNR', 'Loudness'])}"
            f"\n        bitpool:  {info[2]}..{info[3]}"
        )
    elif codec == 0x02 and len(info) >= 6:  # AAC
        rates = int.from_bytes(info[1:3], "big") >> 4
        out += (
            f"\n        object types: {bits(info[0], ['MPEG-2 LC', 'MPEG-4 LC', 'MPEG-4 LTP', 'MPEG-4 Scalable', '', '', '', ''])}"
            f"\n        sampling: {bits(rates, ['8k', '11.025k', '12k', '16k', '22.05k', '24k', '32k', '44.1k', '48k', '64k', '88.2k', '96k'])}"
            f"\n        channels: {bits((info[2] >> 2) & 3, ['1', '2'])}"
            f"\n        VBR: {bool(info[3] & 0x80)}  bitrate: {int.from_bytes(info[3:6], 'big') & 0x7FFFFF} bps"
        )
    elif codec == 0xFF and len(info) >= 6:
        vid, cid = int.from_bytes(info[0:4], "little"), int.from_bytes(info[4:6], "little")
        out += f"  {VENDOR_CODECS.get((vid, cid), f'vendor 0x{vid:04x} codec 0x{cid:04x}')}"
    out += f"\n        raw: {data.hex(' ')}"
    return out


class Avdtp:
    def __init__(self, mac: str):
        self.s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP)
        self.s.settimeout(15)
        self.s.connect((mac, AVDTP_PSM))
        self.label = 0

    def request(self, signal: int, payload: bytes = b"") -> bytes:
        self.label = (self.label + 1) & 0xF
        self.s.send(bytes([self.label << 4, signal]) + payload)  # single packet, command
        while True:
            resp = self.s.recv(1024)
            if resp[0] >> 4 == self.label and resp[0] & 3 != 0:  # ignore the watch's own commands
                break
        mtype = resp[0] & 3
        if mtype != 2:
            raise RuntimeError(f"signal 0x{signal:02x}: {MSG_TYPES[mtype]} {resp.hex(' ')}")
        return resp[2:]

    def close(self):
        self.s.close()


def main(mac: str) -> None:
    print(f"Connecting AVDTP (L2CAP PSM {AVDTP_PSM}) to {mac} ...")
    av = Avdtp(mac)
    print("Connected.\n")
    seps = av.request(DISCOVER)
    for i in range(0, len(seps) - 1, 2):
        seid, in_use = seps[i] >> 2, bool(seps[i] & 0x02)
        media, tsep = seps[i + 1] >> 4, (seps[i + 1] >> 3) & 1
        print(
            f"Endpoint SEID {seid}: {'Audio' if media == 0 else media} "
            f"{'SINK (receives audio)' if tsep else 'SOURCE (sends audio)'}  in_use={in_use}"
        )
        caps = av.request(GET_CAPABILITIES, bytes([seid << 2]))
        j = 0
        while j + 1 < len(caps):
            cat, length = caps[j], caps[j + 1]
            data = caps[j + 2 : j + 2 + length]
            name = CATEGORIES.get(cat, f"category {cat}")
            print(f"    {name}: {decode_codec(data) if cat == 7 else (data.hex(' ') or 'yes')}")
            j += 2 + length
        print()
    av.close()


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "mac", nargs="?", default=None, help="watch MAC (default: secrets/device.md or $WATCH_MAC)"
    )
    main(resolve_mac(p.parse_args().mac))
