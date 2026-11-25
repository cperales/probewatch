# Watch firmware — upstream references and reuse boundary

What a firmware fork for this watch can reuse, and where the line is between upstream assets and
what has to be built for this board. This page is a record only: no upstream code is vendored
here and nothing was flashed or executed. Legal framing is [README.md](../README.md#legal).

## Upstream references

| Upstream | License | What we take | Source |
|---|---|---|---|
| [OpenSiFli/SiFli-SDK](https://github.com/OpenSiFli/SiFli-SDK) | Apache-2.0 | The **build base** for any firmware fork: HAL, drivers, RT-Thread and board BSP. Supports SF32LB55 from v2.3.0; clone with `--recursive`; tags v2.3 (2025-01-21), v2.4 (2025-06-05), v2.5 (2026-06-19). | [ext SiFli-SDK] |
| [Byterialab/xiaomi-smart-watch-research](https://github.com/Byterialab/xiaomi-smart-watch-research) + blog | MIT | **Published facts only**: flash layout, watchface format, debug-surface leads (DLVP/SWD, UART shell, FCES+RSA). Their scripts (payloads, frida, mitm) are not used or copied here. | [ext Byterialab] |
| RT-Thread / LVGL / FlashDB / FAL | Apache-2.0 / MIT / MIT / (verify) | Already present in the shipped firmware and in the SDK, so they are reused rather than rewritten. FAL's exact license still needs confirming. | [fw 2.2.111] |

### Reuse boundary

- **Upstream (reuse):** SiFli-SDK (toolchain and BSP), RT-Thread, LVGL, FlashDB/FAL, and
  Byterialab's published facts.
- **Built here (no published upstream):** the board-specific configuration (pinmux, display and
  touch drivers for this exact board), the flashing-route confirmation, and the app code
  (a game or custom UI). No working SF32LB551 bring-up for this watch has been published.
- **Version caveat:** the shipped 2.2.111 carries an internal "SDK 1.0.9 / commit 1a8993c8"
  (Apr 2025) [fw 2.2.111], while the public SDK starts at v2.3. Treat the two as the same family
  with a newer SDK; do not claim a byte-for-byte rebuild [inferred].
