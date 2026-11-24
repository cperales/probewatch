# Command ids — system, settings, notifications, health

The `(type, subtype)` catalogue for L2 channel 1, **read out of the official app**
(Mi Fitness 9.8.348i, `secrets/apk/`; provenance in [apk-analysis.md](apk-analysis.md)).
Each pair is a literal assignment in app code, found with `trace_android_references` on the
command envelope and read from the decompiled method.

A **✓** marks ids ProbeWatch has already confirmed on the watch (`DETAILS.md`); **✗** marks ids
the watch rejects. Everything else is "read from the app" and still needs a hardware check.

Internal, bind, NFC, media, OTA and debug ids are in [commands-internal.md](commands-internal.md).

## How the app encodes a command

The payload is the `Command` message already vendored in `proto/xiaomi.proto`:

```
uint32 type = 1;   uint32 subtype = 2;
oneof payload { ... 3..25 ... }  uint32 status = 100;
```

In the app the envelope is `defpackage.t1i` (R8-renamed): fields `c` = type, `d` = subtype,
then a oneof payload. Feature code builds it as

```java
t1i p = new t1i();
p.c = 2; p.d = 1;      // battery
p.<setter>(payload);   // optional
DeviceContact.call(did, p, needResponse, callback, timeoutMs);
```

`ContactTaskQueue` then hands it to the SDK client. `--send TYPE SUBTYPE` puts the same two
numbers on the wire, so every row below is directly runnable.

Coverage: 379 construction sites, 330 with literal pairs; the rest build the packet through
helpers.

## Type 2 — device, settings, system

| id | Meaning | ✓ |
|---|---|---|
| 2/0 | unbind / remove device | |
| 2/1 | battery status (read) | ✓ |
| 2/2 | device info (serial, firmware, model) | ✓ |
| 2/3 | time sync | |
| 2/4 | force-upgrade notification | |
| 2/5 | OTA prepare (`{force, type, version, md5}`) | |
| 2/6 | language sync (device settings) | |
| 2/7 | HID status, get (photo transfer) | |
| 2/8 | HID status, set (and HID input data) | |
| 2/9 | un-wear settings get; also NFC PIN status | |
| 2/10 | night mode get | |
| 2/11 | night mode set | |
| 2/12 | sedentary reminder get | |
| 2/13 | sedentary reminder set | |
| 2/14 | misc-setting get; wear-mode get; notification settings get | ✓ |
| 2/15 | misc-setting set; wear-mode set | ✓ |
| 2/17 | find-phone, stop event | |
| 2/18 | find-device start/stop | ✓ |
| 2/19 | authorize-unlock get | |
| 2/20 | authorize-unlock set | |
| 2/21 | un-wear password set | |
| 2/22 | quiet mode get (Alexa) | |
| 2/23 | quiet mode set (Alexa); `DETAILS.md` also reads this as DND and gets `status: 1` | ✗ |
| 2/24 | raise-to-wake get | ✓ |
| 2/25 | raise-to-wake set | ✗ |
| 2/27 | direct-card widget set | |
| 2/28 | direct-card widget get | |
| 2/29 | installed app list (app sort) | |
| 2/30 | app sort set | |
| 2/31 | app layout get | |
| 2/32 | shortcut down-button set | |
| 2/38 | shortcut support list get | |
| 2/39 | workout types | ✓ |
| 2/40 | sport sort set | |
| 2/41 | app layout set | |
| 2/44 | phone-mute mode sync | |
| 2/46 | vibrate-mode list get | |
| 2/47 | vibrate-mode default set | |
| 2/51 | widget screens | ✓ |
| 2/52 | widget group set | |
| 2/53 | widget parts | ✓ |
| 2/56 | Wi-Fi config add | |
| 2/58–61 | vibrate-mode add/update/delete variants | |
| 2/63 | "connected to new phone" notify | |
| 2/65 | AOD get | |
| 2/66 | AOD set | |
| 2/67 | watchface low-latency request | |
| 2/78 | app query status (third-party) | ✗ |
| 2/79 | device state | ✗ |
| 2/80 | device log pull / upload URL | |

`2/34` (DND) was not found among the construction sites; `DETAILS.md` records it as
unimplemented. Several ids are reused (2/9, 2/14, 2/15, 2/18, 2/67): the payload selects the
operation.

## Type 4 — watchfaces

| id | Meaning | ✓ |
|---|---|---|
| 4/0 | watchface list | ✓ |
| 4/1 | set active watchface | ✓ |
| 4/2 | delete watchface | |
| 4/3 | remove face photo (Wear OS path) | |
| 4/4 | install status | ✓ |
| 4/6 | delete unavailable faces by group | |
| 4/10 | face data list | |
| 4/11 | edit/request face layout | |

## Type 7 — notifications and calls

| id | Meaning | ✓ |
|---|---|---|
| 7/0 | add notification | |
| 7/1 | remove notification; missed call | |
| 7/6 | auto-screen-on get | |
| 7/7 | auto-screen-on set | |
| 7/9 | SMS list get | |
| 7/11 | SMS delete | |
| 7/12 | SMS list sync | |
| 7/14 | SMS send result | |
| 7/15 | app icon push (prepare) | |

## Type 8 — health, sport, files

| id | Meaning | ✓ |
|---|---|---|
| 8/0 | user info sync (height, weight, goals…) | |
| 8/1 | today's fitness file ids | |
| 8/2 | history fitness file ids | ✓ |
| 8/3 | request fitness file ids | |
| 8/4 | confirm fitness id | |
| 8/5 | confirm fitness id (fitness-file path) | |
| 8/6 | sport report list; gym offline report | |
| 8/8 | SpO₂ config get | ✓ |
| 8/9 | SpO₂ config set | |
| 8/10 | heart-rate config get; sleep-assist get | |
| 8/11 | heart-rate config set; sleep-assist set | |
| 8/12 | standing reminder get | ✓ |
| 8/13 | standing reminder set | |
| 8/14 | pressure monitoring get | |
| 8/15 | pressure monitoring set | |
| 8/17 | blood-pressure reminder | |
| 8/18 | ECG reminder get | |
| 8/19 | ECG reminder set | |
| 8/20 | "curse" (habit) prediction record | |
| 8/21 | vitality reminder get | |
| 8/22 | vitality reminder set | |
| 8/29 | sport status | ✓ |
| 8/30 | phone-sport pre-request config | |
| 8/35 | vitality score | ✓ |
| 8/38–40 | curse records/prediction/notify flags | |
| 8/41 | sleep segment write-back | |
| 8/42 | goals get | ✓ |
| 8/43 | goals set | |
| 8/45 | start real-time heart rate | ✓ |
| 8/46 | stop real-time heart rate | |
| 8/48–52 | sport/report variants, vitality upload, sport config | |
| 8/57 | track get | |
| 8/58 | track pre-install | |
| 8/60 | track delete | |
| 8/61 | sleep-rhythm monitor get | |
| 8/62 | sleep-rhythm monitor set | |
| 8/63 | sleep-rhythm reminder get | |
| 8/64 | gym sport request | |
| 8/65 | gym pace/speed/data | |
| 8/67 | gym lock; machine screen wake | |
| 8/68 | gym settings set | |
| 8/69 | sleep-rhythm reminder set | |
| 8/70 | research user profile | |
| 8/71–75 | medical/research fitness ids | |
| 8/76–79, 82 | research app/device lists, calibration, BP | |
| 8/83 | Just Dance phone control | |
| 8/87 | training-plan sync | |
| 8/88 | training-plan stop | |

## Type 17 — alarms, world clock, reminders

| id | Meaning | ✓ |
|---|---|---|
| 17/0 | alarms get | |
| 17/4 | alarms delete | |
| 17/5 | alarm add/update; proto alarm sync | |
| 17/6 | alarm weekday info | |
| 17/8 | sleep model get | |
| 17/9 | sleep model set; sleep-model time | |
| 17/10–13 | world clock get/sync/delete | |
| 17/14 | todo/event reminder get | |
| 17/15 | todo/event reminder add/update | |
| 17/16 | alarm alert/dismiss on watch | |
| 17/17 | event reminder update | |
| 17/18 | event reminder delete | |
| 17/19 | reminder list sync | |

## Type 21 — SOS and contacts

| id | Meaning | ✓ |
|---|---|---|
| 21/0 | emergency contacts get | |
| 21/1 | emergency contacts set; SOS contact sync | |
| 21/3 | contact info send | |
| 21/4 | top-contact list get | |
| 21/5 | top-contact add | |
| 21/7 | contact sync | |
| 21/9 | SOS response | |

## Useful probes to run next

```bash
uv run python src/xiaomi_client.py --send 2 19          # authorize unlock (laptop)
uv run python src/xiaomi_client.py --send 2 65          # always-on display
uv run python src/xiaomi_client.py --send 8 61          # sleep rhythm monitor
```

Start with ids whose payload is empty or one integer: a silent answer still tells us the watch
knows the id. Record results in `DETAILS.md`.

## Limits

- The app names the pairs; payload schemas still come from `proto/xiaomi.proto` (the javalite
  classes carry no field names).
- Reused ids (2/9, 2/14, 2/15, 2/18, 2/67) are one pair with a mode inside the payload.
- Type 1 bind/auth is in [commands-internal.md](commands-internal.md#type-1--auth-and-bind).
- Absence is not proof: an id may exist behind an unresolved helper.
