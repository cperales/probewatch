# Firmware symbols — the RT-Thread kernel group

Symbol names for the RT-Thread kernel, IPC, timer and device-framework functions in the
**HCPU** image. The method, the confidence rules and the DFU/flash cluster are on
[firmware-symbols.md](firmware-symbols.md); the drivers are on
[firmware-symbols-drivers.md](firmware-symbols-drivers.md). Everything here is static
analysis; nothing was flashed or executed and the watch is not contacted. Legal framing is
[README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

## Why this group is trustworthy

These are the functions the SiFli SDK shares verbatim with upstream RT-Thread, so the group
got a second, independent check. A kernel slice of the SDK (tag v2.3.6, 198 functions,
built with `gcc-arm-none-eabi` 14.2) was matched against the image with decompiler
signatures (BSim vectors). Of 41 matches at significance ≥ 10, 32 carry the same name as the
`__func__` anchor — 78% precision, rising to 93% above significance 20. The disagreements are
sibling confusions (`rt_device_write` matched `rt_device_read`), so the anchor decides and the
match is recorded as corroboration.

Exact-hash matching (Ghidra FID) was tried and is not usable here: the best similarity on a
correct pair is 0.869 and none reaches 0.999, because the firmware's compiler differs. The
`body` column is the contiguous range from the entry.

## Kernel and IPC

| Symbol | Entry | Body | Confidence | Name literal |
|---|---|---|---|---|
| `_rt_thread_init` | `0x2000e054` | `0x2000e054–0x2000e0d5` | high | `0x2000e100` |
| `rt_mb_send_wait` | `0x200108bc` | `0x200108bc–0x200108f1` | high | `0x2002d9f3` |
| `plug_holes` | `0x20016efc` | `0x20016efc–0x20016f77` | high | `0x2002dc88` |
| `rt_charge_register` | `0x20017b00` | `0x20017b00–0x20017b37` | medium | `0x20017b48` |
| `rt_completion_wait` | `0x20017c04` | `0x20017c04–0x20017cc9` | high | `0x2002e1b1` |
| `rt_data_queue_pop` | `0x20017e74` | `0x20017e74–0x20017fd9` | high | `0x2002e1e8` |
| `rt_data_queue_push` | `0x20018008` | `0x20018008–0x20018125` | high | `0x2002e1d5` |
| `rt_device_close` | `0x20018138` | `0x20018138–0x2001818d` | high | `0x2002d6fe` |
| `rt_device_control` | `0x20018194` | `0x20018194–0x200181d5` | high | `0x2002d738` |
| `rt_device_find` | `0x200181dc` | `0x200181dc–0x20018235` | high | `0x20018250` |
| `rt_device_hwtimer_register` | `0x20018260` | `0x20018260–0x200182c9` | high | `0x2002e03c` |
| `rt_device_open` | `0x2001831c` | `0x2001831c–0x200183bb` | high | `0x2002d74a` |
| `rt_device_set_tx_complete` | `0x200184ac` | `0x200184ac–0x200184db` | medium | `0x2002d70e` |
| `rt_device_write` | `0x200184e8` | `0x200184e8–0x20018545` | high | `0x2002d728` |
| `rt_event_recv` | `0x20018618` | `0x20018618–0x200187c9` | high | `0x2002da5d` |
| `rt_nor_erase_rom` | `0x2001891c` | `0x2001891c–0x20018ad9` | high | `0x2002d405` |
| `rt_free` | `0x20018f04` | `0x20018f04–0x2001905f` | high | `0x2002dc80` |
| `rt_hw_adc_register` | `0x20019104` | `0x20019104–0x2001914d` | high | `0x2001917c` |
| `rt_hw_serial_isr` | `0x20019890` | `0x20019890–0x200198a7` | high | `0x2002e15e` |
| `rt_hw_watchdog_register` | `0x20019cf8` | `0x20019cf8–0x20019d3b` | medium | `0x20019d4c` |
| `rt_malloc` | `0x2001a6b0` | `0x2001a6b0–0x2001a891` | high | `0x2002dbfb` |
| `rt_mq_delete` | `0x2001ac44` | `0x2001ac44–0x2001acbf` | high | `0x2002d972` |
| `rt_mq_recv` | `0x2001ad10` | `0x2001ad10–0x2001af0b` | high | `0x2002da52` |
| `rt_mq_send` | `0x2001af54` | `0x2001af54–0x2001b019` | high | `0x2002d8af` |
| `rt_mtd_nand_register_device` | `0x2001b030` | `0x2001b030–0x2001b073` | high | `0x2001b084` |
| `rt_mtd_nor_register_device` | `0x2001b0b8` | `0x2001b0b8–0x2001b105` | high | `0x2001b118` |
| `rt_mutex_detach` | `0x2001b14c` | `0x2001b14c–0x2001b199` | high | `0x2002d9d4` |
| `rt_mutex_release` | `0x2001b22c` | `0x2001b22c–0x2001b35d` | high | `0x2002d936` |
| `rt_mutex_take` | `0x2001b368` | `0x2001b368–0x2001b521` | high | `0x2002d8d4` |
| `rt_object_allocate` | `0x2001b578` | `0x2001b578–0x2001b60b` | high | `0x2002dcd0` |
| `rt_object_delete` | `0x2001b618` | `0x2001b618–0x2001b671` | high | `0x2002dce3` |
| `rt_object_init` | `0x2001b75c` | `0x2001b75c–0x2001b7db` | high | `0x2002dcf4` |
| `rt_rbb_blk_alloc` | `0x2001b9fc` | `0x2001b9fc–0x2001bae5` | high | `0x2002e1fe` |
| `rt_rbb_blk_free` | `0x2001bb08` | `0x2001bb08–0x2001bb5d` | high | `0x2002e20f` |
| `rt_rbb_blk_put` | `0x2001bbf0` | `0x2001bbf0–0x2001bc21` | high | `0x2002e225` |
| `rt_sem_control` | `0x2001bf08` | `0x2001bf08–0x2001bf5b` | high | `0x2002d9e4` |
| `rt_sem_create` | `0x2001bf60` | `0x2001bf60–0x2001bfbf` | high | `0x2002d947` |
| `rt_sem_detach` | `0x2001bfc4` | `0x2001bfc4–0x2001c00b` | high | `0x2002d9c6` |
| `rt_sem_init` | `0x2001c048` | `0x2001c048–0x2001c087` | high | `0x2002da03` |
| `rt_sem_release` | `0x2001c090` | `0x2001c090–0x2001c0f1` | high | `0x2002d927` |
| `rt_sem_take` | `0x2001c0fc` | `0x2001c0fc–0x2001c24b` | high | `0x2002d8c8` |
| `rt_serial_open` | `0x2001c474` | `0x2001c474–0x2001c657` | high | `0x2002e14f` |
| `rt_thread_control` | `0x2001cdfc` | `0x2001cdfc–0x2001ce87` | high | `0x2002ddc7` |
| `rt_thread_delete` | `0x2001ced8` | `0x2001ced8–0x2001cf49` | high | `0x2002ddb6` |
| `rt_thread_init` | `0x2001d154` | `0x2001d154–0x2001d1ab` | high | `0x2002ddfb` |
| `rt_thread_resume` | `0x2001d1dc` | `0x2001d1dc–0x2001d24f` | high | `0x2002dda5` |
| `rt_thread_sleep` | `0x2001d260` | `0x2001d260–0x2001d35f` | high | `0x2002ddd9` |
| `rt_thread_startup` | `0x2001d3d8` | `0x2001d3d8–0x2001d43d` | high | `0x2002dde9` |
| `rt_thread_suspend` | `0x2001d484` | `0x2001d484–0x2001d505` | high | `0x2002dd93` |
| `rt_thread_timeout` | `0x2001d52c` | `0x2001d52c–0x2001d591` | high | `0x2002de0a` |
| `rt_timer_control` | `0x2001d780` | `0x2001d780–0x2001d7b7` | high | `0x2002de2c` |
| `rt_timer_detach` | `0x2001d868` | `0x2001d868–0x2001d8c1` | high | `0x2002de1c` |
| `rt_timer_start` | `0x2001d970` | `0x2001d970–0x2001da5d` | high | `0x2002de87` |
| `rt_timer_stop` | `0x2001dac0` | `0x2001dac0–0x2001db1b` | high | `0x2002de3d` |

### Notes

- `rt_sem_take` (`0x2001c0fc`) and `rt_mutex_take` (`0x2001b368`) are the two blocking paths
  every IPC wait goes through; their asserts are the `__func__` anchors.
- `plug_holes` (`0x20016efc`) is the RT-Thread small-memory allocator's coalescing helper, a
  static function that still logs its own name.
- `_rt_thread_init` (`0x2000e054`) is the internal initialiser behind `rt_thread_init`; the
  public wrapper is a separate function at `0x2001d154`.
- `rt_charge_register` and `rt_hw_watchdog_register` are marked medium: present in the 2.2.111
  image, not in the v2.3.6 source tree, so their line numbers cannot be checked.
