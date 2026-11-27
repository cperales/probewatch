# Mass channel (2) — the `ota_type = 2` file push

The watch reports `ota_type = 2` ([device.md](device.md), [ota.md](ota.md)), so firmware,
watchfaces and other large blobs reach it over the **mass channel** — SPP v2 channel **2**,
the app's internal channel type **104** — after a protobuf control handshake on channel 1.
This page is the home for the channel-2 framing and what a read-only open returns on this
watch. Legal framing is [README.md](../README.md#legal).

Source: tagged per line — `[apk 9.8.348i]` for the app, `[fw 2.2.111]` for the image,
`[hw 2.2.111 2026-11-26]` for what was measured on the watch.

## The two halves

A transfer is a channel-1 protobuf handshake that *arms* the receiver, then the raw file
bytes streamed over channel 2. Channel 2 carries no application framing of its own — the
payload is the SiFli package itself.

### Control handshake (channel 1, protobuf)

`[gb]` `proto/xiaomi/wear_mass.proto`: `Command{type=22}` carries `DataUpload`
(`dataUpload`, field 24):

| Message | Fields |
|---|---|
| `DataUploadRequest` (22/0) | `type` (16 watchface, 50 notification icons, 32 firmware), `md5sum`, `size` |
| `DataUploadAck` (22/0) | `md5sum`, `errno` (0 = ready, non-zero = reject), `resumePosition`, `chunkSize` |

`DataUploadAck.chunkSize` is **4096** — measured on this watch `[hw 2.2.111 2026-11-26]` and
on the Redmi Watch 3 Active `[gb]` — the same 4 KB the watch flashes a page at (below). 22/1
is the "silent upgrade / music transfer" control and is not needed to open or close a transfer.

The firmware update additionally sends `Command{type=2, subtype=5}` first
(`System.firmwareInstallRequest{unknown1, unknown2, version, md5}`, field 16; reply
`firmwareInstallResponse{status}`, field 17) — see [ota.md](ota.md).

### Data push (channel 2)

`[apk 9.8.348i]` `RunningMassManager.sendMassData` → `massCall(massId, 104, data,
needResponse=false, …)`. `TaskQueueV2` maps internal type 104 → SPP **channel 2**; its
`needEncrypt` is only `101`/`112`, so mass uses opcode **1 (`OP_WRITE`, plaintext)**, not the
encrypted opcode 2. `SppTaskQueueV1` agrees. So a chunk is: channel 2, opcode 1, payload =
raw package bytes, no response expected (the L1 ARQ still ACKs, delayed — [arq.md](arq.md)).
`segmentLength` is caller-provided and bounded by `DataUploadAck.chunkSize`.

## What the watch does with the bytes

`[fw 2.2.111]` `l2_channel_dispatcher` (`0x1215a9c8`) routes channel 2 to the mass receiver
(`FUN_121104d4`), matching the app's channel map. The header event lands in
`mass_file_header_check` (`0x12173a14`, [lcpu.md](lcpu.md),
[firmware-symbols-lcpu.md](firmware-symbols-lcpu.md)):

- it runs only in FSM **state `0x20`**, which the receiver enters after a *complete*
  `DataUploadRequest` (type + `md5sum` + `size`) allocates the receive buffer;
- it clears a `0x140`-byte sub-file table, logs `mass_file_bin_header`, and requires the
  package header: word 0 == **`0xafcdefad`** (the SiFli magic) and header byte 6 == `0x02`
  (the version word `0x0002026f`, the same header `scripts/extract_firmware.py` parses);
- the header is **`0xa8` bytes**; a sub-file table of up to **10** records of `0x10` bytes
  each (`[u16 type][u16][u32 size][0x10 copied]`, types 1–12) maps each sub-file to a flash
  target;
- the chunk-write branch accumulates into **4 KB (`0x1000`) flash pages** and erases/writes in
  **1 KB (`0x400`)** sub-writes, four per page.

A mismatched magic or version logs `not_match_head` and raises the error flag; no bytes are
written.

## What an open returns on this watch

`[hw 2.2.111 2026-11-26]` probes with phone Bluetooth off, nothing resembling a firmware write
ever sent (no payload began `ad ef cd af`), no file chunk ever pushed; captures in `captures/`:

| Probe | Result |
|---|---|
| ARQ burst: 5× `2/1` back-to-back | seq increments, cumulative L1 ACKs, no NAK, no window stall |
| `22/0` `dataUpload{dataUploadRequest{type:16}}`, bare (no `md5sum`/`size`), plain **and** encrypted | L1-ACKed, **no `DataUploadAck`** — ACKed-and-ignored, encryption-independent |
| `22/0` complete: `dataUploadRequest{type:16 size:1024 md5sum:<16 B>}` (watchface) | **`dataUploadAck{errno:0, resumePosition:0, chunkSize:4096}`**, request md5 echoed |
| `2/5` minimal `system{firmwareInstallRequest{}}` (no version/md5) | L1-ACKed, **no `firmwareInstallResponse`**; the watch neither acted nor was left waiting (a follow-up read was normal) |

So the open is only answered once `DataUploadRequest` carries `size` **and** `md5sum`: a bare
request is ACKed-and-ignored (like the `OP_READ` on channel 2 in
[channels.md](channels.md#findings)), a complete one gets `errno: 0` (ready), the echoed md5,
`resumePosition: 0` and **`chunkSize: 4096`** — matching the firmware's 4 KB page. Pushing no
chunk, the watch self-clears when the session ends. Static analysis confirms the low-battery
rejection: the prepare handler gates on battery ≥ 30 % and rejects below it, and it does not
compare the `version` string ([ota.md](ota.md#watch-side-prepare-gate)).

The full push was then measured `[hw 2.2.111 2026-11-27]`: `--mass-push` sent the complete
`2/5` (`version` + `md5`) and got **`status 0`** (battery 89 %), then `22/0`
`dataUploadRequest{type:32}` got **`errno:0 chunkSize:4096`**, and 8193 B of a deliberately
**bad-magic** payload (not `ad ef cd af`) streamed on channel 2 as plaintext `OP_WRITE` chunks.
The watch armed and received it; the header check rejects the bad magic without writing flash,
and a follow-up read was normal — so the `2/5` `0 ok` code is now confirmed on hardware.

The `.bin` it carries is exactly `header (0xa8) + image0 + image1`, with **no separate
RSA-2048 signature blob** `[fw 2.2.111]`: the sub-file table (offset 8, ten 16-byte entries)
ends each entry in a 4-byte field, and the images are the raw HCPU and compressed LCPU streams.
So the package itself carries only 4-byte per-sub-file values; the signing gate (if enforced)
is against the flash `sec_configuration` (FCES header), not this file.

## How the official app sends it

`[apk 9.8.348i]` `MassDataDispatcher` drives the push **one segment at a time** (stop-and-wait):
`sendMassData` → wait for the socket-write callback → next segment. The per-segment timeout is
**40 s** (`elapsed > 40000 → onFail`) and `sendMassData` waits **12 s** (80 s on the play
channel), far longer than the watch's ~20 s session cut — which is what lets it survive a slow
link. It **resumes**: `DataUploadAck.resumePosition` is read as `sentLength` and the remaining
file is split from there. The file is cut into **10 MB rounds**, each prefixed with a 22-byte
header (type byte, file MD5, length) and suffixed with a CRC-32; `SppChannel` reports MTU
`16394` `[apk 9.8.348i]`. On the watch, the receiver (`FUN_121104d4`) restarts a **45 s**
inter-packet timer on every packet (`FUN_1215b11c(..., 45000, ...)`) and looks up an existing
context by data_id, so a 40 s gap fits inside 45 s and a reconnect can resume `[fw 2.2.111]`.

Measured `[hw 2.2.111 2026-11-27]`: across 9 dropped sessions the watch answered
`resumePosition 0` every time, so a reconnect restarts from 0 — partial firmware (type 32) is
**not** persisted across SPP sessions on this unit, and the app's `pauseMass`
(`Command{22,1}`, control 1) is the only explicit resume message (sent on stop/cancel).

## The client

The channel-2 chunk framing is channel + opcode + raw bytes, already covered by
`encode_v2` / `_send_data` ([architecture.md](architecture.md)); `DataUpload` is protobuf
(`xiaomi_pb`); the package header parser is `scripts/extract_firmware.py`, so there is no
separate mass-channel codec. The push itself is `XiaomiWatch.mass_push`, exposed as
`--mass-push PATH` (`2/5` prepare → `22/0` `DataUpload` → plaintext `OP_WRITE` chunks on
channel 2). It is the first **write** path in the client and is gated behind that explicit
flag; no test in `make check` runs it (the watch is only ever *read* here).
