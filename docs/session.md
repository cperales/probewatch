# Session — handshake, auth, keys and lifetime

How an RFCOMM connection becomes an authenticated, encrypted session, and how long the watch
keeps it. The frames underneath are in [protocol.md](protocol.md), retransmission is in
[arq.md](arq.md), and the code that does this is in [architecture.md](architecture.md).

Source: [gb] (the client ports Gadgetbridge's Java auth), confirmed on the watch
[hw 2.2.110 2026-11-20], unless tagged.

## Handshake

1. RFCOMM to channel 2, the SPP service (SDP `0x1101`, see [device.md](device.md#sdp-services)).
2. SPP v1 version probe; the watch answers `02 00 5f` = SPP v2
   ([protocol.md](protocol.md#spp-v1-version-probe)).
3. L1 `START` with the `SESSION_START` blob; the watch answers with its own config
   ([protocol.md](protocol.md#session-start-cmd-frames)).
4. Three auth messages on channel 1, always plaintext (`type == 1`).

## Authentication

The auth key is 16 bytes (32 hex chars in `secrets/auth_key.txt`), taken from Mi Fitness.
Resetting or unbinding the watch regenerates it. Pairing the PC directly by MAC
(`src/pair_watch.py --direct`) keeps it valid.

```
PC → Watch: Command(1,26) { auth { appVerify { nonce = phone_nonce (16 B random) } } }
Watch → PC: Command(1)    { auth { deviceVerify { nonce = watch_nonce, hmac } } }
            keys = HKDF(auth_key, phone_nonce ‖ watch_nonce)          (below)
            check hmac == HMAC-SHA256(dec_key, watch_nonce ‖ phone_nonce)  → wrong key if not
PC → Watch: Command(1,27) { auth { appConfirm {
              encryptedNonces     = HMAC-SHA256(enc_key, phone_nonce ‖ watch_nonce),
              encryptedDeviceInfo = AES-CCM(enc_key, CompanionDevice) } } }
Watch → PC: Command(1,27) { auth { ... } }
```

After the last reply every command except `type == 1` is encrypted. The watch's capability
fields: `device_capability: 52851550` is fixed; `device_capability_2` appears only in some
sessions and varies (e.g. `20697`) [hw 2.2.111 2026-11-24].

## Key derivation

HKDF-SHA256 with IKM = the auth key, salt = `phone_nonce ‖ watch_nonce` (32 B), info =
`"miwear-auth"`, L = 64. Only the first 40 bytes are used:
`dec_key(16) | enc_key(16) | dec_nonce(4) | enc_nonce(4)`. `derive_keys()` implements it with
HMAC by hand, to match the Java code byte for byte.

The watch derives the same thing [fw 2.2.111]: `hkdf_sha256.c`, info `miwear-auth` (11 B),
the salt built from two 16-byte copies, and the split named `session_key.dev_key` / `app_key`.
A second derivation with `miwear-bind` belongs to companion binding, which this client does not
use. Disassembly evidence: [lcpu.md](lcpu.md#protocol-code-verified-by-disassembly).

## Encryption

| Mode | Used for | Detail | Source |
|---|---|---|---|
| AES-128-CTR | every opcode-2 DATA payload | IV = the key itself, for every message; the keystream restarts per message | [gb], same as `CipherApiCall.encryptDataV2` [apk 9.8.348i] |
| AES-CCM | the `CompanionDevice` blob in auth step 3 only | 4-byte tag; nonce = `enc_nonce ‖ u32 0 ‖ u32 LE counter` | [gb] |

Which traffic is encrypted [apk 9.8.348i]: `needEncrypt(type)` is true only for internal types
101 (channel 1, protobuf) and 112 (channel 8, Lyra). Channels 2–7 and 9 normally travel as
opcode 1, plaintext.

The app also keeps a v1 path [apk 9.8.348i]: IV = `deviceIV(8) ‖ 00000000 ‖ counter(4)`, and
encrypted type-101 ciphertext is prefixed with 2 bytes of that counter. The client never
negotiates it; older firmware may speak it.

## Lifetime

| Fact | Detail | Source |
|---|---|---|
| The watch closes the link ~20–26 s after auth, with or without traffic | resets at 22.7, 23.0, 25.5 and 25.7 s; a `--keepalive` every 3 s keeps the exchange going but does **not** extend the session | [hw 2.2.110 2026-11-20] |
| Same cap with a keepalive | auth at 2.44 s, last frame at 25.47 s (~23 s after auth), keepalive every 3 s | [hw 2.2.111 2026-11-23] |
| Steadier on 2.2.111 | 7 idle sessions (`--listen 40`): 6 closed 22.1–22.4 s after auth, one at 12.4 s; still independent of traffic | [hw 2.2.111 2026-11-24] |
| Cause | the LCPU login FSM waits in `WAIT_APP_VERIFY`/`WAIT_APP_CONFIRM` for Mi Fitness's app-level exchange, which this client never sends; its 10 s timer fires, `SCHD_EVT_ADMIN_LOGIN_RESTART` restarts it once, and the second timeout frees the login session and the link | [fw 2.2.111] |
| Reconnecting | the first attempts after a reset fail with `EHOSTDOWN` (errno 112); a retry ~10 s later connects | [hw 2.2.110 2026-11-20] |
| Idle heartbeat | `18/0` (an empty Music command) about once per second while the link is idle; absent while other traffic flows | [hw 2.2.110 2026-11-20] |
| No heartbeat on 2.2.111 | none in 7 sessions (3 with the watch worn): only the two auth frames arrived | [hw 2.2.111 2026-11-24] |

Consequences: long experiments run in windows of ~20 s, `--send` is repeatable so a query matrix
fits in one session, and a capture that ends in a reset is still written to disk. Keeping a
session alive needs the app's login verify/confirm exchange (next steps in
[lcpu.md](lcpu.md#next)).
