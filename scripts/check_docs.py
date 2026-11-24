#!/usr/bin/env python3
"""Lint the Markdown docs: links, the docs index, banned words and source tags.

Agents and humans navigate this repository by link and by the index in docs/README.md,
so a dead path or a stale index row is a broken harness. Read-only unless `--fix` is given,
which rewrites the size column of the index. Run from the repository root (`make lint` does).

Usage: uv run python scripts/check_docs.py [--fix]
"""

import argparse
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
LINK = re.compile(r"\]\(([^)]+)\)")
SKIP_PREFIXES = ("http://", "https://", "#", "mailto:")

# `| [page.md](page.md) | 7 KB | ...` rows of docs/README.md; sizes are round(bytes / 1024).
INDEX_ROW = re.compile(r"^(\| \[([\w.-]+\.md)\]\(\2\) \| )(\d+)( KB \|)", re.MULTILINE)

# AGENTS.md "Legal and provenance": these words misdescribe interoperability work.
BANNED = re.compile(r"\b(?:bypass|unlock|jailbreak|crack|hack)\w*", re.IGNORECASE)
# A quoted word is a mention (the rule itself); the app's feature name is a proper noun.
BANNED_ALLOWED = re.compile(r'"\w+"|authorize[- ]unlock', re.IGNORECASE)
# README's Legal section is the canonical disclaimer and is kept verbatim.
BANNED_SKIP_SECTION = ("README.md", "## Legal")

# Source tags, legend in docs/README.md. A tag is not followed by `(`, so link text is skipped.
TAG = re.compile(r"\[(hw|apk|fw|gb|inferred)((?: [^\]]*)?)\](?!\()")
VERSION = r"\d+\.\d+\.\d+"
TAG_ARGS = {
    "hw": re.compile(rf" {VERSION} \d{{4}}-\d{{2}}-\d{{2}}"),
    "apk": re.compile(rf" {VERSION}\w*"),
    "fw": re.compile(rf" {VERSION}"),
    "gb": re.compile(""),
    "inferred": re.compile(""),
}


def link_files(root: pathlib.Path) -> list[pathlib.Path]:
    return [root / "README.md", root / "AGENTS.md", *sorted((root / "docs").glob("*.md"))]


def dead_links(root: pathlib.Path) -> list[str]:
    bad = []
    for doc in link_files(root):
        if not doc.exists():
            continue
        for target in LINK.findall(doc.read_text()):
            if target.startswith(SKIP_PREFIXES):
                continue
            path_part = target.split("#", 1)[0]  # ignore in-page anchors
            if path_part and not (doc.parent / path_part).resolve().exists():
                bad.append(f"dead link: {doc.relative_to(root)}: {target}")
    return bad


def index_problems(root: pathlib.Path) -> list[str]:
    docs = root / "docs"
    index = docs / "README.md"
    rows = {m.group(2): int(m.group(3)) for m in INDEX_ROW.finditer(index.read_text())}
    pages = {p.name for p in docs.glob("*.md")} - {"README.md"}
    bad = [
        f"index: docs/{name} is not listed in docs/README.md" for name in sorted(pages - set(rows))
    ]
    bad += [
        f"index: docs/README.md lists missing page {name}" for name in sorted(set(rows) - pages)
    ]
    for name in sorted(pages & set(rows)):
        actual = round((docs / name).stat().st_size / 1024)
        if rows[name] != actual:
            bad.append(f"index: {name} is listed as {rows[name]} KB, is {actual} KB (--fix)")
    return bad


def fix_index(root: pathlib.Path) -> int:
    """Rewrite the index size column; return how many rows changed."""
    docs = root / "docs"
    index = docs / "README.md"
    changed = 0

    def resize(m: re.Match[str]) -> str:
        nonlocal changed
        page = docs / m.group(2)
        if not page.exists():
            return m.group(0)
        actual = str(round(page.stat().st_size / 1024))
        changed += actual != m.group(3)
        return f"{m.group(1)}{actual}{m.group(4)}"

    index.write_text(INDEX_ROW.sub(resize, index.read_text()))
    return changed


def banned_words(root: pathlib.Path) -> list[str]:
    bad = []
    for doc in link_files(root):
        if not doc.exists():
            continue
        rel = str(doc.relative_to(root))
        skipping = False
        for number, line in enumerate(doc.read_text().splitlines(), 1):
            if line.startswith("## "):
                skipping = (rel, line.strip()) == BANNED_SKIP_SECTION
            if skipping:
                continue
            for word in BANNED.findall(BANNED_ALLOWED.sub("", line)):
                bad.append(f"banned word: {rel}:{number}: {word!r} (see AGENTS.md, Legal)")
    return bad


def bad_tags(root: pathlib.Path) -> list[str]:
    bad = []
    for doc in sorted((root / "docs").glob("*.md")):
        for number, line in enumerate(doc.read_text().splitlines(), 1):
            for kind, args in TAG.findall(line):
                if not TAG_ARGS[kind].fullmatch(args):
                    rel = doc.relative_to(root)
                    bad.append(f"bad tag: {rel}:{number}: [{kind}{args}] (legend: docs/README.md)")
    return bad


def check(root: pathlib.Path) -> list[str]:
    return dead_links(root) + index_problems(root) + banned_words(root) + bad_tags(root)


def main(argv: list[str] | None = None, root: pathlib.Path = ROOT) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--fix", action="store_true", help="rewrite the docs index sizes")
    args = parser.parse_args(argv)
    if args.fix:
        print(f"index sizes updated: {fix_index(root)} row(s)")
    problems = check(root)
    for line in problems:
        print(line, file=sys.stderr)
    if problems:
        return 1
    print(f"docs OK ({len(link_files(root))} files)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
