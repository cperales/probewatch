# Channels 2 and 5 — Capture and Analysis

SPP v2 DATA frames carry a one-byte channel id before the payload. Only channel 1
(`CH_PROTOBUF`, a `xiaomi.Command`) is decoded. Channels 2 (`CH_DATA`) and 5
(`CH_ACTIVITY`) are ACKed and then dropped, and nothing is known about their encoding,
their triggers or their cadence.

This page is the method for changing that: how to capture, what to capture and how to
read the result. Findings go at the bottom once they are measured on hardware.

## Why the console cannot see them

`--listen` drains `XiaomiWatch.inbox`, which only ever receives channel 1. A frame on any
other channel produces one line in the `-v` log and is discarded, so the only observability
is `--capture`, which writes every frame to a file.

## Capturing

```bash
uv run python src/xiaomi_client.py --capture                 # captures/<timestamp>.ndjson
uv run python src/xiaomi_client.py --capture run/workout.ndjson --listen 200
```

`--capture` records both directions for the whole connection, including the session
negotiation and the auth steps:

| Field | Meaning |
|---|---|
| `t` | seconds since the capture file was opened |
| `dir` | `rx` (from the watch) or `tx` (from us) |
| `type` | SPP v2 frame type: `0` NACK, `1` ACK, `2` SESSION, `3` DATA |
| `ch` | channel, DATA frames only |
| `op` | opcode: `1` plaintext, `2` encrypted, DATA frames only |
| `seq` | frame sequence number |
| `len`, `hex` | payload length and bytes |
| `note` | set on anomalies (e.g. a DATA frame too short to hold a channel/opcode) |

RX payloads are stored **after** decryption and TX payloads **before** encryption, so a
record is always the plaintext bytes and records are comparable whatever opcode was used.
Recording TX is what later separates "a reply to our request" from "a periodic push".

`captures/` is git-ignored on purpose: decrypted activity data is personal data. Do not
commit captures, and quote only truncated, anonymous samples in docs or tests.

Two behaviours to keep in mind on the watch side: a frame must be ACKed before anything
else happens (a missed ACK kills the link), and the capture file is flushed per record so a
dropped connection does not lose what was already written.

## Trigger matrix

Run one session per row, 2–5 minutes each, phone Bluetooth off and the watch worn. Record
how many frames each channel produced.

| Session | Why |
|---|---|
| Idle | Baseline: is there a periodic stream at all? |
| Walking | Steps and heart rate should change; expect accumulator or sample streams |
| Workout started on the watch | Strongest candidate for channel 5 activity data |
| Candidate request ids | `8/45`, `8/2`, `8/3`, `8/8`, `8/12`, `8/13`, `8/35`; note rejections |

The watch is a limited-firmware model — `2/23`, `2/25`, `2/34`, `2/78`, `2/79` all answer
`status: 1` — so do not assume a health request is implemented. Treat the request ids as
candidates and rely on watch-initiated traffic for the rest.

A session with zero frames on 2 and 5 is a result; count it.

## Analysing

```bash
uv run python src/decode_capture.py captures/<file>.ndjson
uv run python src/decode_capture.py captures/<file>.ndjson --channel 5 --samples 10
```

Per channel it prints frame count, distinct lengths, opcodes, the median interval and, for
channels that are not 1, sample payloads. Then two hypotheses:

- **Protobuf.** Every generated message is tried against every sample on the channel. A
  candidate must consume the whole payload, set at least one *known* field, expose the same
  fields in all samples and leave **no unknown fields** — unknown fields survive a parse and
  re-serialise, so without that last check almost any message looks like a match. Matches are
  ranked by how many known fields they decode and printed as a short list. Short payloads are
  inherently ambiguous (`08 02 10 01` is a valid `HourMinute` *and* a valid `DeviceState`), so
  treat the top of the list as a hypothesis and corroborate it with cadence and length.
- **Record stream.** The samples are concatenated and searched for a u16 length prefix at
  offsets 0–8, in both byte orders. Two or more records that consume the stream exactly is
  evidence; a single record is not.

If neither fits, look at fixed-width samples (a length of 1–2 bytes repeating at a steady
interval is heart rate, not a protobuf) and at whether the first bytes of a payload could be
a counter rather than a length.

## Findings

Measured 2026-11-20 on firmware 2.2.110, phone Bluetooth off: **13 sessions, ~243 s of
captured session time, 242 DATA frames — every one of them on channel 1.** Zero frames on
channel 2, zero on channel 5.

| Observation | Evidence |
|---|---|
| No frame on channel 2 or 5, in any scenario | Idle, keepalive, query matrix, live workout, after the workout |
| A session dies ~20–26 s after auth, whatever the traffic | Resets at 22.7, 23.0, 25.5 and 25.7 s; a keepalive every 3 s does not extend it. Cause is the LCPU login FSM's 10 s × 2 timeout ([lcpu.md](lcpu.md)) |
| After a reset the watch answers `EHOSTDOWN` for a few seconds | Immediate reconnect fails with errno 112; a retry ~10 s later connects |
| The idle heartbeat is `18/0`, once per second | Present in sessions with no traffic, absent while the `8/47` stream runs |
| Live health data is protobuf on **channel 1**, not channel 5 | `8/45` starts `8/47` `realTimeStats { steps calories heartRate }` every ~1 s; during a workout 74 samples tracked 0→112 bpm |
| A workout does not open a new channel | Four sessions during active squats: 114 frames, all channel 1, `steps`/`calories` at 0 |
| Activity files are never queued, even after saving the workout | `8/2` replies `activityRequestFileIds: ""` before, during and after; also with `activitySyncRequestToday { unknown1: 1 }` |
| Workout status is a status only | `8/29` → `workoutStatusWatchV2 { status: 0 }`; `8/26`, `8/50`, `8/53` → `status: 1`; `8/30` silent |
| `8/8`, `8/12`, `8/35`, `2/39` answer | Responses in the matrix capture |
| Channel 2 `OP_READ` is ACKed but silent | 2026-11-23: 4-byte `Command{0,0}` (`08001000`) with opcode 3 → L1 ACK, no channel-2 DATA, no reset within 4 s |

### Verdict

Channels 2 and 5 are **not** this firmware's live path: the real-time stream is protobuf on
channel 1 and a workout adds nothing. One probe extends the negative result to the read verb:
`OP_READ` on channel 2 is accepted at L1 and ignored by the application. The only untested use
left is bulk transfer — activity files, watchface images, notification icons — and
`activityRequestFileIds` is the pointer to it. Triggering that needs the phone-side sync sequence (what Mi Fitness sends to make the
watch produce a file id), which a Linux client cannot guess from the protos alone; it would
need a phone capture to reproduce.

Until that is available, the negative result stands: on this watch, with a Linux client
driving the session, channels 2 and 5 carry nothing.

Because of the lifetime cap, `--keepalive` exists (it keeps the session responsive but does
not extend it) and `--send` is repeatable, so a query matrix fits in one window. A capture
that ends in a reset is still written to disk.
