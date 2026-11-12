"""``austial generate service <name>`` -- mirrors ``nest g service``.

``--shared`` creates it in ``src/shared/services/`` (a service several modules use) instead of its own feature folder;
a name path (``auth/mailer``) then becomes a subfolder.
"""

from __future__ import annotations

from pathlib import Path

from austial.cli.generators.base import ensure_packages, find_project_root, modules_dir, render, write_file
from austial.cli.generators.component_gen import SHARED_FOLDERS
from austial.cli.naming import to_kebab_case, to_pascal_case, to_snake_case


def generate_service(name: str, *, shared: bool = False, project_root: Path | None = None) -> Path:
    root = project_root or find_project_root()
    if shared:
        *folders, leaf = [part for part in name.replace("\\", "/").split("/") if part]
        directory = (root / "src" / "shared" / SHARED_FOLDERS["service"]).joinpath(*(to_snake_case(f) for f in folders))
    else:
        leaf = name
        directory = modules_dir(root) / to_snake_case(leaf)
    snake_name = to_snake_case(leaf)
    class_name = to_pascal_case(leaf)
    ctx = {"snake_name": snake_name, "class_name": class_name, "kebab_name": to_kebab_case(leaf)}

    ensure_packages(directory, root)
    file_path = directory / f"{snake_name}_service.py"
    write_file(file_path, render("service/service.py.j2", **ctx))
    return file_path
