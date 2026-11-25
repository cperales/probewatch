# Scripts Reference

All device-facing scripts are standalone entrypoints in `src/`, run with `uv run python
src/<script>.py`. Each has a module docstring describing its purpose, prerequisites, and usage.
Offline tooling lives in `scripts/` ([Firmware tooling](#firmware-tooling)).

Every script that connects resolves its MAC the same way (`src/watch_secrets.py`): first
argument, then `$WATCH_MAC`, then the `MAC:` line in the git-ignored `secrets/device.md`.
`watch_secrets.py` is a shared helper, not an entrypoint.

## Discovery scripts

### `src/find_watch.py`

Active BLE scan that flags Xiaomi-looking advertisements. Detects the watch even with
random/private addresses by checking:

- Service UUID fragments: `fe95`, `fee0`, `fee1` (Xiaomi/Huami)
- Company ID: `0x038F` (Xiaomi), `0x0157` (Anhui Huami), `0x0B48` (Xiaomi alt)
- Name hints: `redmi`, `xiaomi`, `watch`, `mi `

```bash
uv run python src/find_watch.py [--timeout N]
```

### `src/scan.py`

Minimal BLE scan. Lists all devices and marks the target MAC from `secrets/device.md` with
`<== TARGET`. Prints service UUIDs, manufacturer data, service data, and TX power for the
target only.

```bash
uv run python src/scan.py
```

## Connection & pairing

### `src/pair_watch.py`

Interactive BlueZ pairing/trust automation. Drives `bluetoothctl` through `pexpect`, handles
the numeric-comparison passkey flow, and sets the device as trusted.

```bash
uv run python src/pair_watch.py [MAC] [--timeout N] [--direct]
```

| Flag | Effect |
|---|---|
| `--direct` | Skip scanning; use SDP query to page the watch directly (for watches bound to Mi Fitness) |

**Important**: Do **not** reset/unbind the watch from Mi Fitness — that regenerates the auth
key and invalidates `secrets/auth_key.txt`. Use `--direct` to pair without resetting.

### `src/watch_info.py`

Connect to the watch over BLE and read everything readable:

- All GATT services and characteristics (UUID, description, properties)
- Readable characteristic values (decoded as UTF-8 strings or hex)
- Standard SIG characteristic mapping (Device Name, Model Number, Serial Number, etc.)
- Heart-rate subscription (10 s) if the HRM characteristic is present
- Summary table at the end

```bash
uv run python src/watch_info.py [MAC] [--scan-timeout N]
```

Requires: phone Bluetooth off, watch advertising.

## Protocol queries

### `src/xiaomi_client.py`

Full SPP v2 client: RFCOMM connect → version probe → session negotiation → 3-step HKDF
authentication → protobuf queries.

```bash
uv run python src/xiaomi_client.py [MAC] [--channel 1] [--key-file PATH] [-v]
```

| Flag | Effect |
|---|---|
| `--channel N` | L2 channel (default 1 = protobuf; 6 = OTA) |
| `--opcode MODE` | `write` (default), `write_enc`, or `read` for `--send` |
| `--key-file PATH` | Auth key file (default `secrets/auth_key.txt`) |
| `--send TYPE SUBTYPE` | Send a command, repeatable; empty body unless `--payload` is given |
| `--payload TEXT` | `text_format` body for a single `--send` |
| `--ota-require` | Send the read-only OTA `REQUIRE` handshake on channel 6 and decode the reply |
| `--timeout SECONDS` | Per-command wait for a response (default 8) |
| `--listen SECONDS` | Print unsolicited channel-1 frames for this long after connecting |
| `--keepalive SECONDS` | During `--listen`, send a read-only query this often |
| `--capture [PATH]` | Record every frame, both directions, to NDJSON (default `captures/<timestamp>.ndjson`) |
| `-v` | Verbose: trace every TX/RX frame in hex |

Without `--send`, `--ota-require` or `--listen` it only connects and authenticates. A basic
read is `--send 2 2 --send 2 1` (device info, battery); the id catalogue is in
[commands.md](commands.md) and what the watch answered in [commands-tested.md](commands-tested.md).
`-v` traces every frame and is the first thing to use on protocol failures.

Channel 6 (OTA) speaks the app's own `0x5A` framing: `--ota-require` sends the read-only
`REQUIRE` handshake and prints the decoded page size, interval and timeout. That engine is
`ota_type = 1`; this watch reports `ota_type = 2` and updates over the mass channel, so expect
no answer on channel 6 ([ota.md](ota.md)).

### `src/probe_extra.py`

Extended query set: 20 additional Xiaomi protocol queries in a single authenticated session.
Queries device settings, workout types, widget configuration, activity data, health stats,
and more.

```bash
uv run python src/probe_extra.py [MAC] [--key-file PATH]
```

Each entry is a read-only status request (`Command(type, subtype)` with no payload): camera
remote status, password status, raise-to-wake, DND status, workout types, widget screens,
heart-rate settings, vitality score, real-time stats, and more. `find-device` is the one
side effect — it makes the watch ring — so it stays last in the list.

### `src/decode_capture.py`

Offline analysis of a `--capture` file. Prints per-channel frame counts, distinct lengths,
opcodes and interval medians; for channels other than 1 it also reports sample payloads,
which generated protobuf message accounts for a payload (strict round-trip, so unknown-field
noise does not count as a match), and whether the payloads form a u16 length-prefixed record
stream.

```bash
uv run python src/decode_capture.py captures/<file>.ndjson [--channel N] [--samples N]
```

Read-only and hardware-free. See [channels.md](channels.md) for the capture method and the
trigger matrix.

## Audio

### `src/audio_test.py`

Hands-Free Profile (HFP) audio test: play beeps, record from the watch mic, or loopback
(record then play back).

```bash
uv run python src/audio_test.py beep
uv run python src/audio_test.py record [-s 5]
uv run python src/audio_test.py loopback [-s 5]
```

| Mode | Effect |
|---|---|
| `beep` | Generate tones, play on watch speaker |
| `record` | Record from watch mic → `recordings/watch_mic_<timestamp>.wav` |
| `loopback` | Record then play back on the watch |

See [audio.md](audio.md) for SCO transport quirks and verification methods.

## Probing scripts

### `src/spp_probe.py`

Passive RFCOMM byte logger on channel 2. Connects to the SPP channel and prints every byte
the watch sends, without sending anything itself. Useful for observing protocol behavior.

```bash
uv run python src/spp_probe.py [MAC] [--channel 2] [--seconds 15]
```

Requires: Python with `AF_BLUETOOTH` (system interpreter).

### `src/a2dp_probe.py`

Read-only AVDTP probe over L2CAP PSM 25. Sends only DISCOVER and GET_CAPABILITIES commands,
then decodes and displays endpoints and codec capabilities (SBC, AAC, vendor-specific).

```bash
uv run python src/a2dp_probe.py [MAC]
```

Requires: Python with `AF_BLUETOOTH` (system interpreter).

## Firmware tooling

Offline tools under `scripts/`. They never touch the watch.

### `scripts/fetch_firmware_url.py`

Reproduces the app's `latest_ver` request (`POST hlth.io.mi.com/healthapp/device/latest_ver`)
and prints the JSON reply; `--download` saves the image and checks the server MD5.

```bash
uv run python scripts/fetch_firmware_url.py --fw-ver 2.2.110 [--download [PATH]]
```

Needs the `miothealth` account cookie (`cUserId`/`serviceToken`) in
`secrets/miot_health_cookie.txt`, `--cookie`, or `$MIOT_HEALTH_COOKIE`; without it the server
answers 401. `--print-curl` shows the equivalent request. See [ota.md](ota.md).

### `scripts/extract_firmware.py`

Unpacks a SiFli `ad ef cd af` package into `secrets/firmware/extracted/{hcpu,lcpu}.bin`,
verifying the size fields and aborting on mismatch instead of writing a short image.

```bash
uv run python scripts/extract_firmware.py [IMAGE] [--out DIR]
```

See [firmware.md](firmware.md) and [lcpu.md](lcpu.md).

### `scripts/pointer_density.py`

Counts the words that address the image itself over candidate load bases; a wrong base
collapses the count. Read-only.

```bash
uv run python scripts/pointer_density.py [--image hcpu|lcpu] [--shift OFFSET]
```

Result: [firmware.md](firmware.md#load-map-hcpu-verified).
