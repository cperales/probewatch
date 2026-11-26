# Command ids — internal, media and third-party channels

The long tail of the `(type, subtype)` catalogue: bind/auth, NFC, eSIM, weather, stocks,
calendar, factory/debug, media, Alexa, app management and MiLink. Same provenance as
[commands.md](commands.md): read from the app, source [apk 9.8.348i] unless tagged. A **✓**
marks an id the watch answered or acted on and **✗** one it rejects; results, firmware and
dates are in [commands-tested.md](commands-tested.md).

Most of these need a structured payload, so they are documentation rather than ready probes.
Meanings are the app's method and class names; where those are opaque (`fz2#a`), they are the
best reading of the call site.

## Type 1 — auth and bind

| id | Meaning | Watch |
|---|---|---|
| 1/1 | bind info get (v1 binder) | |
| 1/2 | bind result send (v1) | |
| 1/17 | bind info get (v2 / Wear OS binder) | |
| 1/18 | bind key apply / local bind step | |
| 1/19 | bind verify / confirm step | |
| 1/25 | bind confirm variant | |

These are transport-level bind messages. The client's own auth steps already live on type 1
(always channel 1, plaintext; see [session.md](session.md#authentication)) and are not `--send` experiments.

## Type 5 — NFC and transit cards

Built by `defpackage.fz2` (the NFC facade) and `AutoSwitchCardViewModel`.

| id | Meaning |
|---|---|
| 5/0 | raw APDU exchange with the watch SE |
| 5/1 | open/close card session (`r` = true, `n` = false) |
| 5/2 | end/close TAI session |
| 5/3 | write card data |
| 5/4 | read/commit card data |
| 5/5 | card operation (`j`) |
| 5/6 | card id / serial get |
| 5/7 | card read (`p`) |
| 5/8 | card probe (`a`) |
| 5/10 | status get (`t`) |
| 5/11 | card switcher list |
| 5/13 | card write step |
| 5/14 | card update step |
| 5/16 | card image/info |
| 5/17, 5/19 | TAI enable/disable |
| 5/18 | sector probe (Mifare) |
| 5/20 | Mifare Classic read |
| 5/21, 5/22 | auto-switch card off/on |

## Type 9 — eSIM / LPA

| id | Meaning |
|---|---|
| 9/1 | eUICC info get |
| 9/2 | profiles list |
| 9/3 | profile operation (enable/disable/delete) |
| 9/5 | prepare profile download |
| 9/6 | download profile |
| 9/9 | HTTP response proxy |

## Type 10 — weather

| id | Meaning | Watch |
|---|---|---|
| 10/0–2 | weather payload parts (city, current, forecast) | |
| 10/4 | weather + pressure | |
| 10/5, 10/6 | device location update | |
| 10/5, 10/7–10 | weather settings sync variants | |

## Type 11 — stock quotes

| id | Meaning |
|---|---|
| 11/0 | stock info sync |
| 11/1 | stock list update |
| 11/2 | stock delete |
| 11/3 | stock list save |
| 11/4 | symbol list get |

## Type 12 — calendar

| id | Meaning |
|---|---|
| 12/1 | calendar sync (add/clear) |

## Type 13 — factory, self-check and debug

| id | Meaning |
|---|---|
| 13/0 | factory mode |
| 13/1 | NFC config |
| 13/2 | device log dump |
| 13/4 | media log dump |
| 13/6 | device mode get |
| 13/7 | self-check start / switch / exit |
| 13/9, 13/12, 13/13 | installed-app info (debug) |
| 13/10, 13/15 | sensor replay / capture |
| 13/11 | debug packet (`yh2`) |

## Type 14 — AIShan third-party faces

| id | Meaning |
|---|---|
| 14/0 | generic command (wrapper `AFlashPacketSender`) |
| 14/7 | connect-success handshake |

## Type 15 — Wear OS faces

| id | Meaning |
|---|---|
| 15/3 | install Wear OS face |

## Type 16 — location

| id | Meaning |
|---|---|
| 16/2 | post location |

## Type 18 — music and media

| id | Meaning |
|---|---|
| 18/1 | media state sync (default device, no-music, permission) |
| 18/3 | music config load |
| 18/7 | song list by id |
| 18/10 | songs by page / single song |
| 18/11 | pre-send file |

## Type 19 — Alexa

| id | Meaning |
|---|---|
| 19/0 | AVS instructions |
| 19/1 | AVS config sync |
| 19/2 | AVS config load |

## Type 20 — apps and smart home

| id | Meaning |
|---|---|
| 20/0 | installed watch apps |
| 20/1 | prepare app install |
| 20/3 | uninstall app |
| 20/4 | launch app |
| 20/7 | phone app status sync |
| 20/8 | phone message send |
| 20/11 | WeChat license |
| 20/13 | smart-home device list |
| 20/15 | smart-home scenes |
| 20/17 | smart-home control result |
| 20/19 | course schedule |
| 20/20 | third-party blood sugar |

## Type 22 — mass channel (`DataUpload`)

| id | Meaning |
|---|---|
| 22/0 | `DataUpload`: `DataUploadRequest{type, md5sum, size}` → `DataUploadAck{errno, resumePosition, chunkSize}` (`proto/xiaomi/wear_mass.proto`) |
| 22/1 | mass "control" (silent upgrade, music transfer) |

This is the family the `ota_type = 2` path uses to arm the channel-2 file push; the request
shape, the channel-2 framing and what a read-only open returns are in
[mass-channel.md](mass-channel.md) (see also [ota.md](ota.md)).

## Type 23 — MiLink and AICR

| id | Meaning |
|---|---|
| 23/3 | share-device sync |
| 23/4 | share-device update |
| 23/8 | control result |
| 23/10 | MiLink device list |
| 23/12 | connect state |
| 23/19, 23/22 | phone state |
