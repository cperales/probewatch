#!/usr/bin/env python3
"""Extract the HCPU and LCPU images from a SiFli ``ad ef cd af`` watch package.

The OTA file is a SiFli container with two Cortex-M images: a plaintext RT-Thread
application for the HCPU and a raw-DEFLATE record stream for the LCPU (the core
that runs the Bluetooth/SPP stack). This reproduces the extraction locally; the
package is only read, nothing is flashed or executed. The walk verifies itself
against the size fields, so a mismatch aborts instead of writing a short image.

Usage:
    uv run python scripts/extract_firmware.py [IMAGE] [--out DIR]
"""

from __future__ import annotations

import argparse
import re
import struct
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = ROOT / "secrets" / "firmware"
DEFAULT_OUT = FIRMWARE_DIR / "extracted"

MAGIC = b"\xad\xef\xcd\xaf"
HEADER_SIZE = 0xA8

# Top-header fields (little-endian u32).
OFF_IMAGE0_SIZE = 0x0C
OFF_IMAGE1_STORED = 0x1C
OFF_IMAGE1_TOTAL = 0x20

# Record stream: every block expands to 0x2800 bytes except the final one.
BLOCK = 0x2800
MIN_LEN = 8

# Distinct-string markers that identify the LCPU (the protocol lives there).
MARKERS = ("spp", "rfcomm", "l2cap", "gatt", "mass", "hkdf", "protobuf")


def find_image(arg: str | None) -> Path:
    """Resolve the package: the argument, else the single .bin in secrets/firmware."""
    if arg:
        return Path(arg)
    images = sorted(FIRMWARE_DIR.glob("*.bin"))
    if len(images) != 1:
        raise SystemExit(
            f"expected one .bin in {FIRMWARE_DIR.relative_to(ROOT)}, found {len(images)}"
        )
    return images[0]


def parse_header(data: bytes) -> tuple[int, int, int]:
    """Return (image0_size, image1_stored, image1_total) from the package header."""
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise SystemExit("not a SiFli package: expected magic ad ef cd af")
    image0_size, image1_stored, image1_total = (
        struct.unpack_from("<I", data, off)[0]
        for off in (OFF_IMAGE0_SIZE, OFF_IMAGE1_STORED, OFF_IMAGE1_TOTAL)
    )
    return image0_size, image1_stored, image1_total


def inflate_block(buf: bytes) -> tuple[bytes, int, bool]:
    """Raw-inflate one record; returns (output, bytes consumed, stream finished)."""
    engine = zlib.decompressobj(-zlib.MAX_WBITS)
    try:
        out = engine.decompress(buf)
    except zlib.error:
        return b"", 0, False
    return out, len(buf) - len(engine.unused_data), engine.eof


def extract_lcpu(data: bytes, start: int) -> tuple[bytes, int]:
    """Walk the record stream at *start*; return (image, record count).

    The first record is introduced by ``[total][block][complen][uncomplen]``.
    Later records are either ``[uncomplen][deflate]`` or ``[complen][uncomplen]
    [deflate]``; the declared lengths include a 4-byte encoder pad that the
    final record may truncate. Everything must expand to exactly *total* bytes.
    """
    total, block, first_len, first_out = struct.unpack_from("<IIII", data, start)
    if block != BLOCK or first_out != BLOCK:
        raise ValueError(f"unexpected block framing {block:#x}/{first_out:#x}")
    out, _, ok = inflate_block(data[start + 16 : start + 16 + first_len])
    if not ok or len(out) != first_out:
        raise ValueError("first record does not inflate to one block")

    image = bytearray(out)
    pos = start + 16 + first_len
    records = 1

    while pos < len(data):
        if len(data) - pos < MIN_LEN:
            raise ValueError(f"truncated record at {pos:#x}")
        mark = struct.unpack_from("<I", data, pos)[0]
        if mark == BLOCK:
            out, used, ok = inflate_block(data[pos + 4 :])
            if ok and len(out) == BLOCK:
                image += out
                pos += 4 + used
                records += 1
                continue
        declared, expected = struct.unpack_from("<II", data, pos)
        if declared == 0 or declared > len(data) - pos:
            raise ValueError(f"bad record length {declared:#x} at {pos:#x}")
        # The last record's pad may run past EOF; inflate to the end and stop.
        out, _, ok = inflate_block(data[pos + 8 :])
        if not ok or len(out) != expected:
            raise ValueError(f"record at {pos:#x} does not inflate to {expected:#x}")
        image += out
        records += 1
        pos += 8 + declared

    if len(image) != total:
        raise ValueError(f"walk produced {len(image):#x} B, header says {total:#x} B")
    return bytes(image), records


def marker_counts(image: bytes) -> dict[str, int]:
    """Count distinct printable strings containing each protocol marker."""
    strings = {s.lower() for s in re.findall(rb"[ -~]{5,}", image)}
    return {mark: sum(1 for s in strings if mark.encode() in s) for mark in MARKERS}


def write_image(path: Path, image: bytes) -> None:
    path.write_bytes(image)
    print(f" -> {path}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("image", nargs="?", default=None, help="package .bin (default: secrets)")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output directory")
    args = parser.parse_args()

    path = find_image(args.image)
    data = path.read_bytes()
    image0_size, image1_stored, image1_total = parse_header(data)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"package  {path} ({len(data):,} B)")
    print(
        f"header   image0={image0_size:,} B  image1 stored={image1_stored:,} B"
        f"  image1 total={image1_total:,} B"
    )

    hcpu = data[HEADER_SIZE : HEADER_SIZE + image0_size]
    sp, reset = struct.unpack_from("<II", hcpu)
    print(f"hcpu     {len(hcpu):,} B  SP={sp:#x} reset={reset:#08x}")
    write_image(out_dir / "hcpu.bin", hcpu)

    lcpu, records = extract_lcpu(data, HEADER_SIZE + image0_size)
    sp, reset = struct.unpack_from("<II", lcpu)
    print(f"lcpu     {records} records -> {len(lcpu):,} B  SP={sp:#x} reset={reset:#08x}")
    counts = " ".join(f"{k}={v}" for k, v in marker_counts(lcpu).items())
    print(f"markers  {counts}")
    write_image(out_dir / "lcpu.bin", lcpu)
    return 0


if __name__ == "__main__":
    sys.exit(main())
