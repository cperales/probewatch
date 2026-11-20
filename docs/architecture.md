# Architecture — `src/xiaomi_client.py`

The Xiaomi client is a single file with five distinct layers. Each layer is used only by the
one directly above it, forming a clean vertical stack.

```
XiaomiWatch (connect, request, close)
    └── Session (HKDF keys, AES-CTR encrypt/decrypt, AES-CCM)
            └── encode_v2 / parse_v2 (SPP v2 framing, CRC-16/ARC)
                    └── parse_v1 / V1_VERSION_REQUEST (SPP v1 version probe)
                            └── Rfcomm (ctypes/libc socket, fill buffer)
```

## Layer 1 — Rfcomm

Opens an RFCOMM socket via `ctypes`/libc rather than `socket.socket`. This serves two
purposes:

1. **Explicit `sockaddr_rc` struct**: The MAC address is stored **byte-reversed** in an
   explicit `ctypes.Structure`, making the layout auditable and correct.
2. **Works without `AF_BLUETOOTH`**: The raw-socket path works on interpreters that lack
   `socket.AF_BLUETOOTH` (e.g., CPython builds downloaded by `uv`).

```python
class Rfcomm:
    def __init__(self, mac, channel, timeout=20)  # opens socket, connects
    def send(self, data)                           # os.write to fd
    def fill(self, timeout) -> bool                # select-based read, appends to buf
    def close(self)                                # os.close(fd)
```

`fill()` uses `select.select()` to wait for data, reads up to 4096 bytes, and appends to
`self.buf`. Every parser below consumes from the front of this buffer. Incomplete frames
leave bytes in the buffer for the next call.

## Layer 2 — SPP v1 (version probe)

The watch reports its SPP protocol version via a v1-format probe. This layer handles only
that probe:

```
BA DC FE 00 C0 03 00 00 00 00 EF
```

- Channel 0 (version), flags 0xC0 (flag | needsResponse), length 3, opcode READ, serial 0
- The response payload contains the version bytes (e.g., `02 00 5f` = SPP v2)
- If the watch does not report v2, the client aborts (only v2 is implemented)

## Layer 3 — SPP v2 framing

Every frame on the wire follows this format:

```
A5 A5  [type] [seq] [length] [CRC-16]  [payload]
└─preamble┘ └─────── header ───────┘ └───────┘
```

| Field | Size | Description |
|---|---|---|
| Preamble | 2 B | `0xA5 0xA5` |
| Type | 1 B | `0`=NACK, `1`=ACK, `2`=SESSION, `3`=DATA |
| Sequence | 1 B | Incrementing per client TX |
| Length | 2 B | Payload length (little-endian) |
| CRC | 2 B | CRC-16/ARC over payload |

**Frame types**:

| Type | Direction | Purpose |
|---|---|---|
| NACK (0) | Watch → PC | Bad frame, expects retransmission |
| ACK (1) | PC → Watch | Acknowledges a DATA frame |
| SESSION (2) | Both | Session config (START/ACK) |
| DATA (3) | Both | Payload data |

**DATA payloads** start with `[channel, opcode]`:

| Byte | Value | Meaning |
|---|---|---|
| Channel | 1 | `CH_PROTOBUF` (protobuf commands) |
| | 2 | `CH_DATA` (ignored/dropped) |
| | 5 | `CH_ACTIVITY` (ignored/dropped) |
| Opcode | 1 | `OP_PLAIN` (unencrypted) |
| | 2 | `OP_ENCRYPTED` (AES-CTR encrypted) |

**SESSION_START** is a byte blob captured from the official app (not hand-crafted):

```
1  1 03 00 01 00 00    # version 1.0.0
2  02 00 00 FC         # max packet 0xFC00 (64000 B)
3  02 00 20 00         # tx window 32
4  02 00 10 27         # send timeout 10000 ms
```

## Layer 4 — Session (crypto)

The session layer handles key derivation and encryption. All crypto is derived from the
auth key stored in `secrets/auth_key.txt`.

### Key derivation (HKDF-SHA256)

```
secret = auth_key (32 hex chars → 16 bytes)
salt   = phone_nonce || watch_nonce  (32 bytes)
info   = "miwear-auth"
output = 64 bytes
used   = first 40 → [dec_key(16) | enc_key(16) | dec_nonce(4) | enc_nonce(4)]
         (the remaining 24 bytes are never read)
```

The HKDF implementation is manual (not using `cryptography`'s HKDF) to match the original
Gadgetbridge Java code exactly.

### Encryption

| Mode | When | Details |
|---|---|---|
| **AES-CTR** | Normal traffic (all encrypted DATA frames) | Key = the 16-byte key itself, used as the IV. No counter: every message restarts the keystream from the same IV. |
| **AES-CCM** | Phone-info blob in auth step 3 | Tag length = 4 B. Nonce = `enc_nonce || counter_hi || counter_lo`. |

### Session class

```python
class Session:
    def __init__(self, secret)           # generates phone_nonce (16 B random)
    def set_keys(watch_nonce)            # HKDF → dec_key, enc_key, dec_nonce, enc_nonce
    def ccm_encrypt(data, counter)       # AES-CCM encrypt (for auth step 3)
    def encrypt_v2(data)                 # AES-CTR encrypt (normal traffic)
    def decrypt_v2(data)                 # AES-CTR decrypt
```

## Layer 5 — XiaomiWatch (client)

The top-level client orchestrates the connection and query flow.

### `connect()` — 6-step handshake

```
[1] RFCOMM connect to MAC, channel 2
[2] Send v1 version probe → verify SPP v2
[3] Send SESSION_START → wait for session config ACK
[4] Auth step 1: send phone_nonce (type=1, subtype=26)
[5] Auth step 2: verify watch HMAC, derive session keys
[6] Auth step 3: send encrypted proof (type=1, subtype=27)
```

After step 6, `sess.encrypted = True` and every non-auth command is sent encrypted. Auth
commands (`type == 1`) always go out plaintext, which is why no further auth is sent.

### `_pump()` — frame dispatcher

Reads from `link.buf`, parses v2 frames, and dispatches:

- **ACK frames**: log sequence number
- **NACK frames**: log that watch expects a retransmission
- **SESSION frames**: mark session as established
- **DATA frames**: send ACK, decrypt if needed, parse as protobuf, queue in `inbox`

Every DATA frame receives an ACK from the client. Non-protobuf channels (2, 5) are logged
and dropped.

### `wait_for(type, subtype, timeout)`

Blocks until a matching command arrives in `inbox` or timeout expires. Calls `_pump()` in
1-second increments.

### `request(type, subtype, timeout)`

Sends an empty command (type/subtype only) and waits for the response.

### Command routing

Auth commands (`type == 1`) are sent **plaintext** on the protobuf channel. All other
commands are sent **encrypted**. This decision is made in `send_command()`.

## Generated protobuf bindings

`src/xiaomi_pb/` is generated from `proto/` and contains:

- `xiaomi_pb2.py` — root `Command` message (type, subtype, auth, system, health, etc.)
- `xiaomi/wear_*_pb2.py` — 13 submodule messages (account, calendar, clock, common,
  contact, fitness, mass, media, notification, system, thirdparty_app, watchface, weather)

The generated modules import each other as `from xiaomi import wear_*_pb2`. The directory
is a namespace package (no `__init__.py`). **Never hand-edit** these files.

Protos use `proto2` on purpose: every `required` field must be set before
`SerializeToString()` or it raises.
