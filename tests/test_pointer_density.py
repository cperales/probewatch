"""Unit tests for the pointer-density check (`scripts/pointer_density.py`).

Pure logic: synthetic images only, no real firmware file (that one is git-ignored).
"""

import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from pointer_density import count_in_range, image_words, self_pointers, sweep

BASE = 0x20000000
SIZE = 0x400


def _image(values: list[int], pad: int = 0) -> bytes:
    body = struct.pack(f"<{len(values)}I", *values)
    return body + b"\x00" * pad


def test_words_are_sorted_and_shifted() -> None:
    data = _image([0x30, 0x10, 0x20])
    assert image_words(data) == [0x10, 0x20, 0x30]
    assert image_words(data, shift=0x10) == [0x00, 0x10, 0x20]


def test_words_drop_a_trailing_partial_word() -> None:
    assert len(image_words(b"\x01\x02\x03")) == 0
    assert len(image_words(b"\x01\x02\x03\x04\x05")) == 1


def test_count_in_range_is_half_open() -> None:
    words = [10, 20, 30, 40]
    assert count_in_range(words, 20, 40) == 2
    assert count_in_range(words, 0, 1000) == 4
    assert count_in_range(words, 41, 1000) == 0


def test_self_pointers_bracket_the_image() -> None:
    words = [BASE - 0x10, BASE, BASE + 0x3FF, BASE + 0x400, BASE + 0x500]
    assert self_pointers(words, BASE, SIZE) == [BASE, BASE + 0x3FF]


def test_sweep_peaks_at_the_true_base() -> None:
    # Twelve pointers spread over the image, as a real image does.
    values = [BASE + offset for offset in range(0x40, SIZE, 0x40)]
    words = image_words(_image(values))
    results = dict(sweep(words, BASE, SIZE, window=0x1000, step=0x100))
    assert results[BASE] == len(values)
    # One image-length below, the window no longer covers them.
    assert results[BASE - SIZE] == 0
    # The peak is at the base, not next to it.
    assert max(results, key=results.get) == BASE


def test_shift_recovers_a_relocated_image() -> None:
    stored = [BASE + 0x40 + 0x26000, BASE + 0x80 + 0x26000]
    words = image_words(_image(stored), shift=0x26000)
    assert self_pointers(words, BASE, SIZE) == [BASE + 0x40, BASE + 0x80]
    # Without the shift the same words point past the image.
    unshifted = image_words(_image(stored))
    assert self_pointers(unshifted, BASE, SIZE) == []
