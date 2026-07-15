"""Best-effort patcher that registers a newly generated module into the
nearest ``app_module.py``, mirroring how the real ``nest`` CLI updates
``app.module.ts`` after ``nest g module``/``nest g resource``.

Text-based and intentionally conservative: if the file doesn't look like what
`austial new`/`austial generate` produce, it leaves it alone and tells the
caller so a manual edit instruction can be printed instead.
"""

from __future__ import annotations

import re
from pathlib import Path

_IMPORTS_ARRAY_RE = re.compile(r"imports\s*=\s*\[(.*?)\]", re.DOTALL)


def register_module(app_module_path: Path, class_name: str, import_line: str) -> bool:
    """Returns True if the patch was applied, False if it was already present
    or the file couldn't be safely patched."""
    text = app_module_path.read_text()

    if import_line in text:
        return False  # already registered, nothing to do

    lines = text.splitlines()

    # Group the new import with its isort "block" (contiguous run of
    # from/import lines sharing the same top-level package as `import_line`,
    # e.g. all `from src...` lines) and re-sort that block alphabetically, so
    # the patched file stays isort-clean instead of just tacking the new line
    # onto the end of the whole import section.
    package = import_line.split()[1].split(".")[0]
    prefixes = (f"from {package}.", f"import {package}.")
    block_indices = [i for i, line in enumerate(lines) if line.startswith(prefixes)]

    if block_indices:
        first, last = block_indices[0], block_indices[-1]
        block = [lines[i] for i in block_indices] + [import_line]
        block = sorted(set(block))
        lines[first : last + 1] = block
    else:
        last_import_idx = 0
        for i, line in enumerate(lines):
            if line.startswith("from ") or line.startswith("import "):
                last_import_idx = i
        lines.insert(last_import_idx + 1, import_line)

    text = "\n".join(lines) + "\n"

    match = _IMPORTS_ARRAY_RE.search(text)
    if not match:
        app_module_path.write_text(text)
        return False

    inner = match.group(1)
    new_inner = f"{inner.rstrip()}, {class_name}" if inner.strip() else class_name
    text = text[: match.start(1)] + new_inner + text[match.end(1) :]

    app_module_path.write_text(text)
    return True
