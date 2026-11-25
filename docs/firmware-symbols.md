# Firmware symbols — the Ghidra name map

Symbol names for the **HCPU** image, derived from RT-Thread `__func__` literals. The second
image has its own page: [firmware-symbols-lcpu.md](firmware-symbols-lcpu.md). This page is
static: the symbols were extracted from the 2.2.111 firmware image locally; nothing was
flashed or executed and the watch is not contacted. Legal framing is
[README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

Where a symbol lives by cluster:

| Cluster | Page |
|---|---|
| kernel, IPC, timers, device framework (`rt_*`, `plug_holes`) | [firmware-symbols-kernel.md](firmware-symbols-kernel.md) |
| board drivers, serial/I2C/UART, GUI (`sifli_*`, `drv_*`, `lvsf_*`) | [firmware-symbols-drivers.md](firmware-symbols-drivers.md) |
| DFU/OTA, FAL/FlashDB, RTC | this page |
| Bluetooth/SPP/protobuf | [firmware-symbols-lcpu.md](firmware-symbols-lcpu.md) |

## Method

RT-Thread logs its own `__func__`. The bare name literal (e.g. `dfu_image_install_flash_lite`
at `0x2002d0d4`) is referenced only from inside the function that bears it, so
`xref(name_literal)` → `resolve_containing_procedure(ref)` names the function. Each entry
below was found this way; `name_literal` records the anchor so each row is re-checkable.

The pass runs over all **794 strings** of the image
(`secrets/ghidra/scripts/DumpStringXrefs.java`, output `hcpu-strings.ndjson`): 200 are
bare-identifier anchors and 143 functions own one. `__func__` is then separated from a
coincidental identifier at the call site — the literal is loaded into `r1` and passed to the
assert handler (`0x200179e4`) next to a `__LINE__` immediate. A data string such as a mutex or
device name is the first argument and lands in `r0`; those are rejected.

Two independent checks back the rows: the `__LINE__` immediate must fall inside a same-named
function in the SiFli-SDK source (v2.3.6), and the kernel cluster was cross-matched with
decompiler signatures (BSim) against a compiled SDK slice.

| Confidence | Meaning |
|---|---|
| high | assert call site and the line number lands inside the same-named source function, or the BSim match agrees at significance ≥ 10 |
| medium | assert call site only: the source is not in the public SDK (prebuilt `sifli_lib` or app code), so the line cannot be checked |

Two exclusions are deliberate. Functions carrying **two different** `__func__` literals are not
named from the anchor (`0x200100d0`, `0x200166e8`, `0x200157d8`, `0x2001c680`): an inlined
callee logs its own name, so the entry cannot be chosen this way — `dfu_ctrl_reset_handler`
below is the worked example. Literals owned by no function or by a data table
(`NO_TAG`, `DFUCTRL`, `status_table`, `db_lock`) are skipped.

## Provider caveat

Re-imported with Ghidra 12.2 under the Cortex-M language `ARM:LE:32:Cortex` (ARMv8-M /
Cortex-M33): HCPU at `0x20000000`, 923 functions. Entry points and bodies are reliable; a
body is the contiguous range from the entry (some Ghidra bodies have detached fragments).
The `0x200100d0` region did **not** split: it is one function, `dfu_ctrl_reset_handler`, whose
callees `dfu_offline_install` and `dfu_reboot_install` the compiler inlined (one prologue at
`0x200100d0`, one epilogue at `0x200104da`).

## DFU, flash and RTC

| Symbol | Entry | Body | Confidence | Name literal |
|---|---|---|---|---|
| `dfu_offline_install` | — | `—` | medium | `0x2002cf8c` |
| `dfu_reboot_install` | — | `—` | medium | `0x20010528` |
| `dfu_app_launch` | `0x2000fc84` | `0x2000fc84–0x2000fd83` | medium | `0x2002c6a8` |
| `dfu_ctrl_reset_handler` | `0x200100d0` | `0x200100d0–0x200104dd` | high | `0x2002cfa0` |
| `dfu_ctrl_update_prog_info` | `0x200105f0` | `0x200105f0–0x2001061b` | medium | `0x20010638` |
| `dfu_decompress` | `0x20010654` | `0x20010654–0x20010753` | high | `0x2002d11f` |
| `dfu_gui_page_init` | `0x20010afc` | `0x20010afc–0x20010b8f` | medium | `0x20010bc8` |
| `dfu_gui_percent_set_pos` | `0x20010f14` | `0x20010f14–0x20010fa9` | medium | `0x20010fd4` |
| `dfu_gui_sem_deinit` | `0x20010ff4` | `0x20010ff4–0x20011099` | medium | `0x20011100` |
| `dfu_gui_fill_msg` | `0x2001114c` | `0x2001114c–0x20011209` | medium | `0x2002c6cf` |
| `dfu_img_install_flash` | `0x20011340` | `0x20011340–0x20011813` | medium | `0x2002d100` |
| `dfu_image_install_flash_lite` | `0x20011840` | `0x20011840–0x20011cc9` | high | `0x2002d0d4` |
| `dfu_offline_header_alloc` | `0x20011d98` | `0x20011d98–0x20011e77` | high | `0x2002cf09` |
| `dfu_ota_bootloader_ram_run_set` | `0x20011ed8` | `0x20011ed8–0x20011f45` | high | `0x2002cfca` |
| `dfu_packet_erase_flash` | `0x20011fac` | `0x20011fac–0x20012007` | high | `0x2002d019` |
| `_fdb_init_ex` | `0x2000d3bc` | `0x2000d3bc–0x2000d55d` | high | `0x2002c897` |
| `_fdb_read_status` | `0x2000d920` | `0x2000d920–0x2000d975` | high | `0x2002cba6` |
| `_fdb_write_status` | `0x2000d9ac` | `0x2000d9ac–0x2000da3f` | high | `0x2002cbb7` |
| `fal_partition_erase` | `0x200134e0` | `0x200134e0–0x2001359b` | high | `0x2002cdbd` |
| `fal_partition_read` | `0x20013670` | `0x20013670–0x2001372d` | high | `0x2002cdaa` |
| `fal_partition_write` | `0x200137b8` | `0x200137b8–0x20013875` | high | `0x2002cdd1` |
| `fdb_kv_get_blob` | `0x20013940` | `0x20013940–0x20013a6f` | medium | `0x20013acc` |
| `fdb_kv_set_blob` | `0x20013adc` | `0x20013adc–0x20013bb3` | medium | `0x20013be8` |
| `fdb_kvdb_init` | `0x20013c00` | `0x20013c00–0x20013d51` | high | `0x2002cb66` |
| `read_kv` | `0x2001723c` | `0x2001723c–0x2001744b` | high | `0x2002cb74` |
| `rt_rtc_control` | `0x2001bcb4` | `0x2001bcb4–0x2001bd8f` | high | `0x2001bda0` |

### Notes

- `dfu_ctrl_reset_handler` (`0x200100d0`) is a **single function**, not a merged region: the
  entry `RT_ASSERT(env->mode == DFU_CTRL_OTA_MODE)` at `0x200100e0` carries its own
  `__func__`, repeated at the `0x200104a0` assert.
- `dfu_offline_install` — name literal `0x2002cf8c`, `__func__` logged at `0x200101b6` and
  `0x20010298`; **inlined** into `dfu_ctrl_reset_handler`, so it has no independent entry.
- `dfu_reboot_install` — name literal `0x20010528` (string embedded in code), `__func__`
  logged at `0x20010210`; **inlined** into `dfu_ctrl_reset_handler`, no independent entry.
- `rt_rtc_control` — the `adr r1,[0x2001bda0]` at `0x2001bcc0` is its own
  `RT_ASSERT(dev != RT_NULL)` name.
- `dfu_packet_erase_flash` is referenced from two functions (`0x20010894` and `0x20011fac`).
  The row is the second: the first is a short pre-flight check that logs the same name.

## Pipeline

The symbol map lives in `secrets/ghidra/symbols.json` (git-ignored) and holds both images,
the per-row site evidence and the naming passes. Two scripts regenerate the importable forms:

- `uv run python scripts/export_symbols.py` — writes `symbols.ghidra.txt` (Ghidra
  `ImportSymbolsScript.py` format) and `scripts/apply_symbols.py` (prints `set_address_name`
  commands for REA).
- `uv run python scripts/apply_symbols.py` — prints `set_address_name(image, addr, name)`
  for every symbol with a non-null entry (129 commands: 118 HCPU + 11 LCPU; the LCPU rows
  without an entry are call sites, not functions).
