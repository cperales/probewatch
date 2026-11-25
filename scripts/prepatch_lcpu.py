#!/usr/bin/env python3
"""Pre-patch the LCPU binary: subtract 0x26000 from absolute pointer words.

The LCPU firmware stores absolute pointers shifted by ``0x26000``
(``true = stored - 0x26000``). This script scans the binary for words that,
when added to ``0x26000``, fall in the valid LCPU address range and patches
them in-place. PC-relative offsets are left untouched.

Usage:
    uv run python scripts/prepatch_lcpu.py [IMAGE] [--out PATH] [--dry-run]
"""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = ROOT / "secrets" / "firmware" / "extracted"

# LCPU runs from 0x12000000; the image is ~5.5 MB so valid addresses are
# 0x12000000 .. 0x12560000. We use a generous upper bound.
LCPU_BASE = 0x12000000
LCPU_TOP = 0x12600000
SHIFT = 0x26000

# Padded range of *stored* values that resolve to valid addresses.
STORED_MIN = LCPU_BASE - SHIFT
STORED_MAX = LCPU_TOP - SHIFT


def find_image(arg: str | None) -> Path:
    if arg:
        return Path(arg)
    images = sorted(FIRMWARE_DIR.glob("lcpu*.bin"))
    if not images:
        raise SystemExit(f"no lcpu*.bin in {FIRMWARE_DIR.relative_to(ROOT)}")
    return images[0]


def prepatch(data: bytes, dry_run: bool = False) -> tuple[bytes, int]:
    """Subtract SHIFT from every aligned word in the valid stored range.

    Returns ``(patched, count)`` where *count* is the number of words patched.
    """
    arr = bytearray(data)
    count = 0
    for i in range(0, len(arr) - 3, 4):
        word = struct.unpack_from("<I", arr, i)[0]
        if STORED_MIN <= word <= STORED_MAX:
            arr[i : i + 4] = struct.pack("<I", word - SHIFT)
            count += 1
            if not dry_run:
                print(f"  patch {i:#08x}: {word:#010x} -> {word - SHIFT:#010x}")
    return bytes(arr), count


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
    )
    parser.add_argument("image", nargs="?", default=None, help="lcpu binary")
    parser.add_argument("--out", default=None, help="output path")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print patches but don't write",
    )
    args = parser.parse_args()

    path = find_image(args.image)
    data = path.read_bytes()
    print(f"read  {path} ({len(data):,} B)")

    patched, count = prepatch(data, dry_run=args.dry_run)
    print(f"patched {count} words in {len(patched):,} B")

    if not args.dry_run:
        out = Path(args.out) if args.out else path
        out.write_bytes(patched)
        print(f"wrote {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
