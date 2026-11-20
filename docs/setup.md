# Setup & Bootstrap

## Prerequisites

| Requirement | Details |
|---|---|
| **Watch** | Redmi Watch 5 Active (`M2351W1`), paired and trusted with this PC |
| **Phone Bluetooth** | Must be **off** — the watch talks to one client at a time |
| **PipeWire + WirePlumber** | Required for audio tests (`headset-head-unit` profile) |
| **BlueZ tools** | `bluetoothctl`, `sdptool`, `hciconfig`, `pactl`, `paplay`, `parecord` |
| **uv** | Python package manager (see below) |
| **Python 3.10+** | Must be the distro build (`/usr/bin/python3`) with `AF_BLUETOOTH` |

Unofficial hobby project, provided as-is: using these tools may void your watch's warranty or
breach Mi Fitness terms. See the Legal section in [README.md](../README.md#legal).

## Step 1 — Create the virtual environment

```bash
uv sync --python /usr/bin/python3
```

This creates `.venv` from the system interpreter. The system build is the **only** one that
compiles Bluetooth socket support (`socket.AF_BLUETOOTH`) into the interpreter. CPython builds
that `uv` downloads do not include it, which is why `pyproject.toml` sets:

```toml
[tool.uv]
python-preference = "system"
```

This prevents `uv` from quietly substituting a downloaded interpreter that lacks Bluetooth
support — `src/spp_probe.py` and `src/a2dp_probe.py` depend on it.

## Step 2 — Fetch protobuf definitions

```bash
./fetch_protos.sh                # download proto/ + regenerate src/xiaomi_pb/
./fetch_protos.sh --protos-only  # download proto/ only (skip regeneration)
```

The script:

1. Downloads 14 `.proto` files from a pinned Gadgetbridge commit (`93d4d79a…`, 2026-11-15)
2. Verifies each file against recorded SHA-256 sums
3. Writes `proto/SOURCE.md` with provenance
4. Runs `grpc_tools.protoc` to regenerate `src/xiaomi_pb/`

Override the pin: `GADGETBRIDGE_REF=<commit-or-tag> ./fetch_protos.sh` (skips checksums).

## Step 3 — Provide the auth key and local identifiers

The watch must be bound to Mi Fitness (which creates the auth key) and paired with this PC
(`src/pair_watch.py --direct`). The key is a 32 hex-character string stored in:

```
secrets/auth_key.txt
```

This file is git-ignored. Never print or commit it. `src/xiaomi_client.py` reads it on
startup and validates its length.

The watch MAC, its serial number, and any other local identifiers go in `secrets/device.md`
(also git-ignored). Every script reads its `MAC:` line when no MAC argument is given, and
`$WATCH_MAC` overrides it:

```markdown
# Local device facts (git-ignored)
- MAC: AA:BB:CC:DD:EE:FF
- Serial: <device serial>
```

## Step 4 — Verify the environment

`make check` runs the whole watch-free harness (ruff, doc links, pytest, context budget,
`compileall`). The individual checks below are for debugging the environment:

```bash
# Check the venv interpreter has AF_BLUETOOTH
uv run python -c "import socket; print(socket.AF_BLUETOOTH)"
# Should print: 31

# Check proto files exist
ls proto/*.proto proto/xiaomi/*.proto
# Should list 14 files

# Check generated bindings
ls src/xiaomi_pb/xiaomi_pb2.py src/xiaomi_pb/xiaomi/*_pb2.py
# Should list xiaomi_pb2.py + 13 wear_* modules
```

## Dependencies

Runtime (in `pyproject.toml`):

| Package | Purpose |
|---|---|
| `bleak>=1.0` | BLE client (GATT scan, notifications) |
| `cryptography>=42` | AES-CTR, AES-CCM, HKDF, HMAC |
| `pexpect>=4.9` | Interactive `bluetoothctl` automation |
| `protobuf>=5` | Parse Xiaomi protobuf commands |

Dev (in `dependency-groups`):

| Package | Purpose |
|---|---|
| `grpcio-tools>=1.60` | `grpc_tools.protoc` for regenerating bindings |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `AttributeError: module 'socket' has no attribute 'AF_BLUETOOTH'` | Wrong interpreter (uv downloaded CPython) | Re-sync: `uv sync --python /usr/bin/python3` |
| `ImportError: No module named 'xiaomi_pb2'` | Protos not fetched | Run `./fetch_protos.sh` |
| `watch did not report SPP v2` | Wrong auth key or not paired | Re-pair with `src/pair_watch.py --direct` |
| `no watch MAC: pass it as an argument, ...` | Neither `secrets/device.md` nor `$WATCH_MAC` set | Add the `MAC:` line (Step 3) or pass the MAC |
| `paplay` exits 0 but no sound | SCO transport broken | `reset_link()` in `src/audio_test.py` recreates it |
| Watch not found by BLE scripts | Connected to phone | Turn off phone Bluetooth |
