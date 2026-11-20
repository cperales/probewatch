"""List every BLE advertisement, marking the target watch from secrets/device.md.

Usage: uv run python src/scan.py
"""

import asyncio

from bleak import BleakScanner

from watch_secrets import default_mac

TARGET = default_mac()  # empty when secrets/device.md is absent: list everything


async def main():
    found = await BleakScanner.discover(timeout=15, return_adv=True)
    for addr, (dev, adv) in sorted(found.items(), key=lambda x: -x[1][1].rssi):
        mark = "  <== TARGET" if TARGET and addr.upper() == TARGET else ""
        print(f"{addr} rssi={adv.rssi} name={adv.local_name or dev.name}{mark}")
        if TARGET and addr.upper() == TARGET:
            print("   service_uuids:", adv.service_uuids)
            print("   manufacturer_data:", {k: v.hex() for k, v in adv.manufacturer_data.items()})
            print("   service_data:", {k: v.hex() for k, v in adv.service_data.items()})
            print("   tx_power:", adv.tx_power)


if __name__ == "__main__":
    asyncio.run(main())
