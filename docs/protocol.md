# Protocol Specification — Xiaomi SPP v2

This document describes the Xiaomi proprietary protocol running over Bluetooth Classic
RFCOMM channel 2 (SPP). It is a port of Gadgetbridge's Java implementation.

## Transport

| Layer | Protocol | Details |
|---|---|---|
| Physical | Bluetooth BR/EDR | Classic Bluetooth (not BLE) |
| Link | RFCOMM | Channel 2 (SDP UUID `0x1101`, "BTS2 SPPA") |
| Session | SPP v2 | Custom framing on top of RFCOMM |
| Payload | Protobuf | Google Protocol Buffers (proto2) |

## Frame Format (SPP v2)

Every frame on the wire follows this binary layout:

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

### Frame types

| Type | Name | Direction | Purpose |
|---|---|---|---|
| 0 | NACK | Watch → PC | Bad frame received; expects retransmission |
| 1 | ACK | PC → Watch | Acknowledges a DATA frame |
| 2 | SESSION | Both | Session configuration (START/ACK) |
| 3 | DATA | Both | Payload data (commands, responses) |

### CRC-16/ARC

```python
def crc16_arc(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc
```

Standard CRC-16/ARC (polynomial 0xA001, initial value 0).

## DATA frame payload

DATA frames carry a 2-byte header before the actual payload:

```
Byte 0: Channel (4 bits) | Flags (4 bits)
Byte 1: Opcode
Bytes 2+: Payload (plaintext or encrypted)
```

### Channels

| Channel | Name | Purpose |
|---|---|---|
| 1 | `CH_PROTOBUF` | Protobuf commands and responses |
| 2 | `CH_DATA` | Raw data (logged and dropped) |
| 5 | `CH_ACTIVITY` | Activity data (logged and dropped) |

### Opcodes

| Opcode | Name | Encryption |
|---|---|---|
| 1 | `OP_PLAIN` | None (auth commands only) |
| 2 | `OP_ENCRYPTED` | AES-CTR (all other commands) |

## SESSION frames

### Client → Watch: START_SESSION_REQUEST

Sent immediately after version probe. Captured from the official app:

```
Opcode: 1 (START_SESSION_REQUEST)
Version: 1.0.0
Max packet size: 0xFC00 (64000 bytes)
TX window: 32
Send timeout: 10000 ms
```

### Watch → Client: Session config ACK

The watch responds with its own session configuration. The client accepts any valid config.

## SPP v1 version probe

Before switching to v2 framing, the client sends a v1-format probe:

```
BA DC FE 00 C0 03 00 00 00 00 EF
```

| Byte | Value | Meaning |
|---|---|---|
| 0-2 | `BA DC FE` | V1 preamble |
| 3 | `0x00` | Channel 0 (version) |
| 4 | `0xC0` | Flags (flag bit + needsResponse) |
| 5-6 | `0x03 0x00` | Length = 3 (little-endian) |
| 7 | `0x00` | Opcode READ |
| 8 | `0x00` | Serial number |
| 9 | `0x00` | Data type |
| 10 | `EF` | V1 epilogue |

The watch responds with version bytes. The client requires version >= 2 and aborts otherwise.

## Protobuf command format

After authentication, all communication uses Google Protocol Buffers (proto2):

```protobuf
message Command {
  required uint32 type = 1;
  optional uint32 subtype = 2;

  optional Account auth = 3;
  optional System system = 4;
  optional Watchface watchface = 6;
  optional Health health = 10;
  optional Calendar calendar = 14;
  optional Music music = 20;
  optional Notification notification = 9;
  optional Weather weather = 12;
  optional Schedule schedule = 19;
  optional Rpk rpk = 22;
  optional Phonebook phonebook = 23;
  optional DataUpload dataUpload = 24;
  optional uint32 status = 100;
}
```

### Command types and subtypes

| Type | Subtype | Name | Direction |
|---|---|---|---|
| 1 | 26 | Auth step 1 (phone nonce) | PC → Watch |
| 1 | 27 | Auth step 3 (app confirm) | PC → Watch |
| 2 | 1 | Battery query | PC → Watch |
| 2 | 2 | Device info query | PC → Watch |
| 2 | 7 | Camera remote get | PC → Watch |
| 2 | 9 | Password status | PC → Watch |
| 2 | 14 | Misc setting get (dndSync) | PC → Watch |
| 2 | 24 | Raise-to-wake | PC → Watch |
| 2 | 28 | Simple-widgets | PC → Watch |
| 2 | 29 | Display-items | PC → Watch |
| 2 | 34 | DND status | PC → Watch |
| 2 | 39 | Workout types | PC → Watch |
| 2 | 51 | Widget screens | PC → Watch |
| 2 | 53 | Widget parts | PC → Watch |
| 2 | 78 | Device state | PC → Watch |
| 2 | 79 | Device state (full) | PC → Watch |
| 2 | 18 | Find device | PC → Watch |
| 7 | 43 | Goals config | PC → Watch |
| 8 | 2 | Activity today | PC → Watch |
| 8 | 3 | Activity past | PC → Watch |
| 8 | 8 | Heart-rate settings | PC → Watch |
| 8 | 12 | Standing reminder | PC → Watch |
| 8 | 13 | Goal notification | PC → Watch |
| 8 | 35 | Vitality score | PC → Watch |
| 8 | 45 | Real-time stats | PC → Watch |

## Authentication flow

The 3-step authentication uses the watch's auth key (from Mi Fitness) to derive session keys.

### Step 1: Phone nonce

```
PC → Watch: Command(type=1, subtype=26)
            { auth { appVerify { nonce = phone_nonce (16 B random) } } }

Watch → PC: Command(type=1)
            { auth { deviceVerify { nonce = watch_nonce (16 B), hmac = HMAC-SHA256(dec_key, watch_nonce||phone_nonce) } } }
```

The PC verifies the HMAC. If it doesn't match, the auth key is wrong.

### Step 2: Derive session keys

```
secret  = auth_key (16 bytes from secrets/auth_key.txt)
salt    = phone_nonce || watch_nonce (32 bytes)
info    = "miwear-auth"

HKDF-SHA256(secret, salt, info, 64) → 64 B, of which the first 40 are used:
    [dec_key(16) | enc_key(16) | dec_nonce(4) | enc_nonce(4)]
```

### Step 3: App confirm

```
PC → Watch: Command(type=1, subtype=27)
            {
              auth {
                appConfirm {
                  encryptedNonces = HMAC-SHA256(enc_key, phone_nonce||watch_nonce)
                  encryptedDeviceInfo = AES-CCM(companion_device_info, tag=4B)
                }
              }
            }

Watch → PC: Command(type=1, subtype=27)
            { auth { appConfirm { ... } } }
```

After step 3 succeeds, `encrypted = True` and all subsequent commands use AES-CTR encryption.
Auth commands (`type == 1`) are always sent plaintext; nothing auth-related follows step 3.

## Encryption details

### AES-CTR (normal traffic)

```python
cipher = Cipher(AES(key), CTR(key))  # key used as IV
encrypted = cipher.encryptor().update(data)
```

The 16-byte key is used **as the IV** for every message. There is no per-message counter
increment — each message starts from the same IV state. This is the Xiaomi convention.

### AES-CCM (auth step 3)

```python
nonce = enc_nonce || counter_hi (4 B) || counter_lo (4 B)
encrypted = AESCCM(key, tag_length=4).encrypt(nonce, data, None)
```

Tag length is 4 bytes (32 bits). Used only for the phone-info blob in auth step 3.

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

The protocol has two framing versions:

| Version | Preamble | CRC | Status |
|---|---|---|---|
| v1 | `BA DC FE ... EF` | None | Version probe only |
| v2 | `A5 A5` + header | CRC-16/ARC | Full protocol |

The client probes v1 first, then switches to v2 framing. Only v2 is implemented for
actual data transfer.
