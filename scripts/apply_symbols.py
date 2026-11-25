#!/usr/bin/env python3
"""Apply the Ghidra symbol map to a REA session.

Reads ``secrets/ghidra/symbols.json`` and prints
``set_address_name(image, addr, name)`` commands for
every symbol with a non-null entry.

Usage:
    uv run python scripts/apply_symbols.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SYMBOLS_JSON = ROOT / "secrets" / "ghidra" / "symbols.json"


def load_symbols(path: Path) -> dict:
    with path.open() as f:
        return json.load(f)


def apply(data: dict) -> None:
    """Print set_address_name commands for each symbol."""
    images = data.get("images", {})
    for img_key in ("hcpu", "lcpu"):
        img = images.get(img_key)
        if not img:
            continue
        symbols = img.get("symbols", [])
        for s in symbols:
            entry = s.get("entry")
            if entry is None:
                continue
            # Convert hex string to int
            if isinstance(entry, str):
                addr = int(entry, 16)
            else:
                addr = entry
            print(f"set_address_name({img_key!r}, 0x{addr:x}, {s['name']!r})")


if __name__ == "__main__":
    data = load_symbols(SYMBOLS_JSON)
    apply(data)

