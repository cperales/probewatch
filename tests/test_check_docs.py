"""Unit tests for the docs linter (`scripts/check_docs.py`).

Pure logic: every test builds a throwaway repository under `tmp_path`; the real docs
are never read or rewritten.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from check_docs import bad_tags, banned_words, check, dead_links, fix_index, index_problems, main


def _repo(tmp_path: Path, pages: dict[str, str], index_rows: dict[str, int]) -> Path:
    docs = tmp_path / "docs"
    docs.mkdir()
    (tmp_path / "README.md").write_text("# Repo\n\nSee [docs](docs/README.md).\n")
    (tmp_path / "AGENTS.md").write_text('Never write "unlock".\n')
    for name, text in pages.items():
        (docs / name).write_text(text)
    rows = "".join(f"| [{name}]({name}) | {kb} KB | page |\n" for name, kb in index_rows.items())
    (docs / "README.md").write_text(
        f"# Index\n\n| Document | Size | Description |\n|---|---|---|\n{rows}"
    )
    return tmp_path


def test_clean_repo_passes(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.md": "x" * 3000}, {"a.md": 3})
    assert check(root) == []
    assert main([], root=root) == 0


def test_size_drift_is_reported_and_fixed(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.md": "x" * 5000}, {"a.md": 2})
    assert index_problems(root) == ["index: a.md is listed as 2 KB, is 5 KB (--fix)"]
    assert fix_index(root) == 1
    assert "| [a.md](a.md) | 5 KB | page |" in (root / "docs" / "README.md").read_text()
    assert index_problems(root) == []
    assert main(["--fix"], root=root) == 0


def test_unlisted_and_missing_pages(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.md": "a", "b.md": "b"}, {"a.md": 0, "gone.md": 1})
    assert index_problems(root) == [
        "index: docs/b.md is not listed in docs/README.md",
        "index: docs/README.md lists missing page gone.md",
    ]


def test_dead_link(tmp_path: Path) -> None:
    root = _repo(tmp_path, {"a.md": "[x](nope.md) [y](a.md#top) [z](https://e.org)"}, {"a.md": 0})
    assert dead_links(root) == ["dead link: docs/a.md: nope.md"]


def test_banned_words_and_exceptions(tmp_path: Path) -> None:
    text = 'It unlocks nothing.\n| 2/19 | authorize-unlock get |\nNever write "hack".\n'
    root = _repo(tmp_path, {"a.md": text}, {"a.md": 0})
    assert banned_words(root) == [
        "banned word: docs/a.md:1: 'unlocks' (see AGENTS.md, Legal)",
    ]


def test_readme_legal_section_is_skipped(tmp_path: Path) -> None:
    root = _repo(tmp_path, {}, {})
    (root / "README.md").write_text("# R\n\n## Legal\n\nNothing for bypassing.\n\n## Use\n\nhack\n")
    assert banned_words(root) == ["banned word: README.md:9: 'hack' (see AGENTS.md, Legal)"]


def test_source_tags(tmp_path: Path) -> None:
    good = "[hw 2.2.111 2026-11-24] [apk 9.8.348i] [fw 2.2.111] [gb] [inferred]"
    bad = "[hw 2026-11-24] [apk] [gb 1.0.0]"
    links = "[apk-analysis.md](apk-analysis.md) [hw](a.md)"
    root = _repo(tmp_path, {"a.md": f"{good}\n{bad}\n{links}\n"}, {"a.md": 0})
    assert bad_tags(root) == [
        "bad tag: docs/a.md:2: [hw 2026-11-24] (legend: docs/README.md)",
        "bad tag: docs/a.md:2: [apk] (legend: docs/README.md)",
        "bad tag: docs/a.md:2: [gb 1.0.0] (legend: docs/README.md)",
    ]
