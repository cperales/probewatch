# Watch firmware — what the 2.2.111 image is

The image the watch runs, and what it says about the device. This page is static: the image
was downloaded and string-scanned only; nothing was flashed or executed and the watch is not
contacted. Legal framing is [README.md](../README.md#legal).

## Provenance

| Fact | Value |
|---|---|
| Version | 2.2.111 (was 2.2.110; Mi Fitness installed it on 2026-11-22) |
| File | `3b86d2fa0b2572e42bd09b4bfd2da6eb_upd_lchz.watch.n65agl.bin` |
| Size | 3,452,039 B |
| MD5 | `3b86d2fa0b2572e42bd09b4bfd2da6eb` (equals the server's) |
| Host | `fk-res-abroad-cdn.home.mi.com` |
| Local | `secrets/firmware/…bin` (git-ignored) |

It was fetched without the account API. Mi Fitness logs the whole `LatestVersion` object
(including `fullPackageUrl` and `md5`) to `logcat` under the `CheckUpdate` tag, and that URL
is a signed CDN link (query-string `Expires`/`Signature`), so `curl` is enough. The app's own
copy lands in `/sdcard/Android/data/com.xiaomi.wearable/files/Download/<model>/<md5>` and can
be `adb pull`ed. `scripts/fetch_firmware_url.py` is the direct-API route, which needs the
`miothealth` cookie (see [ota.md](ota.md)).

## What it is

Not Linux. It is a monolithic **RT-Thread** image for a **SiFli** part in the
**SF32LB5x / Cortex-M33** family (the image carries `m33` and Thumb-2 code; the exact SKU is
not confirmed). Layout: a small SiFli boot header (`ad ef cd af`), then the RT-Thread
application and its string/rodata.

| Evidence in the image | Layer |
|---|---|
| `rt_hw_watchdog_register`, `rt_watchdog_init`, `rt_adc_enable`, `rt_flash_read/erase`, `rt_rtc_control` | RT-Thread kernel |
| `drv.rtc`, `drv.spi_flash`, `drv.wdt` | RT-Thread device model |
| `2020 - 2022 Copyright by SiFli team`, `sifli_pin_irq_enable`, `sifli_adc_control`, `sifli_dma_transmit` | SiFli BSP |
| `Flash Abstraction Layer (V%s)`, `fal_partition_read/write/erase`, `Partition (%s) not found` | RT-Thread FAL partition table |
| `FlashDB V%s`, `[FlashDB][kv]` | armink FlashDB key/value store |
| `dfu_image_install_flash_lite`, `dfu_packet_erase_flash dest 0x%x`, `dfu_ota_bootloader_ram_run_set`, `dfu_reboot_install` | DFU/OTA installer |
| `app_watch`, `battery_charger_init ok!`, `dac`, `RTC use LXT`, `Init RTC, wake = %d` | app, power, audio, alarms |

The strings are readable, so string-guided analysis works; the image also carries
decompression helpers (a few regions may be packed). The `dfu_*` + `FAL` names say the
watch-side update path is: receive a file, erase the target partition, write it, reboot into
the bootloader. That is the counterpart of the app's file push.

## Which OTA engine this model uses

The app logs `productDevice = ota_type 2` for `M2351W1`: the **general** engine, i.e. a
protobuf prepare (`Command{type=2, subtype=5}` `{force, type=15, firmwareVersion, fileMd5}`)
followed by a **mass-channel (2 / 104) file push**, not the channel-6 `0x5A` protocol. Channel
6 (`HyOtaExecutor`) belongs to `ota_type = 1` models and is documented in [ota.md](ota.md) for
completeness; `--ota-require` is not answered by this watch.

## Sound and alarms

Both live in this image, not in the app:

- **Audio**: the SiFli `dac` driver path (tone/beep), not an I²S codec; the app's HFP audio is
  a separate Bluetooth profile (see [audio.md](audio.md)).
- **Alarms**: `rt_rtc_control`, `drv.rtc`, `RTC use LXT`, `Init RTC, wake = %d` — an RTC
  compare/wake path on the LXT crystal.

## Load map (verified)

The image is a `ad ef cd af` SiFli container: a **0xa8-byte header**, then a Cortex-M image
that runs from SRAM at **`0x20000000`**. So disassembly uses **file offset `0xa8` ↔ vaddr
`0x20000000`** (carve `image[0xa8:]`, load base `0x20000000`, ARM little-endian, Thumb).

The vector table is at the start of that image (file `0xa8`): initial `SP = 0x20036970`
(top of a ~222 KB window), `reset = 0x20000909` (file `0x9b0`; prologue sets MSP then branches).
Auto-analysis (Ghidra via REA, generic `ARM:LE:32:v7` — no Cortex-M profile, but the odd
Thumb vectors seed it) finds **929 procedures / 795 strings**. Function names are not in the
image, but RT-Thread logs its own `__func__`: the bare `name` literal is referenced only from
inside the function that bears it, so an xref to it names the function. Example verified:
`dfu_image_install_flash_lite` (literal `0x2002d0d4`) is referenced from 7 sites in
`0x20011800–0x20011c3e` — that span is the installer body.

The DFU/OTA installer (the watch side of the `ota_type = 2` update) is the densest named
cluster: `dfu_offline_install[_lite]`, `dfu_offline_header_alloc`, `dfu_img_install[_flash]`,
`dfu_image_install_flash_lite`, `dfu_packet_erase_flash`, `dfu_decompress`,
`dfu_ota_bootloader_ram_run_set`, `dfu_reboot_install`, `dfu_ctrl_{reset_handler,
boot_to_user_fw, update_prog_info, error_handle}`, `dfu_protocol_session_close`, `dfu_env`
(`DFU_CTRL_OTA_MODE`), plus a `dfu_gui_*` on-watch progress screen. FAL/FlashDB are present as
expected (`fal_init`, `fal_partition_{read,write,erase}`, `fdb_kvdb_init`). The SPP/BLE frame
dispatcher and `mass`/`channel`/`auth` protocol strings are **not** in this slice — that code
is elsewhere (likely a separate image part or the LCPU) and needs its own search.

## Next: disassembly

1. RT-Thread and the SiFli SDK are open source: diff the recovered code against them to name
   the scheduler, drivers, FAL/FlashDB and DFU routines.
2. Then the pieces this repo cares about: the SPP/BLE frame dispatcher, the mass-file/DFU
   handler (start from the `dfu_offline_install` / `dfu_image_install_flash_lite` cluster), the
   DAC/audio path and the RTC/alarm scheduler (`rt_rtc_control`, `Init RTC, wake = %d`).
