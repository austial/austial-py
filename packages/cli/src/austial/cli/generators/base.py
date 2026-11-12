"""Shared helpers for every generator: template rendering + project-root
discovery, mirroring what the ``nest`` CLI's schematics engine does."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
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


_dry_run: ContextVar[list[Path] | None] = ContextVar("austial_dry_run", default=None)


@contextmanager
def dry_run() -> Iterator[list[Path]]:
    """Inside the block nothing is written; the paths that *would* be created are collected instead
    (``austial generate ... --dry-run``)."""
    created: list[Path] = []
    token = _dry_run.set(created)
    try:
        yield created
    finally:
        _dry_run.reset(token)


def is_dry_run() -> bool:
    return _dry_run.get() is not None


def write_file(path: Path, content: str, *, force: bool = False) -> bool:
    """Writes `content` to `path`, creating parent directories as needed.
    Returns False (and leaves the file untouched) if it already exists and
    `force` wasn't given -- mirrors `nest g`'s "already exists" guard."""
    if path.exists() and not force:
        return False
    collector = _dry_run.get()
    if collector is not None:
        if path.name != "__init__.py":  # package markers are noise in the report
            collector.append(path)
        return True
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


# Where the root module lives: the modular layout first, then the flat layout older projects use.
APP_MODULE_PATHS = (Path("src") / "app" / "app_module.py", Path("src") / "app_module.py")
APP_MODULE_REFS = ("src.app.app_module:AppModule", "src.app_module:AppModule")


def app_module_file(root: Path) -> Path:
    """The project's root-module file: ``src/app/app_module.py``, or the legacy ``src/app_module.py`` if that is
    what the project has. Returns the modular path when neither exists (a new project)."""
    for relative in APP_MODULE_PATHS:
        if (root / relative).exists():
            return root / relative
    return root / APP_MODULE_PATHS[0]


def app_module_ref(root: Path) -> str:
    """``module.path:AppModule`` of the project's root module, for the layout the project actually uses."""
    legacy = not (root / APP_MODULE_PATHS[0]).exists() and (root / APP_MODULE_PATHS[1]).exists()
    return APP_MODULE_REFS[1] if legacy else APP_MODULE_REFS[0]


def ensure_packages(directory: Path, root: Path) -> None:
    """Writes an ``__init__.py`` into `directory` and every parent below ``<root>/src``, so each folder on the way
    to a generated file is importable (existing files are left alone)."""
    src = root / "src"
    for folder in (directory, *directory.parents):
        if folder == src:
            break
        write_file(folder / "__init__.py", "")


def modules_dir(root: Path) -> Path:
    """Where feature modules live: ``src/app/modules/`` in the modular layout, ``src/modules/`` in the older flat one.
    An existing folder wins; for a project with neither yet, the root module's layout decides."""
    modular = root / "src" / "app" / "modules"
    flat = root / "src" / "modules"
    if modular.exists():
        return modular
    if flat.exists():
        return flat
    return modular if (root / APP_MODULE_PATHS[0]).exists() else flat


def modules_package(root: Path) -> str:
    """Dotted import path of :func:`modules_dir` (``src.app.modules`` or ``src.modules``)."""
    return ".".join(modules_dir(root).relative_to(root).parts)


def find_project_root(start: Path | None = None) -> Path:
    """Walks upward from `start` (default: cwd) looking for `src/app/app_module.py` (or the older flat
    `src/app_module.py`), the marker of an Austial project root."""
    current = (start or Path.cwd()).resolve()
    for candidate in (current, *current.parents):
        if any((candidate / relative).exists() for relative in APP_MODULE_PATHS):
            return candidate
    raise ProjectNotFoundError(
        "Couldn't find an Austial project in this or any parent directory "
        "(looked for `src/app/app_module.py`). Run this inside a project created "
        "with `austial new`, or create `src/app/app_module.py` by hand first."
    )
