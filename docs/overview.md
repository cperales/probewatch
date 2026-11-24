# Project Overview

Linux-side probes for the **Redmi Watch 5 Active** (model `M2351W1`) that discover, pair,
query, and stream audio from the watch over Bluetooth — BLE, RFCOMM, L2CAP, and a full Python
port of Xiaomi's proprietary SPP v2 protocol. Device identifiers (MAC, serial) are local only,
in the git-ignored `secrets/` directory.

## What this project does

| Capability | How |
|---|---|
| **BLE discovery** | Scan advertisements, flag Xiaomi devices by UUID/company ID/name |
| **BlueZ pairing** | Interactive pairing/trust via `bluetoothctl` (with `--direct` for hidden watches) |
| **GATT enumeration** | Connect over BLE, list services/characteristics, read values, subscribe to heart-rate |
| **SPP v2 protocol** | Full handshake: version probe → session → HKDF auth → encrypted protobuf queries |
| **Audio (HFP)** | Play beeps, record from the watch mic, loopback — all over PipeWire + BlueZ SCO |
| **Protocol probing** | Passive RFCOMM byte logger, read-only AVDTP L2CAP capabilities probe |

## Architecture at a glance

```
┌────────────────────────────────────────────────────────────┐
│ src/                                                       │
│   find_watch.py      BLE active scan, flags Xiaomi devices │
│   scan.py            minimal BLE scan                      │
│   watch_info.py      GATT read + heart-rate subscription   │
│   pair_watch.py      BlueZ pairing/trust                   │
│   spp_probe.py       passive RFCOMM byte logger            │
│   a2dp_probe.py      read-only AVDTP/L2CAP probe           │
│   xiaomi_client.py   SPP v2 handshake, auth, queries       │
│   probe_extra.py     extended query set                    │
│   audio_test.py      HFP beep / record / loopback          │
│   watch_secrets.py   MAC resolution from secrets/device.md │
│   xiaomi_pb/         generated bindings (git-ignored)      │
├────────────────────────────────────────────────────────────┤
│ proto/               vendored .proto files (Gadgetbridge)  │
│ secrets/             auth_key.txt, device.md (git-ignored) │
│ recordings/          WAV files from audio_test.py          │
└────────────────────────────────────────────────────────────┘
```

## Key constraints

- **One client at a time**: the watch connects to only one Bluetooth client. Phone Bluetooth
  must be off for scripts to see the watch.
- **Auth key is persistent**: resetting/unbinding the watch from Mi Fitness regenerates the
  key and invalidates `secrets/auth_key.txt`. Use `--direct` pairing to avoid this.
- **No build system**: this is a collection of standalone Python scripts. Verification means
  running them against the physical watch.
- **System Python required**: `socket.AF_BLUETOOTH` is only available in the distro CPython
  build. `pyproject.toml` enforces `python-preference = "system"`.

## Licensing

This repository is **AGPL-3.0-or-later**. `proto/` is vendored from
[Gadgetbridge](https://codeberg.org/Freeyourgadget/Gadgetbridge) (AGPL-3.0) and
`src/xiaomi_client.py` is a port of Gadgetbridge's Java SPP/auth classes. Treat new
protocol code as an AGPL-3.0 derivative.

This is an unofficial hobby project, provided as-is: see the Legal section in
[README.md](../README.md#legal). Running it may void the watch's warranty or breach Mi Fitness
terms of service.

## Reference documents

| Document | Contents |
|---|---|
| [setup.md](setup.md) | Bootstrap, dependencies, environment |
| [scripts.md](scripts.md) | Every script: purpose, arguments, examples |
| [architecture.md](architecture.md) | `xiaomi_client.py` layers, crypto, framing |
| [protocol.md](protocol.md) | SPP v2 protocol spec, frame format, auth flow |
| [audio.md](audio.md) | HFP audio subsystem, SCO quirks, measurements |
| [device.md](device.md) | The watch: identity, firmware history, SDP services |
