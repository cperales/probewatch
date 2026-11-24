# Command ids — notifications, health, alarms, contacts

The rest of the channel-1 `(type, subtype)` catalogue read out of the official app. How the
app encodes a command, and types 2 and 4, are in [commands.md](commands.md).

Source: [apk 9.8.348i] unless tagged.

A **✓** in the Watch column marks ids that answered on the watch and **✗** ids it rejects;
the responses, firmware and dates are in [commands-tested.md](commands-tested.md). Everything
else is "read from the app" and still needs a hardware check.

## Type 7 — notifications and calls

| id | Meaning | Watch |
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

| id | Meaning | Watch |
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

| id | Meaning | Watch |
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

| id | Meaning | Watch |
|---|---|---|
| 21/0 | emergency contacts get | |
| 21/1 | emergency contacts set; SOS contact sync | |
| 21/3 | contact info send | |
| 21/4 | top-contact list get | |
| 21/5 | top-contact add | |
| 21/7 | contact sync | |
| 21/9 | SOS response | |
