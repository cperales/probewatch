# ProbeWatch

**Unofficial Linux probes for the Redmi Watch 5 Active (M2351W1).**

ProbeWatch discovers, pairs, queries, and streams audio from the watch over Bluetooth — BLE
discovery, BlueZ pairing, RFCOMM/L2CAP probes, and a full Python port of Xiaomi's SPP v2
protocol (framing, HKDF authentication, AES encryption, protobuf commands). Device-specific
identifiers are not in the repository; they live in the git-ignored `secrets/` directory.

ProbeWatch is a personal, unofficial hobby project: reverse engineering done on a watch I own, to
use it from Linux in the spirit of [Gadgetbridge](https://codeberg.org/Freeyourgadget/Gadgetbridge).
It reads state and talks to the device; it does not unlock or modify it.

The repository is its own agent harness: `make check` (ruff, doc-link check, pytest, a
context-size budget, `compileall`) needs no watch and is exactly what CI runs. Hardware
behaviour still has to be verified by running a script against the watch.

## Documentation

`docs/` holds the long-form docs: [index](docs/README.md), [overview](docs/overview.md),
[setup](docs/setup.md), [scripts reference](docs/scripts.md),
[architecture](docs/architecture.md), [protocol spec](docs/protocol.md), and
[audio notes](docs/audio.md).

## Prerequisites

- The watch must be **paired and trusted** with this PC. Use `src/pair_watch.py --direct` when
  the watch is still bound to Mi Fitness (it won't advertise then, so discovery-based
  pairing fails).
- **Never reset / unbind the watch from Mi Fitness** — that regenerates the auth key and
  invalidates `secrets/auth_key.txt`. `--direct` exists precisely to avoid this.
- **Phone Bluetooth must be off** — the watch talks to one client at a time and stops
  advertising while connected to the phone.
- `secrets/auth_key.txt` (32 hex chars) is required by `src/xiaomi_client.py`. It is git-ignored.
- Local identifiers — the watch MAC, its serial number, and any other watch seen in range —
  live in `secrets/device.md` (git-ignored). Every script reads the `MAC:` line from it when no
  MAC is given on the command line; `WATCH_MAC` in the environment overrides the file.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and a Python with Bluetooth support.

```bash
# .venv from the distro interpreter, fetch proto/ + generate src/xiaomi_pb/
make setup
make protos

# local, git-ignored identifiers: at least the watch MAC, plus the auth key
mkdir -p secrets
echo "- MAC: AA:BB:CC:DD:EE:FF" > secrets/device.md
echo "0123456789abcdef0123456789abcdef" > secrets/auth_key.txt
```

`secrets/device.md` also records the serial number, the Mi Fitness device id, and any other
watch seen in range. Only the `MAC:` line is parsed (the rest is for humans and agents), so a
minimal file looks like:

```markdown
# Local device facts (git-ignored)
- MAC: AA:BB:CC:DD:EE:FF
- Serial: <device serial>
- Second watch in range: <MAC>
```

Every script that connects needs a MAC from that file, from `$WATCH_MAC`, or as its first
argument; without one it exits with that instruction instead of guessing an address.

`--python /usr/bin/python3` is not optional decoration: `socket.AF_BLUETOOTH` is enabled at
CPython build time, and the CPython builds uv downloads do **not** enable it. `src/spp_probe.py`
and `src/a2dp_probe.py` need it, so `pyproject.toml` also sets
`[tool.uv] python-preference = "system"` to keep uv from quietly choosing a downloaded
interpreter.

Dependencies live in `pyproject.toml` (lockfile: `uv.lock`): `bleak`, `cryptography`,
`pexpect`, `protobuf`, plus `grpcio-tools` in the `dev` group, used only by `fetch_protos.sh`
to regenerate `src/xiaomi_pb/`.

Prefix any command with `uv run`, or activate the venv once with `source .venv/bin/activate`.
`make check` runs the whole watch-free harness; `make test` and `make lint` are its halves.

## Scripts

| Script | Needs | Purpose |
|---|---|---|
| `src/find_watch.py` | BLE | Active scan, flags Xiaomi-looking advertisements |
| `src/scan.py` | BLE | Minimal scan, marks the target MAC |
| `src/watch_info.py` | BLE, phone BT off | Enumerates GATT services/chars + 10 s heart-rate notifications |
| `src/pair_watch.py` | `bluetoothctl`, `sdptool` | BlueZ pairing/trust; `--direct` skips scanning |
| `src/spp_probe.py` | RFCOMM ch 2 | Passive byte logger on the SPP channel |
| `src/a2dp_probe.py` | L2CAP PSM 25 | Read-only AVDTP discover/capabilities |
| `src/xiaomi_client.py` | paired watch, auth key | SPP v2 handshake + auth + device/battery queries (`-v` traces hex frames) |
| `src/audio_test.py` | PipeWire + `headset-head-unit` profile | `beep` / `record` / `loopback`; WAVs go to `recordings/` |

### Usage examples

```bash
# Discover the watch on the network
uv run python src/find_watch.py

# Pair / trust the watch with this PC
uv run python src/pair_watch.py --direct

# Enumerate BLE GATT services and subscribe to heart-rate
uv run python src/watch_info.py

# Query device info and battery over SPP v2
uv run python src/xiaomi_client.py -v

# Play beeps through the watch speaker
uv run python src/audio_test.py beep

# Record from the watch mic
uv run python src/audio_test.py record -s 5

# Record then play back on the watch
uv run python src/audio_test.py loopback -s 5
```

## `src/xiaomi_client.py` architecture

One file, layered; each layer is used only by the one above:

1. **Rfcomm** — RFCOMM socket opened via `ctypes`/libc; `fill()` appends to `link.buf`, and
   every parser below consumes from its front.
2. **SPP v1** (`parse_v1`, `V1_VERSION_REQUEST`) — only the `BA DC FE … EF` version probe;
   aborts unless the watch reports v2.
3. **SPP v2 framing** (`encode_v2`/`parse_v2`) — `A5 A5`, type/seq/len, CRC-16/ARC; frame
   types NACK/ACK/SESSION/DATA; DATA payloads start with `[channel, opcode]` (1 = plain,
   2 = encrypted). `SESSION_START` is a byte blob captured from the official app.
4. **Session** — HKDF(phone nonce ‖ watch nonce) → 64 B split into dec key / enc key /
   dec nonce / enc nonce; normal traffic is AES-CTR with the key as IV, per message.
5. **XiaomiWatch** — `connect()` runs RFCOMM → version probe → session → 3 auth steps;
   `_pump()` ACKs every DATA frame, decrypts, and queues `xiaomi_pb2.Command` objects in
   `inbox`; `wait_for(type, subtype)` pops a matching command, `request(t, s)` = send empty
   command + wait.

## Audio (HFP) notes

- **Verify with controller counters**: `hciconfig hci0` → `sco_tx` must move (roughly
  300 packets/s). `paplay` exits 0 in ~0.8 s while sending **0** packets, and `parecord`
  writes digital silence and exits 0 — neither return code nor duration alone is proof.
- Every stream needs a **fresh SCO transport**: `pactl set-card-profile <card> off`, then
  `headset-head-unit`, with the existing waits.
- Never keep a capture stream open while playing on the same watch — the single SCO link
  goes to the capture and playback sends nothing.
- Capture loses ~1 s at the start (SCO setup), hence `record()` recording `seconds + LINK_SETTLE`
  and retrying when a take is all zeros.
- The watch tears the SCO link down after **~1.3 s** of continuous playback, so longer clips
  are played in 0.7 s pieces with an audible gap.

## Protobuf bindings (`proto/`, `src/xiaomi_pb/`)

Both directories are git-ignored: `proto/` is vendored from Gadgetbridge and `src/xiaomi_pb/` is
generated from it, so `src/xiaomi_client.py` does not run in a fresh clone until you bootstrap them:

```bash
./fetch_protos.sh                # download proto/, then regenerate src/xiaomi_pb/
./fetch_protos.sh --protos-only  # download proto/ only
```

The script pins a Gadgetbridge commit, verifies the 14 downloaded `.proto` files against
recorded SHA-256 sums, writes `proto/SOURCE.md`, and then runs `grpc_tools.protoc` into
`src/xiaomi_pb/` (see `fetch_protos.sh` for the exact command).
Override the pin with `GADGETBRIDGE_REF=<commit-or-tag>` (the checksum check is skipped then).
Expect a harmless `Import xiaomi/wear_common.proto is unused` warning.

Generated modules import each other as `from xiaomi import wear_*_pb2`. The generated tree
lives at `src/xiaomi_pb/xiaomi_pb2.py` + `src/xiaomi_pb/xiaomi/*` (namespace package, no
`__init__.py`). **Never hand-edit** the generated files.

Protos are `proto2` on purpose: every `required` field must be set before
`SerializeToString()` or it raises.

## Provenance / licensing

This repository is licensed under the **GNU Affero General Public License v3.0 or later**
(see [`LICENSE`](LICENSE)).

Gadgetbridge and its code belong to its authors.

`proto/` is vendored from [Gadgetbridge](https://codeberg.org/Freeyourgadget/Gadgetbridge)
(AGPL-3.0) by `fetch_protos.sh`, at the commit it pins, and `src/xiaomi_client.py` is a port of
Gadgetbridge's Java SPP/auth classes. Treat new protocol code as an AGPL-3.0 derivative, not
original work.

## Legal

Unofficial, unaffiliated project — not endorsed or sponsored by Xiaomi. "Redmi", "Xiaomi" and
"Mi Fitness" are trademarks of Xiaomi Inc.; "Bluetooth" is a trademark of the Bluetooth SIG.
The marks are used descriptively, to say which hardware these scripts talk to.

This is interoperability work on a watch I own: it reads device state and streams audio over
Bluetooth profiles. It ships no vendor code, firmware, logos, app assets, auth keys, or device
identifiers, and there is nothing here for bypassing paid services or copy protection.

Provided **as-is, without warranty of any kind**. Running it may void your watch's warranty or
breach Mi Fitness terms of service; you are responsible for what you do with your own hardware.

## Reference

- `DETAILS.md` — Spanish-language device/protocol reference with verified SDP service table,
  SPP session parameters, protocol IDs, firmware/serial/battery facts, and HFP measurements.
