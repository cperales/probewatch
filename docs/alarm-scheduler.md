# Alarms — the scheduler and the RTC wake

How the watch keeps a list of alarms and arms its real-time clock to wake for the next one,
recovered by reading the two firmware images. The sound path itself (DAC volume, the codec
tone) is in [sound-alarms.md](sound-alarms.md); [firmware.md](firmware.md) only says which
image each half lives in. Nothing was flashed or executed and the watch was not contacted for
this page. Legal framing is [README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged. Addresses are LCPU `0x12…` (load base `0x12000000`,
data pointers stored `+0x26000` with the Thumb bit) and HCPU `0x2001…`.

## The service thread

`0x1202647c` calls the RT-Thread thread initialiser with:

| Argument | Value |
|---|---|
| thread control block | `0x603b4a7c` (LCPU RAM) |
| name | `alarmsvc` |
| entry | `0x122640e8` |
| stack | `0x2004e9c0`, `0x400` bytes |
| priority, tick | `0xc`, `5` |

The context it shares with the rest of the module is `0x603b3d2c`: a list head at `+0`, a
mutex at `+8`, an event object at `+0x38`, and the currently armed alarm node at `+0x64`.
The entry is a wait loop — `rt_event_recv(ctx+0x38, 0xffff, 6, -1, &bits)` and then
`0x1204f3c8` — so everything else in the module only has to raise that event.

The RT-Thread API names come from the argument shape; the calls go through
`movw ip`/`movt ip`/`bx ip` veneers into ROM.

## The scan (`0x1204f3c8`)

Under the mutex it reads the current time (`0x1219f11c`, `0x12190138`), then walks the list
twice:

1. **Per node**: `[node+8]` is a flag word. Bit 0 is "enabled"; bits 8–14 are a day mask with
   the values `0x100`, `0x200`, `0x400`, `0x800`, `0x1000`, `0x2000`, plus `0x4000` handled
   separately. The time of day is at `+0x10`/`+0x14`/`+0x18`, a day/absolute field at
   `+0x1c`/`+0x20`/`+0x28`, and a callback at `+0xc`.
2. **Selection**: of the enabled nodes it keeps the smallest positive delta (the next alarm)
   and the smallest negative one (the missed alarm), both in seconds.

The arithmetic is unambiguous: `0xe10` (3600) for hours and `0x15180` (86400) for days,
building `day*86400 + h*3600 + m*60 + s` on both sides of the comparison.

It then calls `0x121900e4(node)` for the chosen node, stores it in `ctx+0x64`, and invokes
the node's own callback `[node+0xc]` when the alarm is due.

## The RTC arm (`0x121900e4`)

```
dev = rt_device_find("rtc");
if (!dev) return 1;
args = { time fields from node+0x10, enable = node[8] & 1 };
r = rt_device_control(dev, 0x13, &args);   /* RT_DEVICE_CTRL_RTC_SET_ALARM */
if (r) return r;
if (args.enable)
    rt_device_control(dev, 0x12, &args);   /* RT_DEVICE_CTRL_RTC_GET_ALARM */
node+0x10..0x18 = args;                    /* read back */
```

So the scheduler does not touch a register itself: it finds the `"rtc"` device and issues the
RT-Thread alarm commands. Five other sites call the same helper, all in the alarm module.

## The LCPU RTC driver

The LCPU has its own `drv_rtc` instance on the same block the HCPU uses, **`0x500cb000`**,
with the strings `RTC use LXT RTC_CR=%08X`, `rc10k Freq=%dkHz, cycle=%d, rtc ppm=%d` and
`rtc register err code: %d`.

Its control op is `0x12264ec8`: it asserts `"rt_rtc_control"` / `"dev != RT_NULL"` at line
`0x1bd` (the same source line as the HCPU build) and dispatches `cmd - 0x10` through a `tbb`
whose bytes are `04 43 4b 62 7c 87 8d`:

| cmd | Target | Effect |
|---|---|---|
| `0x10` | `0x12264ef4` | GET_TIME |
| `0x11` | `0x12264f72` | SET_TIME |
| `0x12` | `0x12264f82` | GET_ALARM: clear `ctx+0x34` (0x2c B), read back |
| `0x13` | `0x12264fb0` | **SET_ALARM** |
| `0x14` | `0x12264fe4` | GET_TIMESPEC |
| `0x15` | `0x12264ffa` | arm the compare (`0x12026348`) |
| `0x16` | `0x12265006` | `0x1217730c` timestamp, `*0xf42` |

`SET_ALARM` (`0x12264fb0`) with `args[0] == 0` calls `0x120261a6`, which clears the alarm
enable and interrupt bits. With `args[0] != 0` it zeroes `ctx+0x34`, stores `0x38a00000` at
`ctx+0x50`, copies the three time bytes, and calls `0x12026404`.

`0x12026404` is the hardware write. It waits until a write is allowed, then:

- `[base+0x18] = compare` (from `0x1229cbcc`), `[base+0x1c] |= time` (from `0x120fbcc0`);
- `0xe000e104 |= 0x20000` — enable the RTC interrupt in the NVIC;
- `[base+8] |= 0x800`, then `[base+8] |= 0x100` — alarm enable, then interrupt enable.

`0x12026348` (cmd `0x15`) is the plain compare write: `[base+0x20] = args`, or
`0x80000000` when `args >= 1`, and it returns 2 while a write is still pending.

## Which core owns the alarm — corrected

The HCPU `rt_rtc_control` at `0x2001bcb4` has the *same* source but a different dispatch
table (`04 43 5a 5a 5a 4b 51`): its `0x12`, `0x13` and `0x14` all go to `0x2001bd8a` and the
only vendor-specific writer is `0x15`. The LCPU copy is the one with a real `SET_ALARM`.

Both cores can reach the `0x500cb000` block, but the alarm service — the list, the scan, the
`SET_ALARM` call — is on the **LCPU**. An earlier reading of this repository put the whole
compare/wake path on the HCPU; that holds only for `set_time` and the vendor `0x15`, not for
an alarm. `[fw 2.2.111]`

## The internal message router

`0x12258624` is the thread that consumes the LCPU's internal message bus. It reads a
16-bit type at `msg[0]` (rejecting `> 0xa`) and an id at `msg[2]`, then subtracts a per-type
base and indexes a `tbh`:

| Type | Base | Entries |
|---|---|---|
| 0 | `0xc402` | 0x26 |
| 2 | `0xc606` | 0x29 |

Type-2 ids and targets:

| id | target | id | target | id | target |
|---|---|---|---|---|---|
| `c606` | `25875c` | `c614` | `258966` | `c622` | `258a0a` |
| `c607` | `25885e` | `c615` | `25896c` | `c623` | `258a18` |
| `c608` | `258868` | `c616` | `258972` | `c624` | `258a22` |
| `c609` | `2588c8` | `c617` | `25897c` | `c625` | `258b60` |
| `c60a` | `2588ce` | `c618` | `258986` | `c626` | `258a2c` |
| `c60b` | `2588de` | `c619` | `25898c` | `c627` | `258a6e` |
| `c60c` | `2588e4` | `c61a` | `258992` | `c628` | `258a32` |
| `c60d` | `2588ea` | `c61b` | `2589a2` | `c629` | `258a38` |
| `c60e` | `2588f8` | `c61c` | `2589d4` | `c62a` | `258a8a` |
| `c60f` | `258820` | `c61d` | `2589dc` | `c62b` | `258a50` |
| `c610` | `2588fe` | `c61e` | `2589ee` | `c62c` | `258a56` |
| `c611` | `25892e` | `c61f` | `2587f0` | `c62d` | `258a60` |
| `c612` | `258950` | `c620` | `2589f4` | `c62e` | `258a66` |
| `c613` | `25895a` | `c621` | `258a04` | | |

`0x258b60` is the drop/exit label.

The id is `0xc600 + subtype`. The second dispatcher `app_system_subtype_dispatch`
(`0x1205afe8`) subtracts `0xc603` for subtype 3, and the watch's own find-device reply uses
type 2 / id `0xc612` for `2/18` (`0x12187f10`), so the mi_pb base `0xc606` covers subtypes
6–46. `2/18` is therefore index 12 → `0x12258950`, which loads a 16-bit payload field and
calls `0x1220a9d4` (a protobuf-response sender). The ring body is **not** on that path: an
earlier note that followed `0x12049f44` was reading index 18 (subtype 24), and the
association with `2/18` is withdrawn. `[fw 2.2.111]`

## Which commands reach this

`17/0` (alarms get) returns the stored schedule on hardware
([commands-tested.md](commands-tested.md)), so alarm commands **are** dispatched; the static
`Command.type` switch for types 11–25 was just not located. The schedule lives in the
`alarm_clock_user` flash region `0x134e0000` (read by `0x122af590`).

The only verified command is the shell `__cmd_alarm_dump` (`0x49bc8c`): handler `0x12263ea0`
walks the list and calls `alarm_node_rtc_arm` per node. The popup `0x1221bea4` rings via
`play_sound` ([sound-alarms.md](sound-alarms.md)).

## Still open

- Where the `2/18` ring actually happens. Its mi_pb case builds a response; the tone may be
  raised by the BLE service or by a popup, and neither was traced to `play_sound`.
- The alarm's list-insert path and the callback at `[node+0xc]`.
- Which event id in the popup dispatcher `0x12042550` means ring versus vibrate
  ([sound-alarms.md](sound-alarms.md)).
