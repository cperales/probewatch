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

Fetched without the account API: Mi Fitness logs the `LatestVersion` object (`fullPackageUrl`,
`md5`) to `logcat`; the URL is a signed CDN link, so `curl` is enough. The direct-API route is
`scripts/fetch_firmware_url.py` (needs the `miothealth` cookie, [ota.md](ota.md)).

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
| `app_watch`, `battery_charger_init ok!`, `RTC use LXT`, `Init RTC, wake = %d` | app, power, alarms (RTC wake) |
| `spp_connect`, `rfcomm chl = 0x%x`, `l2cap`, `gatt`, `miwear_mass_*`, `hkdf_sha256.c`, `dac set volume`, `alarm_remind`, `al_alarm_set` | LCPU Bluetooth/SPP stack, DAC/tone, alarm scheduler |

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

Mostly the **LCPU**: the DAC/codec path, the codec tone, and the whole alarm service — the
`alarmsvc` list scan and the RTC `SET_ALARM`/wake write. The **HCPU** has its own `drv_rtc`
copy but only `set_time` and the vendor compare command. Neither image has a "beep" or "tone"
string. See [sound-alarms.md](sound-alarms.md) and [alarm-scheduler.md](alarm-scheduler.md).
The app's HFP audio is a separate Bluetooth profile (see [audio.md](audio.md)).

## Load map (HCPU, verified)

The HCPU image runs from SRAM at **`0x20000000`**: file offset `0xa8` ↔ vaddr `0x20000000`
(carve `image[0xa8:]`, load base `0x20000000`, ARM little-endian, Thumb). The vector table is
at the image start (`SP = 0x20036970`, reset `0x20000909`; prologue sets MSP then branches).
Auto-analysis (Ghidra 12.2, `ARM:LE:32:Cortex`) finds **923 functions / 794 strings**. Function
names are not in the image, but RT-Thread logs its own `__func__`: the bare `name` literal is
referenced only from inside the function that bears it, so an xref to it names the function.
143 carry such an anchor; 110 are named from it and 64 more from an SDK slice match
(**184** in all; [firmware-symbols.md](firmware-symbols.md)).

### Pointer density

`uv run python scripts/pointer_density.py` counts the image's self-pointers: 1,737 of 47,558
words (3.7%) at `0x20000000`. The count stays near its peak only for bases within the image
size of `0x20000000`, so it rules out gross errors; the vector table fixes the exact value. It
is inconclusive for the LCPU (too many self-pointers), whose base and `-0x26000` relocation
come from the vector table ([lcpu.md](lcpu.md)).

The DFU/OTA installer (`ota_type = 2`) is the densest named cluster, plus the FAL/FlashDB
calls it makes; the rows are on [firmware-symbols.md](firmware-symbols.md).

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
on the watch, so an image cannot be re-signed from the device [inferred]. That check is not in
the HCPU installer (image0 has no SHA-256/RSA code [fw 2.2.111]); the SDK's
`dfu_img_verification` is compiled out here, so the bootloader verifies — with no rollback
check ([firmware-symbols.md](firmware-symbols.md)).

## Next

1. LCPU mining, string-guided (started in [lcpu.md](lcpu.md)): the mass-channel receiver, the
   channel table and session teardown, the protobuf dispatch, and HKDF/AES.
2. Verify anything claimed on hardware; record measured facts on their topic page.
