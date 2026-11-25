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
    # Load HCPU: either the merged layout (images.hcpu) or the original
    # HCPU-only file (image + symbols). Running this twice must be a no-op.
    with HCPU_JSON.open() as f:
        hcpu_doc = json.load(f)
    if "images" in hcpu_doc:
        hcpu = hcpu_doc["images"]["hcpu"]
    else:
        hcpu = {**hcpu_doc["image"], "symbols": hcpu_doc["symbols"]}

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
        "method": hcpu_doc.get("method", ""),
        "provider_caveat": hcpu_doc.get("provider_caveat", ""),
        "images": {"hcpu": hcpu, "lcpu": lcpu},
    }

    MERGED_JSON.write_text(json.dumps(merged, indent=2) + "\n")
    hcpu_count = len(hcpu["symbols"])
    lcpu_count = len(lcpu["symbols"])
    print(f"Merged {hcpu_count} HCPU + {lcpu_count} LCPU symbols -> {MERGED_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
