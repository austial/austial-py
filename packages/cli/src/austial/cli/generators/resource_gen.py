"""``austial generate resource <name>`` -- mirrors ``nest g resource``:
scaffolds a full CRUD module (module + controller + service + dto + entity)
in one shot and registers it into the nearest ``app_module.py``."""

from __future__ import annotations

from pathlib import Path

from austial.cli.generators.app_module_patcher import register_module
from austial.cli.generators.base import find_project_root, render, write_file
from austial.cli.naming import to_kebab_case, to_pascal_case, to_snake_case


def generate_resource(name: str, *, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    snake_name = to_snake_case(name)
    class_name = to_pascal_case(name)
    ctx = {"snake_name": snake_name, "class_name": class_name, "kebab_name": to_kebab_case(name)}

    module_dir = root / "src" / "modules" / snake_name
    write_file(module_dir / "__init__.py", "")
    write_file(module_dir / "dto" / "__init__.py", "")
    write_file(module_dir / "entities" / "__init__.py", "")

    write_file(module_dir / "entities" / f"{snake_name}_entity.py", render("resource/entity.py.j2", **ctx))
    write_file(module_dir / "dto" / f"create_{snake_name}_dto.py", render("resource/create_dto.py.j2", **ctx))
    write_file(module_dir / "dto" / f"update_{snake_name}_dto.py", render("resource/update_dto.py.j2", **ctx))
    write_file(module_dir / f"{snake_name}_service.py", render("resource/service.py.j2", **ctx))
    write_file(module_dir / f"{snake_name}_controller.py", render("resource/controller.py.j2", **ctx))
    write_file(module_dir / f"{snake_name}_module.py", render("resource/module.py.j2", **ctx))

    app_module_path = root / "src" / "app_module.py"
    if app_module_path.exists():
        register_module(
            app_module_path,
            f"{class_name}Module",
            f"from src.modules.{snake_name}.{snake_name}_module import {class_name}Module",
        )
    return module_dir / f"{snake_name}_module.py"
