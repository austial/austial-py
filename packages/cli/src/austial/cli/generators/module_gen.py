"""``austial generate module <name>`` -- mirrors ``nest g module``."""

from __future__ import annotations

from pathlib import Path

from austial.cli.generators.app_module_patcher import register_module
from austial.cli.generators.base import find_project_root, render, write_file
from austial.cli.naming import to_kebab_case, to_pascal_case, to_snake_case


def generate_module(name: str, *, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    snake_name = to_snake_case(name)
    class_name = to_pascal_case(name)
    ctx = {"snake_name": snake_name, "class_name": class_name, "kebab_name": to_kebab_case(name)}

    module_dir = root / "src" / "modules" / snake_name
    write_file(module_dir / "__init__.py", "")
    file_path = module_dir / f"{snake_name}_module.py"
    write_file(file_path, render("module/module.py.j2", **ctx))

    app_module_path = root / "src" / "app_module.py"
    if app_module_path.exists():
        register_module(
            app_module_path,
            f"{class_name}Module",
            f"from src.modules.{snake_name}.{snake_name}_module import {class_name}Module",
        )
    return file_path
