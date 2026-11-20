"""Resolve this checkout's watch MAC from the git-ignored `secrets/` directory.

`secrets/device.md` holds the identifiers of the local hardware; its `MAC:` line is
the default for every script. Precedence, highest first: MAC given on the command
line, `WATCH_MAC` in the environment, `secrets/device.md`.

Nothing tracked depends on the file: a fresh clone runs and exits with an
instruction instead of picking up someone else's address.
"""

import os
import re
from pathlib import Path

DEVICE_FILE = Path(__file__).resolve().parent.parent / "secrets" / "device.md"
MAC_LINE = re.compile(
    r"^\s*(?:[-*]\s*)?\**MAC\**\s*:\s*`?([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})`?\s*$", re.MULTILINE
)


def default_mac() -> str:
    """MAC from `$WATCH_MAC` or `secrets/device.md`, or "" when neither is set."""
    env = os.environ.get("WATCH_MAC", "").strip()
    if env:
        return env.upper()
    try:
        text = DEVICE_FILE.read_text()
    except OSError:
        return ""
    m = MAC_LINE.search(text)
    return m.group(1).upper() if m else ""


def resolve_mac(value: str | None = None) -> str:
    """Return the MAC to use, or exit with an explanation when there is none."""
    mac = (value or default_mac()).strip()
    if not mac:
        raise SystemExit(
            "no watch MAC: pass it as an argument, set WATCH_MAC, or add "
            "`- MAC: xx:xx:xx:xx:xx:xx` to secrets/device.md"
        )
    return mac
