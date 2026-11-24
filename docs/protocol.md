# Protocol — Xiaomi SPP v2 wire format

The bytes on RFCOMM channel 2: the L1 frame, the session-start exchange, the L2 channels and
opcodes, and the v1 version probe. What happens on top is elsewhere: auth and encryption in
[session.md](session.md), ACKs and retransmission in [arq.md](arq.md), command ids in
[commands.md](commands.md).

Source: [gb] (the client ports Gadgetbridge's Java SPP classes), matched by the app
[apk 9.8.348i] and used against the watch [hw 2.2.110 2026-11-20], unless tagged.

## Transport

| Layer | Protocol | Details |
|---|---|---|
| Physical | Bluetooth BR/EDR | Classic Bluetooth, not BLE |
| Link | RFCOMM | channel 2 (SDP `0x1101`, "BTS2 SPPA") |
| L1 | SPP v2 | `A5 A5` frames, ARQ |
| L2 | `[channel, opcode, payload]` | inside DATA frames |
| Payload | Protobuf (proto2) | `xiaomi.Command` on channel 1 |

## L1 frame

```
Offset  Size  Field    Description
0       2     magic    0xA5 0xA5
2       1     flags    (frx << 4) | type; frx 0 = NRX, 1 = FRX; the client sends frx 0
3       1     seq      sender's sequence number, 0-255, wraps
4       2     length   payload length, little-endian
6       2     crc      CRC-16/ARC over the payload (poly 0xA001, init 0)
8       N     payload
```

The header layout is `L1Packet.getBytes()` in the app [apk 9.8.348i].

| Type | Client name | App name | Purpose |
|---|---|---|---|
| 0 | NACK | NAK | out-of-order frame; the peer resends ([arq.md](arq.md)) |
| 1 | ACK | ACK | acknowledges DATA, cumulatively |
| 2 | SESSION | CMD | transport control: start/stop and config |
| 3 | DATA | DATA | an L2 packet |

## Session start (CMD frames)

The first payload byte of a type-2 frame selects the command [apk 9.8.348i]:

| CMD | Value | Meaning |
|---|---|---|
| `CMD_L1START_REQ` | 1 | the client opens the transport and sends its config TLVs |
| `CMD_L1START_RSP` | 2 | the peer accepts and sends its own |
| `CMD_L1STOP_REQ` / `_RSP` | 3 / 4 | teardown; the client does not use it yet, it drops RFCOMM |

Config TLVs are `type u8, length u16 LE, data`; `CONFIG_TYPE_*` is `1` VERSION, `2` MPS,
`3` TX_WIN, `4` SEND_TIMEOUT, `5` DEVICE_TYPE, `6` DEVICE_NAME. `SESSION_START` in
`src/xiaomi_client.py` is the 21-byte blob the app sends, captured rather than built: keep it as
it is.

### Session parameters

| Parameter | Client → watch | Watch → client [hw 2.2.110 2026-11-20] |
|---|---|---|
| Version | 1.0.0 | |
| Max packet (MPS) | `0xFC00` (64512 B) | `0x8000` (32768 B) |
| TX window | 32 | 3 |
| Send timeout | 10000 ms | 16000 ms |

The client accepts whatever valid config the watch sends. In practice a 24 KB frame already
closes the link ([arq.md](arq.md#measured)).

## L2 packet (DATA payload)

`channel u8, opcode u8, payload` (`L2Packet` [apk 9.8.348i]). The client, like Gadgetbridge,
uses only the low nibble of the channel byte [gb]. This is the one channel table; other pages
link here.

| Ch | Client | App `L2Packet.Channel` | Internal type | Encrypted | Purpose |
|---|---|---|---|---|---|
| 1 | `CH_PROTOBUF` | `TRANSPORT_CHANNEL_PB` | 100 plain / 101 enc | yes (101) | protobuf commands |
| 2 | `CH_DATA` | `TRANSPORT_CHANNEL_MASS` | 104 | no | mass data, file push ([channels.md](channels.md), [ota.md](ota.md)) |
| 3 | `CH_MASS_VOICE` | `TRANSPORT_CHANNEL_MASS_VOICE` | 103 | no | voice/audio payloads |
| 4 | `CH_FILE_SENSOR` | `TRANSPORT_CHANNEL_FILE_SENSOR` | 107 `TYPE_CAPTURE` | no | sensor files |
| 5 | `CH_ACTIVITY` | `TRANSPORT_CHANNEL_FILE_FITNESS` | 102 `TYPE_FITNESS` | no | activity files ([channels.md](channels.md)) |
| 6 | `CH_OTA` | `TRANSPORT_CHANNEL_OTA` | 105 | no | firmware update, `ota_type = 1` models ([ota.md](ota.md)) |
| 7 | `CH_NETWORK` | `TRANSPORT_CHANNEL_NETWORK` | 108 `TYPE_NET_PROXY` | no | phone as network proxy |
| 8 | `CH_LYRA` | `TRANSPORT_CHANNEL_LYRA` | 112 | yes | voice assistant |
| 9 | `CH_RESEARCH` | `TRANSPORT_CHANNEL_RESEARCH` | 113 | no | debug/research |

"Encrypted" is the app's `needEncrypt()` ([session.md](session.md#encryption)).

| Opcode | Client | Meaning |
|---|---|---|
| 1 | `OP_WRITE` | write, plaintext |
| 2 | `OP_WRITE_ENC` | write, AES-CTR encrypted |
| 3 | `OP_READ` | read; on channel 2 it is ACKed and unanswered ([channels.md](channels.md#findings)) [hw 2.2.111 2026-11-23] |

The client ACKs frames on every channel but decodes only channel 1 (protobuf) and channel 6
(OTA segments). The others are logged and dropped, and `--capture` is the only way to keep
them.

## SPP v1 version probe

`BA DC FE 00 C0 03 00 00 00 00 EF`: channel 0, flags `0xC0` (flag | needs-response), length 3,
opcode READ, serial 0, type 0. The watch answers with version bytes, `02 00 5f` on this watch.
The client requires v2 and aborts otherwise. v1 has no CRC and carries nothing else here.

## Protobuf command

On channel 1 the payload is a proto2 `xiaomi.Command` (from `proto/xiaomi.proto`):

```
required uint32 type = 1;  optional uint32 subtype = 2;
optional ... payload fields 3..25 ...;  optional uint32 status = 100;
```

The CLI builds payloads with `text_format.Parse`, so the caller names every field, and proto2
`required` fields must be set or `SerializeToString()` raises. The `(type, subtype)` ids are in
[commands.md](commands.md), and what the watch answers is in
[commands-tested.md](commands-tested.md).
