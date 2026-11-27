#!/usr/bin/env python3
"""MkDocs hook: point links that escape docs/ at the GitHub blob page.

docs/ pages link to the repository README (`../README.md#legal`) so that GitHub keeps one
canonical Legal section (see AGENTS.md). MkDocs only serves docs_dir, so it would leave those
links broken in the generated site. Rewrite `../<path>.md[#anchor]` to the GitHub blob URL;
absolute (http/https) links are untouched.

Usage: referenced from mkdocs.yml (`hooks:`); not run directly.
"""

import re

REPO_BLOB = "https://github.com/cperales/probewatch/blob/main/"
# A relative link that climbs out of docs/: `](../README.md#legal)`.
ESCAPING = re.compile(r"\]\(\.\./([\w./-]+\.md)(#[^)]*)?\)")


def on_page_markdown(markdown: str, **_: object) -> str:
    """Rewrite out-of-tree Markdown links to the repository's GitHub blob page."""
    return ESCAPING.sub(lambda m: f"]({REPO_BLOB}{m.group(1)}{m.group(2) or ''})", markdown)
