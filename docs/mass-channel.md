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
chunk, the watch self-clears when the session ends. The documented `2/5` reply codes (`0 ok,
2 already pushed, 3 error, 4 low battery`, [ota.md](ota.md)) stay unverified: reading them
needs a prepare with a real `version`/`md5`, which arms the firmware path, so it was not sent.

## Not in the client

The channel-2 chunk framing is channel + opcode + raw bytes, already covered by
`encode_v2` / `_send_data` ([architecture.md](architecture.md)); `DataUpload` is protobuf
(`xiaomi_pb`); the package header parser is `scripts/extract_firmware.py`. There is no separate
mass-channel codec to add, and the `START`/`DATA` push is deliberately not part of
`src/xiaomi_client.py`.
