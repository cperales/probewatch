# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

The main project guide (prerequisites, scripts, venv, protobuf regeneration, licensing) lives in
`AGENTS.md` and is imported here; keep shared guidance there rather than duplicating it:

@AGENTS.md

`AGENTS.md` also documents the layered architecture of `src/xiaomi_client.py` (RFCOMM → SPP v1
probe → SPP v2 framing → `Session` crypto → `XiaomiWatch`) and the conventions for extending
it. Update it there, not here, so both agents see the same guidance.
