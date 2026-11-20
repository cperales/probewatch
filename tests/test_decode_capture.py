"""Unit tests for the offline capture analyser (`src/decode_capture.py`).

No hardware, no network: every input is a synthetic NDJSON record or a synthetic frame.
"""

import json

import pytest

from decode_capture import (
    header_hypotheses,
    load,
    message_registry,
    protobuf_candidates,
    samples,
    summarise,
)


def _record(**overrides) -> dict:
    record = {"t": 0.0, "dir": "rx", "type": 3, "ch": 5, "op": 2, "seq": 0, "len": 0, "hex": ""}
    record.update(overrides)
    return record


class TestSummarise:
    """Per-channel statistics over received DATA frames."""

    def test_groups_by_channel_with_intervals(self):
        records = [
            _record(t=0.0, ch=5, hex="aa", len=1),
            _record(t=1.0, ch=5, hex="bb", len=1),
            _record(t=3.0, ch=5, hex="cc", len=1),
            _record(t=0.5, ch=2, hex="dd", len=1),
        ]
        stats = summarise(records)

        assert stats[5]["frames"] == 3
        assert stats[5]["intervals"] == [1.0, 2.0]
        assert stats[5]["interval_median"] == 1.5
        assert stats[2]["frames"] == 1

    def test_ignores_tx_and_non_data_frames(self):
        records = [
            _record(dir="tx"),
            _record(type=1),  # ACK
            _record(ch=1, hex="01"),
        ]
        stats = summarise(records)
        assert list(stats) == [1], "only the received DATA frame counts"
        assert stats[1]["frames"] == 1

    def test_aggregates_lengths_and_opcodes(self):
        records = [
            _record(len=4, op=2),
            _record(len=4, op=2),
            _record(len=8, op=1),
        ]
        stats = summarise(records)[5]
        assert stats["lengths"] == [4, 8]
        assert stats["opcodes"] == [1, 2]


class TestSamples:
    """Payload extraction for display and candidate testing."""

    def test_returns_decrypted_bytes_up_to_limit(self):
        records = [
            _record(hex="dead", ch=5),
            _record(hex="beef", ch=5),
            _record(hex="cafe", ch=2),
        ]
        assert samples(records, 5, 5) == [b"\xde\xad", b"\xbe\xef"]
        assert samples(records, 5, 1) == [b"\xde\xad"]
        assert samples(records, 2, 5) == [b"\xca\xfe"]


class TestProtobufCandidates:
    """Round-trip detection with the false-positive guards."""

    def test_finds_the_matching_message(self):
        import xiaomi_pb2

        data = xiaomi_pb2.Command(type=2, subtype=1, status=1).SerializeToString()
        hits = [name for name, _ in protobuf_candidates([data], message_registry())]
        assert any(name.endswith(".Command") for name in hits)

    def test_rejects_messages_that_leave_unknown_fields(self):
        """A smaller schema must not "match" by treating the extra fields as unknown."""
        from xiaomi import wear_system_pb2

        data = wear_system_pb2.DeviceState(chargingState=2, wearingState=1, sleepState=2)
        hits = [
            name
            for name, _ in protobuf_candidates([data.SerializeToString()], message_registry(), 200)
        ]
        assert any(name.endswith(".DeviceState") for name in hits)
        assert not any(name.endswith(".HourMinute") for name in hits)

    def test_respects_the_limit(self):
        from xiaomi import wear_system_pb2

        data = wear_system_pb2.DeviceState(chargingState=2, wearingState=1, sleepState=2)
        hits = protobuf_candidates([data.SerializeToString()], message_registry(), 3)
        assert len(hits) == 3
        assert all(isinstance(name, str) and isinstance(text, str) for name, text in hits)

    def test_requires_every_sample_to_fit(self):
        """A message that explains one sample but not the next is not a candidate."""
        from xiaomi import wear_system_pb2

        state = wear_system_pb2.DeviceState(chargingState=2, wearingState=1).SerializeToString()
        other = wear_system_pb2.DoNotDisturb(status=2).SerializeToString()
        hits = [name for name, _ in protobuf_candidates([state, other], message_registry())]
        assert not any(name.endswith(".DeviceState") for name in hits)

    def test_rejects_unknown_field_noise(self):
        """Unknown fields re-serialise unchanged, so they must not count as a match."""
        assert protobuf_candidates([b"\xff\xff\xff\xff"], message_registry()) == []

    def test_rejects_empty(self):
        assert protobuf_candidates([], message_registry()) == []
        assert protobuf_candidates([b""], message_registry()) == []


class TestHeaderHypotheses:
    """Detection of private u16 length-prefixed record streams."""

    @staticmethod
    def _stream(records: list[bytes], prefix: bytes = b"", endian: str = "<") -> bytes:
        import struct

        body = b"".join(struct.pack(endian + "H", len(r)) + r for r in records)
        return prefix + body

    def test_detects_length_prefixed_stream(self):
        blob = self._stream([b"abc", b"defg"])
        assert "offset 0, u16 LE length -> 2 records" in header_hypotheses([blob])

    def test_detects_stream_after_a_header(self):
        blob = self._stream([b"abc", b"defg"], prefix=b"\x01\x02\x03\x04")
        assert any(hit.startswith("offset 4,") for hit in header_hypotheses([blob]))

    def test_detects_big_endian(self):
        blob = self._stream([b"abc", b"defg"], endian=">")
        assert any("u16 BE" in hit for hit in header_hypotheses([blob]))

    def test_fixed_width_samples_are_not_records(self):
        blob = b"\x01\x02\x03\x04" * 4  # e.g. four 4-byte samples
        assert header_hypotheses([blob]) == []

    def test_single_record_is_not_evidence(self):
        blob = self._stream([b"abc"])
        assert header_hypotheses([blob]) == []


class TestLoad:
    """Reading the NDJSON produced by `xiaomi_client.py --capture`."""

    def test_parses_and_skips_blank_lines(self, tmp_path):
        path = tmp_path / "c.ndjson"
        path.write_text(json.dumps(_record()) + "\n\n" + json.dumps(_record(ch=2)) + "\n")
        records = load(str(path))
        assert [r["ch"] for r in records] == [5, 2]

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            load(str(tmp_path / "absent.ndjson"))
