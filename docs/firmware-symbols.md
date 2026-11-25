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
Cortex-M33). Both images now use it: HCPU at `0x20000000` (923 functions) and the pre-patched
LCPU at `0x12000000` with a 4 GB heap (16,901 functions at import). Entry points and bodies are
reliable. The `0x200100d0` region did **not** split into three functions: it is one function,
`dfu_ctrl_reset_handler`, whose callees `dfu_offline_install` and `dfu_reboot_install` the
compiler inlined (one prologue at `0x200100d0`, one epilogue at `0x200104da`).

For LCPU the "Non-Returning Functions - Discovered" pass is disabled before analysis: the
image carries no ROM, so thunks to `0x2006xxxx` are unresolvable, and the pass marked them
non-returning. Callers then stopped at the call — `hkdf_sha256_expand` ended at `0x121cf8b9`
instead of its real `bx lr` at `0x121cf910`. Functions reached only through a data word (thread
entries) are not created by auto-analysis; they were created from their verified prologues.

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

Imported from the pre-patched image at base `0x12000000` under `ARM:LE:32:Cortex`, 4 GB heap,
block `0x12000000`–`0x12551fff`, 16,901 functions at import. Bodies below are the Cortex
bounds; three rows are **call sites**, not function entries (`entry` empty).

| Symbol | Entry | Body | Confidence | Evidence |
|---|---|---|---|---|
| `login_fsm_timeout_handler` | `0x1200390e` | `0x1200390e`–`0x12003975` | high | logs `'login_fsm_timeout_handler'`; sets `[inst+0x20]=3` and frees the login session; entry word stored at `0x120038c0` |
| `login_fsm_timer_arm` | — | inside `0x12003a74` | medium | call site `0x12003b5e`: `FUN_12157c04(inst, 10000)` arms the 10 s timeout in `WAIT_APP_VERIFY`/`WAIT_APP_CONFIRM` |
| `hkdf_auth_call` | — | inside `0x12003a74` | medium | call site `0x12003d7c`: info literal `0x12003ff8` → `'miwear-auth'`; 64-byte output |
| `hkdf_sha256_expand` | `0x121cf810` | `0x121cf810`–`0x121cf911` | high | 32-byte blocks, ciphertext counter, assert `'okm_size < 255 * sizeof(t)'`; ends `bx lr` at `0x121cf910` |
| `hkdf_bind_call` | — | inside `0x1212af24` | medium | call site `0x1212b1d2`: info literal `0x1212b40c` → `'miwear-bind'` (companion binding) |
| `spp_connected_handler` | `0x12032e64` | `0x12032e64`–`0x12032ed7` | high | logs `'Spp connected:channel=%d'`; stores the channel byte; registers `'spp_connect'` with event `0x0e` |
| `spp_disconnected_handler` | `0x12032f28` | `0x12032f28`–`0x12032f9b` | high | logs `'Spp disconnected_channel:%d'`; registers `'spp_disconnect'` with event `0x0e` |
| `spp_ble_thread_init` | `0x120362a0` | `0x120362a0`–`0x120362ff` | high | name `'spp_ble_d'`, 4 KB stack, priority 20; entry word `0x120362a1` stored at `0x1249a42c` |
| `channel_msh_command` | `0x12049a78` | `0x12049a78`–`0x12049ba3` | high | MSH probe/read/enable/disable; debug console, not the production path |
| `protobuf_queue_init` | `0x1203311c` | `0x1203311c`–`0x1203317b` | high | creates `protobuf_preprocess_queue` (4 B × `0x50`) and the `mi_pb` thread (`0x5000` stack, priority 19) |
| `protobuf_dispatch_thread` | `0x12258624` | `0x12258624`–`0x12258bb3` | high | `rt_mq_recv(q,&msg,4,-1)` then TBH jump tables on u16 type (0..10) and u16 subtype (`0xc402`..`0xc427`); entry word stored at `0x120331b8` |
| `l2_channel_dispatcher` | `0x1215a9c8` | `0x1215a9c8`–`0x1215aaa9` | high | switch on channel 1..7 routing PB/MASS/OTA/NETWORK; SAR string table at `0x1215aab0` |
| `mass_file_header_check` | `0x12173a14` | `0x12173a14`–`0x12174353` | high | header event: state `0x20`, clears a `0x140`-byte buffer, logs `mass_file_bin_header`, checks the first word against `0xafcdefad` |
| `send_msg_to_protobuf_thread` | `0x121a08fc` | `0x121a08fc`–`0x121a0921` | high | 4-byte `rt_mq_send` wrapper; name literal `0x121a092c` |

### Notes

- `login_fsm_timer_arm`, `hkdf_auth_call` and `hkdf_bind_call` are **call sites** inside
  `FUN_12003a74` (login FSM state handler) and `FUN_1212af24` (bind routine); they are not
  exported as functions.
- `channel_msh_command`: the earlier entry `0x12049a80` was 8 bytes into the prologue; the
  function starts at `0x12049a78` (`push {r4-r8,lr}`).
- `spp_ble_thread_init`, `protobuf_queue_init` and `protobuf_dispatch_thread` are referenced
  only by data words, so auto-analysis left them undefined; they were created from their
  verified prologues.

## Pipeline

The symbol map lives in `secrets/ghidra/symbols.json` (git-ignored). Two scripts regenerate
the importable formats:

- `uv run python scripts/export_symbols.py` — writes `symbols.ghidra.txt` (Ghidra
  `ImportSymbolsScript.py` format) and `scripts/apply_symbols.py` (prints `set_address_name`
  commands for REA).
- `uv run python scripts/apply_symbols.py` — prints `set_address_name(image, addr, name)`
  for every symbol with a non-null entry (19 commands: 8 HCPU + 11 LCPU).

## Next

1. Systematic `__func__` xref naming over the full HCPU image (Phase C7).
