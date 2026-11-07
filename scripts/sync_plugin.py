"""Refreshes the plugin's bundled AGENTS.md from the docs site (or a local docs checkout).

uv run python scripts/sync_plugin.py                              # downloads https://docs.austial.com/AGENTS.md
uv run python scripts/sync_plugin.py ../austial-py-doc/public/AGENTS.md
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

TARGET = Path(__file__).resolve().parent.parent / "plugins" / "austial" / "skills" / "austial-framework" / "AGENTS.md"
URL = "https://docs.austial.com/AGENTS.md"


def main() -> int:
    source = sys.argv[1] if len(sys.argv) > 1 else None
    if source:
        text = Path(source).read_text(encoding="utf-8")
    else:
        text = urllib.request.urlopen(URL, timeout=30).read().decode()  # noqa: S310
    if "# AGENTS.md" not in text:
        print("That does not look like the Austial AGENTS.md; leaving the plugin untouched.")
        return 1
    TARGET.write_text(text, encoding="utf-8")
    print(f"Updated {TARGET.relative_to(TARGET.parents[4])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
