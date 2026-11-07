"""``austial generate library|app <name>`` -- mirrors Nest's monorepo ``libraries`` and ``applications``.

* ``library`` -> ``libs/<name>/`` : a module + service other apps import (``from libs.<name>... import``).
* ``app``     -> ``apps/<name>/`` : an additional application with its own ``main.py``, next to ``src/``.

Both live at the project root, which ``austial serve`` and pytest already have on the import path.
"""

from __future__ import annotations

from pathlib import Path

from austial.cli.generators.base import find_project_root, render, write_file
from austial.cli.naming import to_kebab_case, to_pascal_case, to_snake_case


def _context(name: str) -> dict[str, str]:
    return {"snake_name": to_snake_case(name), "class_name": to_pascal_case(name), "kebab_name": to_kebab_case(name)}


def generate_library(name: str, *, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    ctx = _context(name)
    folder = root / "libs" / ctx["snake_name"]
    write_file(root / "libs" / "__init__.py", "")
    write_file(folder / "__init__.py", "")
    write_file(folder / f"{ctx['snake_name']}_service.py", render("library/service.py.j2", **ctx))
    path = folder / f"{ctx['snake_name']}_module.py"
    write_file(path, render("library/module.py.j2", **ctx))
    return path


def generate_app(name: str, *, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    ctx = _context(name)
    folder = root / "apps" / ctx["snake_name"]
    write_file(root / "apps" / "__init__.py", "")
    write_file(folder / "__init__.py", "")
    write_file(folder / "app_module.py", render("app/app_module.py.j2", **ctx))
    path = folder / "main.py"
    write_file(path, render("app/main.py.j2", **ctx))
    return path
