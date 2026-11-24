#!/usr/bin/env python3
"""Report the context cost of the repository and enforce its budget.

Another model with a 128k window has to be able to read this repository without
burning the window on a lockfile. Sizes are bytes plus a rough token estimate
(bytes / 3.8, the usual English/code ratio; treat them as an order of magnitude).

`--check` fails when AGENTS.md or a single docs/ page outgrows its budget.
"""

import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
AGENTS_LIMIT = 12_000
DOC_LIMIT = 8_000
BYTES_PER_TOKEN = 3.8

# (patterns, label, read policy) — the policy column is the point of the table.
GROUPS = [
    (["AGENTS.md"], "agent contract", "always"),
    (["README.md", "CLAUDE.md"], "entry docs", "once"),
    (["docs/*.md"], "long-form docs", "on demand"),
    (["src/*.py"], "scripts", "the file you change"),
    (["tests/*.py"], "tests", "the test you are fixing"),
    (["fetch_protos.sh", "Makefile", "pyproject.toml", "scripts/*.py"], "harness", "on demand"),
    (["proto/**/*.proto"], "protos", "only the message you need"),
    (["src/xiaomi_pb/**/*.py"], "generated bindings", "NEVER (generated)"),
    (["uv.lock"], "lockfile", "NEVER"),
    (["LICENSE"], "license text", "NEVER"),
]


def expand(pattern: str) -> list[pathlib.Path]:
    return [p for p in ROOT.glob(pattern) if p.is_file()]


def main() -> int:
    print(f"{'bytes':>8} {'~tokens':>8}  {'read policy':<26} group")
    for patterns, label, policy in GROUPS:
        paths = [p for pattern in patterns for p in expand(pattern)]
        size = sum(p.stat().st_size for p in paths)
        print(f"{size:>8} {round(size / BYTES_PER_TOKEN):>8}  {policy:<26} {label}")

    failures = []
    agents = ROOT / "AGENTS.md"
    if agents.stat().st_size > AGENTS_LIMIT:
        failures.append(f"AGENTS.md is {agents.stat().st_size} B > {AGENTS_LIMIT} B")
    for doc in sorted((ROOT / "docs").glob("*.md")):
        if doc.stat().st_size > DOC_LIMIT:
            failures.append(f"{doc.relative_to(ROOT)} is {doc.stat().st_size} B > {DOC_LIMIT} B")

    for failure in failures:
        print(f"budget exceeded: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
