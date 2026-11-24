# Architecture — `src/xiaomi_client.py`

How the client is built. This page describes the code; the protocol it speaks is described on
[protocol.md](protocol.md) (frames, channels), [session.md](session.md) (auth, keys,
encryption) and [arq.md](arq.md) (ACKs, windows).

One file, five layers. Each layer is used only by the one directly above it:

```
XiaomiWatch   connect, ARQ, dispatch, request/wait_for, listen
  └── Session         derive_keys (HKDF), AES-CTR, AES-CCM
        └── encode_v2 / parse_v2   SPP v2 frames, crc16_arc
              └── parse_v1 / V1_VERSION_REQUEST   version probe
                    └── Rfcomm      ctypes/libc socket, fill() → buf
```

## Layer 1 — `Rfcomm`

Opens the RFCOMM socket through `ctypes`/libc rather than `socket.socket`, for two reasons:
the `sockaddr_rc` struct (`_SockaddrRc`) is explicit and auditable, and it works on
interpreters without `socket.AF_BLUETOOTH` (uv-downloaded CPythons). The struct stores the MAC
**byte-reversed**; keep the reversal.

| Method | Does |
|---|---|
| `__init__(mac, channel, timeout=20)` | opens and connects the socket |
| `send(data)` | `os.write` to the fd |
| `fill(timeout) -> bool` | `select`, reads up to 4096 B, appends to `self.buf` |
| `close()` | closes the fd |

Every parser above consumes from the front of `buf`. An incomplete frame leaves its bytes for
the next call.

## Layer 2 — SPP v1 (`parse_v1`, `V1_VERSION_REQUEST`)

Only the version probe. The client aborts unless the watch reports v2. Bytes:
[protocol.md](protocol.md#spp-v1-version-probe).

## Layer 3 — SPP v2 framing (`encode_v2`, `parse_v2`, `crc16_arc`)

`encode_v2(ptype, seq, payload)` writes the 8-byte header and the CRC. `parse_v2(buf)` has two
result shapes on purpose:

- `None`: incomplete, wait for more bytes.
- `(None, 0, b"", n)`: junk or a CRC failure, consume `n` bytes. It resyncs on the next `A5 A5`.

`SESSION_START` is the app's 21-byte session config, kept byte for byte
([protocol.md](protocol.md#session-start-cmd-frames)). The channel-6 OTA codec
(`encode_ota_segment`, `parse_ota_segment`, `decode_ota_*`) sits beside this layer
([ota.md](ota.md)).

## Layer 4 — `Session`

| Member | Does |
|---|---|
| `__init__(secret)` | stores the auth key, draws a 16-byte `phone_nonce` |
| `set_keys(watch_nonce)` | `derive_keys()` → `dec_key`, `enc_key`, `dec_nonce`, `enc_nonce` |
| `ccm_encrypt(data, counter)` | AES-CCM, auth step 3 only |
| `encrypt_v2` / `decrypt_v2` | AES-CTR, a fresh cipher per message (`_ctr`) |
| `encrypted` | set after auth; nothing reads it — `send_command` decides on `type == 1` |

`derive_keys()` is HKDF written out with `hmac_sha256()` rather than `cryptography`'s HKDF, to
match the Java code exactly. The algorithms: [session.md](session.md).

## Layer 5 — `XiaomiWatch`

### `connect()`

```
[1] RFCOMM connect, channel 2
[2] v1 version probe → require SPP v2
[3] SESSION_START → wait for the watch's config
[4] auth step 1: phone nonce (1/26)
[5] auth step 2: check the watch HMAC, derive the keys
[6] auth step 3: proof + device info (1/27); then sess.encrypted = True
```

Auth always runs on channel 1: `l2_channel` is saved and restored around it. Messages:
[session.md](session.md#authentication).

### Sending

- `send_command(cmd)`: `type == 1` goes out plaintext (`OP_WRITE`), everything else encrypted
  (`OP_WRITE_ENC`), on `self.l2_channel`. Send non-auth commands only after `connect()`.
- `_send_data(opcode, payload)`: assigns the seq, stores the frame in `_sent` for
  retransmission, and returns `None` when the window is full (the caller pumps and retries).
  The CLI's `--send` calls it directly with `--opcode`, so it skips `send_command`.
- `request(t, s)`: an empty command, then `wait_for(t, s)`.

### `_pump(timeout)`, the receive loop

Reads frames until `timeout` passes without one, and never sleeps past a pending ACK or
retransmit deadline (`_flush_due`). Per frame type:

- **ACK / NACK**: release frames from `_sent`, or resend from the NAKed seq
  ([arq.md](arq.md#what-the-client-does)).
- **SESSION**: the watch's config; marks the session as up.
- **DATA**: in-order check (NAK or drop otherwise), ACK at once or delayed, decrypt opcode 2,
  write to `--capture`, then dispatch by channel. Channel 1 is parsed as `xiaomi_pb2.Command`
  into `inbox`; channel 6 goes to `_handle_ota`; every other channel is logged and dropped.

The receive side reads the channel as the low nibble of the first payload byte
(`payload[0] & 0x0F`).

### Waiting and listening

- `wait_for(type, subtype, timeout)`: pops the first match from `inbox`, pumping in 1-second
  steps. `subtype=None` matches any.
- `listen(seconds, keepalive)`: prints whatever arrives; `--keepalive` sends `2/1` every N
  seconds. It does not extend the session ([session.md](session.md#lifetime)).

## CLI

`main()` parses `--send TYPE SUBTYPE [--payload text_format]` (repeatable), `--channel`,
`--opcode`, `--timeout`, `--listen`, `--keepalive`, `--capture`, `--ota-require`, `--key-file`
and `-v`.
`build_command()` turns `--payload` into a `Command`, and `load_key()` reads
`secrets/auth_key.txt`. Flags and examples: [scripts.md](scripts.md).

## Generated protobuf bindings

`src/xiaomi_pb/` is generated from `proto/` by `make protos`: `xiaomi_pb2.py` (the root
`Command`) and `xiaomi/wear_*_pb2.py` (13 modules). It is a namespace package (no
`__init__.py`), the modules import each other as `from xiaomi import wear_*_pb2`, and
`xiaomi_client.py` puts `src/xiaomi_pb` on `sys.path`. Never hand-edit it. The protos are
`proto2`: set every `required` field before `SerializeToString()`, or it raises.
