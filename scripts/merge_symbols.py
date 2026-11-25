#!/usr/bin/env python3
"""Merge HCPU and LCPU symbol files into a single symbols.json.

Reads ``secrets/ghidra/symbols.json`` (HCPU) and ``secrets/ghidra/lcpu-symbols.json``
(LCPU) and writes a merged file with an ``images`` object containing both.

Usage:
    uv run python scripts/merge_symbols.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HCPU_JSON = ROOT / "secrets" / "ghidra" / "symbols.json"
LCPU_JSON = ROOT / "secrets" / "ghidra" / "lcpu-symbols.json"
MERGED_JSON = ROOT / "secrets" / "ghidra" / "symbols.json"


def main() -> int:
    # Load HCPU (the current symbols.json)
    with HCPU_JSON.open() as f:
        hcpu = json.load(f)

    # Load LCPU
    with LCPU_JSON.open() as f:
        lcpu = json.load(f)

    # Build merged structure
    merged = {
        "_comment": (
            "Symbol map for the Redmi Watch 5 Active (M2351W1) 2.2.111 firmware. "
            "Git-ignored (device artifact). Durable across RE sessions: the "
            "REA/Ghidra project is ephemeral, this file is not. Apply with "
            "apply_symbols.py against a fresh carve. See README.md for the "
            "load map and method."
        ),
        "method": hcpu.get("method", ""),
        "provider_caveat": hcpu.get("provider_caveat", ""),
        "images": {
            "hcpu": {
                "model": hcpu["image"]["model"],
                "firmware": hcpu["image"]["firmware"],
                "source_bin": hcpu["image"]["source_bin"],
                "source_bin_md5": hcpu["image"]["source_bin_md5"],
                "carve": hcpu["image"]["carve"],
                "carved_sha256": hcpu["image"]["carved_sha256"],
                "load_base": hcpu["image"]["load_base"],
                "arch": hcpu["image"]["arch"],
                "vector_table": hcpu["image"]["vector_table"],
                "symbols": hcpu["symbols"],
            },
            "lcpu": {
                "image": lcpu["image"],
                "load_base": lcpu["load_base"],
                "extraction": lcpu["extraction"],
                "relocation": lcpu["relocation"],
                "symbols": lcpu["symbols"],
            },
        },
    }

    MERGED_JSON.write_text(json.dumps(merged, indent=2) + "\n")
    hcpu_count = len(hcpu["symbols"])
    lcpu_count = len(lcpu["symbols"])
    print(f"Merged {hcpu_count} HCPU + {lcpu_count} LCPU symbols -> {MERGED_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
