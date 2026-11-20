# Mi Fitness APK — static analysis notes

What the official Android app (`com.xiaomi.wearable`, "Mi Fitness") reveals about the SPP v2
stack the watch speaks. Everything here is **static** (no APK is executed, no watch involved);
see [protocol.md](protocol.md) for the hardware-verified behaviour and [architecture.md](architecture.md)
for how `src/xiaomi_client.py` implements it.

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

## Layer 1 — frame and ARQ

`L1Packet.getBytes()` is authoritative for the 8-byte header:

```
magic u16      0xA5A5                      (constant -23131 as a signed short)
flags  u8      (frx << 4) | type           frx: 0 = NRX, 1 = FRX
seqNum u8
length u16     payload length, little-endian
crc    u16     CRC-16/ARC over the payload
```

`type` is `0` NAK, `1` ACK, `2` **CMD**, `3` DATA. `protocol.md` calls type 2 `SESSION`;
in the app it is `CMD`, and its first payload byte selects the command:

| CMD | Value | Meaning |
|---|---|---|
| `CMD_L1START_REQ` | 1 | client opens the transport, carries the config TLVs |
| `CMD_L1START_RSP` | 2 | peer accepts |
| `CMD_L1STOP_REQ` / `_RSP` | 3 / 4 | teardown |

Config TLVs are `type u8, length u16, data`, and `CONFIG_TYPE_*` is
`1` VERSION, `2` MPS, `3` TX_WIN, `4` SEND_TIMEOUT, `5` DEVICE_TYPE, `6` DEVICE_NAME. The
21-byte blob the app sends is exactly the `SESSION_START` already documented in
`protocol.md`: version `1.0.0`, MPS `64512`, window `32`, timeout `10000 ms`.

Beyond that blob the app runs a real selective-repeat ARQ, which our client does not:

| Constant | Value | Consequence |
|---|---|---|
| `SAR_DEFAULT_MPS` | 64512 | max payload per L1 frame |
| `SAR_DEFAULT_TX_WIN_LOCAL` / `_REMOTE` | 32 / 4 | local send window, peer's advertised window |
| `SAR_SEND_TIMEOUT` | 10 s | retransmit unacked DATA |
| `SAR_CUM_ACK_TIMEOUT` | 500 ms | cumulative ACK after a quiet burst |

Only DATA frames need ACKing; ACK immediately when `payload[0]` is `1` or `8` or when the
pending count reaches `window * 2/3`, otherwise delay. A DATA frame whose `seq - expected`
is `>= 128` (unsigned) is a stale duplicate and is dropped rather than NAKed; anything else
out of order gets a NAK and the peer retransmits from `txBase`. Sending more than 32 unacked
DATA frames is refused, so a bulk transfer stalls without window accounting.

## Layer 2 — channels and opcodes

`L2Packet` is `channel u8, opcode u8, payload`. The channel table is the useful part, because
our client only decodes channel 1 and drops the rest:

| Ch | `L2Packet.Channel` | Internal `ChannelType` | Notes |
|---|---|---|---|
| 1 | `TRANSPORT_CHANNEL_PB` | 100 plain / 101 encrypted | protobuf commands — what we use today |
| 2 | `TRANSPORT_CHANNEL_MASS` | 104 | mass data (see [channels.md](channels.md)) |
| 3 | `TRANSPORT_CHANNEL_MASS_VOICE` | 103 | voice/audio payloads |
| 4 | `TRANSPORT_CHANNEL_FILE_SENSOR` | 107 (`TYPE_CAPTURE`) | sensor file transfer |
| 5 | `TRANSPORT_CHANNEL_FILE_FITNESS` | 102 (`TYPE_FITNESS`) | activity files |
| 6 | `TRANSPORT_CHANNEL_OTA` | 105 | firmware/asset update |
| 7 | `TRANSPORT_CHANNEL_NETWORK` | 108 (`TYPE_NET_PROXY`) | phone-as-network proxy |
| 8 | `TRANSPORT_CHANNEL_LYRA` | 112 | voice assistant |
| 9 | `TRANSPORT_CHANNEL_RESEARCH` | 113 | debug/research |

Opcodes are `1` WRITE, `2` WRITE_ENC, and **`3` READ** — the third one is absent from our
client and from `protocol.md`. Send priorities are channel 1 → 2, channel 3 → 3, channel
7 → 1, everything else 0 (higher goes first among unassigned DATA).

## Encryption

`CipherApiCall` confirms the v2 rule we already use: `encryptDataV2`/`decryptDataV2` are
`AES-CTR(key, iv = key)` over each message independently. Only opcode 2 is encrypted, and
`needEncrypt(type)` is true for exactly two internal types: `101`, i.e. channel 1
(protobuf), and `112`, i.e. channel 8 (Lyra). Channels 2–7 and 9 normally travel with
opcode 1 (plaintext), so they need the ARQ but not the session key.

A separate v1 path still exists for the same types: IV is `deviceIV(8) ‖ 00000000 ‖ counter(4)`,
and for encrypted type 101 the ciphertext is prefixed with 2 bytes of that counter. Our
client never negotiates it, but the peer may speak it on older firmware.

## What this unlocks, and what it does not

- Channels 4, 5, 6, 7, 8 and 9 are reachable with the transport we already have; they need
  only the ARQ above plus a payload schema. `OTA` (6) and `FILE_FITNESS` (5) are the ones
  worth probing first, since they move bulk data.
- `OP_READ` (3) is a second verb on every channel — currently untested against the watch.
- The L1 `CMD_L1STOP_*` flow lets us close a session cleanly instead of dropping RFCOMM.
- **Not** recovered: the protobuf schemas. The app's watch messages are generated with a
  nano/javalite runtime that strips field and message names, so `strings` on the DEX yields
  no `miscSettingGet`/`widgetScreens`-style identifiers. Enumerating command ids means
  reading generated classes in the app module (`com.xiaomi.fitness.*`, largely obfuscated) —
  a separate, heavier pass.
