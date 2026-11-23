# OTA (HyperOS) updates — what the official app does

How the official app (`com.xiaomi.wearable` 9.8.348i, in `secrets/apk/`) updates the watch.
Everything here is **static** (no APK executed, no watch involved): transport facts are
cross-checked with [apk-analysis.md](apk-analysis.md) and [protocol.md](protocol.md). Legal
framing is [README.md](../README.md#legal).

## The two OTA engines

The app picks an engine from the server product-catalog key `ota_type` (`Product.ota` →
`getOtaMode()`); `util.DeviceSender.startOta()`:

| `ota_type` | Engine | Transport |
|---|---|---|
| `0` | none | — |
| `1` | `HyOtaExecutor` (`OTA_CUSTOM_HY`) | channel 6, bespoke `0x5A` protocol |
| `2` | `GeneralOtaExecutor` / `EcoGeneralOtaExecutor` | mass channel 2/104 file push + a protobuf "prepare" |

`1` is the newer, watch-driven engine. "HY" is the app's internal name; the APK never prints
the word "HyperOS", so that association is an inference from the `OTA_CUSTOM_HY` constant.

> **This watch is `ota_type = 2`.** Mi Fitness logs `productDevice = ota_type 2` for `M2351W1`
> (2026-11-22, `CheckUpdate` tag), so it updates through the general/mass engine. Channel 6 is
> the `ota_type = 1` protocol and `--ota-require` is not answered by this model; the watch
> side is in [firmware.md](firmware.md).

## Version check

Native/Bluetooth watches: read `firmwareVersion` over the SDK, then
`POST https://hlth.io.mi.com/healthapp/device/latest_ver` (headers `locale` and a `Cookie`),
body `{"did","model","platform":"android","app_level","fw_ver","channel":"prod"}` →
`LatestVersion` `{version, md5, url, diffUrl, diffMd5, fullPackageUrl, force, isNeedUpdate}`.
The endpoint is **authenticated**: `VerifyToken` adds
`Cookie: cUserId=…; serviceToken=…` for the `miothealth` service, and `ParameterInterceptor`
appends `locale=…`. Without a logged-in account it answers
`HTTP 401 {"code":2,"message":"auth err"}`.

Huami devices: `POST …/healthapp/huami/ota` with an `OtaUpgradeRequest`
(firmware/resource/font/gps flag+version, hardwareVersion, lang,
`appPlatform=android_phone`) → `OtaUpgradeResult` bundle (firmware, resource, font, gps and
baseResource, each with url/md5/version/length/flag).

`POST …/healthapp/device/bledevice_info {"did","fw_ver"}` reports the installed version back.
`force` triggers a protobuf `Command{type=2, subtype=4}` on channel 1 that makes the watch
show its own "update available" prompt.

## Download

`util.Downloader` (OkHttp): `HEAD` for length, `Range` resume, progress as an `Int` flow.
Target file is `Downloads/<model>/<md5>`: the server MD5 is both the filename and the
integrity check (`MD5Util.getFileMD5(file) == md5`). `diffUrl` is preferred when present.
`scripts/fetch_firmware_url.py` reproduces the check (read-only) and can download the full
image with MD5 verification; it reads the `miothealth` cookie from
`secrets/miot_health_cookie.txt` or `--cookie`. Without the app's login, the simpler route
is to let Mi Fitness download an update and pull the image from
`/sdcard/Android/data/com.xiaomi.wearable/files/Download/<model>/<md5>`.

## The HY transfer (channel 6)

Channel 6 (`CH_OTA`, internal type 105), opcode `OP_WRITE` — **plaintext** (never `OP_WRITE_ENC`).
Each L2 payload is one segment:

```
5A | len BE u16 (= payload + 2) | flag u8 | frameNo u8 | payload | CRC16 BE u16
```

- `flag`: `0` single, `1` first, `2` middle, `3` last (multi-segment reassembly by `frameNo`).
- `CRC16` = CRC-16/ARC over `len ‖ flag ‖ frameNo ‖ payload` (the same table as L1; big-endian
  on the wire). The app does **not** verify it on receive.
- All integers here are **big-endian** — unlike L1's little-endian length.
- `MAX_SEGMENT_DATA_SIZE = 4217`, so a 4 KB page fits one frame.

Inside the payload: `[0A][cmd][args…]` (`SERVICE_ID = 10`).

| Cmd | Name | Dir | Args |
|---|---|---|---|
| `0` | `REQUIRE` | app→watch | none |
| `1` | `START` | app→watch | `fileSize` BE32, `1024` BE32 |
| `2` | `DATA` | both | tx: `pageNo` u8 + bytes; rx: `offset` BE32, `length` BE32, page bitmap |
| `3` | `ERROR` | watch→app | code u8 + UTF-8 description |
| `4` | `RESET` | app→watch | none |
| `5` | `PROGRESS` | watch→app | percent u8 |
| `6` | `SILENT_START` | app→watch | like `START` |
| `7` | `SILENT_PAUSE` | app→watch | none |

The `REQUIRE` reply is 3 bytes: page size `= b0 * 32`, interval `= b1 * 10` ms (parsed then
ignored by the app), timeout `= b2 * 100` ms (5000 ms before the first reply).

## Sequence

```
require (0A 00)                → reply(pageSize, interval, timeout)
start  (0A 01 | size | 1024)   → [0A 06 if silent]
loop:
  data(offset, length, bitmap) → send each page whose bit is 1
                                  (page N+1 only after page N's write callback; pageNo is u8)
  progress(pct)                → pct >= 100 ⇒ reset (0A 04) ⇒ onComplete()
  error(code, desc)            → code 7 = low battery (percent is in desc)
```

`stop()` sends `SILENT_PAUSE` (`0A 07`); `reset()` unregisters the handler and closes the
file. If the watch is silent for `timeout` ms the app restarts from `REQUIRE` once, then
`error(-3)`. `silent` (`SILENT_START`) is the auto-update path (`SilentUpgradeManager`); the
manual screen sends `START`.

## General path (`ota_type = 2`)

Protobuf `Command{type=2, subtype=5}` `{force, type=15, firmwareVersion, fileMd5}` →
reply `{0 ok, 2 already pushed, 3 error, 4 low battery}`, then the SDK mass-channel file push
(`openMassChannel` → `MassDataDispatcher` → `closeMassChannel`) with the device-provided
`segmentLength`.

## What this means for ProbeWatch

The ARQ, `CH_OTA` and `OP_READ` are in `src/xiaomi_client.py`, and the `0x5A`/`0A` codec
lives there too (`encode_ota_segment` / `parse_ota_segment` / `decode_ota_*`), with
`--ota-require` as the read-only probe. That covers `ota_type = 1`; the Redmi Watch 5 Active
reports `ota_type = 2`, so for this watch the target is the mass channel (2) plus
`Command{type=2, subtype=5}` — the watch side is in [firmware.md](firmware.md). The flashing
path (`START`/`DATA`) is deliberately not part of the client.
