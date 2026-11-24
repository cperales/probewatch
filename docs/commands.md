# Command ids — system, settings, watchfaces

The `(type, subtype)` catalogue for L2 channel 1, **read out of the official app**
(provenance in [apk-analysis.md](apk-analysis.md)). Each pair is a literal assignment in app
code, found with `trace_android_references` on the command envelope and read from the
decompiled method.

Source: [apk 9.8.348i] unless tagged.

A **✓** in the Watch column marks ids that answered on the watch and **✗** ids it rejects;
the responses, firmware and dates are in [commands-tested.md](commands-tested.md). Everything
else is "read from the app" and still needs a hardware check.

Notifications, health, alarms and contacts are in [commands-health.md](commands-health.md);
internal, bind, NFC, media, OTA and debug ids in [commands-internal.md](commands-internal.md).

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

| id | Meaning | Watch |
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
| 2/23 | quiet mode set (Alexa); the DND test used it and got `status: 1` | ✗ |
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

`2/34` (DND) was not found among the construction sites; the watch answers it with
`status: 1`. Several ids are reused (2/9, 2/14, 2/15, 2/18, 2/67): the payload selects the
operation.

## Type 4 — watchfaces

| id | Meaning | Watch |
|---|---|---|
| 4/0 | watchface list | ✓ |
| 4/1 | set active watchface | ✓ |
| 4/2 | delete watchface | |
| 4/3 | remove face photo (Wear OS path) | |
| 4/4 | install status | ✓ |
| 4/6 | delete unavailable faces by group | |
| 4/10 | face data list | |
| 4/11 | edit/request face layout | |

## Limits

- The app names the pairs; payload schemas still come from `proto/xiaomi.proto` (the javalite
  classes carry no field names).
- Reused ids (2/9, 2/14, 2/15, 2/18, 2/67) are one pair with a mode inside the payload.
- Type 1 bind/auth is in [commands-internal.md](commands-internal.md#type-1--auth-and-bind).
- Absence is not proof: an id may exist behind an unresolved helper.
