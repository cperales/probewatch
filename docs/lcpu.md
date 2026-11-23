# LCPU firmware — the Bluetooth/SPP side

The second image in the 2.2.111 package (see [firmware.md](firmware.md)) is the core that runs
the Bluetooth stack: SPP, the protobuf dispatcher, the login/auth FSM, the mass-file receiver
and the L2 channel routing. This page records what static analysis found and what one read-only
hardware probe confirmed. Legal framing is [README.md](../README.md#legal).

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
| Login FSM | `MIWEAR_LOGIN_FSM_START/WAIT_APP_VERIFY/WAIT_APP_CONFIRM`; arms a **10 000 ms** timer (`FUN_12157c04(inst, 10000)` at `0x12003b5e`); `login_fsm_timeout_handler` (`0x1200390e`) sets state 3 and frees the login session |
| Auth HKDF | `FUN_121cf810` (HKDF-SHA256 expand, 32-byte blocks, `okm_size < 255*32`); the auth call at `0x12003d7c` uses info **`miwear-auth`**, 64-byte output; a second call uses `miwear-bind` |
| L2 routing | `FUN_1215a9c8` switches on channel 1–7 and routes PB/MASS/OTA/NETWORK to handlers, logging via the SAR table at `0x1215aab0` |
| Mass-file receiver | `FUN_12173a14`: the header event requires state `0x20`, clears a `0x140`-byte buffer, logs `mass_file_bin_header=…` and validates the first word against **`0xafcdefad`** (the SiFli package magic) |
| HKDF source | `hkdf_sha256.c` with the `okm_size < 255 * sizeof(t)` assertion |

## Auth and session lifetime

The watch derives the session key exactly like `derive_keys()` in `src/xiaomi_client.py`:
HKDF-SHA256 with IKM = the 16-byte auth key, salt = `rand_app ‖ rand_dev` (2 × 16 B, built by two
16-byte copies), info = `miwear-auth` (11 B), L = 64. The watch names the split
`session_key.dev_key` / `app_key`. The `miwear-bind` derivation belongs to the companion-device
binding path, which this client does not use.

Why sessions die at ~20 s: the client completes device auth, but the **login FSM** waits in
`WAIT_APP_VERIFY`/`WAIT_APP_CONFIRM` for the Mi Fitness app-level exchange. The FSM's 10 s
timer fires, `SCHD_EVT_ADMIN_LOGIN_RESTART` restarts it once, and the second timeout frees the
login session and the link drops — matching the measured 20–26 s. The Linux client never sends
the app verify/confirm, so every session ends this way. Measured 2026-11-23: auth at 2.44 s,
last frame at 25.47 s (**~23 s post-auth**) with a keepalive every 3 s — traffic does not
extend it.

## Hardware probe (read-only)

2026-11-23, firmware 2.2.111, phone Bluetooth off. Connect + auth succeeded; `OP_READ` (3) on
**channel 2** with a 4-byte `Command{0,0}` (`08001000`) was ACKed at L1, produced no channel-2
DATA and did not reset within 4 s. An unsolicited mass-channel read is transport-valid but not
answered — consistent with [channels.md](channels.md).

## Next

1. Patch absolute words by `-0x26000`, re-import the full image, and decode the protobuf
   type/subtype jump tables (the command ids) and the login FSM transitions.
2. Reproduce the app login/verify exchange (from the APK) so the FSM leaves
   `WAIT_APP_VERIFY` — that is what keeps a session alive.
3. Mass push: match the APK's `MassDataDispatcher` framing to `FUN_12173a14`, then probe.
4. Verify on hardware and update `DETAILS.md` with measured facts.
