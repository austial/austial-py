"""``austial generate guard|pipe|interceptor|filter|middleware|decorator|class <name>`` -- mirrors the
same ``nest g`` schematics.

``<name>`` may carry a path: ``auth/api-key`` creates ``src/modules/auth/api_key/api_key_guard.py``
(``--flat`` drops the innermost folder: ``src/modules/auth/api_key_guard.py``).
"""

from __future__ import annotations

from pathlib import Path

from austial.cli.generators.base import find_project_root, render, write_file
from austial.cli.naming import to_kebab_case, to_pascal_case, to_snake_case

# kind -> (template, file suffix)
COMPONENT_KINDS: dict[str, tuple[str, str]] = {
    "guard": ("guard/guard.py.j2", "guard"),
    "pipe": ("pipe/pipe.py.j2", "pipe"),
    "interceptor": ("interceptor/interceptor.py.j2", "interceptor"),
    "filter": ("filter/filter.py.j2", "filter"),
    "middleware": ("middleware/middleware.py.j2", "middleware"),
    "decorator": ("decorator/decorator.py.j2", "decorator"),
    "gateway": ("gateway/gateway.py.j2", "gateway"),
    "resolver": ("resolver/resolver.py.j2", "resolver"),
    "command": ("command/command.py.j2", "command"),
    "listener": ("listener/listener.py.j2", "listener"),
    "class": ("class/class.py.j2", ""),
}


def generate_component(kind: str, name: str, *, flat: bool = False, project_root: Path | None = None) -> Path:
    template, suffix = COMPONENT_KINDS[kind]
    root = project_root or find_project_root()

    *folders, leaf = [part for part in name.replace("\\", "/").split("/") if part]
    snake_name = to_snake_case(leaf)
    class_name = to_pascal_case(leaf)
    ctx = {
        "snake_name": snake_name,
        "class_name": class_name,
        "kebab_name": to_kebab_case(leaf),
        "constant_name": snake_name.upper(),
    }

    base = root / "src" / "modules"
    directory = base.joinpath(*(to_snake_case(f) for f in folders))
    if not flat:
        directory = directory / snake_name

    # Every folder between src/modules and the file is a package.
    for folder in (directory, *directory.parents):
        if folder == base.parent or folder == base.parent.parent:
            break
        write_file(folder / "__init__.py", "")

    file_name = f"{snake_name}_{suffix}.py" if suffix else f"{snake_name}.py"
    file_path = directory / file_name
    write_file(file_path, render(template, **ctx))
    return file_path
