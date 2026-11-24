# Device — Redmi Watch 5 Active

What the watch is: identity, firmware history, Bluetooth identity and SDP services. Local
identifiers (MAC, serial number, Mi Fitness `did`) are in the git-ignored `secrets/device.md`,
never here.

Source: [hw 2.2.110 2026-11-16] unless tagged.

## Identity

| Field | Value | Source |
|---|---|---|
| Name | Redmi Watch 5 Active | |
| Model | `M2351W1` (also what `2/2` reports) | |
| Mi Fitness model | `lchz.watch.n65agl` | |
| MAC, serial, `did` | see `secrets/device.md` (not published) | |
| OS | Xiaomi HyperOS | |
| SoC | SiFli SF32LB5x, dual Cortex-M33: HCPU (RT-Thread app) + LCPU (Bluetooth/SPP stack); exact SKU unconfirmed, see [firmware.md](firmware.md) | [fw 2.2.111] |
| OTA engine | `ota_type = 2`, general update over the mass channel; see [ota.md](ota.md) | [apk 9.8.348i] |

Other watches of the same model may be in radio range: always check the address against
`secrets/device.md`.

## Firmware history

| Version | When | How it was seen |
|---|---|---|
| 2.2.105 | out of the box | on the watch's screen |
| 2.2.110 | 2026-11-16 | read over the protocol (`2/2`); probably installed when the watch was bound to Mi Fitness |
| 2.2.111 | 2026-11-22 | installed by Mi Fitness; read with `2/2` on 2026-11-24 |

Firmware 2.2.111 is the image documented in [firmware.md](firmware.md).

## Bluetooth identity

Source: [hw 2.2.110 2026-11-20], read from the PC.

| Field | Value |
|---|---|
| Bluetooth name | Redmi Watch 5 Active, plus a suffix from the MAC |
| Address type | public |
| Mode | dual: Bluetooth Classic + BLE |
| Device class | `0x280704`: Wearable / Wrist watch (services: Audio, Telephony) |
| Bluetooth chip / stack | SiFli (vendor in the SDP records) |
| PnP / modalias | `bluetooth:v0AC4pB009d011B` (vendor `0x0AC4`, product `0xB009`, version `0x011B`) |
| Pairing | Secure Simple Pairing, numeric comparison (not legacy) |
| Discoverable | only in "Connect new phone" mode; while bound to a phone it does not advertise |

Recheck on 2.2.111 [hw 2.2.111 2026-11-24]: the class, the modalias (`d011B`) and the UUIDs
cached by BlueZ are unchanged. `sdptool` could not reread the records (`browse` returned only
HID and PnP, `records` timed out), so the service table below is still the 2.2.110 one.

## SDP services

Source: [hw 2.2.110 2026-11-20].

| Service | UUID | Transport | Likely use |
|---|---|---|---|
| BTS2 SPPA (Serial Port) | `0x1101` | RFCOMM channel 2 | Xiaomi protocol: data and sync ([protocol.md](protocol.md)) |
| Hands-Free unit | `0x111E` v1.8 | RFCOMM channel 3 | calls through the watch ([audio.md](audio.md)) |
| Advanced Audio (A2DP Source) | `0x110A` v1.4 | L2CAP PSM 25 | audio from the watch |
| AV Remote Controller | `0x110E`/`0x110F` v1.6 | L2CAP PSM 23 | media control of the phone |
| AV Remote Target | `0x110E`/`0x110C` v1.6 | L2CAP PSM 23 | media control |
| HID remote control | `0x1124` | L2CAP PSM 17 | remote button (e.g. camera shutter) |
| PnP Information | `0x1200` | SDP | device identification |
| Xiaomi Inc. (GATT over BR/EDR) | `0xFDAB` | ATT, handles `0x0028`–`0x0030` | Xiaomi service |
| Unknown (GATT over BR/EDR) | `0x3802` | ATT, handles `0x0031`–`0x0034` | vendor service |

## Battery and state readings

| Reading | Source |
|---|---|
| 86 %, charging; last recorded charge 2026-11-16 17:35:34 CET | [hw 2.2.110 2026-11-16] |
| `level: 95 state: 2`; last recorded charge 2026-11-20 16:29:42 CET (`timestampSeconds: 1795188582`); the same 4 watchfaces, Swirl active | [hw 2.2.111 2026-11-24] |

What each command returns is in [commands-tested.md](commands-tested.md).
