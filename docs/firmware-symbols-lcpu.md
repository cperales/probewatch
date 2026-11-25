# Firmware symbols — the LCPU map

Symbol names for the **LCPU** image, the Bluetooth/SPP core. The method is the same as for
the HCPU map ([firmware-symbols.md](firmware-symbols.md)): RT-Thread logs its own `__func__`,
and an xref to the bare name literal resolves to the function that bears it. What the code
does is in [lcpu.md](lcpu.md). This page is static: nothing was flashed or executed and the
watch is not contacted. Legal framing is [README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

## Load map

LCPU runs from **`0x12000000`** (extracted `image1`, 5,578,752 B). Absolute pointers in the
image are stored shifted: **true = stored - 0x26000** (PC-relative code is already correct),
so the image is imported pre-patched by `scripts/prepatch_lcpu.py`.

Imported from the pre-patched image at base `0x12000000` under `ARM:LE:32:Cortex`, 4 GB heap,
block `0x12000000`–`0x12551fff`, 16,901 functions at import. Bodies below are the Cortex
bounds; three rows are **call sites**, not function entries (`entry` empty).

## Caveat

The "Non-Returning Functions - Discovered" pass is disabled before analysis. The image
carries no ROM, so thunks to `0x2006xxxx` are unresolvable and the pass marked them
non-returning; callers then stopped at the call — `hkdf_sha256_expand` ended at `0x121cf8b9`
instead of its real `bx lr` at `0x121cf910`. Functions reached only through a data word
(thread entries) are not created by auto-analysis; they were created from their verified
prologues.

## Symbols

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

## Scope

This table is the published map, not the limit of what is named: deeper LCPU mining
(protobuf dispatch, mass channel, login FSM) is tracked in [lcpu.md](lcpu.md), not in the
HCPU naming pass. Regenerate the importable forms with `scripts/export_symbols.py`.
