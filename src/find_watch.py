"""Find the watch even if it advertises with a random/private address.

Prints every BLE advertisement with full data and flags Xiaomi-looking ones
(service UUID 0xFE95, Xiaomi company IDs, or 'Redmi'/'Xiaomi'/'Watch' in name).
Usage: uv run python src/find_watch.py [--timeout N]
"""

import argparse
import asyncio

from bleak import BleakScanner

XIAOMI_UUID_FRAGMENTS = ("fe95", "fee0", "fee1")
XIAOMI_COMPANY_IDS = {0x038F: "Xiaomi", 0x0157: "Anhui Huami", 0x0B48: "Xiaomi (alt)"}
NAME_HINTS = ("redmi", "xiaomi", "watch", "mi ")

seen = {}


def is_xiaomi(dev, adv) -> list[str]:
    reasons = []
    name = (adv.local_name or dev.name or "").lower()
    if any(h in name for h in NAME_HINTS):
        reasons.append(f"name '{adv.local_name or dev.name}'")
    for u in list(adv.service_uuids) + list(adv.service_data):
        if any(f in u.lower()[:8] for f in XIAOMI_UUID_FRAGMENTS):
            reasons.append(f"uuid {u}")
    for cid in adv.manufacturer_data:
        if cid in XIAOMI_COMPANY_IDS:
            reasons.append(f"company {XIAOMI_COMPANY_IDS[cid]} (0x{cid:04x})")
    return reasons


def cb(dev, adv):
    seen[dev.address] = (dev, adv)


async def main(timeout: float):
    print(f"Scanning {timeout:.0f}s (active scan) ...")
    async with BleakScanner(cb, scanning_mode="active"):
        await asyncio.sleep(timeout)
    for addr, (dev, adv) in sorted(seen.items(), key=lambda x: -x[1][1].rssi):
        reasons = is_xiaomi(dev, adv)
        flag = "  <== POSSIBLE WATCH: " + "; ".join(reasons) if reasons else ""
        print(f"\n{addr} rssi={adv.rssi} name={adv.local_name or dev.name}{flag}")
        if adv.service_uuids:
            print("   uuids:", adv.service_uuids)
        if adv.manufacturer_data:
            print("   mfr:", {f"0x{k:04x}": v.hex() for k, v in adv.manufacturer_data.items()})
        if adv.service_data:
            print("   svc_data:", {k: v.hex() for k, v in adv.service_data.items()})


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--timeout", type=float, default=30)
    asyncio.run(main(p.parse_args().timeout))
