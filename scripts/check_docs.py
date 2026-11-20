#!/usr/bin/env python3
"""Check that relative links in README/docs point at files that exist.

Agents and humans navigate this repository by link, so a dead path is a broken
harness. Run from the repository root (`make lint` does).
"""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)]+)\)")
SKIP_PREFIXES = ("http://", "https://", "#", "mailto:")


def markdown_files() -> list[pathlib.Path]:
    return [ROOT / "README.md", *sorted((ROOT / "docs").glob("*.md"))]


def main() -> int:
    bad = []
    for doc in markdown_files():
        for target in LINK.findall(doc.read_text()):
            if target.startswith(SKIP_PREFIXES):
                continue
            path_part = target.split("#", 1)[0]  # ignore in-page anchors
            if not path_part:
                continue
            path = (doc.parent / path_part).resolve()
            if not path.exists():
                bad.append(f"{doc.relative_to(ROOT)}: {target}")
    for line in bad:
        print(f"dead link: {line}", file=sys.stderr)
    if bad:
        return 1
    print(f"links OK ({len(markdown_files())} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
