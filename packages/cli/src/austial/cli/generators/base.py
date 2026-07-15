"""Shared helpers for every generator: template rendering + project-root
discovery, mirroring what the ``nest`` CLI's schematics engine does."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render(template_relpath: str, **context: Any) -> str:
    template = _env.get_template(template_relpath)
    return template.render(**context)


def write_file(path: Path, content: str, *, force: bool = False) -> bool:
    """Writes `content` to `path`, creating parent directories as needed.
    Returns False (and leaves the file untouched) if it already exists and
    `force` wasn't given -- mirrors `nest g`'s "already exists" guard."""
    if path.exists() and not force:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return True


def ensure_package_init(directory: Path) -> None:
    """Creates an empty ``__init__.py`` in `directory` (and does *not* recurse
    -- callers create the full chain explicitly) if one doesn't exist yet."""
    init_file = directory / "__init__.py"
    if not init_file.exists():
        directory.mkdir(parents=True, exist_ok=True)
        init_file.write_text("")


class ProjectNotFoundError(Exception):
    pass


def find_project_root(start: Path | None = None) -> Path:
    """Walks upward from `start` (default: cwd) looking for `src/app_module.py`,
    the marker of an Austial project root."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if (candidate / "src" / "app_module.py").exists():
            return candidate
    raise ProjectNotFoundError(
        "Couldn't find an Austial project in this or any parent directory "
        "(looked for `src/app_module.py`). Run this inside a project created "
        "with `austial new`, or create `src/app_module.py` by hand first."
    )
