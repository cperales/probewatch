## What this repo is

ProbeWatch: Linux-side probes for a **Redmi Watch 5 Active** (`M2351W1`): BLE discovery, BlueZ
pairing, raw RFCOMM/L2CAP probes, an HFP audio test, and a Python port of Xiaomi's SPP v2
protocol. Entrypoints are standalone scripts in `src/`; `src/xiaomi_client.py` is the protocol
client the others reuse. `CLAUDE.md` just imports this file.

Device identifiers (watch MAC, serial, Mi Fitness id) and the SPP auth key live in the
git-ignored `secrets/` directory, never in tracked files.

## Harness

`make check` is the contract; CI (`.github/workflows/ci.yml`) runs the same target.

| Command | Does |
|---|---|
| `make setup` | `uv sync --python /usr/bin/python3` |
| `make protos` | `./fetch_protos.sh`: pinned Gadgetbridge download + bindings |
| `make check` | lint + tests + context budget + `compileall` |
| `make lint` | `ruff check`, `ruff format --check`, `bash -n`/shellcheck on `fetch_protos.sh`, `scripts/check_docs.py` |
| `make test` | `uv run pytest`; fetches protos first if `src/xiaomi_pb/` is missing |
| `make fmt` | `ruff format .`, `ruff check --fix .`, `check_docs.py --fix` (index sizes) |
| `make sizes` | context-budget table; fails if `AGENTS.md` > 12,000 B or a `docs/*.md` > 8,000 B |

Single test: `uv run pytest tests/test_xiaomi_client.py -k name`. Nothing in `make check` needs
the watch: `hardware`/`network` markers are deselected by `addopts` in `pyproject.toml`.
`check_docs.py` fails on dead relative links, a stale or incomplete `docs/README.md` index, a
word the Legal section forbids, and a malformed source tag.

## Context budget

Never read `src/xiaomi_pb/`, `uv.lock`, `LICENSE` (generated / lockfile / legal, ~86k tokens).
Read `proto/**/*.proto` only for the message you need, and `docs/*.md` on demand:
`docs/README.md` indexes them (scripts and their flags: `docs/scripts.md`; wire format and the
channel table: `docs/protocol.md`; device facts and firmware history: `docs/device.md`; what each
command returned on the watch: `docs/commands-tested.md`). Fact pages tag their sources
(`[hw …]`, `[apk …]`, `[fw …]`, `[gb]`, `[ext …]`, `[inferred]`; legend in `docs/README.md`).

## Recording a finding

Every fact has one home page in `docs/`; other docs link to it, and `AGENTS.md` keeps the
rules and a summary of the client contract. When a hardware run, the APK or the firmware
confirms or changes something:

1. Find the home page through `docs/README.md`.
2. `grep` its key terms across `AGENTS.md`, `README.md` and `docs/`. Update the home page with
   a source tag (legend in `docs/README.md`); replace any other restatement with a link.
3. A new firmware version also goes in the firmware history of the device page.
4. `uv run python scripts/check_docs.py --fix`, then `make check`.

## Python environment

Run Python through uv: `uv run python src/<tool>.py`. Add dependencies to `pyproject.toml` and
`uv sync`; never `pip install` into `.venv`.

`.venv` must be built from `/usr/bin/python3` (3.14). Only the distro build has
`socket.AF_BLUETOOTH`; uv-downloaded CPythons do not, and `src/spp_probe.py` and
`src/a2dp_probe.py` need it. `[tool.uv] python-preference = "system"` and the pinned sync
command exist for this. `bleak` goes through BlueZ D-Bus and does not need the constant.

`Rfcomm` in `src/xiaomi_client.py` opens its socket via `ctypes`/libc **on purpose** (explicit
`sockaddr_rc`, works without `AF_BLUETOOTH`). That struct stores the MAC **byte-reversed**; keep
the reversal.

## Run-blocking prerequisites (most failures come from these)

- Watch must be paired and trusted with this PC. Use `src/pair_watch.py --direct` when it is
  still bound to Mi Fitness (it does not advertise then, so discovery-based pairing fails).
  Pairing is interactive (drives `bluetoothctl` via `pexpect`; tap ✓ on the watch).
- **Never reset / unbind the watch from Mi Fitness**: that regenerates the auth key and
  invalidates `secrets/auth_key.txt`.
- Phone Bluetooth must be **off**: the watch serves one client at a time and stops advertising
  while connected to the phone.
- `secrets/auth_key.txt` (32 hex chars) is required by `src/xiaomi_client.py` and
  `src/probe_extra.py`. Never print or commit it.
- Every script resolves the MAC via `resolve_mac()` in `src/watch_secrets.py` (argument, then
  `$WATCH_MAC`, then the `MAC:` line of `secrets/device.md`). Add new identifiers to
  `secrets/device.md`, never to docs or code.
- `proto/` and `src/xiaomi_pb/` are git-ignored: run `make protos` once after cloning or
  `import xiaomi_pb2` fails.

## `src/xiaomi_client.py` architecture

One file, layered; each layer is used only by the one above:

1. `Rfcomm`: `fill()` appends to `link.buf`; every parser consumes from its front (incomplete
   frame → `None`, bytes are kept).
2. SPP v1 (`parse_v1`, `V1_VERSION_REQUEST`): only the `BA DC FE … EF` version probe; aborts
   unless the watch reports v2.
3. SPP v2 framing (`encode_v2`/`parse_v2`): `A5 A5`, type/seq/len, CRC-16/ARC; frame types
   NACK/ACK/SESSION/DATA; DATA payloads start `[channel, opcode]`: channels `CH_*` 1-9,
   opcodes `OP_WRITE` 1 (plain), `OP_WRITE_ENC` 2 (encrypted), `OP_READ` 3.
   `SESSION_START` is a byte blob captured from the official app: do not "clean it up".
   `parse_v2` has two shapes on purpose: `None` = incomplete (wait for more bytes),
   `(None, 0, b"", n)` = junk/CRC-skip (consume `n`); it resyncs on the next `A5 A5`.
4. `Session`: HKDF(phone nonce ‖ watch nonce) → 64 B, first 40 used as dec key / enc key / dec
   nonce / enc nonce; traffic is AES-CTR with the key as IV, per message; AES-CCM only for the
   phone-info blob in auth step 3.
5. `XiaomiWatch`: `connect()` = RFCOMM → version probe → session → 3 auth steps (always on
   channel 1; `l2_channel` is saved and restored around them). It runs a selective-repeat
   ARQ: `TX_WINDOW` 32 unacked frames in `_sent` (insertion order, so cumulative ACKs work
   across the 8-bit seq wrap), resend from the first missing seq on **every** NAK, per-frame
   10 s retransmit. Incoming ACKs are delayed (500 ms timer armed once, or `ACK_THRESHOLD`
   pending) except on channels 1 and 8, which are ACKed at once. `_send_data` returns `None`
   when the window is full: pump and retry, never drop. `_pump()` decrypts and queues
   `xiaomi_pb2.Command` in `inbox`; `wait_for(type, subtype)` pops a match, `request(t, s)` =
   empty command + wait. Only `CH_PROTOBUF` (1) and `CH_OTA` (6) are decoded; other channels
   are logged and dropped. 16 KB frames work; one 24 KB frame closes the link (`docs/arq.md`).
   Long form: `docs/architecture.md`.

Rules when extending it:

- `type == 1` (auth) commands go out **plaintext**, everything else encrypted (`send_command`
  decides); send non-auth commands only after `connect()` succeeds.
- New experiments are command lines, not edits: `--send TYPE SUBTYPE [--payload text_format]`
  (repeatable; `--payload` needs exactly one `--send`), `--channel N`, `--opcode
  write|write_enc|read`, `--timeout`, `--listen SECONDS`, `--keepalive`, `--capture [PATH]`
  (default `captures/<timestamp>.ndjson`). CLI `--send` calls `_send_data` with `--opcode`
  directly, so it does not go through `send_command`. Ids come from Gadgetbridge's
  Xiaomi Java services, response shapes from `proto/xiaomi.proto`.
- `-v` traces every TX/RX frame in hex: the first thing to use on protocol failures.

## Writing Python code

- stdlib first; type hints on every signature; a class only when state is genuinely shared.
- `argparse` under `if __name__ == "__main__":` with a thin `main()`; the module docstring says
  what it talks to, whether it is read-only, and has a `Usage:` line.
- Constants at module top in `UPPER_CASE`. Repo-level paths via
  `ROOT = Path(__file__).resolve().parent.parent`; never hardcode absolute paths.
- Reuse protocol code by importing a sibling module (`from xiaomi_client import XiaomiWatch`),
  not by copying.
- `print()` with f-strings, `.hex()` for bytes; no logging framework.
- Double quotes, 4-space indent, 100 columns (`ruff` enforces it; `E501` is ignored). Comment
  protocol facts a reader cannot infer, not what the next line does.

## Tests

`tests/` is pure logic (framing, CRC, crypto, codec decoding, MAC/key validation, CLI
plumbing). Anything needing the watch, phone, or network gets `@pytest.mark.hardware` /
`@pytest.mark.network`. `tests/conftest.py` must never touch the real `secrets/`; use
`tmp_path` and `monkeypatch`.

## Protobuf bindings

`./fetch_protos.sh` downloads 14 `.proto` files from a pinned Gadgetbridge commit (each checked
against a SHA-256 in the script), writes `proto/SOURCE.md`, then runs
`grpc_tools.protoc -Iproto --python_out=src/xiaomi_pb proto/xiaomi.proto proto/xiaomi/*.proto`.
`--protos-only` stops after the download; `GADGETBRIDGE_REF=<commit-or-tag>` overrides the pin
and skips checksums. A new upstream `.proto` needs a line and hash in the script. An "Import
xiaomi/wear_common.proto is unused" warning is harmless.

Keep the generated layout `src/xiaomi_pb/xiaomi_pb2.py` + `src/xiaomi_pb/xiaomi/*` (namespace
package, no `__init__.py`): generated modules import each other as `from xiaomi import wear_*_pb2`
and `xiaomi_client.py` puts `src/xiaomi_pb` on `sys.path`. Never hand-edit generated files.

Protos are `proto2` on purpose: unset `required` fields make `SerializeToString()` raise, and
explicit default values must be set to appear on the wire.

## Audio (HFP): the client's exit code proves nothing

Details and measurements: `docs/audio.md`. Rules that must survive a refactor:

- Verify with `hciconfig hci0`: `sco_tx` must move (~300 packets/s). `paplay` exits 0 in ~0.8 s
  while sending zero packets.
- Every stream needs a fresh SCO transport (`pactl set-card-profile <card> off`, then
  `headset-head-unit`).
- Never keep a capture stream open while playing on the same watch.
- The watch tears SCO down after ~1.3 s, so `loopback` plays 0.7 s pieces with an audible gap;
  CVSD fails the same way. Do not "fix" it with buffers or latency.
- Last resort: `systemctl --user restart wireplumber`.

## Legal and provenance

Keep language descriptive: "read", "query", "probe", "enumerate". Never write "bypass",
"unlock", "jailbreak", "crack" or "hack"; this is interoperability with a watch the author owns.
Never add vendor assets (app, APK, firmware, logos), auth keys, or device identifiers to the
repo. `README.md`'s Legal section is the canonical disclaimer: link to it, do not restate it.

AGPL-3.0-or-later. `proto/` is vendored from Gadgetbridge and `src/xiaomi_client.py` is a port
of its Java SPP/auth classes, so treat new protocol code as derivative work. Unofficial project,
not affiliated with Xiaomi.
