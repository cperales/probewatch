"""Pair + trust the watch with BlueZ (handles the numeric-comparison passkey).

Put the watch in pairing mode first (Ajustes -> Conectar teléfono nuevo),
or use --direct if the watch is already bound to Mi Fitness (DON'T reset it then:
that would invalidate the auth key).
When the 6-digit code shows on the watch, it must match the one printed here;
then tap ✓ on the watch.
Usage: uv run python src/pair_watch.py [MAC] [--timeout N]
"""

import argparse
import subprocess
import sys

import pexpect

from watch_secrets import resolve_mac


def main(mac: str, timeout: int, direct: bool = False) -> int:
    bt = pexpect.spawn("bluetoothctl", encoding="utf-8", timeout=timeout)
    bt.logfile_read = sys.stdout

    def cmd(c: str):
        bt.sendline(c)

    cmd("power on")
    cmd("agent off")
    cmd("agent KeyboardDisplay")
    cmd("default-agent")
    if direct:
        # Watch is bound to a phone: hidden from scans but still answers pages.
        # A direct SDP query makes BlueZ learn the device without discovery.
        print(f"Direct mode: SDP query to {mac} ...")
        r = subprocess.run(["sdptool", "browse", mac], capture_output=True, text=True, timeout=30)
        if "Service Name" not in r.stdout:
            print("\n!! Watch did not answer a direct connection.")
            return 1
    else:
        cmd(f"remove {mac}")  # drop any stale/half-done bond
        bt.expect(r"Device has been removed|not available|Failed to remove", timeout=10)
        cmd("scan on")
        try:
            # Only a genuine discovery event: "[NEW] Device <mac>" or an RSSI update.
            # ("\S*" skips the colour codes bluetoothctl puts inside the brackets;
            #  "[DEL] Device <mac> ..." from the remove above must NOT match.)
            bt.expect(rf"NEW\S*\] Device {mac}|Device {mac} RSSI", timeout=timeout)
        except pexpect.TIMEOUT:
            print("\n!! Watch not seen. Is it in 'Conectar teléfono nuevo' mode?")
            return 1
        # pairing while discovery is still running is fine; stop it afterwards
    cmd(f"pair {mac}")

    passkey = None
    while True:
        i = bt.expect(
            [
                r"Confirm passkey (\d+)",
                r"Request confirmation",
                r"Authorize service",
                r"Pairing successful",
                r"Failed to pair: (\S+)",
                r"Device \S+ not available",
                r"Enter passkey",
                pexpect.TIMEOUT,
            ],
            timeout=timeout,
        )
        if i == 0:
            passkey = bt.match.group(1)
            print(f"\n>>> PASSKEY {passkey}: tap ✓ on the watch if it shows the same code <<<")
            cmd("yes")
        elif i == 1:
            pass  # passkey line follows
        elif i == 2:
            cmd("yes")
        elif i == 3:
            break
        elif i == 4:
            print(f"\n!! Pairing failed: {bt.match.group(1)}")
            return 2
        elif i == 5:
            print("\n!! BlueZ lost the device before pairing.")
            return 5
        elif i == 6:
            print("\n!! Watch asked for a typed passkey; not supported by this script.")
            return 3
        else:
            print("\n!! Timed out waiting for pairing.")
            return 4

    cmd("scan off")
    cmd(f"trust {mac}")
    cmd(f"connect {mac}")
    try:
        bt.expect([r"Connection successful", r"Connected: yes"], timeout=30)
    except pexpect.TIMEOUT:
        print("\n(connect did not confirm; may still be fine for BLE)")
    cmd(f"info {mac}")
    bt.expect(r"Modalias.*\r\n", timeout=5)
    cmd("quit")
    bt.expect(pexpect.EOF, timeout=10)
    print(f"\n=== Paired and trusted {mac} (passkey {passkey}) ===")
    return 0


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "mac", nargs="?", default=None, help="watch MAC (default: secrets/device.md or $WATCH_MAC)"
    )
    p.add_argument("--timeout", type=int, default=60)
    p.add_argument(
        "--direct",
        action="store_true",
        help="pair by MAC without scanning (watch already bound to a phone)",
    )
    a = p.parse_args()
    sys.exit(main(resolve_mac(a.mac), a.timeout, a.direct))
