# Firmware symbols — the RT-Thread kernel group

Symbol names for the RT-Thread kernel, IPC, timer and device-framework functions in the
**HCPU** image. The method and the DFU/flash cluster are on
[firmware-symbols.md](firmware-symbols.md); drivers are on
[firmware-symbols-drivers.md](firmware-symbols-drivers.md). Static analysis only; nothing was
flashed or executed and the watch is not contacted. Legal framing is
[README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

## Evidence

Most rows carry a `__func__` anchor: the literal is the function's own name, loaded into `r1`
and passed to the assert handler with a `__LINE__` immediate from inside that function. The
kernel is shared verbatim with upstream RT-Thread, so a compiled slice of the SDK (v2.3.6,
198 functions) was also matched by decompiler signature: 78% of the anchored matches agree at
significance ≥ 10, 93% above 20.

The second table has **no string anchor**. Those rows come from that match plus the **call
graph**: the firmware function must call the same named functions as its candidate and be
called by the same set, at a similar body size. `rt_calloc` calls `rt_malloc` + `rt_memset`
and `print_number` has one caller, both exactly as upstream; candidates whose graph disagreed
were dropped.

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

## Recovered from the call graph

No name literal by construction.

| Symbol | Entry | Body | Confidence |
|---|---|---|---|
| `_rt_scheduler_stack_check` | `0x2000dfa8` | `0x2000dfa8–0x2000e007` | medium |
| `_rt_timer_remove` | `0x2000e118` | `0x2000e118–0x2000e129` | high |
| `print_number` | `0x20017000` | `0x20017000–0x20017145` | high |
| `rt_calloc` | `0x20017ae0` | `0x20017ae0–0x20017afd` | high |
| `rt_device_register` | `0x20018480` | `0x20018480–0x200184ab` | high |
| `rt_exit_critical` | `0x200188c4` | `0x200188c4–0x200188f5` | high |
| `rt_ipc_list_resume_all` | `0x2001a32c` | `0x2001a32c–0x2001a353` | high |
| `rt_memcpy` | `0x2001ab08` | `0x2001ab08–0x2001ab5d` | medium |
| `rt_memset` | `0x2001ab5e` | `0x2001ab5e–0x2001ab9f` | high |
| `rt_event_init` | `0x2001b1dc` | `0x2001b1dc–0x2001b211` | high |
| `rt_object_detach` | `0x2001b6a8` | `0x2001b6a8–0x2001b6e3` | high |
| `rt_object_get_type` | `0x2001b728` | `0x2001b728–0x2001b741` | high |
| `rt_schedule_insert_thread` | `0x2001be20` | `0x2001be20–0x2001be6d` | high |
| `rt_schedule_remove_thread` | `0x2001be90` | `0x2001be90–0x2001bedd` | high |
| `rt_strnlen` | `0x2001cc38` | `0x2001cc38–0x2001cc4d` | high |
| `rt_thread_create` | `0x2001ce8c` | `0x2001ce8c–0x2001cecb` | high |
| `rt_timer_init` | `0x2001d8fc` | `0x2001d8fc–0x2001d93d` | high |
| `rt_vsnprintf` | `0x2001db30` | `0x2001db30–0x2001dc3f` | high |
### Notes

- `rt_schedule_insert_thread` (`0x2001be20`) and `rt_schedule_remove_thread` (`0x2001be90`)
  are the same size and near-identical; the callers decide. Insert is called by
  `rt_thread_resume`/`control`/`timeout`, remove by `rt_thread_suspend`/`delete`/`control`.
- `rt_exit_critical` (`0x200188c4`) is 50 bytes; the sibling `rt_enter_critical` is 22 bytes
  upstream, so size separates them.
