# Mi Fitness APK — static analysis notes

What the official Android app (`com.xiaomi.wearable`, "Mi Fitness") reveals about the SPP v2
stack the watch speaks. Everything here is **static**: no APK is executed and no watch is
involved. This page is the source record; the facts read from the app live on their topic pages,
tagged [apk 9.8.348i].

Legal framing is [README.md](../README.md#legal): interoperability with a watch we own.

## Artifact and provenance

| Fact | Value |
|---|---|
| Package / version | `com.xiaomi.wearable` 9.8.348i (versionCode 908348) |
| Source | APKPure CDN (`d.apkpure.net`), not a repackager |
| Size | 133,183,199 B (equals the CDN's declared `full_size`) |
| SHA-256 | `42958d4589654d9a9317b9b777f0a8b3c2637b8c8b11229308f9aea4143c2a33` |
| Signing | APK Signature Scheme v2, one signer; subject `C=CN, O=北京小米科技有限责任公司, OU=软件部, CN=管理员`; cert 2010-03-28 → 2035-03-22; cert SHA-256 `b031fe98a4dbb0d4d82661787f25de643182b378e9ef632d8adea75aab58f2d8` |
| Manifest | minSdk 26, targetSdk 34; 47,681 classes, 10,390 resources |

The signer is Xiaomi's shipping certificate and the v2 content digest matches the bytes on
disk; the inspecting tool does **not** verify signatures cryptographically, so treat the
certificate as *declared*, not proven. The APK lives in `secrets/apk/` (git-ignored).

## Where the protocol lives

`com.xiaomi.wearable.*` is the **miwear-core** SDK — Kotlin, and the transport package keeps
its real names (unlike most of the app):

| Package | Role |
|---|---|
| `com.xiaomi.wearable.spp` | RFCOMM client (`00001101-…`, standard SPP), v1 version probe |
| `com.xiaomi.wearable.transport.layerl0` | Channel abstraction, MTU fragmentation, rx reassembly |
| `com.xiaomi.wearable.transport.layerl1` | `A5 A5` frames + selective-repeat ARQ |
| `com.xiaomi.wearable.transport.layerl2` | `[channel, opcode, payload]` |
| `com.xiaomi.wearable.transport.queue` | `TaskQueueV2`: per-channel routing, encryption |
| `com.xiaomi.wearable.wear.api` | `CipherApiCall`: AES-CTR / auth |

## What the app gave, and where it is recorded

| Finding | Page |
|---|---|
| L1 header (`L1Packet.getBytes()`, the `frx` flag), `CMD` start/stop frames and config TLVs; `SESSION_START` is exactly the app's 21-byte blob | [protocol.md](protocol.md#l1-frame) |
| `L2Packet` channel table, internal types, opcodes | [protocol.md](protocol.md#l2-packet-data-payload) |
| Selective-repeat ARQ: `SAR_*` constants, delayed ACKs, NAK, duplicate drop, send priorities | [arq.md](arq.md) |
| `CipherApiCall`: AES-CTR with IV = key, `needEncrypt()` per channel, the v1 IV path | [session.md](session.md#encryption) |
| Command ids: 379 construction sites of the `Command` envelope (`defpackage.t1i`) | [commands.md](commands.md) |
| OTA engines, version check, channel-6 protocol | [ota.md](ota.md) |

## What this enables, and what it does not

- Channels 3–9 are reachable with the transport the client already has (the ARQ is
  implemented); each needs a payload schema. `OTA` (6) and `FILE_FITNESS` (5) move bulk data;
  this watch updates over the mass channel instead ([ota.md](ota.md)).
- `OP_READ` (3) is a second verb on every channel. On channel 2 it is ACKed and not answered
  ([channels.md](channels.md#findings)).
- The L1 `CMD_L1STOP_*` flow would close a session cleanly instead of dropping RFCOMM.
- **Not** recovered: the protobuf schemas. The app's watch messages use a nano/javalite runtime
  that strips field and message names, so `strings` on the DEX yields no
  `miscSettingGet`/`widgetScreens`-style identifiers. Field numbers still come from
  Gadgetbridge's protos.
- **Recovered**: the command ids. Feature code builds the envelope as `new t1i(); c = TYPE;
  d = SUBTYPE` and sends it through `DeviceContact.call` → `ContactTaskQueue` →
  `IMiWearCoreClient.call`; tracing `t1i.<init>` gives the catalogue in
  [commands.md](commands.md).
