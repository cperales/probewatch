## What this repo is

ProbeWatch: Linux-side probes for a **Redmi Watch 5 Active** (model `M2351W1`): BLE discovery, BlueZ
pairing, raw RFCOMM/L2CAP probes, an HFP audio test, and a Python port of Xiaomi's SPP v2
protocol (framing, HKDF auth, AES, protobuf commands). Entrypoints live in `src/`, one
standalone script per tool; `src/xiaomi_client.py` is the protocol client the others reuse.

Device identifiers (watch MAC, serial, Mi Fitness id) and the SPP auth key live in the
git-ignored `secrets/` directory — never in tracked files.

## Harness

`make check` is the contract, locally and in CI (`.github/workflows/ci.yml` runs the same
target, so they cannot drift).

| Command | Does |
|---|---|
| `make setup` | `uv sync --python /usr/bin/python3` |
| `make protos` | `./fetch_protos.sh`: pinned Gadgetbridge download + bindings |
| `make check` | lint + tests + context budget + `compileall` |
| `make lint` | `ruff check`, `ruff format --check`, `bash -n`, shellcheck, doc links |
| `make test` | `uv run pytest`; fetches protos first if `src/xiaomi_pb/` is missing |
| `make fmt` | `ruff format .` and `ruff check --fix .` |
| `make sizes` | prints the context-budget table, fails on an oversized doc |

Nothing in `make check` needs the watch: `hardware`/`network` tests are deselected in
`pyproject.toml`, and `tests/conftest.py` never reads or writes the real `secrets/`.

Raw equivalents are the target bodies in the `Makefile`.

## Context budget

A 128k model can read this repository, but not naively: `uv.lock`, the generated
bindings, and `LICENSE` alone are ~86k tokens. `make sizes` prints the current numbers and
fails if `AGENTS.md` > 12 KB or one `docs/` page > 8 KB.

| Read | Policy |
|---|---|
| `AGENTS.md` | always (~3k tokens) |
| `README.md`, `DETAILS.md`, `docs/*.md` | entry docs once; the rest on demand (~13k total) |
| `src/*.py`, `tests/*.py` | read the file you are changing (~20k total) |
| `proto/**/*.proto` | only the message you need (~9k total) |
| `src/xiaomi_pb/`, `uv.lock`, `LICENSE` | **never** (generated / lockfile / legal text) |

## Python environment

Run Python through uv: `uv run python ...`. Refresh with `uv sync --python /usr/bin/python3`.
Dependencies belong in `pyproject.toml` (lockfile `uv.lock`); add a library there and run
`uv sync`, never `pip install` into `.venv` by hand.

`.venv` is Python 3.14 created from `/usr/bin/python3` and must stay that way. Only the
distro build is compiled with Bluetooth support, so only it has `socket.AF_BLUETOOTH`; the
CPython builds uv downloads do not, and the raw-socket probes (`src/spp_probe.py`,
`src/a2dp_probe.py`) need it. That is why `pyproject.toml` sets
`[tool.uv] python-preference = "system"` and why the sync command pins
`--python /usr/bin/python3`. `bleak` reaches BlueZ over D-Bus, so it does not need the
constant; everything installs from prebuilt wheels.

`Rfcomm` in `src/xiaomi_client.py` opens its socket through `ctypes`/libc **on purpose**,
even though the venv interpreter has `AF_BLUETOOTH`: that keeps `sockaddr_rc` explicit and
works where `AF_BLUETOOTH` is missing. That struct stores the MAC **byte-reversed** — keep
the reversal if you touch it.

## Run-blocking prerequisites (most failures come from these)

- Watch must be paired and trusted with this PC. Use `src/pair_watch.py --direct` when the
  watch is still bound to Mi Fitness (it does not advertise then, so discovery-based pairing
  fails). Pairing is interactive: the script drives `bluetoothctl` through `pexpect` and asks
  you to tap ✓ on the watch when the passkey appears.
- **Never reset / unbind the watch from Mi Fitness**: that regenerates the auth key and
  invalidates `secrets/auth_key.txt`. `--direct` exists precisely to avoid this.
- Phone Bluetooth must be **off**: the watch talks to one client at a time and stops
  advertising while connected to the phone (BLE scripts then see nothing).
- `secrets/auth_key.txt` (32 hex chars) is required by `src/xiaomi_client.py` and
  `src/probe_extra.py`. `secrets/` is git-ignored; never print or commit the key.
- `secrets/device.md` holds the watch MAC, its serial, and any other identifiers; every
  script resolves the MAC through `src/watch_secrets.py` (argument, then `$WATCH_MAC`, then
  the `MAC:` line). Add new identifiers there, never to docs or code.
- `proto/` and `src/xiaomi_pb/` are git-ignored too; run `make protos` once after cloning
  or `src/xiaomi_client.py` fails on `import xiaomi_pb2`.

## Layout

| Path | Purpose |
|---|---|
| `src/find_watch.py`, `src/scan.py` | BLE discovery and Xiaomi-advert flags |
| `src/watch_info.py`, `src/pair_watch.py` | GATT read; BlueZ pairing/trust |
| `src/spp_probe.py`, `src/a2dp_probe.py` | passive RFCOMM log; AVDTP capabilities |
| `src/xiaomi_client.py`, `src/probe_extra.py` | SPP v2 client; extra queries |
| `src/audio_test.py`, `src/watch_secrets.py` | HFP test; MAC resolution (shared) |
| `tests/`, `docs/`, `scripts/` | unit tests; long-form docs; harness helpers |

## `src/xiaomi_client.py` architecture

One file, layered; each layer is used only by the one above:

1. `Rfcomm` — RFCOMM socket opened via `ctypes`/libc; `fill()` appends to `link.buf`, and
   every parser below consumes from its front (incomplete frame → `None`, bytes are kept).
2. SPP v1 (`parse_v1`, `V1_VERSION_REQUEST`) — only the `BA DC FE … EF` version probe; aborts
   unless the watch reports v2.
3. SPP v2 framing (`encode_v2`/`parse_v2`) — `A5 A5`, type/seq/len, CRC-16/ARC; frame types
   NACK/ACK/SESSION/DATA; DATA payloads start with `[channel, opcode]` (1 = plain,
   2 = encrypted). `SESSION_START` is a byte blob captured from the official app — do not
   "clean it up". `parse_v2` has two shapes on purpose: `None` = incomplete (wait for more
   bytes), and `(None, 0, b"", n)` = junk/CRC-skip (consume `n`); it resyncs on the next
   `A5 A5`, so leading junk is consumed with the frame it precedes.
4. `Session` — HKDF(phone nonce ‖ watch nonce) → 64 B, first 40 used as dec key / enc key /
   dec nonce / enc nonce; normal traffic is AES-CTR with the key as IV, per message; AES-CCM
   only for the phone-info blob in auth step 3.
5. `XiaomiWatch` — `connect()` runs RFCOMM → version probe → session → 3 auth steps;
   `_pump()` **ACKs every DATA frame**, decrypts, and queues `xiaomi_pb2.Command` objects in
   `inbox`; `wait_for(type, subtype)` pops a matching command, `request(t, s)` = send empty
   command + wait. Only `CH_PROTOBUF` (1) is decoded; traffic on other channels (`CH_DATA` 2,
   `CH_ACTIVITY` 5) is logged and dropped.

Rules when extending it:

- `type == 1` (auth) commands go out **plaintext**, every other type encrypted
  (`send_command` decides); send non-auth commands only after `connect()` succeeds.
- New experiments are command lines, not edits: `--send TYPE SUBTYPE [--payload text_format]`,
  `--listen SECONDS`, `--capture [PATH]`. Ids come from Gadgetbridge's Xiaomi Java services,
  response shapes from `proto/xiaomi.proto`.
- `-v` traces every TX/RX frame in hex — the first thing to use on protocol failures.

## Writing Python code

Entrypoints live in `src/`, one standalone script per tool, run with
`uv run python src/<tool>.py`. Keep new code in that shape:

- stdlib first; a new third-party library means a line in `pyproject.toml` plus `uv sync`.
- Type hints on every function signature. Use a class only when state is genuinely shared,
  as in `XiaomiWatch`.
- `argparse` under `if __name__ == "__main__":`, a thin `main()` that does the work; the
  module docstring says what the script talks to, whether it is read-only, and carries a
  `Usage:` line.
- Constants at module top in `UPPER_CASE` (`DEFAULT_MAC`, `AVDTP_PSM`); no magic numbers
  inline.
- Paths: `HERE` is `src/`; repo-level files (`secrets/`, `recordings/`) go through
  `ROOT = Path(__file__).resolve().parent.parent`. Never hardcode absolute paths.
- Reuse protocol code by importing a sibling module (`from xiaomi_client import XiaomiWatch`,
  as `src/probe_extra.py` does) instead of copying it into a new script.
- Never hardcode a MAC, serial, or device id: take the MAC from `resolve_mac()` in
  `src/watch_secrets.py`.
- `print()` with f-strings for output, `.hex()` for bytes; no logging framework.
- Double quotes, 4-space indent, 100 columns (`ruff` enforces it). Comment protocol facts a
  reader cannot infer (`why` this byte), not what the next line does.

## Legal framing

Keep the language descriptive: "read", "query", "probe", "enumerate". Never write "bypass",
"unlock", "jailbreak", "crack" or "hack". This is interoperability with a watch the author
owns, not circumvention.

Never add vendor assets (app, APK, firmware, logos), auth keys, or device identifiers to the
repository. `README.md`'s Legal section is the canonical disclaimer; keep it intact and link to
it instead of restating it.

## Tests

`tests/` is pure logic: framing, CRC, crypto, codec decoding, MAC/key validation, CLI
plumbing. No test may need the watch, the phone, or network access. Mark anything that does
with `@pytest.mark.hardware` or `@pytest.mark.network` — the default `addopts` deselects
both, so `make test` stays green on a laptop. Tests import from `src/` through
`pythonpath = ["src"]` in `pyproject.toml`; fixtures live in `tests/conftest.py`, which
must not touch the real `secrets/` (use `tmp_path` and `monkeypatch`).

## Protobuf bindings (`proto/`, `src/xiaomi_pb/`)

Neither directory is tracked. `./fetch_protos.sh` downloads the 14 `.proto` files from a
pinned Gadgetbridge commit (each verified against a recorded SHA-256), writes
`proto/SOURCE.md`, then regenerates `src/xiaomi_pb/` with:

```
uv run python -m grpc_tools.protoc -Iproto --python_out=src/xiaomi_pb \
    proto/xiaomi.proto proto/xiaomi/*.proto
```

`--protos-only` stops after the download; `GADGETBRIDGE_REF=<commit-or-tag>` overrides the
pin and skips the checksums. Regeneration is byte-identical across reruns (verified); expect
a harmless "Import xiaomi/wear_common.proto is unused" warning. If upstream adds a `.proto`
file, add it to the explicit list and its hash in the script.

Layout matters: generated modules import each other as `from xiaomi import wear_*_pb2`, and
`src/xiaomi_client.py` puts `src/xiaomi_pb` on `sys.path` then imports `xiaomi_pb2`. Keep the
generated tree at `src/xiaomi_pb/xiaomi_pb2.py` + `src/xiaomi_pb/xiaomi/*` (namespace
package, no `__init__.py`). Generated files are never edited by hand.

Protos are `proto2` on purpose: every `required` field must be set before
`SerializeToString()` or it raises, and explicit default values must be set to appear on the
wire.

## Audio (HFP) — the client's exit code proves nothing

Details and measurements: `docs/audio.md`. The rules that must survive a refactor:

- Verify with the controller counters: `hciconfig hci0` → `sco_tx` must move (~300 packets/s).
  `paplay` exits 0 in ~0.8 s while sending zero packets.
- Every stream needs a fresh SCO transport (`pactl set-card-profile <card> off`, then
  `headset-head-unit`); a reused one usually breaks playback.
- Never keep a capture stream open while playing on the same watch.
- The watch tears the SCO link down after ~1.3 s, so `loopback` plays 0.7 s pieces with an
  audible gap; CVSD fails the same way. Do not "fix" it with buffers or latency.
- Last resort: `systemctl --user restart wireplumber`.

## Provenance / licensing

AGPL-3.0-or-later; see `LICENSE`. `proto/` is vendored from Gadgetbridge (AGPL-3.0) by
`fetch_protos.sh` at the commit the script pins, and `src/xiaomi_client.py` is a port of
Gadgetbridge's Java SPP/auth classes — treat new protocol code as derivative work, not
original. Unofficial project: not affiliated with Xiaomi.

`DETAILS.md` (Spanish) is the verified device reference: SDP services, protocol ids,
firmware/serial/battery facts, HFP measurements. Update it when device-level findings are
confirmed on hardware.
