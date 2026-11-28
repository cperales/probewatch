# Command results on the watch

What each `(type, subtype)` did when sent to this watch with `src/xiaomi_client.py --send`. The
ids and their meanings are in [commands.md](commands.md) and
[commands-health.md](commands-health.md), and the payload shapes are in `proto/xiaomi.proto`.

Source: [hw 2.2.110 2026-11-20] unless tagged. The watch runs a limited firmware: an id the app
knows can still answer `status: 1`.

## Reads

| Command | Result | Source |
|---|---|---|
| `2/1` battery | `level: 100, state: 3` | |
| `2/2` device info | serial, firmware, model | |
| `2/14` setting 2 | `dndSync` and notification settings | |
| `2/14` setting 1 | `wakeScreen`/`onlyWhenPhoneLocked`/`onlyWhenWorn` | |
| `2/24` raise-to-wake get | `raiseToWake { mode: 2 start 8:00 end 22:00 }` | |
| `2/39` workout types | 100+ types | |
| `2/51` widget screens | 4 screens | |
| `2/53` widget parts | 80+ parts | |
| `4/0` watchface list | 4 faces: Swirl (active), Dynamic data, Step space, Twilight | |
| `4/1` watchface set | `ack: 1`, not the list | |
| `4/4` install status | empty `watchface {}` | |
| `8/2` activity file ids | `activityRequestFileIds: ""`: nothing queued (see below) | |
| `8/3` past activity | no answer | |
| `8/8` SpO₂ config | `allDayCapable: 1 mode: SPO2_MODE_OFF`, low-SpO₂ alarm off (threshold 80) | [hw 2.2.111 2026-11-24] |
| `8/12` standing reminder | `standingReminder { enabled: true dnd: true }`, but the times are out of range (`start 14:96`, `dndEnd 160:30`): the proto probably does not match this firmware [inferred] | [hw 2.2.111 2026-11-24] |
| `8/29` workout status v2 | `workoutStatusWatchV2 { status: 0 }` | |
| `8/26`, `8/50`, `8/53` | `status: 1` | |
| `8/30` | no answer | |
| `8/35` vitality score | `vitalityScore { sevenDay: false dailyProgress: false }` | [hw 2.2.111 2026-11-24] |
| `8/42` goals get | `currentGoals: 1,2,3`, `supportedGoals: 1,2,3,4` | [hw 2.2.111 2026-11-24] |
| `17/0` alarms get | `schedule { alarms: 3 (ids 0,1,2; `alarmDetails { time hour minute } repeatMode enabled smart`), maxAlarms: 10 }` | [hw 2.2.111 2026-11-27] |
| `17/6` weekday info, empty body | no answer | [hw 2.2.111 2026-11-27] |
| `17/16` alert/dismiss, empty body | no answer | [hw 2.2.111 2026-11-27] |

Recheck on 2.2.111 [hw 2.2.111 2026-11-24], reads only: `2/1`, `2/2`, `2/14` (settings 1 and
2), `2/24`, `2/51`, `4/0`, `8/2` and `8/29` answer as on 2.2.110, and `2/34` and `2/78` still
answer `status: 1`. The writes below were not repeated on 2.2.111.
`8/8`, `8/12` and `8/35` already answered with data on 2.2.110; the responses quoted above
are from 2.2.111.

## Live health stream

| Fact | Source |
|---|---|
| `8/45` gets no direct answer but starts `8/47` `realTimeStats { steps calories heartRate }` about once per second, on **channel 1** | |
| During a workout (four sessions of squats): 114 frames, all on channel 1; 74 heart-rate samples from 0 to 112 bpm; `steps`/`calories` stay 0 | |
| Worn and idle: `heartRate` is 0 for ~18 s, then 58–62 bpm; `steps`/`calories` 0 | [hw 2.2.111 2026-11-24] |
| `8/2` keeps answering `activityRequestFileIds: ""` before, during and after a saved workout, also with `activitySyncRequestToday { unknown1: 1 }`: activity sync looks like a file transfer that never gets queued [inferred] | |

Why this matters for channels 2 and 5: [channels.md](channels.md#findings).

## Writes

| Command | Result | Source |
|---|---|---|
| `2/15` `dndSync { enabled: 1 }` | `status: 0`; the next read shows `enabled: 1` | |
| `2/15` `miscNotificationSettings { wakeScreen: 1 onlyWhenPhoneLocked: 2 onlyWhenWorn: 2 }` | `status: 0`; the next read matches | |
| `2/18` `system { findDevice: 0 }` with `--listen 8` | `status: 0`, the watch rings, and it sends `system { findDevice: 1 }` when the alert ends | [hw ? 2026-11-22] |
| `2/18` with no payload, disconnecting at once | `status: 0` but no ring: keep the link open | [hw ? 2026-11-22] |
| `2/23`, `2/34` DND | `status: 1`, not implemented | |
| `2/25` raise-to-wake set | transport ACK, no reply, value unchanged | |
| `2/78`, `2/79` device state | `status: 1` | |
| `17/5` `schedule { createAlarm { time { hour: 0 minute: 5 } repeatMode: 0 enabled: true smart: 2 } }` | `schedule { ackId: 0 }`; the 3-alarm schedule is unchanged, so `createAlarm` is acknowledged but not persisted this way | [hw 2.2.111 2026-11-27] |

DND was tried exhaustively: `2/23` with status 0 and 2, and `2/34` with status 0, all answer
`status: 1` and change neither `2/34` nor the `2/14` setting 2 read (`dndSync.enabled: 0`).

The write path is verified with two persistent settings, each read back in a new session and
then restored:

- **dndSync**: read `enabled: 0` → write `enabled: 1` (`status: 0`) → read `enabled: 1` →
  restore `enabled: 0` → read `enabled: 0`.
- **Notifications**: `wakeScreen 2→1`, `onlyWhenPhoneLocked 1→2`, `onlyWhenWorn 1→2`, read
  back, restored to `2/1/1`.

```bash
uv run python src/xiaomi_client.py --send 2 14 --payload 'system { miscSettingGet { setting: 2 } }'
uv run python src/xiaomi_client.py --send 2 15 --payload 'system { miscSettingSet { dndSync { enabled: 1 } } }'
uv run python src/xiaomi_client.py --send 2 15 --payload 'system { miscSettingSet { miscNotificationSettings { wakeScreen: 1 onlyWhenPhoneLocked: 2 onlyWhenWorn: 2 } } }'
uv run python src/xiaomi_client.py --send 2 14 --payload 'system { miscSettingGet { setting: 1 } }'
uv run python src/xiaomi_client.py --send 2 18 --payload 'system { findDevice: 0 }' --listen 8
```

Payload rules [gb]: `HourMinute` needs both `hour` and `minute`. `wakeScreen` and
`onlyWhenPhoneLocked` are 0 ignore / 1 enable / 2 disable, `onlyWhenWorn` is 1 enable /
2 disable, and `DoNotDisturb.status` is 0 enabled / 2 disabled. Tests of `build_command()` pin
these payload strings.

## Mass channel (`ota_type = 2`)

Read-only open probes; phone Bluetooth off; nothing resembling a firmware write was sent. Full
write-up in [mass-channel.md](mass-channel.md).

| Command | Result | Source |
|---|---|---|
| `22/0` `dataUpload { dataUploadRequest { type: 16 } }`, bare (no `md5sum`/`size`), plain and encrypted | transport ACK, no `DataUploadAck` — ACKed-and-ignored | [hw 2.2.111 2026-11-26] |
| `22/0` complete: `dataUploadRequest { type: 16 size: 1024 md5sum: <16 B> }` (watchface, no chunk pushed) | `dataUploadAck { errno: 0 resumePosition: 0 chunkSize: 4096 }`, request md5 echoed | [hw 2.2.111 2026-11-26] |
| `2/5` `system { firmwareInstallRequest { } }` (empty, no version/md5) | transport ACK, no `firmwareInstallResponse`; watch not armed (a follow-up read was normal) | [hw 2.2.111 2026-11-26] |

The receiver answers only after a *complete* `DataUploadRequest` (type + `md5sum` + `size`),
then replies `errno: 0` with `chunkSize: 4096`; the `2/5` reply codes stay unverified because
reading them needs a real `version`/`md5`.

## DLVP GATT probe

Read-only probe for the DLVP service Byterialab reports at `0xA407`–`0xA40E`
([device.md](device.md#debug-surface)); firmware 2.2.111, no write (no matching
characteristic).

| Probe | Result | Source |
|---|---|---|
| LE GATT (`gatttool -t le`) | 7 svcs / 18 ch, max `0x0033`; no `0xA407`–`0xA40E` | [hw 2.2.111 2026-11-28] |
| BR/EDR ATT (PSM `0x1f`) | same table, max `0x0034`; no `0xA407`–`0xA40E` | [hw 2.2.111 2026-11-28] |
| Vendor `0xaa01` read | refused (ATT `0x0a`); Device Name reads | [hw 2.2.111 2026-11-28] |

Bleak (`src/dlvp_probe.py`) could not hold LE discovery (0 services / "device disconnected");
`gatttool` and a raw ATT socket enumerated instead.

## Next probes

```bash
uv run python src/xiaomi_client.py --send 2 19          # authorize-unlock (laptop)
uv run python src/xiaomi_client.py --send 2 65          # always-on display
uv run python src/xiaomi_client.py --send 8 61          # sleep rhythm monitor
```

Start with ids whose payload is empty or a single integer: even a silent answer shows the watch
knows the id. Record the results here (see "Recording a finding" in `AGENTS.md`).
