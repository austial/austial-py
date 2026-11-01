"""AI-tool instruction files for a new project.

One canonical ``AGENTS.md`` is written, and every other tool's instructions
file is a symlink to it, so there is a single file to edit and no drift. Where
the filesystem can't create symlinks (Windows without Developer Mode), the
file is copied instead. See https://docs.austial.com/ai/setup.
"""

from __future__ import annotations

import os
import shutil
from pathlib import Path

AGENTS_FILE = "AGENTS.md"

# link path (relative to the project root) -> symlink target (relative to the link's own directory)
AGENT_LINKS: dict[str, str] = {
    "CLAUDE.md": "AGENTS.md",
    "GEMINI.md": "AGENTS.md",
    "CONVENTIONS.md": "AGENTS.md",
    ".windsurfrules": "AGENTS.md",
    ".clinerules": "AGENTS.md",
    ".rules": "AGENTS.md",
    ".github/copilot-instructions.md": "../AGENTS.md",
}


def link_agent_files(project_dir: Path) -> list[str]:
    """Points every tool-specific instructions file at ``AGENTS.md``. Returns
    the link paths that had to be copied because symlinks aren't available.
    Existing files are left untouched."""
    source = project_dir / AGENTS_FILE
    copied: list[str] = []
    for link, target in AGENT_LINKS.items():
        path = project_dir / link
        if path.exists() or path.is_symlink():
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.symlink(target, path)
        except (OSError, NotImplementedError):
            shutil.copyfile(source, path)
            copied.append(link)
    return copied
