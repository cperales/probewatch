#!/usr/bin/env python3
"""Build an LCPU oracle package: flip a byte in the uncompressed LCPU image and re-compress.

The real OTA package's image1 is a raw-DEFLATE record stream that inflates to the LCPU
image. Flipping a byte in the *compressed* stream breaks decompression (the HCPU's
`dfu_decompress` rejects it), which tests the decompress path rather than the signing gate.
To target the signing gate, this rebuilds image1 so it still inflates cleanly to a modified
LCPU image: the package is structurally valid, but the installed content differs from the
signed one.

The package layout is `header (0xa8) + image0 + image1`; image1's record stream is
`[total][0x2800][complen][0x2800][deflate]` for the first block, `[0x2800][deflate]` for a
full middle block, and `[complen][uncomplen][deflate]` for the short final block.

Nothing is flashed; the watch is not contacted. The output is put beside the other oracle
variants under `secrets/firmware/oracle/` (git-ignored).

Usage:
    uv run python scripts/prep_lcpu_oracle.py [PACKAGE] [--out PATH] [--flip OFFSET]
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from extract_firmware import extract_lcpu  # noqa: E402  (same directory)

ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = ROOT / "secrets" / "firmware"
DEFAULT_OUT = FIRMWARE_DIR / "oracle" / "oracle-image1-recompressed.bin"

MAGIC = b"\xad\xef\xcd\xaf"
HEADER_SIZE = 0xA8
OFF_IMAGE0_SIZE = 0x0C
OFF_IMAGE1_STORED = 0x1C
BLOCK = 0x2800
DEFAULT_FLIP = 0x10000  # well inside the LCPU code/data, past the vector table


def find_package(arg: str | None) -> Path:
    """Resolve the package: the argument, else the sole .bin in secrets/firmware."""
    if arg:
        return Path(arg)
    images = sorted(FIRMWARE_DIR.glob("*.bin"))
    if len(images) != 1:
        raise SystemExit(f"expected one .bin in {FIRMWARE_DIR}, found {len(images)}")
    return images[0]


def raw_deflate(data: bytes) -> bytes:
    """Raw-DEFLATE one block (no zlib header, as the record stream uses)."""
    engine = zlib.compressobj(9, zlib.DEFLATED, -15)
    return engine.compress(data) + engine.flush()


def compress_lcpu(image: bytes) -> bytes:
    """Rebuild the record stream that ``extract_firmware.extract_lcpu`` walks."""
    blocks = [image[i : i + BLOCK] for i in range(0, len(image), BLOCK)]
    if not blocks or len(blocks[0]) != BLOCK:
        raise SystemExit("LCPU image shorter than one block")
    out = bytearray()
    first = raw_deflate(blocks[0])
    out += struct.pack("<IIII", len(image), BLOCK, len(first), BLOCK) + first
    for block in blocks[1:]:
        packed = raw_deflate(block)
        if len(block) == BLOCK:
            out += struct.pack("<I", BLOCK) + packed
        else:
            out += struct.pack("<II", len(packed), len(block)) + packed
    return bytes(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("package", nargs="?", default=None)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument(
        "--flip", type=lambda s: int(s, 0), default=DEFAULT_FLIP, help="LCPU image offset to flip"
    )
    args = parser.parse_args()

    pkg = find_package(args.package)
    data = pkg.read_bytes()
    if data[:4] != MAGIC:
        raise SystemExit("not a SiFli package (bad magic ad ef cd af)")
    image0_size = struct.unpack_from("<I", data, OFF_IMAGE0_SIZE)[0]
    image1_stored = struct.unpack_from("<I", data, OFF_IMAGE1_STORED)[0]
    image0 = data[HEADER_SIZE : HEADER_SIZE + image0_size]
    image1 = data[HEADER_SIZE + image0_size : HEADER_SIZE + image0_size + image1_stored]

    lcpu, records = extract_lcpu(image1, 0)
    if compress_lcpu(lcpu) != image1 and extract_lcpu(compress_lcpu(lcpu), 0)[0] != lcpu:
        raise SystemExit("re-compression does not round-trip; aborting")
    rebuilt = compress_lcpu(lcpu)
    if extract_lcpu(rebuilt, 0)[0] != lcpu:
        raise SystemExit("re-compression does not round-trip; aborting")

    if not 0 <= args.flip < len(lcpu):
        raise SystemExit(f"--flip {args.flip:#x} outside the LCPU image ({len(lcpu):#x})")
    old = lcpu[args.flip]
    mod = bytearray(lcpu)
    mod[args.flip] = old ^ 0xFF
    new_image1 = compress_lcpu(bytes(mod))
    if extract_lcpu(new_image1, 0)[0] != bytes(mod):
        raise SystemExit("modified stream does not round-trip; aborting")

    header = bytearray(data[:HEADER_SIZE])
    struct.pack_into("<I", header, OFF_IMAGE1_STORED, len(new_image1))
    package = bytes(header) + image0 + new_image1
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(package)

    print(f"package   {pkg} -> {out}")
    print(f"image1    {image1_stored:,} B -> {len(new_image1):,} B ({records} records)")
    print(f"flip      LCPU 0x{args.flip:x}: 0x{old:02x} -> 0x{old ^ 0xFF:02x}")
    print(
        f"package   {len(package):,} B  md5={hashlib.md5(package).hexdigest()}  magic={package[:4].hex()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
