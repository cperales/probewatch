# Documentation Index

Load only what the task needs: these pages are the long-form reference, `AGENTS.md` is the
short contract. `make sizes` tracks their cost (~3.8 bytes/token).

| Document | Size | Description |
|---|---|---|
| [overview.md](overview.md) | 4 KB | Project overview, capabilities, architecture diagram |
| [setup.md](setup.md) | 4 KB | Bootstrap, dependencies, environment, troubleshooting |
| [scripts.md](scripts.md) | 8 KB | Every script: purpose, arguments, usage examples |
| [architecture.md](architecture.md) | 7 KB | `src/xiaomi_client.py` layers, crypto, protobuf bindings |
| [protocol.md](protocol.md) | 8 KB | SPP v2 frame format, auth flow, encryption, command types |
| [commands.md](commands.md) | 8 KB | Command ids from the app: system, settings, notifications, health |
| [commands-internal.md](commands-internal.md) | 5 KB | Command ids: bind, NFC, eSIM, media, apps, mass channel |
| [channels.md](channels.md) | 7 KB | Channels 2 and 5: capture method, trigger matrix, analysis |
| [apk-analysis.md](apk-analysis.md) | 7 KB | Official app: provenance, L1 ARQ, full channel table, crypto |
| [ota.md](ota.md) | 6 KB | Official app's firmware update: version check, download, channel-6 protocol |
| [firmware.md](firmware.md) | 7 KB | The watch package: two images (HCPU/LCPU), unpacking, DFU, `ota_type` |
| [lcpu.md](lcpu.md) | 5 KB | LCPU firmware: SPP/protobuf/mass code, load map, one probe |
| [audio.md](audio.md) | 5 KB | HFP audio, SCO quirks, verification, workarounds |

## Sources

Fact pages tag where each claim comes from. A page names its default source once under its
title ("Source: [apk 9.8.348i] unless tagged"); only lines that differ carry a tag, and tables
use a `Source` column. `make lint` checks the syntax.

| Tag | Meaning |
|---|---|
| `[hw 2.2.111 2026-11-24]` | measured on the watch (firmware, date) |
| `[apk 9.8.348i]` | read from the Mi Fitness APK, static analysis |
| `[fw 2.2.111]` | read from the firmware image, static analysis |
| `[gb]` | from Gadgetbridge or the vendored `.proto` files |
| `[inferred]` | reasoned, not confirmed |

When a newer firmware changes a result, keep the old line with its own tag: the difference is
a finding too.

## Quick links

- **Getting started**: [setup.md](setup.md) → [scripts.md](scripts.md)
- **Understanding the protocol**: [protocol.md](protocol.md) → [architecture.md](architecture.md) → [apk-analysis.md](apk-analysis.md) → [commands.md](commands.md) → [ota.md](ota.md) → [firmware.md](firmware.md) → [lcpu.md](lcpu.md)
- **Audio troubleshooting**: [audio.md](audio.md)
- **Device reference** (Spanish): [DETAILS.md](../DETAILS.md)
