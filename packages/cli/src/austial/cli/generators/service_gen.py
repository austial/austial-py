"""``austial generate service <name>`` -- mirrors ``nest g service``.

``--shared`` creates it in ``src/shared/services/`` (a service several modules use) instead of its own feature folder.
"""

from __future__ import annotations

from pathlib import Path

from austial.cli.generators.base import find_project_root, modules_dir, render, write_file
from austial.cli.naming import to_kebab_case, to_pascal_case, to_snake_case


def generate_service(name: str, *, shared: bool = False, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    snake_name = to_snake_case(name)
    class_name = to_pascal_case(name)
    ctx = {"snake_name": snake_name, "class_name": class_name, "kebab_name": to_kebab_case(name)}

    module_dir = root / "src" / "shared" / "services" if shared else modules_dir(root) / snake_name
    if shared:
        write_file(root / "src" / "shared" / "__init__.py", "")
    write_file(module_dir / "__init__.py", "")
    file_path = module_dir / f"{snake_name}_service.py"
    write_file(file_path, render("service/service.py.j2", **ctx))
    return file_path
