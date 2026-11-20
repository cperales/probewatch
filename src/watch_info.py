"""Connect to the Redmi Watch 5 Active over BLE and read everything readable.

Usage:  uv run python src/watch_info.py [MAC] [--scan-timeout N]
"""

import argparse
import asyncio

from bleak import BleakClient, BleakScanner

from watch_secrets import resolve_mac

# Standard SIG characteristics worth decoding nicely
STRING_CHARS = {
    "00002a00-0000-1000-8000-00805f9b34fb": "Device Name",
    "00002a24-0000-1000-8000-00805f9b34fb": "Model Number",
    "00002a25-0000-1000-8000-00805f9b34fb": "Serial Number",
    "00002a26-0000-1000-8000-00805f9b34fb": "Firmware Revision",
    "00002a27-0000-1000-8000-00805f9b34fb": "Hardware Revision",
    "00002a28-0000-1000-8000-00805f9b34fb": "Software Revision",
    "00002a29-0000-1000-8000-00805f9b34fb": "Manufacturer Name",
}
BATTERY_LEVEL = "00002a19-0000-1000-8000-00805f9b34fb"
PNP_ID = "00002a50-0000-1000-8000-00805f9b34fb"
HEART_RATE_MEAS = "00002a37-0000-1000-8000-00805f9b34fb"


def fmt(raw: bytes) -> str:
    try:
        txt = raw.decode("utf-8")
        if txt.isprintable():
            return f'"{txt}"  (hex {raw.hex()})'
    except UnicodeDecodeError:
        pass
    return raw.hex()


async def main(mac: str, scan_timeout: float) -> None:
    print(f"Scanning up to {scan_timeout:.0f}s for {mac} ...")
    device = await BleakScanner.find_device_by_address(mac, timeout=scan_timeout)
    if device is None:
        print(
            "\nWatch not found. It is probably connected to the phone (Mi Fitness),\n"
            "so it stops advertising. Turn off Bluetooth on the phone (or unpair the\n"
            "watch), keep the watch screen awake near this PC, and run again."
        )
        return

    print(f"Found: {device.name} ({device.address})")
    async with BleakClient(device, timeout=30) as client:
        print(f"Connected: {client.is_connected}   MTU: {client.mtu_size}\n")
        summary = {}

        for service in client.services:
            print(f"[Service] {service.uuid}  {service.description}")
            for ch in service.characteristics:
                props = ",".join(ch.properties)
                line = f"   [Char] {ch.uuid}  {ch.description}  ({props})"
                if "read" in ch.properties:
                    try:
                        raw = bytes(await client.read_gatt_char(ch))
                        line += f"\n          value: {fmt(raw)}"
                        if ch.uuid in STRING_CHARS:
                            summary[STRING_CHARS[ch.uuid]] = raw.decode(errors="replace")
                        elif ch.uuid == BATTERY_LEVEL and raw:
                            summary["Battery"] = f"{raw[0]} %"
                        elif ch.uuid == PNP_ID and len(raw) >= 7:
                            summary["PnP ID"] = (
                                f"vendor=0x{int.from_bytes(raw[1:3], 'little'):04x} "
                                f"product=0x{int.from_bytes(raw[3:5], 'little'):04x} "
                                f"version=0x{int.from_bytes(raw[5:7], 'little'):04x}"
                            )
                    except Exception as e:  # noqa: BLE001
                        line += f"\n          read error: {e}"
                print(line)
                for d in ch.descriptors:
                    print(f"      [Desc] {d.uuid}  {d.description}")

        # Try a few seconds of heart-rate notifications if exposed
        if any(c.uuid == HEART_RATE_MEAS for s in client.services for c in s.characteristics):
            print("\nListening to Heart Rate Measurement for 10s ...")

            def on_hr(_, data: bytearray):
                hr = int.from_bytes(data[1:3], "little") if data[0] & 1 else data[1]
                print(f"   HR: {hr} bpm")
                summary["Heart rate (last)"] = f"{hr} bpm"

            try:
                await client.start_notify(HEART_RATE_MEAS, on_hr)
                await asyncio.sleep(10)
                await client.stop_notify(HEART_RATE_MEAS)
            except Exception as e:  # noqa: BLE001
                print(f"   notify error: {e}")

        print("\n=== Summary ===")
        for k, v in summary.items():
            print(f"{k:20s}: {v}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "mac", nargs="?", default=None, help="watch MAC (default: secrets/device.md or $WATCH_MAC)"
    )
    p.add_argument("--scan-timeout", type=float, default=20)
    a = p.parse_args()
    asyncio.run(main(resolve_mac(a.mac), a.scan_timeout))
