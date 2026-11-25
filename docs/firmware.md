# Watch firmware — what the 2.2.111 image is

The image the watch runs, and what it says about the device. This page is static: the image
was downloaded, unpacked and disassembled locally; nothing was flashed or executed and the
watch is not contacted. Legal framing is [README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

## Provenance

| Fact | Value |
|---|---|
| Version | 2.2.111 ([firmware history](device.md#firmware-history)) |
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

Not Linux. It is a **SiFli** package for an **SF32LB5x** part: a small `ad ef cd af` header,
then two **Cortex-M33** images. The part is dual-core — the **HCPU** runs the RT-Thread
application/GUI, the **LCPU** runs the low-power and Bluetooth stack. The exact SKU is not
confirmed in this image; Byterialab reports SF32LB551 [ext Byterialab].

| Evidence in the image | Layer |
|---|---|
| `rt_hw_watchdog_register`, `rt_watchdog_init`, `rt_adc_enable`, `rt_flash_read/erase`, `rt_rtc_control` | RT-Thread kernel |
| `drv.rtc`, `drv.spi_flash`, `drv.wdt` | RT-Thread device model |
| `2020 - 2022 Copyright by SiFli team`, `sifli_pin_irq_enable`, `sifli_adc_control`, `sifli_dma_transmit` | SiFli BSP |
| `Flash Abstraction Layer (V%s)`, `fal_partition_read/write/erase`, `Partition (%s) not found` | RT-Thread FAL partition table |
| `FlashDB V%s`, `[FlashDB][kv]` | armink FlashDB key/value store |
| `dfu_image_install_flash_lite`, `dfu_packet_erase_flash dest 0x%x`, `dfu_ota_bootloader_ram_run_set`, `dfu_reboot_install` | DFU/OTA installer |
| `app_watch`, `battery_charger_init ok!`, `dac`, `RTC use LXT`, `Init RTC, wake = %d` | app, power, audio, alarms |
| `spp_connect`, `rfcomm chl = 0x%x`, `l2cap`, `gatt`, `miwear_mass_*`, `hkdf_sha256.c` | LCPU Bluetooth/SPP stack |

## The package is two images

The `0xa8`-byte header is followed by `image0` and the `image1` record stream; the three tile
the file exactly (`0xa8 + 0x2e718 + 0x31c4c7 = 3,452,039 B`):

| Field (u32 LE) | Offset | Value | Meaning |
|---|---|---|---|
| image0 size | `0x0c` | `0x2e718` (190,232 B) | plaintext HCPU image |
| image1 stored | `0x1c` | `0x31c4c7` (3,261,639 B) | record stream as shipped |
| image1 total | `0x20` | `0x552000` (5,578,752 B) | uncompressed LCPU image |

- **image0** starts at `0xa8` and runs from SRAM at **`0x20000000`** (initial `SP = 0x20036970`,
  reset `0x20000909`). This is the RT-Thread/SiFli app mapped in the load map below.
- **image1** starts at `0xa8 + 0x2e718 = 0x2e7c0`: a **raw-DEFLATE** record stream. It unpacks
  to 545 blocks of `0x2800` B (final block `0x2000` B), and its vectors point into
  `0x1202xxxx` — the image is linked at **`0x12000000`** (initial `SP = 0x200577c0`, reset
  `0x12029749`). The `0x552000` field is an uncompressed **length** (used as the erase extent
  and checked by `dfu_decompress`), not a load address.

The stream opens with `[total][block=0x2800][first complen][first uncomplen]`; each record is a
self-terminating DEFLATE stream expanding to one block, some prefixed with
`[complen][uncomplen]` and some with `[uncomplen]` only. Declared lengths include a 4-byte
encoder pad, which the final record truncates. The HCPU `dfu_decompress` is a zlib-style
inflate wrapper (CRC-32 seeded `0xffffffff`, `total_uncompress_len > …pksize` check); it has
no decrypt step. `scripts/extract_firmware.py` reproduces the walk (`uv run python
scripts/extract_firmware.py` writes `secrets/firmware/extracted/{hcpu,lcpu}.bin`) and aborts
unless the blocks sum to exactly `0x552000` B.

## Which OTA engine this model uses

`ota_type = 2`, the general engine: a protobuf prepare (`2/5`) followed by a mass-channel file
push, not the channel-6 protocol. The update flow is in [ota.md](ota.md); the installer that
receives it is the DFU cluster below.

## Sound and alarms

Both live in the HCPU image:

- **Audio**: the SiFli `dac` driver path (tone/beep), not an I²S codec; the app's HFP audio is
  a separate Bluetooth profile (see [audio.md](audio.md)).
- **Alarms**: `rt_rtc_control`, `drv.rtc`, `RTC use LXT`, `Init RTC, wake = %d` — an RTC
  compare/wake path on the LXT crystal.

## Load map (HCPU, verified)

The HCPU image runs from SRAM at **`0x20000000`**: file offset `0xa8` ↔ vaddr `0x20000000`
(carve `image[0xa8:]`, load base `0x20000000`, ARM little-endian, Thumb). The vector table is
at the image start (`SP = 0x20036970`, reset `0x20000909`; prologue sets MSP then branches).
Auto-analysis (Ghidra via REA, generic `ARM:LE:32:v7` — no Cortex-M profile, but the odd
Thumb vectors seed it) finds **929 procedures / 795 strings**. Function names are not in the
image, but RT-Thread logs its own `__func__`: the bare `name` literal is referenced only from
inside the function that bears it, so an xref to it names the function.

The DFU/OTA installer (the watch side of the `ota_type = 2` update) is the densest named
cluster: `dfu_offline_install[_lite]`, `dfu_offline_header_alloc`, `dfu_img_install[_flash]`,
`dfu_image_install_flash_lite`, `dfu_packet_erase_flash`, `dfu_decompress`,
`dfu_ota_bootloader_ram_run_set`, `dfu_reboot_install`, `dfu_ctrl_{reset_handler,
boot_to_user_fw, update_prog_info, error_handle}`, `dfu_protocol_session_close`, `dfu_env`
(`DFU_CTRL_OTA_MODE`), plus a `dfu_gui_*` on-watch progress screen. FAL/FlashDB are present as
expected (`fal_init`, `fal_partition_{read,write,erase}`, `fdb_kvdb_init`).

## The BLE/SPP stack lives on the LCPU

The HCPU has **no** protocol code: `mass`, `spp`, `rfcomm` and `aes` appear nowhere in it (the
only `proto` hit is `dfu_protocol_session_close`), and it exposes
`lcpu2hcpu_notification_callback` — it receives Bluetooth events over the inter-core mailbox.
The extracted LCPU image holds the stack: `spp_connect`, `rfcomm chl = 0x%x`,
`send l2cap sig %x`, `gatt`, `bredr`, `ble_*`, `hkdf_sha256.c`, `zh_sha256.c`,
`protobuf_preprocess_queue`, the `miwear_mass_*` receiver and the channel enable/disable
logic. So the firmware is the **watch side** of the protocol, the APK in
[apk-analysis.md](apk-analysis.md) is the **phone side**, and live probing arbitrates. What
the LCPU contains, and the one probe run so far, is in [lcpu.md](lcpu.md).

## Watchface file format

Watchface packages (magic `5A A5 34 12`, a resource table at `0x1C0` of 16-byte
entries) are reported by Byterialab [ext Byterialab].

## Update verification

The phone checks the download's MD5 (see [ota.md](ota.md)); the watch verifies the image
against a baked-in RSA-2048 public key and cert chain [ext Byterialab]. The signing key is not
on the watch, so an image cannot be re-signed from the device [inferred].

## Next

1. LCPU mining, string-guided (started in [lcpu.md](lcpu.md)): the mass-channel receiver (feeds
   the `ota_type = 2` push in [ota.md](ota.md)), the channel table and the session teardown
   (feeds [channels.md](channels.md)), the protobuf dispatch, and HKDF/AES against
   `src/xiaomi_client.py`.
2. HCPU: diff the plaintext app against open-source RT-Thread to name the scheduler, drivers,
   FAL/FlashDB and DFU routines; the installer cluster is already located.
3. Verify anything claimed on hardware; record measured facts on their topic page
   ("Recording a finding" in `AGENTS.md`).
