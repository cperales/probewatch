"""Test audio between this PC and the watch (Hands-Free / HFP headset profile).

  uv run python src/audio_test.py beep              # play beeps on the watch speaker
  uv run python src/audio_test.py record [-s 5]     # record from the watch mic to recordings/
  uv run python src/audio_test.py loopback [-s 5]   # record from the mic, then play it back

The watch must be paired and connected (src/pair_watch.py) with PipeWire using the
"headset-head-unit" profile, which gives a 16 kHz mono sink and source.

Two counter-intuitive rules govern whether any of this works, both measured on the
hardware:

* Every stream needs a freshly created SCO transport. Re-activating the card profile
  (`off`, then `headset-head-unit`) before a playback worked 6/6; reusing a transport
  usually breaks it, and a broken one accepts PCM while transmitting nothing.
* Never keep a capture stream open while playing. A `parecord` on the same device
  takes the SCO connection and playback then sends zero packets - while `paplay`
  still exits 0 after roughly the length of the clip, which is why it looks fine.

Because of that, `paplay`'s exit code and timing prove nothing at all. The only honest
check is the controller's own SCO counters (`hciconfig hci0`): if the TX counter does
not move, no audio reached the watch.

And one limit that shapes the API: the watch closes the SCO link after about 1.3 s of
continuous playback, so anything longer is played in pieces (see `play_chunks`).
"""

import argparse
import math
import re
import struct
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from watch_secrets import default_mac, resolve_mac

MAC = default_mac()  # secrets/device.md or $WATCH_MAC; "" = not configured yet
DEV = MAC.replace(":", "_").upper()
CARD = f"bluez_card.{DEV}"
PROFILE = "headset-head-unit"
RATE = 16000  # HFP mSBC rate
RECORDINGS = Path(__file__).resolve().parent.parent / "recordings"
LINK_SETTLE = 1.5  # SCO link setup time before the first sample comes through
PLAY_TIMEOUT = 5  # seconds to wait beyond the clip length
SCO_PACKETS_PER_SECOND = 300  # measured: 215-248 packets for a 0.75 s clip
CHUNK_SECONDS = 0.7  # the watch drops the SCO link after ~1.3 s of continuous playback


def find_device(kind: str) -> str:
    """kind: 'sinks' or 'sources'. Returns the PipeWire name of the watch device."""
    out = subprocess.run(
        ["pactl", "list", "short", kind], capture_output=True, text=True, check=True
    ).stdout
    for line in out.splitlines():
        name = line.split("\t")[1]
        if DEV in name and not name.endswith(".monitor"):
            return name
    sys.exit(f"Watch {kind[:-1]} not found. Is it connected with the headset profile?\n{out}")


def stop_stream(proc: subprocess.Popen) -> None:
    """A dead SCO link makes the client ignore SIGTERM, so do not wait forever."""
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def restart_wireplumber() -> None:
    """Last resort: after `Failure in Bluetooth audio transport` the transport can stay
    in an error state through profile changes, and only a restart rebuilds it."""
    print("  restarting WirePlumber")
    subprocess.run(["systemctl", "--user", "restart", "wireplumber"], capture_output=True)
    time.sleep(5)


def reset_link() -> None:
    """Re-create the SCO transport by re-activating the HFP profile.

    This is what makes playback reliable (6/6). The transport does not tolerate being
    reused: the next stream usually fails, and a failed transport still accepts PCM
    from every client while sending no SCO packets at all. The waits are the ones the
    measurements were taken with - enabling the profile needs the longer one.
    """
    subprocess.run(["pactl", "set-card-profile", CARD, "off"], capture_output=True)
    time.sleep(0.5)
    subprocess.run(["pactl", "set-card-profile", CARD, PROFILE], capture_output=True)
    time.sleep(1.2)


def sco_counters() -> tuple[int, int]:
    """(rx, tx) SCO packet counts of the Bluetooth controller - the ground truth.

    A playback that never reaches the watch leaves both counters untouched, no matter
    what the client reports.
    """
    out = subprocess.run(["hciconfig", "hci0"], capture_output=True, text=True).stdout
    rx = re.search(r"RX bytes:\d+ acl:\d+ sco:(\d+)", out)
    tx = re.search(r"TX bytes:\d+ acl:\d+ sco:(\d+)", out)
    if not rx or not tx:
        sys.exit(f"Could not read SCO counters from hciconfig:\n{out}")
    return int(rx.group(1)), int(tx.group(1))


def wav_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return w.getnframes() / w.getframerate()


def make_beeps(path: Path, freqs=(880, 0, 1320), dur=0.25, volume=0.6) -> None:
    """Short tones (0 = silence), with 10 ms fade in/out to avoid clicks."""
    frames = bytearray()
    fade = int(RATE * 0.01)
    for f in freqs:
        n = int(RATE * dur)
        for i in range(n):
            env = min(1.0, i / fade, (n - i) / fade)
            v = volume * env * math.sin(2 * math.pi * f * i / RATE) if f else 0.0
            frames += struct.pack("<h", int(v * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(bytes(frames))


def play(path: Path, attempts: int = 3) -> None:
    """Play on the watch speaker, verifying that SCO packets actually left the radio."""
    clip = wav_seconds(path)
    expected = clip * SCO_PACKETS_PER_SECOND
    for attempt in range(1, attempts + 1):
        if attempt == attempts:
            restart_wireplumber()
        reset_link()
        sink = find_device("sinks")
        note = f" (attempt {attempt}/{attempts})" if attempt > 1 else ""
        print(f"Playing {path.name} on {sink}{note} ...")
        before = sco_counters()
        try:
            proc = subprocess.run(
                ["paplay", f"--device={sink}", str(path)],
                capture_output=True,
                text=True,
                timeout=clip + PLAY_TIMEOUT,
            )
            if proc.returncode != 0:
                print(f"  paplay failed ({proc.stderr.strip() or proc.returncode})")
        except subprocess.TimeoutExpired:
            print(f"  paplay did not return after {clip + PLAY_TIMEOUT:.0f}s")
        sent = sco_counters()[1] - before[1]
        if sent >= 0.7 * expected:
            print(f"  played ({sent} SCO packets)")
            return
        print(
            f"  only {sent} of ~{expected:.0f} SCO packets were sent, so nothing reached the watch"
        )
    sys.exit("Could not get audio out of the watch speaker.")


def play_chunks(path: Path) -> None:
    """Play a clip longer than the watch's playback window, in pieces.

    The watch tears the SCO link down after ~1.3 s of continuous playback (visible as the
    SCO entry disappearing from `hcitool con` while the client is still writing), so a
    longer clip is played piece by piece, each on a freshly created transport. That
    leaves an audible gap between pieces; the window itself cannot be extended.
    """
    seconds = wav_seconds(path)
    if seconds <= 0.9:
        play(path)
        return
    pieces = math.ceil(seconds / CHUNK_SECONDS)
    print(
        f"{seconds:.1f}s is longer than the watch's ~1.3s audio window: "
        f"playing it in {pieces} pieces, with a gap between them"
    )
    with wave.open(str(path)) as w:
        params = w.getparams()
        step = int(CHUNK_SECONDS * w.getframerate())
        with tempfile.TemporaryDirectory() as d:
            for i in range(1, pieces + 1):
                frames = w.readframes(step)
                if not frames:
                    break
                piece = Path(d) / f"{path.stem}_part{i}.wav"
                with wave.open(str(piece), "wb") as out:
                    out.setparams(params)
                    out.writeframes(frames)
                print(f"piece {i}/{pieces}")
                play(piece)


def record(seconds: float, attempts: int = 3) -> Path:
    """Capture from the watch mic, retrying while no audio comes through.

    A dead link does not error, it just delivers digital silence, so an all-zero take
    is the only signal that the link never came up.
    """
    RECORDINGS.mkdir(exist_ok=True)
    path = RECORDINGS / f"watch_mic_{time.strftime('%Y%m%d_%H%M%S')}.wav"
    samples: tuple[int, ...] = ()
    for attempt in range(1, attempts + 1):
        if attempt == attempts:
            restart_wireplumber()
        reset_link()
        source = find_device("sources")
        note = f" (attempt {attempt}/{attempts})" if attempt > 1 else ""
        print(f"Recording {seconds:.0f}s from {source} -> {path}{note} ... speak now!")
        proc = subprocess.Popen(
            [
                "parecord",
                f"--device={source}",
                "--file-format=wav",
                f"--rate={RATE}",
                "--channels=1",
                str(path),
            ]
        )
        time.sleep(seconds + LINK_SETTLE)  # the first second is lost to SCO setup
        stop_stream(proc)
        with wave.open(str(path)) as w:
            raw = w.readframes(w.getnframes())
        samples = struct.unpack(f"<{len(raw) // 2}h", raw) if raw else ()
        if any(samples):
            break
        print("  nothing came through (the SCO link never opened), retrying")
    peak = max((abs(s) for s in samples), default=0)
    print(
        f"Recorded {len(samples) / RATE:.1f}s, peak level {100 * peak / 32768:.0f}%"
        + ("  (all zeros: no audio from the watch)" if peak == 0 else "")
    )
    return path


def main() -> None:
    global MAC, DEV, CARD
    p = argparse.ArgumentParser()
    p.add_argument("mode", choices=["beep", "record", "loopback"])
    p.add_argument("-s", "--seconds", type=float, default=5)
    a = p.parse_args()
    MAC = resolve_mac(MAC or None)
    DEV = MAC.replace(":", "_")
    CARD = f"bluez_card.{DEV}"
    if a.mode == "beep":
        with tempfile.TemporaryDirectory() as d:
            wav = Path(d) / "beep.wav"
            make_beeps(wav)
            play(wav)
    elif a.mode == "record":
        record(a.seconds)
    else:
        wav = record(a.seconds)
        play_chunks(wav)
    print("Done.")


if __name__ == "__main__":
    main()
