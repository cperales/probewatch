"""Open the watch's Serial Port (RFCOMM) channel and log raw bytes it sends.

Passive by default: sends nothing, just listens. Requires the watch to be
paired with this PC first (src/pair_watch.py).

Needs a Python built with Bluetooth support (socket.AF_BLUETOOTH). The distro
/usr/bin/python3 has it; CPython builds downloaded by uv do not, which is why the
venv is created from the system interpreter (see README "Setup").

Usage: uv run python src/spp_probe.py [MAC] [--channel 2] [--seconds 15]
"""

import argparse
import socket
import time

from watch_secrets import resolve_mac


def main(mac: str, channel: int, seconds: float) -> None:
    s = socket.socket(socket.AF_BLUETOOTH, socket.SOCK_STREAM, socket.BTPROTO_RFCOMM)
    s.settimeout(20)
    print(f"Connecting RFCOMM {mac} channel {channel} ...")
    s.connect((mac, channel))
    print("Connected. Listening (nothing is sent) ...")
    s.settimeout(1)
    end = time.time() + seconds
    total = 0
    while time.time() < end:
        try:
            data = s.recv(4096)
        except TimeoutError:
            continue
        if not data:
            print("Watch closed the channel.")
            break
        total += len(data)
        print(f"[{time.strftime('%H:%M:%S')}] {len(data)} bytes: {data.hex(' ')}")
    s.close()
    print(f"Done. {total} bytes received.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "mac", nargs="?", default=None, help="watch MAC (default: secrets/device.md or $WATCH_MAC)"
    )
    p.add_argument("--channel", type=int, default=2)
    p.add_argument("--seconds", type=float, default=15)
    a = p.parse_args()
    main(resolve_mac(a.mac), a.channel, a.seconds)
