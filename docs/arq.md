# ARQ — L1 acknowledgement, windows and retransmission

How DATA frames are acknowledged and resent. The frame header is in
[protocol.md](protocol.md#l1-frame); the code is `XiaomiWatch._pump()` and `_send_data()` in
`src/xiaomi_client.py`.

Source: [apk 9.8.348i] (`com.xiaomi.wearable.transport.layerl1`, see
[apk-analysis.md](apk-analysis.md)) unless tagged.

## What the app does

| Constant | Value | Consequence |
|---|---|---|
| `SAR_DEFAULT_MPS` | 64512 | max payload per L1 frame |
| `SAR_DEFAULT_TX_WIN_LOCAL` / `_REMOTE` | 32 / 4 | local send window, peer's advertised window |
| `SAR_SEND_TIMEOUT` | 10 s | retransmit unacked DATA |
| `SAR_CUM_ACK_TIMEOUT` | 500 ms | cumulative ACK after a quiet burst |

- Only DATA frames are ACKed. ACK at once when `payload[0]` (the L2 channel) is `1` or `8`, or
  when the pending count reaches `window * 2/3`; otherwise delay.
- A DATA frame whose `seq - expected` is `>= 128` (unsigned) is a stale duplicate: drop it, do
  not NAK. Any other out-of-order frame gets a NAK and the peer resends from `txBase`.
- More than 32 unacked DATA frames are refused, so a bulk transfer stalls without window
  accounting.
- Send priority: channel 1 → 2, channel 3 → 3, channel 7 → 1, all others 0 (higher goes first
  among unassigned DATA).

## What the client does

The same rules, from the constants on `XiaomiWatch`: `TX_WINDOW` 32, `SEND_TIMEOUT` 10 s,
`CUM_ACK_TIMEOUT` 0.5 s, `ACK_THRESHOLD` = `TX_WINDOW * 2 // 3` = 21. `REMOTE_WINDOW` 4 is
kept for parity with the app's `SAR_DEFAULT_TX_WIN_REMOTE`, but the client does not enforce it.

- Unacked frames sit in `_sent` in insertion order, so a cumulative ACK releases the right
  frames across the 8-bit seq wrap.
- On **every** NAK the client resends from the first missing seq (a range); each frame also has
  its own 10 s retransmit timer.
- `_send_data()` returns `None` when the window is full: the caller pumps and retries, and never
  drops the frame.
- The watch advertises a TX window of 3 in its session config
  ([protocol.md](protocol.md#session-parameters)).

## Measured

| Test | Result | Source |
|---|---|---|
| 300 commands back to back, crossing seq 255 → 0 | the watch ACKs cumulatively per 8-bit seq; the window drains with no retransmit; 300/300 replies | [hw ? 2026-11-22] |
| 40 commands without waiting for replies | the client stops at 32 unacked and resumes as ACKs free the window; 40/40 replies | [hw ? 2026-11-22] |
| 16 KB payload per frame | 20 frames (320 KB) in ~3 s, 20/20 replies | [hw ? 2026-11-22] |
| One 24 KB frame | closes the link: the practical limit is below the watch's advertised `0x8000` | [hw ? 2026-11-22] |

Mi Fitness installed 2.2.111 on 2026-11-22, the same day, and the firmware version for these
runs was not recorded.
