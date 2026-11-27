# LCPU firmware — the Bluetooth/SPP side

The second image in the 2.2.111 package (see [firmware.md](firmware.md)) is the core that runs
the Bluetooth stack: SPP, the protobuf dispatcher, the login/auth FSM, the mass-file receiver
and the L2 channel routing. This page records what static analysis found and what one read-only
hardware probe confirmed. Legal framing is [README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

## What it is

`scripts/extract_firmware.py` unpacks `image1` to 5,578,752 B. Its strings name the protocol
stack — `spp_connect`, `rfcomm chl = 0x%x`, `send l2cap sig %x`, `SAR V2 TRANS`,
`protobuf_preprocess_queue`, `MIWEAR_LOGIN_FSM_*`, `miwear-auth`, `hkdf_sha256.c`,
`miwear_mass_*` — while the HCPU image has no `mass`/`spp`/`rfcomm`/`aes` strings. The watch
side of the protocol is here; the phone side is [apk-analysis.md](apk-analysis.md).

## Load map and the boot relocation

- Base **`0x12000000`**, Cortex-M Thumb; PC-relative code is coherent and the function
  boundaries below are real.
- **Absolute pointers are stored relocated: `true = stored - 0x26000`.** Evidence: the vector
  words `0x1202975d/5f/61` resolve to `0x1200375d/5f/61`, three consecutive `b .` (`E7FE`)
  stubs; the reset resolves to `0x12003748`; and the four `SAR` log-string pool words sit
  consecutively at `0x1215aab0`. With the delta applied, the earlier "thread entry lands
  mid-function" anomalies disappear (the protobuf entry `0x1227e625` is really `0x12258624`).
- Ghidra (via REA) imports with a 2 GB heap; the full image OOMs, a 2 MB slice analyzes.
  Patching every absolute word by `-0x26000` before import should give a clean full-image pass.

## Protocol code, verified by disassembly

| What | Evidence |
|---|---|
| SPP connect / disconnect | `FUN_12032e64` logs `Spp connected:channel=%d`, stores the channel and registers `spp_connect` (event `0x0e`); `FUN_12032f28` mirrors it with `Spp disconnected_channel:%d` / `spp_disconnect` |
| SPP BLE thread | `spp_ble_d`: `rt_thread_init` through ROM thunk `0x10048bed`, 4 KB stack, priority 20 |
| Protobuf dispatch | thread `0x12258624`: `rt_mq_recv(q, &msg, 4, -1)` then two jump tables on `u16 type` (0–10) and `u16 subtype` (`0xc402`–`0xc427`); sender `FUN_121a08fc`; queue `protobuf_preprocess_queue` (4 B × `0x50`), thread `mi_pb` (0x5000 stack, prio 19) |
| Protobuf subtype encoding | the wire `Command.subtype` is a plain int (Gadgetbridge `CMD_FIRMWARE_INSTALL = 5`); the watch compares against `0xc600 + subtype`, so System subtypes 6–46 live in the `mi_pb` type-2 table (`0xc606`–`0xc62e`) and subtypes 3–5 are the gap `0xc603`–`0xc605` |
| Second dispatch (System subtypes 3–5) | `app_preprocess_thread_entry` (`0x12094890`, queue `g_app_preprocess_queue`) routes type 2 to `app_system_subtype_dispatch` (`0x1205afe8`), whose `tbb` over `0xc603`–`0xc608` forwards `0xc605` (prepare) through `ble_service_cb` → `ota_prepare_response`; `0xc603` time / `0xc604` force-upgrade take the same path |
| OTA prepare gate | `app_lv_task_ota_process` (`0x120808c4`), on `{type=5, subtype=0x8108}`, reads battery and rejects `< 0x1e` (30 %) with `Low_power_ota_failed`; else DFU popup + 10 s timer — no `version` compare ([ota.md](ota.md)) |
| Login FSM | `MIWEAR_LOGIN_FSM_START/WAIT_APP_VERIFY/WAIT_APP_CONFIRM`; arms a **10 000 ms** timer (`FUN_12157c04(inst, 10000)` at `0x12003b5e`); on timeout `login_fsm_timeout_handler` (`0x1200390e`) sets state 3, `SCHD_EVT_ADMIN_LOGIN_RESTART` restarts it once, and the second timeout frees the login session and the link |
| Auth HKDF | `FUN_121cf810` (HKDF-SHA256 expand, 32-byte blocks, `okm_size < 255*32`); the auth call at `0x12003d7c` uses info **`miwear-auth`**, 64-byte output; a second call uses `miwear-bind` |
| L2 routing | `FUN_1215a9c8` switches on channel 1–7 and routes PB/MASS/OTA/NETWORK to handlers, logging via the SAR table at `0x1215aab0` |
| Mass-file receiver | `FUN_12173a14`: the header event requires state `0x20`, clears a `0x140`-byte buffer, logs `mass_file_bin_header=…`, validates word 0 against **`0xafcdefad`** (SiFli magic) and header byte 6 against `0x02` (version word `0x0002026f`); parses up to 10 sub-file records of `0x10` B, then writes 4 KB flash pages in 1 KB sub-writes ([mass-channel.md](mass-channel.md)) |
| HKDF source | `hkdf_sha256.c` with the `okm_size < 255 * sizeof(t)` assertion |

## What it explains

- **Key derivation**: the watch's HKDF matches `derive_keys()` byte for byte; the split and the
  unused `miwear-bind` path are in [session.md](session.md#key-derivation).
- **Session lifetime**: the login FSM's 10 s timer, restarted once, is why every session ends
  ~20 s after auth ([session.md](session.md#lifetime)).
- **Mass channel**: the channel-2 receiver, its SiFli package-header checks and what a
  read-only open returns (`22/0`/`2/5` ACKed-and-ignored unless the request is complete) are
  in [mass-channel.md](mass-channel.md); an unsolicited `OP_READ` on channel 2 is valid at L1
  but not answered [hw 2.2.111 2026-11-23] ([channels.md](channels.md#findings)).

## Next

1. Decode the protobuf type/subtype jump tables (the command ids) and the login FSM
   transitions in the re-imported, pre-patched image
   ([firmware-symbols-lcpu.md](firmware-symbols-lcpu.md)).
2. Reproduce the app login/verify exchange (from the APK) so the FSM leaves
   `WAIT_APP_VERIFY` — that is what keeps a session alive.
3. ~~Mass push: match the APK's `MassDataDispatcher` framing to `FUN_12173a14`, then probe.~~
   Done — [mass-channel.md](mass-channel.md): channel 2 = opcode 1 raw bytes, armed by the
   `22/0` `DataUpload` handshake; a read-only open is ACKed-and-ignored on this watch.
4. Verify on hardware and record the result on its topic page ("Recording a finding" in
   `AGENTS.md`).
