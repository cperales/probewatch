# SPDX-License-Identifier: AGPL-3.0-or-later
"""Summarise an SPP capture and hunt for a payload format on unknown channels.

Read-only: works offline on the NDJSON written by `xiaomi_client.py --capture`, so it
never touches the watch. The file protocol and framing come from `xiaomi_client`; this
script only describes and guesses.

Two questions it answers per channel: does the payload parse as protobuf (and as which
message), and, if not, is it a record stream with a length prefix.

Usage: uv run python src/decode_capture.py CAPTURE [--channel N] [--samples N]
"""

import argparse
import importlib
import json
import pkgutil
import statistics
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from xiaomi_client import CH_PROTOBUF, T_DATA  # noqa: E402

KNOWN_CHANNELS = {CH_PROTOBUF: "protobuf"}
UNKNOWN_CHANNELS = (2, 5)  # CH_DATA, CH_ACTIVITY: never decoded on this device
HEADER_MAX_OFFSET = 8  # bytes of private header to try in front of a record stream
MIN_RECORDS = 2  # one split is not evidence of a length-prefixed format


# --------------------------------------------------------------------------- loading
def load(path: str) -> list[dict]:
    """Read the NDJSON capture written by `xiaomi_client.py --capture`."""
    lines = Path(path).read_text().splitlines()
    return [json.loads(line) for line in lines if line]


def summarise(records: list[dict]) -> dict[int, dict]:
    """Per-channel statistics for received DATA frames: count, timing, lengths, opcodes."""
    per_channel: dict[int, dict] = {}
    for record in records:
        if record.get("dir") != "rx" or record.get("type") != T_DATA:
            continue
        if "ch" not in record:
            continue  # malformed/short frame, recorded with a note instead
        stats = per_channel.setdefault(
            record["ch"], {"frames": 0, "times": [], "lengths": [], "opcodes": set()}
        )
        stats["frames"] += 1
        stats["times"].append(record["t"])
        stats["lengths"].append(record["len"])
        stats["opcodes"].add(record.get("op", 0))
    for stats in per_channel.values():
        times = stats.pop("times")
        stats["intervals"] = [round(b - a, 3) for a, b in zip(times, times[1:], strict=False)]
        stats["interval_median"] = (
            round(statistics.median(stats["intervals"]), 3) if stats["intervals"] else None
        )
        stats["lengths"] = sorted(set(stats["lengths"]))
        stats["opcodes"] = sorted(stats["opcodes"])
    return per_channel


def samples(records: list[dict], channel: int, limit: int) -> list[bytes]:
    """First `limit` decrypted payloads on one channel."""
    out = []
    for record in records:
        if record.get("dir") == "rx" and record.get("ch") == channel:
            out.append(bytes.fromhex(record["hex"]))
            if len(out) == limit:
                break
    return out


# --------------------------------------------------------------------------- protobuf
def message_registry() -> dict[str, type]:
    """Every generated message class, keyed by name, so candidates are not hand-listed."""
    import xiaomi as xiaomi_pkg
    import xiaomi_pb2
    from google.protobuf import message_factory

    modules = [xiaomi_pb2]
    for info in pkgutil.iter_modules(xiaomi_pkg.__path__):
        modules.append(importlib.import_module(f"xiaomi.{info.name}"))
    registry: dict[str, type] = {}
    for module in modules:
        for name, descriptor in module.DESCRIPTOR.message_types_by_name.items():
            registry.setdefault(
                f"{module.__name__}.{name}", message_factory.GetMessageClass(descriptor)
            )
    return registry


def _match(data: bytes, cls: type) -> object | None:
    """Parse `data` as `cls`, or return None when it is not a full, meaningful match."""
    message = cls()
    try:
        consumed = message.ParseFromString(data)
    except Exception:  # noqa: BLE001 - any parse failure just rules the candidate out
        return None
    if isinstance(consumed, int) and consumed != len(data):
        return None
    if not message.IsInitialized() or not message.ListFields():
        return None
    # Unknown fields survive a parse and re-serialise, which makes almost any message look
    # like a match. Dropping them and comparing again rejects those false positives.
    message.DiscardUnknownFields()
    if message.SerializeToString(deterministic=True) != data:
        return None
    return message


def protobuf_candidates(
    payloads: list[bytes], registry: dict[str, type], limit: int = 8
) -> list[tuple[str, str]]:
    """Messages that explain *every* payload on a channel, ranked by how much they decode.

    Unknown fields survive a parse and are re-serialised, so a plain round-trip test would
    accept almost anything. A candidate must consume the whole payload, set at least one
    known field and expose the same set of fields in every sample; the ranking then favours
    messages that actually carry data. Short payloads still match many messages — treat the
    top of the list as a hypothesis, not an answer.
    """
    samples = [p for p in payloads if p]
    if not samples:
        return []
    scored: list[tuple[int, str]] = []
    for name, cls in sorted(registry.items()):
        messages = [_match(data, cls) for data in samples]
        if any(message is None for message in messages):
            continue
        shapes = {tuple(field.name for field, _ in message.ListFields()) for message in messages}
        if len(shapes) != 1:  # a message that fits one sample and not the others is noise
            continue
        scored.append((len(shapes.pop()), name))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [(name, _describe(samples[0], registry[name])) for _, name in scored[:limit]]


def _describe(data: bytes, cls: type) -> str:
    """text_format rendering of one payload for display."""
    from google.protobuf import text_format

    message = _match(data, cls)
    return text_format.MessageToString(message, as_one_line=True) if message else ""


# --------------------------------------------------------------------------- framing
def _record_count(blob: bytes, offset: int, endian: str) -> int:
    """How many u16-length-prefixed records the blob holds from `offset`, or 0."""
    index, count = offset, 0
    while index + 2 <= len(blob):
        (length,) = struct.unpack_from(endian + "H", blob, index)
        if length == 0 or index + 2 + length > len(blob):
            return 0
        index += 2 + length
        count += 1
    return count if index == len(blob) else 0


def header_hypotheses(payloads: list[bytes]) -> list[str]:
    """Try private record headers: a u16 length at some small offset, either endianness."""
    blob = b"".join(payloads)
    hits = []
    for offset in range(HEADER_MAX_OFFSET + 1):
        for endian, label in (("<", "LE"), (">", "BE")):
            count = _record_count(blob, offset, endian)
            if count >= MIN_RECORDS:
                hits.append(f"offset {offset}, u16 {label} length -> {count} records")
    return hits


# --------------------------------------------------------------------------- report
def report(records: list[dict], only: int | None, limit: int) -> None:
    stats = summarise(records)
    if not stats:
        print("no received DATA frames in this capture")
        return
    for channel, info in sorted(stats.items()):
        if only is not None and channel != only:
            continue
        label = KNOWN_CHANNELS.get(channel, "unknown")
        print(f"\nchannel {channel} ({label})")
        print(f"  frames:    {info['frames']}")
        print(f"  lengths:   {info['lengths']}")
        print(f"  opcodes:   {info['opcodes']}")
        if info["intervals"]:
            print(
                f"  interval:  median {info['interval_median']}s over {len(info['intervals'])} gaps"
            )
        else:
            print("  interval:  single frame")
        if channel in KNOWN_CHANNELS:
            continue
        payloads = samples(records, channel, limit)
        print(f"  samples:   {[p.hex() for p in payloads]}")
        candidates = protobuf_candidates(payloads, message_registry())
        if candidates:
            print("  protobuf:  ranked hypotheses (none is proof on its own)")
            for name, text in candidates:
                print(f"             {name}: {text}")
        else:
            print("  protobuf:  no message explains every sample")
        headers = header_hypotheses(payloads)
        print(f"  records:   {headers or 'no u16 length prefix up to offset 8'}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarise an SPP capture from xiaomi_client.")
    parser.add_argument("capture", help="NDJSON file written by xiaomi_client.py --capture")
    parser.add_argument("--channel", type=int, default=None, help="only report this channel")
    parser.add_argument("--samples", type=int, default=5, help="payload samples per channel")
    args = parser.parse_args()

    records = load(args.capture)
    print(f"{len(records)} frames from {args.capture}")
    report(records, args.channel, args.samples)


if __name__ == "__main__":
    main()
