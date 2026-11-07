"""Fails if a public symbol exported by ``austial`` is never mentioned in the docs site.

The docs live in the sibling ``austial-py-doc`` repository, so the framework can't break the
docs build -- but it *can* grow a public API nobody documented. Run it before a release:

    uv run python scripts/check_docs_sync.py ../austial-py-doc/content

Add a symbol to ``IGNORED`` (with a reason) only when it is deliberately undocumented.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import austial

IGNORED = {
    "__version__": "package metadata",
}


def documented_text(docs_root: Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(docs_root.rglob("*.mdx")))


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__)
        return 2
    docs_root = Path(argv[1])
    if not docs_root.is_dir():
        print(f"docs directory not found: {docs_root}", file=sys.stderr)
        return 2

    text = documented_text(docs_root)
    missing = [
        name
        for name in sorted(austial.__all__)
        if name not in IGNORED and not re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text)
    ]
    total = len(austial.__all__)
    print(f"{total - len(missing)}/{total} public symbols mentioned in {docs_root}")
    if missing:
        print("Undocumented:", ", ".join(missing))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
