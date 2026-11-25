# Firmware symbols — drivers and graphics

Symbol names for the board drivers, serial/I2C/UART paths, the LCD/GPU layer and the logging
backend in the **HCPU** image. The method and confidence rules are on
[firmware-symbols.md](firmware-symbols.md); the kernel group is on
[firmware-symbols-kernel.md](firmware-symbols-kernel.md). Everything here is static analysis;
nothing was flashed or executed and the watch is not contacted. Legal framing is
[README.md](../README.md#legal).

Source: [fw 2.2.111] unless tagged.

## Confidence in this group

The public SDK does not carry all of this code — parts live in the prebuilt `sifli_lib`
archive and parts are board or app code — so the `__LINE__` cross-check only fires where the
source is public. Every row still has the assert-site evidence: the literal is the function's
own `__func__`, loaded into `r1` and passed to the assert handler with a line immediate from
inside that function. Rows marked medium did not resolve against v2.3.6 source.

## Board drivers

| Symbol | Entry | Body | Confidence | Name literal |
|---|---|---|---|---|
| `HAL_Delay` | `0x20004a0c` | `0x20004a0c–0x20004a23` | high | — |
| `HAL_UART_RxHalfCpltCallback` | `0x2000b168` | `0x2000b168–0x2000b1ad` | high | — |
| `add_pin_mode` | `0x2000e12c` | `0x2000e12c–0x2000e187` | high | `0x2002e0b8` |
| `bf0_gptimer_init2` | `0x2000edbc` | `0x2000edbc–0x2000ee0b` | high | — |
| `drv_epic_init` | `0x200127a4` | `0x200127a4–0x200127c3` | medium | `0x200127e0` |
| `drv_epic_release` | `0x200127f0` | `0x200127f0–0x2001280d` | medium | `0x2001282c` |
| `drv_pwm_control` | `0x200129e4` | `0x200129e4–0x20012a11` | high | `0x20012bec` |
| `i2c_bus_configure` | `0x200146c8` | `0x200146c8–0x20014747` | high | `0x2002d2a5` |
| `lp_timer_start` | `0x2001560c` | `0x2001560c–0x2001564b` | medium | — |
| `master_xfer` | `0x2001602c` | `0x2001602c–0x20016273` | high | `0x2002d2b7` |
| `pin_irq_hdr` | `0x20016e58` | `0x20016e58–0x20016edb` | medium | `0x2002d189` |
| `i2c_bus_lock` | `0x2001a060` | `0x2001a060–0x2001a089` | medium | `0x2001a08c` |
| `_serial_int_tx` | `0x2001c908` | `0x2001c908–0x2001c9d9` | high | `0x2001ca00` |
| `sifli_adc_control` | `0x20021594` | `0x20021594–0x2002173b` | medium | `0x2002d35b` |
| `sifli_configure` | `0x20021b20` | `0x20021b20–0x20021bc9` | high | `0x2002d1d6` |
| `sifli_dma_transmit` | `0x20021cf0` | `0x20021cf0–0x20021da7` | high | `0x2002d1fd` |
| `sifli_get_adc_value` | `0x20021db4` | `0x20021db4–0x20021fd1` | medium | `0x2002d347` |
| `sifli_getc` | `0x20022010` | `0x20022010–0x20022043` | high | `0x2002d1cb` |
| `sifli_hw_efuse_read` | `0x2002211c` | `0x2002211c–0x2002213b` | medium | — |
| `sifli_pin_attach_irq` | `0x20022258` | `0x20022258–0x20022313` | medium | `0x2002d174` |
| `sifli_pin_dettach_irq` | `0x20022354` | `0x20022354–0x200223f1` | medium | `0x20022414` |
| `timer_counter_get` | `0x20022a0c` | `0x20022a0c–0x20022a25` | medium | — |
| `timer_start` | `0x20022b70` | `0x20022b70–0x20022bb9` | medium | — |
| `uart_isr` | `0x20022c10` | `0x20022c10–0x20022d09` | high | `0x2002d1f4` |

## Graphics and display

| Symbol | Entry | Body | Confidence | Name literal |
|---|---|---|---|---|
| `SendLayerDataCpltCbk` | `0x2000c800` | `0x2000c800–0x2000c823` | medium | — |
| `api_lcd_control` | `0x2000e34c` | `0x2000e34c–0x2000e407` | high | `0x2002d56c` |
| `api_lcd_draw_rect` | `0x2000e7c8` | `0x2000e7c8–0x2000e817` | high | — |
| `api_lcd_get_pixel` | `0x2000e878` | `0x2000e878–0x2000e8a9` | high | — |
| `api_lcd_set_window` | `0x2000eaa4` | `0x2000eaa4–0x2000eacd` | high | — |
| `api_unlock` | `0x2000eaf0` | `0x2000eaf0–0x2000eb31` | medium | `0x2002d54c` |
| `disable_low_power` | `0x200121a4` | `0x200121a4–0x200121bd` | high | — |
| `draw_core` | `0x200124ac` | `0x200124ac–0x200126ed` | medium | `0x2002d50d` |
| `gpu_close` | `0x20014334` | `0x20014334–0x20014373` | medium | `0x2002d517` |
| `lcd_display_off` | `0x20014a9c` | `0x20014a9c–0x20014af3` | high | — |
| `lcd_display_on` | `0x20014b08` | `0x20014b08–0x20014b4d` | high | — |
| `lcd_set_brightness` | `0x20014fc8` | `0x20014fc8–0x20015019` | high | — |
| `lvsf_sem_deinit` | `0x20015774` | `0x20015774–0x200157ad` | medium | `0x200157c8` |
| `lvsf_img_create` | `0x200158ac` | `0x200158ac–0x2001593d` | medium | `0x2002c605` |
| `lvsf_img_draw_area` | `0x2001599c` | `0x2001599c–0x200159fb` | medium | `0x2002c5cd` |
| `lvsf_img_dsc_create` | `0x20015a08` | `0x20015a08–0x20015b3b` | medium | `0x2002c5f1` |
| `lvsf_img_set_pos` | `0x20015c60` | `0x20015c60–0x20015ceb` | medium | `0x2002c669` |
| `lvsf_img_set_src` | `0x20015cf8` | `0x20015cf8–0x20015de5` | medium | `0x2002c5e0` |
| `lvsf_lcd_refr` | `0x20015e30` | `0x20015e30–0x20015ec5` | medium | `0x2002c627` |
| `lvsf_screen_clean` | `0x20015f88` | `0x20015f88–0x20015fe1` | medium | `0x2002c615` |
| `rt_lcd_layer_control` | `0x2001a4d0` | `0x2001a4d0–0x2001a4e3` | high | — |
| `aysnc_send_cmplt_cbk` | `0x2001c430` | `0x2001c430–0x2001c45d` | medium | — |
| `send_msg_to_lcd_task` | `0x2002117c` | `0x2002117c–0x20021223` | medium | `0x2002d557` |

## System and logging

| Symbol | Entry | Body | Confidence | Name literal |
|---|---|---|---|---|
| `battery_read_final_info` | `0x2000ed4c` | `0x2000ed4c–0x2000ed85` | medium | `0x2002d666` |
| `lcpu2hcpu_notification_callback` | `0x200153f4` | `0x200153f4–0x2001541f` | high | `0x2001543c` |
| `output_lock` | `0x20016dc8` | `0x20016dc8–0x20016dff` | high | `0x20016e24` |
| `ulog_async_output` | `0x20022d18` | `0x20022d18–0x20022e13` | medium | `0x2002e011` |
| `ulog_backend_register` | `0x20022ea0` | `0x20022ea0–0x20022f1b` | medium | `0x2002dff4` |
| `ulog_formater` | `0x20023044` | `0x20023044–0x20023195` | high | `0x2002dfe6` |
| `ulog_strcpy` | `0x2002339c` | `0x2002339c–0x200233cf` | high | `0x2002e030` |
| `ulog_voutput` | `0x2002342c` | `0x2002342c–0x200234a1` | medium | `0x2002e023` |

### Notes

- `uart_isr` (`0x20022c10`) and `rt_hw_serial_isr` (`0x20019890`, kernel page) are the two
  halves of the serial interrupt path: the first is the driver's own ISR, the second the
  RT-Thread serial framework entry.
- `master_xfer` (`0x2001602c`) is the I2C bus transfer routine registered as the RT-Thread I2C
  device's `master_xfer`; `i2c_bus_configure` and `i2c_bus_lock` sit next to it.
- `output_lock` (`0x20016dc8`) is a tail-call assert site: `adr r1,[0x20016e24]` then
  `b.w 0x200179e4`, which is why the literal is its own name with no local call.
- `lcpu2hcpu_notification_callback` (`0x200153f4`) is the HCPU side of the inter-core
  mailbox documented in [firmware.md](firmware.md).
