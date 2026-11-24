# Documentation Index

Load only what the task needs: these pages are the long-form reference, `AGENTS.md` is the
short contract. `make sizes` tracks their cost (~3.8 bytes/token).

| Document | Size | Description |
|---|---|---|
| [overview.md](overview.md) | 4 KB | Project overview, capabilities, architecture diagram |
| [setup.md](setup.md) | 4 KB | Bootstrap, dependencies, environment, troubleshooting |
| [scripts.md](scripts.md) | 5 KB | Every script: purpose, arguments, usage examples |
| [architecture.md](architecture.md) | 7 KB | `src/xiaomi_client.py` layers, crypto, protobuf bindings |
| [protocol.md](protocol.md) | 8 KB | SPP v2 frame format, auth flow, encryption, command types |
| [commands.md](commands.md) | 8 KB | Command ids from the app: system, settings, notifications, health |
| [commands-internal.md](commands-internal.md) | 4 KB | Command ids: bind, NFC, eSIM, media, apps, mass channel |
| [channels.md](channels.md) | 5 KB | Channels 2 and 5: capture method, trigger matrix, analysis |
| [apk-analysis.md](apk-analysis.md) | 7 KB | Official app: provenance, L1 ARQ, full channel table, crypto |
| [ota.md](ota.md) | 5 KB | Official app's firmware update: version check, download, channel-6 protocol |
| [firmware.md](firmware.md) | 7 KB | The watch package: two images (HCPU/LCPU), unpacking, DFU, `ota_type` |
| [lcpu.md](lcpu.md) | 5 KB | LCPU firmware: SPP/protobuf/mass code, load map, one probe |
| [audio.md](audio.md) | 5 KB | HFP audio, SCO quirks, verification, workarounds |

## Quick links

- **Getting started**: [setup.md](setup.md) → [scripts.md](scripts.md)
- **Understanding the protocol**: [protocol.md](protocol.md) → [architecture.md](architecture.md) → [apk-analysis.md](apk-analysis.md) → [commands.md](commands.md) → [ota.md](ota.md) → [firmware.md](firmware.md) → [lcpu.md](lcpu.md)
- **Audio troubleshooting**: [audio.md](audio.md)
- **Device reference** (Spanish): [DETAILS.md](../DETAILS.md)
