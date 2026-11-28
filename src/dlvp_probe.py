"""Probe the DLVP GATT service and the debug-port pin switch.

DLVP (Debug Lever Via Protocol) is a SiFli settings protocol that static analysis of the
2.2.111 firmware reports over BLE GATT handles 0xA407-0xA40E, with a setting
`jlink_uart_switch` that re-pins PA18/PA19 between JTAG/SWD (value 1) and debug-UART
(value 0) modes and persists to flash. The service UUIDs are built at runtime, so this
probe discovers the characteristics by handle rather than by UUID.

Read-only by default: it lists the GATT handle map and reads the current value of every
characteristic in the DLVP handle range. `--cycle` additionally writes both modes to the
DLVP characteristic(s) and restores the original value, so the write path can be confirmed
on hardware. It never writes to characteristics outside that range.

Usage:  uv run python src/dlvp_probe.py [MAC] [--scan-timeout N] [--cycle]

Source: [ext Byterialab] — static analysis reports the service at GATT handles
0xA407-0xA40E; this script confirms or refutes that claim on hardware.
"""

import argparse
import asyncio

from bleak import BleakClient, BleakScanner

from watch_secrets import resolve_mac

# DLVP handles reported by static analysis (Byterialab). The UUIDs are dynamic.
DLVP_HANDLE_START = 0xA407
DLVP_HANDLE_END = 0xA40E

# jlink_uart_switch values: 0 = debug UART, 1 = JTAG/SWD (pinmux write at 0x5000307C).
MODE_UART = 0
MODE_JTAG = 1
MODE_NAMES = {MODE_UART: "debug-UART", MODE_JTAG: "JTAG/SWD"}


def in_dlvp_range(handle: int) -> bool:
    """Whether a GATT handle is inside the DLVP service range."""
    return DLVP_HANDLE_START <= handle <= DLVP_HANDLE_END


def format_value(raw: bytes | None) -> str:
    """Render a characteristic value, flagging a 1-byte 0/1 switch value."""
    if raw is None:
        return "(no read)"
    if len(raw) == 1 and raw[0] in MODE_NAMES:
        return f"{raw.hex()} ({MODE_NAMES[raw[0]]})"
    return raw.hex()


async def enumerate_gatt(client: BleakClient) -> list[dict]:
    """Return one dict per characteristic: handle, uuid, properties, service, char."""
    results = []
    for service in client.services:
        for ch in service.characteristics:
            results.append(
                {
                    "handle": ch.handle,
                    "uuid": str(ch.uuid),
                    "properties": ",".join(ch.properties),
                    "service_uuid": str(service.uuid),
                    "char": ch,
                }
            )
    return results


async def read_dlvp_values(client: BleakClient, entries: list[dict]) -> None:
    """Read the current value of each DLVP-range characteristic into its entry."""
    for entry in entries:
        if not in_dlvp_range(entry["handle"]):
            continue
        ch = entry["char"]
        if "read" not in ch.properties:
            continue
        try:
            entry["value"] = bytes(await client.read_gatt_char(ch))
        except Exception as err:  # noqa: BLE001
            entry["read_error"] = str(err)


def report(entries: list[dict]) -> None:
    """Print the GATT handle map, then focus on the DLVP handle range."""
    services: dict[str, list[dict]] = {}
    for entry in entries:
        services.setdefault(entry["service_uuid"], []).append(entry)

    print(f"\n{len(entries)} characteristics across {len(services)} services:")
    for svc_uuid, chars in services.items():
        print(f"\n  Service {svc_uuid} ({len(chars)} chars)")
        for c in sorted(chars, key=lambda x: x["handle"]):
            print(f"    {c['handle']:#06x}  {c['uuid']}  [{c['properties']}]")

    print(f"\n=== DLVP handle range {DLVP_HANDLE_START:#06x}-{DLVP_HANDLE_END:#06x} ===")
    dlvp = [e for e in entries if in_dlvp_range(e["handle"])]
    if not dlvp:
        print("  No characteristic in that range: the DLVP service is not advertised here.")
        return
    for c in sorted(dlvp, key=lambda x: x["handle"]):
        if "read_error" in c:
            shown = f"read error: {c['read_error']}"
        elif "value" in c:
            shown = format_value(c["value"])
        else:
            shown = "(no read property)"
        print(f"  handle {c['handle']:#06x}  {c['uuid']}  [{c['properties']}]  {shown}")


async def cycle_dlvp(client: BleakClient, entries: list[dict]) -> None:
    """Write each jlink_uart_switch mode to the DLVP characteristic(s), then restore."""
    dlvp = [e for e in entries if in_dlvp_range(e["handle"])]
    writable = [
        e
        for e in dlvp
        if "write" in e["char"].properties or "write-without-response" in e["char"].properties
    ]
    if not writable:
        print("\n  No writable characteristic in the DLVP handle range.")
        return

    print("\n=== Write cycle (jlink_uart_switch) ===")
    for entry in sorted(writable, key=lambda x: x["handle"]):
        ch = entry["char"]
        with_response = "write" in ch.properties
        print(f"\n  {entry['uuid']} (handle {entry['handle']:#06x})")
        try:
            original = bytes(await client.read_gatt_char(ch))
            print(f"    original: {format_value(original)}")
        except Exception as err:  # noqa: BLE001
            print(f"    original read error: {err}")
            continue

        for mode in (MODE_UART, MODE_JTAG):
            name = MODE_NAMES[mode]
            try:
                await client.write_gatt_char(ch, bytes([mode]), response=with_response)
                print(f"    write {mode} ({name}) -> OK")
            except Exception as err:  # noqa: BLE001
                print(f"    write {mode} ({name}) -> {err}")
            try:
                back = bytes(await client.read_gatt_char(ch))
                print(f"    read back: {format_value(back)}")
            except Exception as err:  # noqa: BLE001
                print(f"    read back error: {err}")

        try:
            await client.write_gatt_char(ch, original, response=with_response)
            print(f"    restore {format_value(original)} -> OK")
        except Exception as err:  # noqa: BLE001
            print(f"    restore error: {err}")


async def main(mac: str, scan_timeout: float, cycle: bool) -> None:
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
        entries = await enumerate_gatt(client)
        if not entries:
            print(
                "\nNo GATT services discovered. For this dual-mode watch BlueZ may have\n"
                "connected over the classic bearer; force LE with\n"
                "`gatttool -t le --primary` / `gatttool -t le --characteristics`."
            )
        await read_dlvp_values(client, entries)
        report(entries)
        if cycle:
            await cycle_dlvp(client, entries)


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument(
        "mac", nargs="?", default=None, help="watch MAC (default: secrets/device.md or $WATCH_MAC)"
    )
    p.add_argument("--scan-timeout", type=float, default=20)
    p.add_argument(
        "--cycle",
        action="store_true",
        help="write jlink_uart_switch 0 (UART) and 1 (JTAG), then restore the original",
    )
    a = p.parse_args()
    asyncio.run(main(resolve_mac(a.mac), a.scan_timeout, a.cycle))
