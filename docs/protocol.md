# Protocol Specification — Xiaomi SPP v2

Xiaomi's proprietary protocol over Bluetooth Classic RFCOMM channel 2 (SPP), a port
of Gadgetbridge's Java implementation.

## Transport

| Layer | Protocol | Details |
|---|---|---|
| Physical | Bluetooth BR/EDR | Classic Bluetooth (not BLE) |
| Link | RFCOMM | Channel 2 (SDP UUID `0x1101`, "BTS2 SPPA") |
| Session | SPP v2 | Custom framing on top of RFCOMM |
| Payload | Protobuf | Google Protocol Buffers (proto2) |

## Frame Format (SPP v2)

```
Offset  Size    Field       Description
------  ------  ----------  --------------------------------
0       2       Preamble    0xA5 0xA5
2       1       Type        Frame type (see below)
3       1       Sequence    Client TX sequence (0-255, wraps)
4       2       Length      Payload length (little-endian)
6       2       CRC         CRC-16/ARC over payload
8       N       Payload     Frame-specific data
```

| Type | Name | Direction | Purpose |
|---|---|---|---|
| 0 | NACK | Watch → PC | Bad frame received; expects retransmission |
| 1 | ACK | PC → Watch | Acknowledges a DATA frame |
| 2 | SESSION | Both | Session configuration (START/ACK) |
| 3 | DATA | Both | Payload data (commands, responses) |

CRC is standard CRC-16/ARC (polynomial 0xA001, initial value 0).

## DATA frame payload

```
Byte 0: Channel (4 bits) | Flags (4 bits)
Byte 1: Opcode
Bytes 2+: Payload (plaintext or encrypted)
```

| Channel | Name | Purpose |
|---|---|---|
| 1 | `CH_PROTOBUF` | Protobuf commands and responses |
| 2 | `CH_DATA` | Raw data (logged and dropped) |
| 5 | `CH_ACTIVITY` | Activity data (logged and dropped) |

| Opcode | Name | Encryption |
|---|---|---|
| 1 | `OP_PLAIN` | None (auth commands only) |
| 2 | `OP_ENCRYPTED` | AES-CTR (all other commands) |

NACK retransmit: the client stores the full encoded DATA frame (channel + opcode +
encrypted payload) under its seq and resends it verbatim, once per seq.

Channels 2 and 5 are ACKed and then dropped; `--capture` is the only way to record them.
See [channels.md](channels.md) for the capture format, trigger matrix and analysis.

## SESSION frames

Client → Watch START_SESSION_REQUEST (after the version probe): opcode 1, version
1.0.0, max packet 0xFC00, TX window 32, send timeout 10000 ms. The watch replies with
its own config; the client accepts any valid config.

## SPP v1 version probe

`BA DC FE 00 C0 03 00 00 00 00 EF` (channel 0, flags 0xC0, length 3, opcode READ,
serial 0, type 0). The watch replies with version bytes; the client requires >= 2.

## Protobuf command format

After auth all traffic is proto2 `Command { required uint32 type = 1; optional uint32
subtype = 2; optional System system = 4; ... optional uint32 status = 100; }`.
Payloads are built with `text_format.Parse`, so the caller names every field.

| Type/Subtype | Name |
|---|---|
| 1/26, 1/27 | Auth steps 1 and 3 |
| 2/1 | Battery |
| 2/2 | Device info |
| 2/14 | Misc setting get |
| 2/15 | Misc setting set |
| 2/18 | Find device |
| 2/23 | DND mode set (Gadgetbridge) |
| 2/24 | Raise-to-wake get |
| 2/25 | Raise-to-wake set (proto comment) |
| 2/34 | DND status (proto comment) |
| 2/39 | Workout types |
| 2/51 | Widget screens |
| 2/53 | Widget parts |
| 4/0 | Watchface list |
| 4/1 | Watchface set/ack |
| 4/2 | Watchface delete |
| 4/4 | Watchface install status |

## Hardware verification (Redmi Watch 5 Active, firmware 2.2.110)

Tested with `src/xiaomi_client.py --send TYPE SUBTYPE [--payload ...]`. The watch is a
limited-firmware model; several proto settings are not implemented.

| Command | Result |
|---|---|
| 2/1, 2/2, 2/14, 2/18, 2/39, 2/51, 2/53 | ✓ data response |
| 2/24 (raise-to-wake get) | ✓ `raiseToWake { mode: 2 start 8:00 end 22:00 }` |
| 2/25 (raise-to-wake set) | ✗ transport ACK, no reply; value unchanged |
| 2/23, 2/34 (DND) | ✗ `status: 1` |
| 2/78, 2/79 (device state) | ✗ `status: 1` |
| 8/2 (activity today) | ✓ `activityRequestFileIds: ""` always, including after a saved workout |
| 8/3 (activity past) | ✗ no answer |
| 8/29 (workout status v2) | ✓ `workoutStatusWatchV2 { status: 0 }` |
| 8/26, 8/30, 8/50, 8/53 | ✗ `status: 1` / no answer |
| 8/8, 8/12, 8/35 | ✓ data response |
| 8/45 (real-time stats) | no reply; starts the `8/47` stream |
| 8/47 (unsolicited) | ✓ `realTimeStats { steps calories heartRate }` every ~1 s |
| 4/0 (watchface list) | ✓ `watchfaceList` with 4 faces |
| 4/1 (watchface set) | ACK `ack: 1`; not the list |
| 4/4 (install status) | ✓ empty `watchface {}` |

### Verified outbound writes

Each is read → write → reconnect → read back → restore, in separate sessions.

Find-device (no persistent state):

```
uv run python src/xiaomi_client.py --send 2 18       # -> status: 0, watch rings
```

DND sync (2/14 get setting 2, 2/15 set). Original `enabled: 0`:

```
uv run python src/xiaomi_client.py --send 2 14 --payload 'system { miscSettingGet { setting: 2 } }'
uv run python src/xiaomi_client.py --send 2 15 --payload 'system { miscSettingSet { dndSync { enabled: 1 } } }'   # -> status: 0
uv run python src/xiaomi_client.py --send 2 14 --payload 'system { miscSettingGet { setting: 2 } }'              # -> enabled: 1
uv run python src/xiaomi_client.py --send 2 15 --payload 'system { miscSettingSet { dndSync { enabled: 0 } } }'   # restore
uv run python src/xiaomi_client.py --send 2 14 --payload 'system { miscSettingGet { setting: 2 } }'              # -> enabled: 0
```

Notification settings (2/14 get setting 1, 2/15 set). Original `2/1/1`:

```
uv run python src/xiaomi_client.py --send 2 15 --payload 'system { miscSettingSet { miscNotificationSettings { wakeScreen: 1 onlyWhenPhoneLocked: 2 onlyWhenWorn: 2 } } }'
uv run python src/xiaomi_client.py --send 2 14 --payload 'system { miscSettingGet { setting: 1 } }'
uv run python src/xiaomi_client.py --send 2 15 --payload 'system { miscSettingSet { miscNotificationSettings { wakeScreen: 2 onlyWhenPhoneLocked: 1 onlyWhenWorn: 1 } } }'
uv run python src/xiaomi_client.py --send 2 14 --payload 'system { miscSettingGet { setting: 1 } }'
```

Payload constraints: `HourMinute` requires both `hour` and `minute`; `wakeScreen`
0 ignore / 1 enable / 2 disable, `onlyWhenPhoneLocked` 0 ignore / 1 enable / 2 disable,
`onlyWhenWorn` 1 enable / 2 disable. `DoNotDisturb.status` is 0 enabled / 2 disabled.
The watch does not implement the writes for 2/23, 2/25, 2/34, 2/78 or 2/79: every DND
variant returns `status: 1` and leaves `dndSync.enabled` unchanged. Full attempts are in
`DETAILS.md`.

## Authentication flow

3-step auth uses the watch's auth key (from Mi Fitness):

```
PC → Watch: Command(1,26) { auth { appVerify { nonce = phone_nonce (16 B) } } }
Watch → PC: Command(1)   { auth { deviceVerify { nonce, hmac } } }

HKDF-SHA256(auth_key, phone_nonce||watch_nonce, "miwear-auth", 64)
  → [dec_key(16) | enc_key(16) | dec_nonce(4) | enc_nonce(4)]

PC → Watch: Command(1,27) { auth { appConfirm {
  encryptedNonces = HMAC(enc_key, phone_nonce||watch_nonce),
  encryptedDeviceInfo = AES-CCM(device_info, tag=4) } } }
```

After step 3 `encrypted = True`; auth commands (`type == 1`) stay plaintext.

## Encryption details

AES-CTR uses the 16-byte key itself as the IV for every message, no counter increment.
AES-CCM (auth step 3 only) uses nonce = `enc_nonce || counter_hi(4) || counter_lo(4)`
with a 4-byte tag.

## Session parameters

| Parameter | Value | Source |
|---|---|---|
| Max packet size | 0xFC00 (64000 B) | Client → Watch |
| TX window | 32 | Client → Watch |
| Send timeout | 10000 ms | Client → Watch |
| Watch max packet | 0x8000 (32768 B) | Watch → Client |
| Watch TX window | 3 | Watch → Client |
| Watch timeout | 16000 ms | Watch → Client |

## Protocol evolution

| Version | Preamble | CRC | Status |
|---|---|---|---|
| v1 | `BA DC FE ... EF` | None | Version probe only |
| v2 | `A5 A5` + header | CRC-16/ARC | Full protocol |

The client probes v1 first, then switches to v2 framing. Only v2 carries data.
