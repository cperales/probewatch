#!/usr/bin/env python3
"""Prepare modified SiFli firmware packages for the signature-rejection oracle.

Reads the real OTA package and writes two modified copies under a git-ignored
directory. Both keep the ``ad ef cd af`` magic and the sub-file sizes intact, so
they pass the LCPU header check; the client recomputes the MD5 from the file it is
given, so both also pass the end-of-push MD5 check. They differ in *where*
integrity is broken, to show which later check (if any) rejects a modified image:

``oracle-image.bin``
    one byte flipped inside image0 (the HCPU app). Invalidates any per-image
    hash/signature; if nothing checks it, the watch would install a corrupted
    image (the risky variant).

``oracle-header.bin``
    one byte flipped in sub-file 0's trailing 4-byte hash. The images are
    untouched, so a watch that ignores the hash just reflashes the same good
    firmware (the safe control).

What the package is: ``header (0xa8) + image0 + image1`` exactly, with **no
separate RSA-2048 signature blob**. The per-sub-file entries end in a 4-byte
field, and image0/image1 are the raw HCPU and compressed LCPU streams; the signing
gate (if enforced) is therefore against the flash ``sec_configuration`` (FCES
header at ``0x12000000``), not this file.

Nothing is flashed or executed; the watch is not contacted.

Usage:
    uv run python scripts/prep_oracle_firmware.py [PACKAGE] [--out DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = ROOT / "secrets" / "firmware"
DEFAULT_OUT = FIRMWARE_DIR / "oracle"

MAGIC = b"\xad\xef\xcd\xaf"
HEADER_SIZE = 0xA8
OFF_IMAGE0_SIZE = 0x0C

# Sub-file table starts at offset 8; each entry is 16 B: [u16 type][u16 flags][u32 size][u32][u32].
OFF_SUBFILE_TABLE = 8
HEADER_HASH_OFF = OFF_SUBFILE_TABLE + 12  # sub-file 0's trailing 4-byte hash
IMAGE_FLIP_OFF = HEADER_SIZE + 0x1000  # well inside image0, past the vector table


def find_package(arg: str | None) -> Path:
    """Resolve the package: the argument, else the sole .bin in secrets/firmware."""
    if arg:
        return Path(arg)
    images = sorted(FIRMWARE_DIR.glob("*.bin"))
    if len(images) != 1:
        raise SystemExit(f"expected one .bin in {FIRMWARE_DIR}, found {len(images)}")
    return images[0]


def flip(data: bytes, offset: int) -> tuple[bytes, int, int]:
    """Return (modified, old_byte, new_byte) with one byte XORed at *offset*."""
    old = data[offset]
    new = old ^ 0xFF
    out = bytearray(data)
    out[offset] = new
    return bytes(out), old, new


def report(path: Path, data: bytes) -> None:
    """Print size, MD5 and the magic sanity check for one written variant."""
    md5 = hashlib.md5(data).hexdigest()
    magic = "ok" if data[:4] == MAGIC else "BAD"
    print(f"  {path.name}: {len(data):,} B  md5={md5}  magic={magic}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package", nargs="?", default=None)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args()

    pkg = find_package(args.package)
    data = pkg.read_bytes()
    if data[:4] != MAGIC:
        raise SystemExit("not a SiFli package (bad magic ad ef cd af)")
    image0_size = struct.unpack_from("<I", data, OFF_IMAGE0_SIZE)[0]

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"package  {pkg} ({len(data):,} B, image0 {image0_size:,} B)")

    image, old, new = flip(data, IMAGE_FLIP_OFF)
    (out / "oracle-image.bin").write_bytes(image)
    print(
        f"\nimage variant (risky): 0x{old:02x}->0x{new:02x} at 0x{IMAGE_FLIP_OFF:x} (inside image0)"
    )
    report(out / "oracle-image.bin", image)

    header, old, new = flip(data, HEADER_HASH_OFF)
    (out / "oracle-header.bin").write_bytes(header)
    print(
        f"\nheader variant (safe): 0x{old:02x}->0x{new:02x} at 0x{HEADER_HASH_OFF:x} (sub-file 0 hash)"
    )
    report(out / "oracle-header.bin", header)

    print(f"\nwritten to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
