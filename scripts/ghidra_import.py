#!/usr/bin/env python3
"""Headless Ghidra import for the HCPU and LCPU firmware images.

Carves the HCPU image from the SiFli package, extracts/inflates the LCPU record
stream (optionally pre-patching it), then invokes Ghidra's ``analyzeHeadless``
to import each as *Raw Binary* with language **ARM:LE:32:Cortex** (ARMv8-M /
Cortex-M33), the image base address, and auto-analysis.

This is the import step the plan (`secrets/plans/ghidra-mapping.md`, Phase A1)
calls for; it gives a proper Cortex-M language the REA increment lacked.

Usage:
    uv run python scripts/ghidra_import.py [PACKAGE] [--out DIR] [--lcpu-patch]
    uv run python scripts/ghidra_import.py --help
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import struct
import subprocess
import sys
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIRMWARE_DIR = ROOT / "secrets" / "firmware"
EXTRACTED_DIR = FIRMWARE_DIR / "extracted"
PACKAGE_FILE = FIRMWARE_DIR / "3b86d2fa0b2572e42bd09b4bfd2da6eb.bin"
GHIDRA_DIR = ROOT / "secrets" / "ghidra"
GHIDRA_PROJECTS = GHIDRA_DIR / "projects"
GHIDRA_HOME = Path(os.environ.get("GHIDRA_HOME", str(Path.home() / "tools" / "ghidra_12.2_PUBLIC")))
GHIDRA_BIN = GHIDRA_HOME / "support" / "analyzeHeadless"

# SiFli header constants (shared with scripts/extract_firmware.py).
MAGIC = b"\xad\xef\xcd\xaf"
HEADER_SIZE = 0xA8
OFF_IMAGE0_SIZE = 0x0C
OFF_IMAGE1_STORED = 0x1C
OFF_IMAGE1_TOTAL = 0x20

# HCPU: carved from image[0xa8 : 0xa8+image0_size], loaded at 0x20000000.
# The README records the full-body carve (image[0xa8:]) as b863f868…; that
# hash covers HCPU + the LCPU record stream. The HCPU image alone is image0
# and its hash is checked against the extract_firmware.py output.
HCPU_LOAD_BASE = 0x20000000
FULL_BODY_SHA256 = "b863f8685d247a830267bdccd7cc17208d7191bda3fef09b9eb05b27c9f80135"

# LCPU: inflated from the DEFLATE record stream, loaded at 0x12000000.
LCPU_LOAD_BASE = 0x12000000

# LCPU relocation: absolute pointers are stored shifted by 0x26000.
LCPU_SHIFT = 0x26000
LCPU_TOP_ADDR = 0x12600000
LCPU_STORED_MIN = LCPU_LOAD_BASE - LCPU_SHIFT
LCPU_STORED_MAX = LCPU_TOP_ADDR - LCPU_SHIFT

# Ghidra settings.
LANGUAGE = "ARM:LE:32:Cortex"
GHIDRA_MAXMEM = "4096m"  # 4 GB; the 5.5 MB LCPU image OOMs on the default 2 GB.

# LCPU record stream block size (from extract_firmware.py).
BLOCK = 0x2800
MIN_RECORD = 8


def find_package(arg: str | None) -> Path:
    """Resolve the SiFli package: argument, else the known file, else the sole .bin."""
    if arg:
        return Path(arg)
    if PACKAGE_FILE.exists():
        return PACKAGE_FILE
    bins = sorted(FIRMWARE_DIR.glob("*.bin"))
    if len(bins) == 1:
        return bins[0]
    raise SystemExit(
        f"no package found: need {PACKAGE_FILE.relative_to(ROOT)} or one .bin in "
        f"{FIRMWARE_DIR.relative_to(ROOT)}"
    )


def parse_header(data: bytes) -> tuple[int, int, int]:
    """Return (image0_size, image1_stored, image1_total) from the package header."""
    if len(data) < HEADER_SIZE or data[:4] != MAGIC:
        raise SystemExit("not a SiFli package: expected magic ad ef cd af")
    image0_size, image1_stored, image1_total = (
        struct.unpack_from("<I", data, off)[0]
        for off in (OFF_IMAGE0_SIZE, OFF_IMAGE1_STORED, OFF_IMAGE1_TOTAL)
    )
    return image0_size, image1_stored, image1_total


def sha256hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inflate_block(buf: bytes) -> tuple[bytes, int, bool]:
    """Raw-inflate one DEFLATE record; returns (output, bytes consumed, finished)."""
    engine = zlib.decompressobj(-zlib.MAX_WBITS)
    try:
        out = engine.decompress(buf)
    except zlib.error:
        return b"", 0, False
    return out, len(buf) - len(engine.unused_data), engine.eof


def extract_lcpu(data: bytes, start: int, total: int) -> tuple[bytes, int]:
    """Walk the DEFLATE record stream at *start*; return (image, record count).

    The first record is introduced by ``[total][block][complen][uncomplen]``.
    Later records are either ``[uncomplen][deflate]`` or ``[complen][uncomplen]
    [deflate]``; the declared lengths include a 4-byte encoder pad that the
    final record may truncate. Everything must expand to exactly *total* bytes.
    """
    if len(data) - start < 16:
        raise SystemExit(f"truncated LCPU header at {start:#x}")
    declared_total, block, first_len, first_out = struct.unpack_from("<IIII", data, start)
    if declared_total != total:
        raise SystemExit(f"LCPU total mismatch: header {total:#x} != record {declared_total:#x}")
    if block != BLOCK or first_out != BLOCK:
        raise SystemExit(f"unexpected block framing {block:#x}/{first_out:#x}")
    out, _, ok = inflate_block(data[start + 16 : start + 16 + first_len])
    if not ok or len(out) != first_out:
        raise SystemExit("first LCPU record does not inflate to one block")

    image = bytearray(out)
    pos = start + 16 + first_len
    records = 1

    while len(image) < total and pos < len(data):
        if len(data) - pos < MIN_RECORD:
            raise SystemExit(f"truncated LCPU record at {pos:#x}")
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
            raise SystemExit(f"bad LCPU record length {declared:#x} at {pos:#x}")
        out, _, ok = inflate_block(data[pos + 8 :])
        if not ok or len(out) != expected:
            raise SystemExit(f"LCPU record at {pos:#x} does not inflate to {expected:#x}")
        image += out
        records += 1
        pos += 8 + declared

    if len(image) != total:
        raise SystemExit(f"LCPU walk produced {len(image):#x} B, header says {total:#x} B")
    return bytes(image), records


def prepatch_lcpu(data: bytes) -> tuple[bytes, int]:
    """Subtract LCPU_SHIFT from every aligned word in the valid stored range.

    Returns ``(patched, count)`` where *count* is the number of words patched.
    """
    arr = bytearray(data)
    count = 0
    for i in range(0, len(arr) - 3, 4):
        word = struct.unpack_from("<I", arr, i)[0]
        if LCPU_STORED_MIN <= word <= LCPU_STORED_MAX:
            arr[i : i + 4] = struct.pack("<I", word - LCPU_SHIFT)
            count += 1
    return bytes(arr), count


def run_headless(
    project_dir: Path,
    image_path: Path,
    base: int,
    maxmem: str,
    do_analysis: bool,
    pre_scripts: list[str] | None = None,
    script_path: Path | None = None,
) -> int:
    """Invoke Ghidra ``analyzeHeadless`` for one image; return the exit code.

    ``project_dir`` is the Ghidra project directory; its parent is the project
    location and its basename is the project name. ``pre_scripts`` run before
    auto-analysis (they can toggle analyzers); ``script_path`` is where Ghidra
    looks them up.
    """
    GHIDRA_PROJECTS.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(GHIDRA_BIN),
        str(project_dir.parent),
        project_dir.name,
        "-import",
        str(image_path),
        "-loader",
        "BinaryLoader",
        "-loader-baseAddr",
        f"0x{base:x}",
        "-processor",
        LANGUAGE,
        "-overwrite",
    ]
    if pre_scripts and script_path is not None:
        cmd += ["-scriptPath", str(script_path)]
        for name in pre_scripts:
            cmd += ["-preScript", name]
    if not do_analysis:
        cmd.append("-noanalysis")

    env = os.environ.copy()
    env["GHIDRA_HEADLESS_MAXMEM"] = maxmem

    mode = "auto-analysis" if do_analysis else "import-only"
    print(f"  {mode}: {' '.join(cmd)}")
    return subprocess.run(cmd, env=env, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "package", nargs="?", default=None, help="SiFli package .bin (default: secrets/firmware)"
    )
    parser.add_argument(
        "--out", default=str(EXTRACTED_DIR), help="output directory for carved images"
    )
    parser.add_argument(
        "--lcpu-patch",
        action="store_true",
        help="Pre-patch the LCPU image (subtract 0x26000 from absolute pointers)",
    )
    parser.add_argument(
        "--maxmem", default=GHIDRA_MAXMEM, help=f"Headless heap (default: {GHIDRA_MAXMEM})"
    )
    parser.add_argument(
        "--only",
        choices=("both", "hcpu", "lcpu"),
        default="both",
        help="Import only one image (default: both)",
    )
    parser.add_argument(
        "--no-analysis",
        action="store_true",
        help="Skip auto-analysis (import-only, for a quick smoke test)",
    )
    parser.add_argument(
        "--script-path",
        default=str(GHIDRA_DIR / "scripts"),
        help="Ghidra script directory for --pre-script (default: secrets/ghidra/scripts)",
    )
    parser.add_argument(
        "--pre-script",
        action="append",
        default=[],
        metavar="NAME",
        help="Ghidra script to run before auto-analysis (repeatable)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    pkg = find_package(args.package)
    pkg_data = pkg.read_bytes()
    print(f"package  {pkg} ({len(pkg_data):,} B)")

    image0_size, _, image1_total = parse_header(pkg_data)

    # --- HCPU: image0, carved after the 0xa8 header ---
    body = pkg_data[HEADER_SIZE:]
    body_sha = sha256hex(body)
    if body_sha != FULL_BODY_SHA256:
        print(f"  WARNING: full-body sha256 {body_sha} != README {FULL_BODY_SHA256}")
    else:
        print(f"body     sha256={body_sha} (matches README carve)")

    hcpu = pkg_data[HEADER_SIZE : HEADER_SIZE + image0_size]
    if len(hcpu) != image0_size:
        raise SystemExit(f"short HCPU carve: {len(hcpu):,} != {image0_size:,}")
    sp, reset = struct.unpack_from("<II", hcpu)
    hcpu_sha = sha256hex(hcpu)
    print(f"hcpu     {len(hcpu):,} B  SP={sp:#x} reset={reset:#08x}  sha256={hcpu_sha}")
    hcpu_path = out_dir / "hcpu_import.bin"
    hcpu_path.write_bytes(hcpu)

    # --- LCPU: inflate the record stream that follows image0 ---
    lcpu, records = extract_lcpu(pkg_data, HEADER_SIZE + image0_size, image1_total)
    sp, reset = struct.unpack_from("<II", lcpu)
    print(f"lcpu     {records} records -> {len(lcpu):,} B  SP={sp:#x} reset={reset:#08x}")

    lcpu_count = 0
    if args.lcpu_patch:
        lcpu, lcpu_count = prepatch_lcpu(lcpu)
        lcpu_path = out_dir / "lcpu_patched_import.bin"
        print(f"patch    {lcpu_count:,} words ({LCPU_SHIFT:#x}) -> {lcpu_path.name}")
    else:
        lcpu_path = out_dir / "lcpu_import.bin"
        print("patch    skipped (pass --lcpu-patch to relocate)")
    lcpu_path.write_bytes(lcpu)

    # --- Headless imports ---
    print(f"\nGhidra    {GHIDRA_BIN}")
    print(f"language  {LANGUAGE}  maxmem {args.maxmem}")

    hcpu_proj = GHIDRA_PROJECTS / "hcpu"
    lcpu_proj = GHIDRA_PROJECTS / "lcpu"

    rc_hcpu = 0
    rc_lcpu = 0

    if args.only in ("both", "hcpu"):
        print("\n--- HCPU ---")
        rc_hcpu = run_headless(
            hcpu_proj,
            hcpu_path,
            HCPU_LOAD_BASE,
            args.maxmem,
            not args.no_analysis,
            args.pre_script,
            Path(args.script_path),
        )
        print(f"HCPU import {'OK' if rc_hcpu == 0 else f'FAILED (exit {rc_hcpu})'}")

    if args.only in ("both", "lcpu"):
        print("\n--- LCPU ---")
        rc_lcpu = run_headless(
            lcpu_proj,
            lcpu_path,
            LCPU_LOAD_BASE,
            args.maxmem,
            not args.no_analysis,
            args.pre_script,
            Path(args.script_path),
        )
        print(f"LCPU import {'OK' if rc_lcpu == 0 else f'FAILED (exit {rc_lcpu})'}")

    # --- Record what was produced ---
    # With --only, keep the other image's block from the previous summary
    # instead of writing nulls over a verified import.
    summary_path = GHIDRA_DIR / "import_summary.json"
    previous = json.loads(summary_path.read_text()) if summary_path.exists() else {}

    hcpu_block = (
        {
            "source": "image0 (header stripped)",
            "image": str(hcpu_path.relative_to(ROOT)),
            "bytes": len(hcpu),
            "base": f"0x{HCPU_LOAD_BASE:x}",
            "sha256": hcpu_sha,
            "project": str(hcpu_proj.relative_to(ROOT)) if rc_hcpu == 0 else None,
            "exit": rc_hcpu,
        }
        if args.only in ("both", "hcpu")
        else previous.get("hcpu", {})
    )
    lcpu_block = (
        {
            "source": "image1 (DEFLATE record stream)",
            "image": str(lcpu_path.relative_to(ROOT)),
            "bytes": len(lcpu),
            "records": records,
            "base": f"0x{LCPU_LOAD_BASE:x}",
            "patched": args.lcpu_patch,
            "patched_words": lcpu_count,
            "project": str(lcpu_proj.relative_to(ROOT)) if rc_lcpu == 0 else None,
            "exit": rc_lcpu,
        }
        if args.only in ("both", "lcpu")
        else previous.get("lcpu", {})
    )
    summary = {
        "language": LANGUAGE,
        "maxmem": args.maxmem,
        "hcpu": hcpu_block,
        "lcpu": lcpu_block,
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(f"\nsummary  {summary_path.relative_to(ROOT)}")

    return 0 if rc_hcpu == 0 and rc_lcpu == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
