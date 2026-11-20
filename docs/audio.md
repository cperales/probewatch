# Audio (HFP) — Hands-Free Profile

The audio subsystem uses Bluetooth Classic's Hands-Free Profile (HFP) to stream audio
between the PC and the watch. The watch acts as the Hands-Free (HF) unit and the PC as
the Audio Gateway (AG).

## Profile and codec

| Parameter | Value |
|---|---|
| Profile | Hands-Free (`headset-head-unit`; `headset-head-unit-cvsd` for narrowband) |
| Codec | mSBC (wideband, 16 kHz) or CVSD (narrowband, 8 kHz) |
| Sample rate | 16 kHz with mSBC, 8 kHz with CVSD |
| Channels | Mono |
| Sink node | `bluez_output.<mac>.1` (playback to the watch) |
| Source node | `bluez_input.<mac>.0` (capture from the watch mic) |
| Default volume | 40% (-23.88 dB) on the sink |

`<mac>` is the watch address with underscores, so the names can be read from
`pactl list short sinks` / `pactl list short sources`. `src/audio_test.py` derives them
from the MAC (`DEV` and `CARD`).

## SCO transport — the core problem

The Single Connected (SCO) link between PC and watch has two critical quirks that make
audio unreliable:

### Quirk 1: Transport reuse breaks playback

A SCO transport **does not tolerate being reused**. After the first playback:

- The transport enters a broken state that **accepts PCM data from every client**
- `paplay` exits 0 in ~0.8 s while sending **zero SCO packets**
- The watch receives nothing, but the client reports success

**Fix**: Re-create the SCO transport before every playback:

```bash
pactl set-card-profile bluez_card.<mac> off
sleep 0.5
pactl set-card-profile bluez_card.<mac> headset-head-unit
sleep 1.2
```

(`reset_link()` in `src/audio_test.py` does exactly this for the configured MAC.)

This worked 6/6 times in testing. Reusing a transport usually fails.

### Quirk 2: Capture takes the SCO link

If a capture stream (`parecord`) is open while playing:

- The single SCO link goes entirely to the capture
- Playback sends **zero packets** even though `paplay` exits 0
- The watch receives nothing

**Fix**: Never keep a capture stream open while playing. `loopback` mode records first,
then plays back (after closing the capture).

## Verification — the only reliable check

**`paplay` return code and timing prove nothing.** The only honest verification is the
Bluetooth controller's own SCO counters:

```bash
hciconfig hci0
# Look for: RX bytes:xxx acl:xxx sco:(N)
#           TX bytes:xxx acl:xxx sco:(N)
```

If the TX counter does not move, **no audio reached the watch**. Measured rates are
roughly 300 packets/s (215-248 packets for a 0.75 s clip).

## Playback window limit

The watch tears the SCO link down after **~1.3 seconds** of continuous playback. This is
visible in `hcitool con` — the SCO entry disappears while the client is still writing.

| Clip length | Result |
|---|---|
| ≤ 0.75 s | Plays in one piece (215-248 packets) |
| 0.75–1.3 s | May work in one piece |
| > 1.3 s | Fails at ~1.3 s (counter stops short, e.g. 140 of ~380) |

**Workaround**: Split longer clips into 0.7 s pieces, each on a fresh transport. This
leaves an audible gap between pieces that cannot be avoided.

## Capture behavior

Capture does **not** have the 1.3 s limit. Recorded captures of 4 s work fine.

### Capture quirks

| Issue | Detail |
|---|---|
| SCO setup loss | First ~1 s is lost to SCO establishment |
| Dead link = silence | `parecord` writes digital silence and exits 0 (no error) |
| All-zero detection | `record()` retries when the take is all zeros |
| Echo cancellation | Watch mic does not pick up its own speaker (can't verify playback this way) |

### Recording parameters

```python
LINK_SETTLE = 1.5    # SCO setup time before first sample
record(seconds) → records (seconds + LINK_SETTLE)
```

## Failure recovery

| Symptom | Recovery |
|---|---|
| `Failure in Bluetooth audio transport` | `systemctl --user restart wireplumber` |
| Transport object survives restarts | Re-create the profile (`off` → `headset-head-unit`) |
| All attempts fail | `restart_wireplumber()` as last resort |

## Audio test script (`src/audio_test.py`)

The script implements all the workarounds above:

| Function | What it does |
|---|---|
| `reset_link()` | Re-creates SCO transport (off → profile, waits) |
| `sco_counters()` | Reads TX/RX SCO counters from `hciconfig` |
| `play(path)` | Plays with SCO counter verification, retries up to 3x |
| `play_chunks(path)` | Splits >0.9 s clips into 0.7 s pieces |
| `record(seconds)` | Records with LINK_SETTLE, retries on all-zero |
| `make_beeps(path)` | Generates tones with fade in/out |

### Usage

```bash
uv run python src/audio_test.py beep              # play test tones
uv run python src/audio_test.py record -s 5       # record 5 s from mic
uv run python src/audio_test.py loopback -s 5     # record then play back
```

WAV files are saved to `recordings/watch_mic_<timestamp>.wav`.

## Why this is unreliable

The root cause is not in the Xiaomi protocol — it is in the BlueZ/WirePlumber stack on
Linux. The SCO transport implementation does not handle state transitions cleanly:

1. A broken transport accepts PCM without transmitting
2. The transport object survives WirePlumber restarts
3. The watch enforces a hard 1.3 s limit on continuous playback

The workarounds in `audio_test.py` are practical fixes, not protocol-level solutions.
The underlying issue requires changes to BlueZ or WirePlumber firmware.
