"""``austial generate controller <name>`` -- mirrors ``nest g controller``."""

from __future__ import annotations

from pathlib import Path

from austial.cli.generators.base import find_project_root, render, write_file
from austial.cli.naming import to_kebab_case, to_pascal_case, to_snake_case


def generate_controller(name: str, *, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    snake_name = to_snake_case(name)
    class_name = to_pascal_case(name)
    ctx = {"snake_name": snake_name, "class_name": class_name, "kebab_name": to_kebab_case(name)}

    module_dir = root / "src" / "modules" / snake_name
    write_file(module_dir / "__init__.py", "")
    file_path = module_dir / f"{snake_name}_controller.py"
    write_file(file_path, render("controller/controller.py.j2", **ctx))
    return file_path
