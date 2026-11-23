"""Unit tests for the firmware package extractor (`scripts/extract_firmware.py`).

Pure logic: synthetic packages and record streams only. No hardware, no network,
and no real firmware file (that one is git-ignored and local).
"""

import struct
import sys
import zlib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from extract_firmware import BLOCK, HEADER_SIZE, extract_lcpu, marker_counts, parse_header


def _deflate(data: bytes) -> bytes:
    engine = zlib.compressobj(9, zlib.DEFLATED, -zlib.MAX_WBITS)
    return engine.compress(data) + engine.flush()


def _record(uncomplen: int, payload: bytes, with_complen: bool = True) -> bytes:
    body = _deflate(payload)
    head = (
        struct.pack("<II", len(body), uncomplen) if with_complen else struct.pack("<I", uncomplen)
    )
    return head + body


def _stream(blocks: list[bytes]) -> bytes:
    """Build the image1 record stream for *blocks*, mirroring the real framing."""
    total = sum(len(block) for block in blocks)
    first = _deflate(blocks[0])
    stream = struct.pack("<IIII", total, BLOCK, len(first) + 4, BLOCK) + first + b"\x00" * 4
    stream += _record(BLOCK, blocks[1], with_complen=False)  # uncomplen only
    stream += _record(BLOCK, blocks[2])  # complen + uncomplen
    stream += _record(len(blocks[3]), blocks[3])  # final, smaller block
    return stream


class TestParseHeader:
    def test_reads_the_three_sizes(self):
        header = bytearray(HEADER_SIZE)
        header[:4] = b"\xad\xef\xcd\xaf"
        struct.pack_into("<I", header, 0x0C, 0x2E718)
        struct.pack_into("<I", header, 0x1C, 0x31C4C7)
        struct.pack_into("<I", header, 0x20, 0x552000)
        assert parse_header(bytes(header)) == (0x2E718, 0x31C4C7, 0x552000)

    def test_rejects_another_container(self):
        with pytest.raises(SystemExit):
            parse_header(b"not a sifli image" + b"\x00" * HEADER_SIZE)


class TestExtractLcpu:
    def test_round_trips_every_record_shape(self):
        blocks = [b"A" * BLOCK, b"B" * BLOCK, b"C" * BLOCK, b"D" * 0x200]
        image, records = extract_lcpu(_stream(blocks), 0)
        assert image == b"".join(blocks)
        assert records == 4

    def test_rejects_a_short_walk(self):
        stream = bytearray(_stream([b"A" * BLOCK, b"B" * BLOCK, b"C" * BLOCK, b"D" * 0x200]))
        struct.pack_into("<I", stream, 0, BLOCK * 4)  # header claims more than the blocks hold
        with pytest.raises(ValueError, match="header says"):
            extract_lcpu(bytes(stream), 0)

    def test_rejects_a_wrong_block_size(self):
        stream = bytearray(_stream([b"A" * BLOCK, b"B" * BLOCK, b"C" * BLOCK, b"D" * 0x200]))
        struct.pack_into("<I", stream, 4, 0x1000)
        with pytest.raises(ValueError, match="block framing"):
            extract_lcpu(bytes(stream), 0)


class TestMarkerCounts:
    def test_counts_distinct_strings(self):
        counts = marker_counts(b"spp_connect\x00mass_file\x00spp_connect\x00")
        assert counts["spp"] == 1
        assert counts["mass"] == 1
        assert counts["gatt"] == 0
