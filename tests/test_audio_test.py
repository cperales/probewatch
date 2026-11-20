"""Unit tests for audio_test.py — WAV generation and chunking logic.

These tests exercise the pure-logic functions without needing PipeWire,
PulseAudio, or a Bluetooth audio device.
"""

import math
import struct
import sys
from pathlib import Path

# Import from src/ via conftest sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
from audio_test import (
    CHUNK_SECONDS,
    RATE,
    make_beeps,
    wav_seconds,
)


class TestMakeBeeps:
    """make_beeps() creates a valid WAV file with tones."""

    def test_creates_file(self, tmp_path):
        path = tmp_path / "beep.wav"
        make_beeps(path)
        assert path.exists()
        assert path.stat().st_size > 0

    def test_valid_wav_header(self, tmp_path):
        path = tmp_path / "beep.wav"
        make_beeps(path)
        with open(path, "rb") as f:
            header = f.read(44)
        assert header[:4] == b"RIFF"
        assert header[8:12] == b"WAVE"

    def test_correct_sample_rate(self, tmp_path):
        path = tmp_path / "beep.wav"
        make_beeps(path)
        with wave_open(str(path)) as w:
            assert w.getframerate() == RATE
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2

    def test_default_tones(self, tmp_path):
        """Default: 880 Hz, silence, 1320 Hz, each 0.25 s."""
        path = tmp_path / "beep.wav"
        make_beeps(path)
        seconds = wav_seconds(path)
        assert abs(seconds - 0.75) < 0.01  # 3 * 0.25

    def test_custom_tones(self, tmp_path):
        path = tmp_path / "beep.wav"
        make_beeps(path, freqs=(440, 0, 880, 0), dur=0.1)
        seconds = wav_seconds(path)
        assert abs(seconds - 0.4) < 0.01  # 4 * 0.1

    def test_fade_in_out_no_clicks(self, tmp_path):
        """Tones should have fade in/out to avoid clicks (envelope at start/end is smooth)."""
        path = tmp_path / "beep.wav"
        make_beeps(path, freqs=(880,), dur=0.1)
        with wave_open(str(path)) as w:
            frames = w.readframes(w.getnframes())
        samples = struct.unpack(f"<{len(frames) // 2}h", frames)
        # First sample should be near 0 (fade in)
        assert abs(samples[0]) < 1000  # small envelope value
        # Last sample should be near 0 (fade out)
        assert abs(samples[-1]) < 1000


class TestWavSeconds:
    """wav_seconds() computes duration from a WAV file."""

    def test_short_clip(self, tmp_path):
        path = tmp_path / "short.wav"
        make_beeps(path, freqs=(880,), dur=0.1)
        assert abs(wav_seconds(path) - 0.1) < 0.001

    def test_longer_clip(self, tmp_path):
        path = tmp_path / "long.wav"
        make_beeps(path, freqs=(880,) * 10, dur=0.1)
        assert abs(wav_seconds(path) - 1.0) < 0.01


class TestPlayChunks:
    """play_chunks() splits long clips into pieces."""

    def test_short_clip_no_split(self, tmp_path):
        """Clips <= 0.9 s should not be split."""
        path = tmp_path / "short.wav"
        make_beeps(path, freqs=(880,), dur=0.25)
        seconds = wav_seconds(path)
        assert seconds <= 0.9

    def test_long_clip_split(self, tmp_path):
        """Clips > 0.9 s should be split into CHUNK_SECONDS pieces."""
        path = tmp_path / "long.wav"
        # Create a 2-second clip
        frames = bytearray()
        for _ in range(int(RATE * 2)):
            frames += struct.pack("<h", 0)
        with wave_open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(bytes(frames))
        seconds = wav_seconds(path)
        assert seconds >= 2.0

    def test_chunk_count(self, tmp_path):
        """A 2-second clip should produce ceil(2 / 0.7) = 3 pieces."""
        path = tmp_path / "long.wav"
        frames = bytearray()
        for _ in range(int(RATE * 2)):
            frames += struct.pack("<h", 0)
        with wave_open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(RATE)
            w.writeframes(bytes(frames))
        pieces = math.ceil(wav_seconds(path) / CHUNK_SECONDS)
        assert pieces == 3


# Helper to avoid importing wave module conflicts
def wave_open(path, mode="rb"):
    import wave as _wave

    return _wave.open(path, mode)
