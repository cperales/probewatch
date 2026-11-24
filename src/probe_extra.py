"""Query additional Xiaomi type/subtype pairs in a single SPP session.

Try the ids here before adding them to the query dict in `xiaomi_client.py`.

Usage: uv run python src/probe_extra.py [MAC] [--key-file PATH]
"""

import argparse
import contextlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from watch_secrets import resolve_mac  # noqa: E402
from xiaomi_client import XiaomiWatch, load_key  # noqa: E402

# Every entry is sent as an empty Command(type, subtype): a status/get request.
# `find-device` is the one with a visible side effect (the watch rings), so it is
# kept last so that running the script past it is always a deliberate choice.
QUERIES = [
    ("camera remote status", 2, 7),
    ("password status", 2, 9),
    ("raise-to-wake", 2, 24),
    ("simple-widgets", 2, 28),
    ("display-items", 2, 29),
    ("dnd-status", 2, 34),
    ("misc-setting-get (dndSync)", 2, 14),
    ("workout-types", 2, 39),
    ("widget-screens", 2, 51),
    ("widget-parts", 2, 53),
    ("device-state-full", 2, 79),
    ("heart-rate-settings", 8, 10),
    ("standing-reminder", 8, 12),
    ("goal-notification", 8, 21),
    ("vitality-score", 8, 35),
    ("real-time-stats", 8, 45),
    ("activity-today", 8, 2),
    ("activity-past", 8, 3),
    ("goals-config", 8, 42),
    ("find-device (rings the watch)", 2, 18),
]


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "mac", nargs="?", default=None, help="watch MAC (default: secrets/device.md or $WATCH_MAC)"
    )
    p.add_argument("--key-file", default=os.path.join(ROOT, "secrets", "auth_key.txt"))
    args = p.parse_args()

    w = XiaomiWatch(resolve_mac(args.mac), 2, load_key(args.key_file))
    try:
        w.connect()
        print("\nextra queries (single session)")
        for name, t, s in QUERIES:
            r = w.request(t, s, timeout=8)
            if r is None:
                print(f"\n--- {name} (type {t}, sub {s}) --- (no answer)")
            else:
                print(f"\n--- {name} (type {t}, sub {s}) ---")
                if r.HasField("system"):
                    print(f"  system: {r.system}")
                if r.HasField("health"):
                    print(f"  health: {r.health}")
                print(f"  full: {r}")
    except Exception as e:
        print(f"\nERROR: {e}")
    finally:
        with contextlib.suppress(Exception):
            w.close()


if __name__ == "__main__":
    main()
