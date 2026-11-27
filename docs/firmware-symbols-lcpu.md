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
| `mass_file_header_check` | `0x12173a14` | `0x12173a14`–`0x12174353` | high | header event: state `0x20`, clears a `0x140`-byte buffer, logs `mass_file_bin_header`, checks word 0 against `0xafcdefad` and byte 6 against `0x02` (version `0x0002026f`); 10× `0x10`-byte sub-file table from offset 8, then 4 KB flash pages in 1 KB sub-writes ([mass-channel.md](mass-channel.md)) |
| `send_msg_to_protobuf_thread` | `0x121a08fc` | `0x121a08fc`–`0x121a0921` | high | 4-byte `rt_mq_send` wrapper; name literal `0x121a092c` |
| `send_msg_to_preprocess_thread` | `0x1219e75c` | `0x1219e75c`–`0x1219e7bd` | high | `rt_mq_send(g_app_preprocess_queue,…)` wrapper; name literal `send_msg_to_preprocess_thread` `0x12426a21`; logs `msg type 0x%x len %d` |
| `app_preprocess_thread_entry` | `0x12094890` | `0x12094890`–`0x12095249` | high | the **second dispatch** thread: `rt_mq_recv` loop + switch on u16 type (0/1/2/3/5/7/9); `__func__` `app_preprocess_thread_entry` `0x12095260` (assert `0x7b9`); type 2 → `app_system_subtype_dispatch`; queue `g_app_preprocess_queue` `0x120953a0` |
| `app_system_subtype_dispatch` | `0x1205afe8` | `0x1205afe8`–`0x1205b0c7` | high | `tbb` over `0xc603`–`0xc608` (System subtypes 3–8): `0xc603` (time), `0xc604` (force-upgrade), `0xc605` (prepare) rebuild a `{subtype,…}` message and tail-call `ble_service_cb`; `0xc606`/`0xc607` fall through; `0xc608` runs the new-phone connect path |
| `ble_service_cb` | `0x12194e40` | `0x12194e40`–`0x12194f5d` | high | logs `ble_service_cb: type 0x%04x`; switch on `0x9601`–`0x9608`; `0xc605` → copies payload and calls `ota_prepare_response`; `0xc603`/`0xc604` handled in the same default chain |
| `ota_prepare_response` | `0x1200c0ac` | `0x1200c0ac`–`0x1200c13b` | high | the `2/5` prepare sink: wraps `firmwareInstallRequest` into a type-`0x10` message and sends it (`FUN_12191b78`/`FUN_121a076c`); no `version`/`md5` comparison |
| `app_lv_task_ota_process` | `0x120808c4` | `0x120808c4`–`0x12080997` | high | logs `app_lv_task_ota_process: type %d, subtype %d` (`__func__` `0x12416429`); on `{type=5, subtype=0x8108}` reads battery (`FUN_120d0578`), **gates `< 0x1e` (30 %)** → `Low_power_ota_failed`, else `APP_POPUP_DFU battery level` + 10 s timer (`[inst+0x2c]=10000`) |
| `dfu_lite_install_state` | `0x120fec9c` | `0x120fec9c`–`0x120feea7` | high | DFU install state handler; on event 0/1 sends `{type=5, subtype=0x8108}` (the message that arms `app_lv_task_ota_process`); logs `… last ota failed, ignore event`, `DFU APP RESUME RESPONSE`, `install start` |
| `dfu_get_version` | `0x120ff250` | `0x120ff250`–`0x120ff281` | high | reads the installed `ota ver`; logs `dfu_get_version addr: 0x%x`; called only from `FUN_120fe86c` (DFU control), never from the `2/5` prepare path |

### Notes

- `login_fsm_timer_arm`, `hkdf_auth_call` and `hkdf_bind_call` are **call sites** inside
  `FUN_12003a74` (login FSM state handler) and `FUN_1212af24` (bind routine); they are not
  exported as functions.
- `channel_msh_command`: the earlier entry `0x12049a80` was 8 bytes into the prologue; the
  function starts at `0x12049a78` (`push {r4-r8,lr}`).
- `spp_ble_thread_init`, `protobuf_queue_init` and `protobuf_dispatch_thread` are referenced
  only by data words, so auto-analysis left them undefined; they were created from their
  verified prologues.
- `app_preprocess_thread_entry` is the **second dispatch**: the `mi_pb` type-2 table covers
  `0xc606`–`0xc62e`; this thread routes type 2 through `app_system_subtype_dispatch`
  (`0xc603` time, `0xc604` force-upgrade, `0xc605` prepare). `0xc600 + subtype` is confirmed
  end-to-end ([ota.md](ota.md)).

## Scope

This table is the published map, not the limit of what is named. Regenerate the importable
forms with `scripts/export_symbols.py`.

The mass channel (2) cluster, decompiled for the resume question
([mass-channel.md](mass-channel.md)): `mass_receiver` `0x121104d4` (channel-2 data, 45 s timer),
`sdk_mass_pb_handle` `0x12110e24` (`22/0` handler), `mass_control_handle` `0x12110d20` (`22/1`
pause/cancel), `mass_prepare` `0x1220a3f4` (resumes from the stored offset iff md5/size/type
match), `mass_channel2_data` `0x1220a4bc` (`offset += len`), `mass_end_handler` `0x1220a2cc`
(zeroes it on session end).
