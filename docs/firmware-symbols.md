# Firmware symbols — the Ghidra name map

Symbol names for both HCPU and LCPU images, derived from RT-Thread `__func__` literals.
This page is static: the symbols were extracted from the 2.2.111 firmware image locally;
nothing was flashed or executed and the watch is not contacted. Legal framing is
[README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

## Method

RT-Thread logs its own `__func__`. The bare name literal (e.g. `dfu_image_install_flash_lite`
at `0x2002d0d4`) is referenced only from inside the function that bears it, so
`xref(name_literal)` → `resolve_containing_procedure(ref)` names the function. Each entry
below was found this way; `name_literal` records the anchor so each row is re-checkable.

## Provider caveat

Re-imported with Ghidra 12.2 under the Cortex-M language `ARM:LE:32:Cortex` (ARMv8-M /
Cortex-M33; 923 functions). Entry points and bodies are reliable. The `0x200100d0` region
did **not** split into three functions: it is one function, `dfu_ctrl_reset_handler`, whose
callees `dfu_offline_install` and `dfu_reboot_install` the compiler inlined (one prologue at
`0x200100d0`, one epilogue at `0x200104da`).

## HCPU symbols

HCPU runs from SRAM at **`0x20000000`** (carve `image[0xa8:]`, load base `0x20000000`).
The vector table is at the image start (`SP = 0x20036970`, reset `0x20000909`).

| Symbol | Entry | Body | Confidence | Name literal | Group |
|---|---|---|---|---|---|
| `dfu_decompress` | `0x20010654` | `0x20010654`–`0x20010753` | high | `0x2002d11f` | dfu |
| `dfu_ctrl_reset_handler` | `0x200100d0` | `0x200100d0`–`0x200104dd` | high | `0x2002cfa0` | dfu |
| `dfu_image_install_flash_lite` | `0x20011840` | `0x20011840`–`0x20011cc9` | high | `0x2002d0d4` | dfu |
| `dfu_offline_header_alloc` | `0x20011d98` | `0x20011d98`–`0x20011e77` | high | `0x2002cf09` | dfu |
| `dfu_ota_bootloader_ram_run_set` | `0x20011ed8` | `0x20011ed8`–`0x20011f45` | high | `0x2002cfca` | dfu |
| `dfu_packet_erase_flash` | `0x20011fac` | `0x20011fac`–`0x20012007` | high | `0x2002d019` | dfu |
| `fal_partition_write` | `0x200137b8` | `0x200137b8`–`0x20013875` | high | `0x2002cdd1` | fal |
| `rt_rtc_control` | `0x2001bcb4` | `0x2001bcb4`–`0x2001bd8f` | high | `0x2001bda0` | rtc |

### Notes

- `dfu_ctrl_reset_handler` (`0x200100d0`) is a **single function**, not a merged region: the
  entry `RT_ASSERT(env->mode == DFU_CTRL_OTA_MODE)` at `0x200100e0` carries its own
  `__func__`, repeated at the `0x200104a0` assert.
- `dfu_offline_install` — name literal `0x2002cf8c`, `__func__` logged at `0x200101b6` and
  `0x20010298`; **inlined** into `dfu_ctrl_reset_handler`, so it has no independent entry.
- `dfu_reboot_install` — name literal `0x20010528` (string embedded in code), `__func__`
  logged at `0x20010210`; **inlined** into `dfu_ctrl_reset_handler`, no independent entry.
- `rt_rtc_control` — resolved to `FUN_2001bcb4`; the `adr r1,[0x2001bda0]` at `0x2001bcc0`
  is its own `RT_ASSERT(dev != RT_NULL)` name.

## LCPU symbols

LCPU runs from **`0x12000000`** (extracted `image1`, 5,578,752 B). Absolute pointers in the
image are stored shifted: **`true = stored - 0x26000`** (PC-relative code is already correct).

| Symbol | Entry | Confidence | Evidence |
|---|---|---|---|
| `login_fsm_timeout_handler` | `0x1200390e` | high | logs `'login_fsm_timeout_handler'`; sets `[inst+0x20]=3` and frees the login session |
| `login_fsm_timer_arm` | `0x12003b5e` | high | `FUN_12157c04(inst, 10000)` — 10 s timeout while state waits in `WAIT_APP_VERIFY`/`WAIT_APP_CONFIRM` |
| `hkdf_auth_call` | `0x12003d7c` | high | info literal `0x12003ff8` → `'miwear-auth'`; 64-byte output; salt = 2 × 16-byte randoms; IKM = 16-byte secret |
| `spp_connected_handler` | `0x12032e64` | high | logs `'Spp connected:channel=%d'`; stores the channel byte; registers `'spp_connect'` with event `0x0e` |
| `spp_disconnected_handler` | `0x12032f28` | high | logs `'Spp disconnected_channel:%d'`; registers `'spp_disconnect'` with event `0x0e` |
| `spp_ble_thread_init` | `0x120362a0` | medium | name `'spp_ble_d'`, stack `0x1000`, priority 20; entry literal `0x1205c35d` minus `0x26000` = `0x1203635d` |
| `channel_msh_command` | `0x12049a80` | medium | MSH probe/read/enable/disable; debug console, not the production path |
| `protobuf_queue_init` | `0x1203311c` | high | creates `protobuf_preprocess_queue` (4 B × 0x50 slots) and the `mi_pb` thread (0x5000 stack, priority 19) |
| `protobuf_dispatch_thread` | `0x12258624` | high | `rt_mq_recv(q,&msg,4,-1)` then TBH jump tables on u16 type (0..10) and u16 subtype (0xc402..0xc427); entry literal `0x1227e625` minus `0x26000` |
| `l2_channel_dispatcher` | `0x1215a9c8` | high | switch on channel 1..7 (jump table) routing PB/MASS/OTA/NETWORK; SAR string table at `0x1215aab0` |
| `mass_file_header_check` | `0x12173a14` | high | on header event: requires state `0x20`, clears a 0x140-byte buffer, logs `mass_file_bin_header`; compares first word to `0xafcdefad` |
| `send_msg_to_protobuf_thread` | `0x121a08fc` | high | 4-byte `rt_mq_send` wrapper; name literal `0x121a092c` |
| `hkdf_sha256_expand` | `0x121cf810` | high | 32-byte blocks, ciphertext counter, assert `'okm_size < 255 * sizeof(t)'` |
| `hkdf_bind_call` | `0x1212b1d2` | medium | info literal `0x1212b40c` → `'miwear-bind'` (companion binding, not used by the client) |

## Pipeline

The symbol map lives in `secrets/ghidra/symbols.json` (git-ignored). Two scripts regenerate
the importable formats:

- `uv run python scripts/export_symbols.py` — writes `symbols.ghidra.txt` (Ghidra
  `ImportSymbolsScript.py` format) and `scripts/apply_symbols.py` (prints `set_address_name`
  commands for REA).
- `uv run python scripts/apply_symbols.py` — prints `set_address_name(image, addr, name)`
  for every symbol with a non-null entry (22 commands: 8 HCPU + 14 LCPU).

## Next

1. Re-import LCPU with `GHIDRA_HEADLESS_MAXMEM` raised to handle the full 5.5 MB image.
2. Systematic `__func__` xref naming over the full HCPU image (Phase C7).
