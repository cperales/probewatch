# Sound — DAC, tone and alert dispatch

How the watch plays a tone and sets its volume, recovered by reading the LCPU firmware image.
The alarm list and the RTC wake are in [alarm-scheduler.md](alarm-scheduler.md);
[firmware.md](firmware.md) says which image each half lives in. Nothing was flashed or
executed and the watch was not contacted for this page. Legal framing is
[README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged. LCPU addresses are `0x12…` (load base `0x12000000`, data
pointers stored `+0x26000` with the Thumb bit; string addresses inside code are **not**
shifted).

## Where it lives

All of it is on the **LCPU**. The HCPU image has no DAC, tone or `play_sound` code — only the
RTC time/compare path covered in [alarm-scheduler.md](alarm-scheduler.md#which-core-owns-the-alarm--corrected).

| Piece | Address |
|---|---|
| DAC command handler | `0x120d1360` |
| codec volume setter | `0x12163908` |
| 1 kHz sine self-test | `0x120f6f68` |
| `play_sound` / `play_sound_stop` | `0x1218fb48` / `0x12193fc0` |
| alert popup dispatcher | `0x12042550` |

Neither image has a "beep" or "tone" string: the tone is an MMIO sequence, not a named
routine. Symbol rows: [firmware-symbols-lcpu.md](firmware-symbols-lcpu.md).

## The DAC volume path

`0x120d1360` is the DAC command handler, `f(dac_ctx, subtype, value)`. A `tbb` at
`0x120d1376` dispatches on `subtype`:

| Subtype | Effect | Log string |
|---|---|---|
| `1` | enable sequence: two register writes `0x4e`, `0x4f` | — |
| `2` | teardown | — |
| `0x1c` | store `value` to `ctx+0xb8` | `AUDCODEC set source %d` |
| `0x1d` | store `value` to `ctx+0xc0` | `AUDCODEC set dest %d` |
| `0x1e`, `0x1f` | unsupported, returns -1 | — |
| `0x20` | clamp to `0..0x6c`, set both channels | `dac set volume: prc=%d codec=%d` |
| `0x21` | mute | `codec dac mute set:%d` |

Volume goes through `0x12163908(ctx+0xb0, channel, vol)` for channel 0 and 1. That function
rejects `vol` outside `-72..108` — the same `0x6c` bound — then converts with `udiv r2, #6`
into a packed attenuation field, so the scale is a curve, not linear.

The codec context is `0x603d1630`; `0x12264118` initialises it, zeroes `0x178` bytes, sets
`[ctx+0xb0] = 0x50088000` (the audio block) and calls the device helper `0x12161a8c` with the
name `"audcodec"`.

The handler's address is a data word at file offset `0x2e38ec`, inside a 21-entry array of
Thumb pointers (`0x2e38a0`–`0x2e38f4`) that also holds the `AUDPRC DAC dest invalid` routine
at entry 8. The array base is not referenced anywhere in the image, so **which index selects
an entry, and from where, is not established**.

## The tone routine

`__cmd_codec_hp_sin1k_test` at `0x120f6f68` (986 B) is the closest thing to a beep: a 1 kHz
sine self-test written straight to registers, with no callee except a delay veneer. It drives
`0x50088004` (audio block), `0x500c0010` (codec clock), `0x5000000c` and `0x500ca068`:

1. Enable the codec clock, write `0x7101` to `0x500c0010+0x18` (the divider for 1 kHz), wait
   100 ms.
2. Enable the audio block (`+0x80` bits `0x10000000`, `0x08000000`, `0x8000`; `+0x88`,
   `+0x8c`, `+0x90`).
3. Wait 50 ms, then a **binary search over 8 iterations**: write a divisor into `+0x80` bits
   `0x3e0000`, poll `+0xa0` bit 31, read the counter at `+0xa4`, compare against
   `0x072e0000`/`0x072f0000` (1838), halve the step and repeat. An auto-trim loop that tunes
   the divider until the measured frequency lands in the window.
4. Restore the tuned divisor and walk the analog enable sequence at `+0xbc`/`+0xc0`, with
   5/1/10/10 ms delays.
5. Set the final codec fields (`+0x00 |= 0xc`, `+0x0c = 0x1402`, `+0x30 = 0xa2`,
   `+0x38 = 6`, `+0x00 |= 2`) and return 1.

Confidence: **medium** for the naming — the register offsets and the bisection are read from
the code, but which SiFli block each base is comes from the SDK layout, not the image.

## The sound path

`play_sound(id, arg)` at `0x1218fb48` builds `{1, id, 0, 0, arg-1}` and posts message
`0xc802` on channel 5. `play_sound_stop()` at `0x12193fc0` posts the same id with flag 0.
The factory speaker self-test callbacks (`0x1201f93c`, `0x1201f9c8`, `0x1201fa1c`) call
`play_sound(5, -1)` and `play_sound(0x18, -1)`. `play_sound` has 39 BL callers over 33
functions — every popup logic object, so it is the common entry for every sound.

The alarm ring is one of them: `g_popups_alarm_remind_logic` at `0x1221bea4` calls
`play_sound(0xf` or `0x27, 0x1e)`, choosing between the two by a per-alarm flag, and
`g_popups_alarm_remind_third_time_logic` at `0x1221c22c` calls it twice for the third
reminder. The logic objects are invoked through a pointer, so no direct call leads to them.

The audio module dispatches on `msg[2]`. `0xc802` opens a range: `subs r1, r0, #0xc802;
cmp r1, #0xe` → a `tbh` at `0x12094ad4` for `0xc802`..`0xc810`. Case `0xc802` is
`0x12094af6`, which loads `msg+8` and calls `0x12042550`.

`0x12042550` is the **alarm-reminder popup dispatcher**, not a DAC routine. It looks up page
and logic names — `binding`, `drain_water`, `alarm_remind`, `alarm_rmd_thr`, `cd_finished`,
`wake_up_remind`, `sound_vibrate` — through `0x1a22c0`, then takes a two-byte alert:
`[alert]` a flag and `[alert+1]` an event id. Event `0x12` is special-cased; ids `0xd`..`0x20`
index a `tbb` at `0x12042644`:

| event | target | event | target |
|---|---|---|---|
| `0xd`, `0x15`, `0x16` | `0x1204265c` | `0x19` | `0x120426c6` |
| `0xe`, `0x10`, `0x13`, `0x14`, `0x17`, `0x18`, `0x1a`–`0x1f` | `0x120426b8` | `0x20` | `0x12042774` |
| `0xf`, `0x11`, `0x12` | `0x120426a6` | | |

Confidence: the chain `play_sound` → `0xc802` → `0x12042550` is certain; **which event id
means ring versus vibrate is not resolved**, and the popup half may only raise the UI while
the sound comes from a separate path.

## Confirmed command → routine mappings

The shell (MSH) registry at file offset `0x49b4d0` is a table of 3-word entries
`{name, description, handler}` with relocated pointers. Two entries reach the code above and
are the only fully confirmed mappings:

| Command | Handler | Reaches |
|---|---|---|
| `audio_codec` | `0x120f6f68` | `__cmd_codec_hp_sin1k_test`, the tone routine |
| `set codec dac volume` | `0x120f6f08` | `__cmd_codec_dac_set_vol` → `0x12163908` |

`__cmd_codec_dac_set_vol(argc, argv)` requires `argc == 2`, parses the value with
`atoi` (`0x1219f16c`) and calls the setter for both channels. Neither command is reachable
over SPP: they need a shell.

The same registry holds `__cmd_wdt`, `__cmd_mic_gain`, `__cmd_pdm_gain`, `__cmd_aprc_debug`
and `__cmd_update_pll`; see the symbol map for their handlers.

## Still open

- Which handler actually rings the watch for `2/18`: its mi_pb case builds a response, so the
  tone comes from somewhere else ([alarm-scheduler.md](alarm-scheduler.md#the-internal-message-router)).
- The 21-entry DAC pointer array's index and caller.
- Which alert event id selects the ring pattern.
