#!/usr/bin/env python3
"""Score candidate load bases for a Cortex-M image by pointer density.

A firmware image is full of 32-bit literals that are addresses of things inside the
image itself: function pointers in vector tables and dispatch tables, string and data
pointers in structures. If the assumed load base is right, those words land inside
``[base, base + size)``; if it is wrong by much more than the image size, they land
outside and the count collapses. This script counts that population for a range of
candidate bases, so the base can be confirmed (or a wrong one refuted) without
trusting the analysis tool that found the functions.

The test is coarse by construction: a word that points into the image stays in range
until the base has moved by roughly the image size, so the sweep resolves the base to
that order and no better. It is a check against gross errors (a wrong megabyte, the
flash alias of a RAM address, an unapplied relocation), not a substitute for a
vector-table read. ``--shift`` applies a fixed offset to every stored word first,
which is how the LCPU image was relocated before import.

Read-only: the image is opened and read, nothing is flashed or executed.

Usage:
    uv run python scripts/pointer_density.py [--image hcpu|lcpu] [--path FILE]
        [--base ADDR] [--shift OFFSET] [--window BYTES] [--step BYTES]
"""

from __future__ import annotations

import argparse
import bisect
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXTRACTED = ROOT / "secrets" / "firmware" / "extracted"

# Load base of each image, as established from the vector table (docs/firmware.md).
IMAGES = {"hcpu": 0x20000000, "lcpu": 0x12000000}
SIZES = {"hcpu": 190232, "lcpu": 5578752}

WORD = 4


def image_words(data: bytes, shift: int = 0) -> list[int]:
    """Every complete 32-bit little-endian word, sorted, with ``shift`` subtracted."""
    count = len(data) // WORD
    words = [
        (value - shift) & 0xFFFFFFFF for (value,) in struct.iter_unpack("<I", data[: count * WORD])
    ]
    words.sort()
    return words


def count_in_range(words: list[int], low: int, high: int) -> int:
    """Number of sorted ``words`` in ``[low, high)``."""
    return bisect.bisect_left(words, high) - bisect.bisect_left(words, low)


def self_pointers(words: list[int], base: int, size: int) -> list[int]:
    """The words that are addresses inside an image of ``size`` bytes loaded at ``base``."""
    low, high = base, base + size
    start = bisect.bisect_left(words, low)
    stop = bisect.bisect_left(words, high)
    return words[start:stop]


def sweep(words: list[int], base: int, size: int, window: int, step: int) -> list[tuple[int, int]]:
    """``(base, count)`` for every candidate base in ``base ± window`` at ``step``."""
    return [
        (candidate, count_in_range(words, candidate, candidate + size))
        for candidate in range(base - window, base + window + 1, step)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Pointer-density check for a load base.")
    parser.add_argument("--image", choices=sorted(IMAGES), default="hcpu")
    parser.add_argument("--path", type=Path, help="image to read (default: extracted <image>.bin)")
    parser.add_argument("--base", type=lambda text: int(text, 0), help="claimed load base")
    parser.add_argument("--shift", type=lambda text: int(text, 0), default=0)
    parser.add_argument("--window", type=lambda text: int(text, 0), default=0x100000)
    parser.add_argument("--step", type=lambda text: int(text, 0), default=0x1000)
    args = parser.parse_args()

    path = args.path or EXTRACTED / f"{args.image}.bin"
    base = args.base if args.base is not None else IMAGES[args.image]
    data = path.read_bytes()
    words = image_words(data, args.shift)
    size = len(data)

    print(f"image   {path}")
    print(
        f"        {size:,} B, {len(words):,} words"
        + (f", shift {args.shift:#x}" if args.shift else "")
    )
    print(f"base    {base:#010x} .. {base + size:#010x}")

    hits = self_pointers(words, base, size)
    odd = sum(1 for value in hits if value & 1)
    if hits:
        print(
            f"self    {len(hits):,} words ({100 * len(hits) / len(words):.1f}%): "
            f"{odd:,} odd (Thumb code), {len(hits) - odd:,} even (data)"
        )
        print(f"        {hits[0]:#010x} .. {hits[-1]:#010x}")
    else:
        print("self    0 words: no word of this image points inside it at that base")

    results = sweep(words, base, size, args.window, args.step)
    best_count = max(count for _candidate, count in results)
    best_bases = [candidate for candidate, count in results if count == best_count]
    claimed = count_in_range(words, base, base + size)
    low, high = base - args.window, base + args.window
    print(f"\nsweep   {low:#010x} .. {high:#010x}, step {args.step:#x} ({len(results)} bases)")
    print(
        f"peak    {best_count:,} at {best_bases[0]:#010x}"
        + (f" (+{len(best_bases) - 1} ties)" if len(best_bases) > 1 else "")
        + f"; claimed base {claimed:,} ({100 * claimed / best_count if best_count else 0:.0f}% of peak)"
    )
    # The count saturates while the window still covers the pointer population, so the
    # useful figure is the width of that plateau, not the single best candidate.
    for fraction in (0.9, 0.6):
        steady = [candidate for candidate, count in results if count >= fraction * best_count]
        print(
            f">={fraction:.0%}    {min(steady):#010x} .. {max(steady):#010x} "
            f"({len(steady)} bases, {max(steady) - min(steady):#x} wide)"
        )

    print("\ncontrols")
    for label, candidate in (
        ("-one image", base - size),
        ("-1 MB", base - 0x100000),
        ("-0x26000", base - 0x26000),
        ("+0x26000", base + 0x26000),
        ("+1 MB", base + 0x100000),
        ("QSPI alias 0x10000000", 0x10000000),
    ):
        count = count_in_range(words, candidate, candidate + size)
        print(f"  {label:>22} {candidate:#010x}  {count:>9,}")


if __name__ == "__main__":
    main()
