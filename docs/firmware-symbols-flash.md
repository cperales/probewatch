# Firmware symbols — FAL and the FlashDB key-value store

Symbol names for the flash abstraction layer (FAL) and the FlashDB KV store in the **HCPU**
image. The method and confidence rules are on [firmware-symbols.md](firmware-symbols.md); the
DFU/OTA cluster and RTC are there too, drivers and graphics on
[firmware-symbols-drivers.md](firmware-symbols-drivers.md). Everything here is static analysis;
nothing was flashed or executed and the watch is not contacted. Legal framing is
[README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

## Confidence in this group

Part of this cluster has `__func__` anchors (the FAL and KV entry points). The rest is the
static half of FlashDB: helpers such as `find_kv`, `del_kv`, `sector_iterator` and the
status/sector caches. Those were recovered by matching a compiled FAL/FlashDB slice of the
SDK (v2.3.6) and then checking the **call graph** — the firmware function must call and be
called by the same named functions as its candidate, at a similar size.

The cluster is dense enough for that check to be self-corroborating: once `find_kv`,
`del_kv`, `set_kv`, `alloc_kv`, `update_kv_cache` and `_fdb_db_path` are placed, each one's
neighbours line up. `move_kv` ends up agreeing on **seven** callees and `_fdb_db_path` on
**thirteen** callers, which is far outside what a coincidental signature match produces.
Rows marked medium have no graph agreement; size and signature similarity carry them.

## FAL and the KV store

| Symbol | Entry | Body | Confidence | Name literal |
|---|---|---|---|---|
| `_fdb_db_path` | `0x2000d344` | `0x2000d344–0x2000d351` | high | — |
| `_fdb_get_status` | `0x2000d394` | `0x2000d394–0x2000d3bb` | high | — |
| `_fdb_init_ex` | `0x2000d3bc` | `0x2000d3bc–0x2000d55d` | high | `0x2002c897` |
| `_fdb_init_finish` | `0x2000d60c` | `0x2000d60c–0x2000d68d` | high | — |
| `_fdb_kv_load` | `0x2000d708` | `0x2000d708–0x2000d8b7` | high | — |
| `_fdb_read_status` | `0x2000d920` | `0x2000d920–0x2000d975` | high | `0x2002cba6` |
| `_fdb_set_status` | `0x2000d97c` | `0x2000d97c–0x2000d9ab` | high | — |
| `_fdb_write_status` | `0x2000d9ac` | `0x2000d9ac–0x2000da3f` | high | `0x2002cbb7` |
| `alloc_kv` | `0x2000e1a8` | `0x2000e1a8–0x2000e257` | high | — |
| `check_and_recovery_kv_cb` | `0x2000f1e8` | `0x2000f1e8–0x2000f2c3` | high | — |
| `check_and_update_part_cache` | `0x2000f300` | `0x2000f300–0x2000f369` | medium | — |
| `check_sec_hdr_cb` | `0x2000f3dc` | `0x2000f3dc–0x2000f42d` | high | — |
| `create_kv_blob` | `0x2000f514` | `0x2000f514–0x2000f6f1` | high | — |
| `del_kv` | `0x2000fa84` | `0x2000fa84–0x2000fb7b` | high | — |
| `fal_init` | `0x200131b0` | `0x200131b0–0x20013201` | high | — |
| `fal_partition_erase` | `0x200134e0` | `0x200134e0–0x2001359b` | high | `0x2002cdbd` |
| `fal_partition_find` | `0x20013628` | `0x20013628–0x20013649` | medium | — |
| `fal_partition_read` | `0x20013670` | `0x20013670–0x2001372d` | high | `0x2002cdaa` |
| `fal_partition_write` | `0x200137b8` | `0x200137b8–0x20013875` | high | `0x2002cdd1` |
| `fdb_calc_crc32` | `0x2001391c` | `0x2001391c–0x2001393b` | high | — |
| `fdb_kv_get_blob` | `0x20013940` | `0x20013940–0x20013a6f` | medium | `0x20013acc` |
| `fdb_kv_set_blob` | `0x20013adc` | `0x20013adc–0x20013bb3` | medium | `0x20013be8` |
| `fdb_kvdb_init` | `0x20013c00` | `0x20013c00–0x20013d51` | high | `0x2002cb66` |
| `find_kv` | `0x20013dbc` | `0x20013dbc–0x20013e7f` | high | — |
| `find_kv_cb` | `0x20013e80` | `0x20013e80–0x20013eb5` | high | — |
| `format_sector` | `0x20013f28` | `0x20013f28–0x20013fe3` | high | `0x2002cb58` |
| `kv_iterator` | `0x20014a20` | `0x20014a20–0x20014a9b` | high | — |
| `move_kv` | `0x200162fc` | `0x200162fc–0x20016459` | high | — |
| `mtd_nor_dev_erase` | `0x20016ad0` | `0x20016ad0–0x20016ae3` | high | — |
| `read_kv` | `0x2001723c` | `0x2001723c–0x2001744b` | high | `0x2002cb74` |
| `read_sector_info` | `0x200174f4` | `0x200174f4–0x200177cb` | high | `0x2002cb47` |
| `rt_flash_write` | `0x20018ce4` | `0x20018ce4–0x20018ebd` | medium | — |
| `sector_iterator` | `0x200210f6` | `0x200210f6–0x2002115b` | high | — |
| `set_kv` | `0x200213a8` | `0x200213a8–0x20021459` | high | — |
| `update_kv_cache` | `0x20023514` | `0x20023514–0x200235cb` | high | — |
| `update_sec_status` | `0x20023628` | `0x20023628–0x200236a1` | high | — |
| `update_sector_cache` | `0x200236a2` | `0x200236a2–0x20023705` | high | — |

### Notes

- `_fdb_db_path` (`0x2000d344`) is 14 bytes and is called from 13 sites, all of them the KV
  code — the widest caller agreement in the group. Two other 14-byte functions
  (`0x2000d352`, `0x2000d37c`) are *not* it: they call `fal_partition_erase` and
  `fal_partition_write`, so they are sector helpers that the match had confused with it.
- `update_sec_status` (`0x20023628`) and `update_sector_cache` (`0x200236a2`) are the two
  sector-cache updaters; `_fdb_set_status` (`0x2000d97c`) and `_fdb_get_status`
  (`0x2000d394`) are the status-record pair. The anchored `_fdb_read_status` and
  `_fdb_write_status` call them, which is what fixed their names.
- `read_sector_info` (`0x200174f4`) and `format_sector` (`0x20013f28`) are the two big
  anchored routines this cluster hangs from; both are listed here rather than on the driver
  page because every caller is FlashDB.
- `rt_flash_write` (`0x20018ce4`) is the RT-Thread flash device write behind FAL. Its only
  caller in the image is `dfu_ctrl_reset_handler`, and it allocates a bounce buffer with
  `rt_malloc`/`rt_free`, so the row is medium: the size differs from the slice (474 B vs
  600 B) and the slice's `malloc`/`free` are newlib names for the same calls.
- `fdb_kvdb_init` (`0x20013c00`) is the entry point: it calls `_fdb_kv_load`,
  `sector_iterator`, `_fdb_init_finish` and `fal_init`, all of which are now named.
