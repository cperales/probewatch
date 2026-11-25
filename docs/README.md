# Documentation Index

Load only what the task needs: these pages are the long-form reference, `AGENTS.md` is the
short contract. `make sizes` tracks their cost (~3.8 bytes/token).

| Document | Size | Description |
|---|---|---|
| [overview.md](overview.md) | 3 KB | Project overview, capabilities, script map |
| [setup.md](setup.md) | 4 KB | Bootstrap, dependencies, environment, troubleshooting |
| [scripts.md](scripts.md) | 8 KB | Every script: purpose, arguments, usage examples |
| [device.md](device.md) | 4 KB | The watch: identity, firmware history, Bluetooth identity, SDP services |
| [architecture.md](architecture.md) | 6 KB | `src/xiaomi_client.py`: layers, functions, protobuf bindings |
| [protocol.md](protocol.md) | 5 KB | Wire format: L1 frame, session start, the channel/opcode table, v1 probe |
| [session.md](session.md) | 5 KB | Handshake, auth, HKDF keys, AES-CTR/CCM, session lifetime |
| [arq.md](arq.md) | 3 KB | L1 ACKs, windows and retransmission; app constants and measurements |
| [commands.md](commands.md) | 4 KB | Command ids from the app: system, settings, watchfaces |
| [commands-health.md](commands-health.md) | 4 KB | Command ids: notifications, health, alarms, contacts |
| [commands-internal.md](commands-internal.md) | 5 KB | Command ids: bind, NFC, eSIM, media, apps, mass channel |
| [commands-tested.md](commands-tested.md) | 6 KB | What each command returned on the watch: reads, writes, live stream |
| [channels.md](channels.md) | 7 KB | Channels 2 and 5: capture method, trigger matrix, analysis, findings |
| [apk-analysis.md](apk-analysis.md) | 4 KB | Official app: provenance, where the protocol lives, what it gave |
| [ota.md](ota.md) | 6 KB | Official app's firmware update: version check, download, channel-6 protocol |
| [firmware.md](firmware.md) | 8 KB | The watch package: two images (HCPU/LCPU), unpacking, DFU, load map |
| [firmware-symbols.md](firmware-symbols.md) | 7 KB | HCPU symbol map: method, confidence rules, DFU/FAL/FlashDB cluster |
| [firmware-symbols-kernel.md](firmware-symbols-kernel.md) | 8 KB | HCPU kernel group: IPC, timers, device framework, BSim cross-check |
| [firmware-symbols-drivers.md](firmware-symbols-drivers.md) | 5 KB | HCPU drivers, serial/I2C, LCD/GPU and logging symbols |
| [firmware-symbols-lcpu.md](firmware-symbols-lcpu.md) | 5 KB | LCPU symbol table: load map, caveat, addresses, call sites |
| [lcpu.md](lcpu.md) | 4 KB | LCPU firmware: SPP/protobuf/mass code, load map, login FSM |
| [audio.md](audio.md) | 6 KB | HFP audio, SCO quirks, verification, workarounds |
| [firmware-upstreams.md](firmware-upstreams.md) | 2 KB | Firmware build bases, published facts and the reuse boundary |

## Sources

Fact pages tag where each claim comes from. A page names its default source once under its
title ("Source: [apk 9.8.348i] unless tagged"); only lines that differ carry a tag, and tables
use a `Source` column. `make lint` checks the syntax.

| Tag | Meaning |
|---|---|
| `[hw 2.2.111 2026-11-24]` | measured on the watch: firmware (`?` if not recorded) and date (of the measurement, or of the commit that first recorded it) |
| `[apk 9.8.348i]` | from the Mi Fitness app: APK static analysis, or its own logs |
| `[fw 2.2.111]` | read from the firmware image, static analysis |
| `[gb]` | from Gadgetbridge or the vendored `.proto` files |
| `[ext <label>]` | from an external source named in the tag; URLs in [External sources](#external-sources) |
| `[inferred]` | reasoned, not confirmed |

When a newer firmware changes a result, keep the old line with its own tag: the difference is
a finding too.

### External sources

| Label | Where |
|---|---|
| `Byterialab` | [xiaomi-smart-watch-research](https://github.com/Byterialab/xiaomi-smart-watch-research) |
| `SiFli-SDK` | [OpenSiFli/SiFli-SDK](https://github.com/OpenSiFli/SiFli-SDK) |

## Quick links

- **Getting started**: [setup.md](setup.md) → [scripts.md](scripts.md)
- **The watch**: [device.md](device.md) → [commands-tested.md](commands-tested.md)
- **Understanding the protocol**: [protocol.md](protocol.md) → [session.md](session.md) → [arq.md](arq.md) → [commands.md](commands.md) → [architecture.md](architecture.md)
- **Sources**: [apk-analysis.md](apk-analysis.md) (the app) → [ota.md](ota.md) → [firmware.md](firmware.md) → [firmware-upstreams.md](firmware-upstreams.md) (upstreams) → [lcpu.md](lcpu.md) (the watch)
- **Audio troubleshooting**: [audio.md](audio.md)
