"""Fails when a distribution imports ``austial.<module>`` that belongs to a distribution it does not depend on.

Each ``packages/<dist>/src/austial/<module>`` is owned by that distribution. A distribution may import its own
modules and those of the distributions it lists in ``dependencies``; anything else would break for users who
install it alone.
Imports guarded by ``TYPE_CHECKING`` or placed inside a function (lazy, behind an optional extra) are allowed.

    uv run python scripts/check_package_boundaries.py
"""

from __future__ import annotations

import ast
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent / "packages"


def distributions() -> dict[str, dict[str, object]]:
    found: dict[str, dict[str, object]] = {}
    for pyproject in sorted(ROOT.glob("*/pyproject.toml")):
        project = tomllib.loads(pyproject.read_text())["project"]
        modules = {
            p.name for p in (pyproject.parent / "src" / "austial").iterdir() if p.is_dir() and p.name != "__pycache__"
        }
        deps = {re.split(r"[\[<>=!~ ]", d, maxsplit=1)[0] for d in project.get("dependencies", [])}
        found[project["name"]] = {"dir": pyproject.parent, "modules": modules, "deps": deps}
    return found


def top_level_austial_imports(path: Path) -> set[str]:
    """Modules imported at module level (not inside functions, not under TYPE_CHECKING)."""
    tree = ast.parse(path.read_text())
    found: set[str] = set()

    def visit(nodes: list[ast.stmt]) -> None:
        for node in nodes:
            if isinstance(node, ast.Import):
                found.update(
                    a.name.split(".")[1] for a in node.names if a.name.startswith("austial.") and "." in a.name
                )
            elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("austial."):
                found.add(node.module.split(".")[1])
            elif isinstance(node, ast.If) and "TYPE_CHECKING" in ast.unparse(node.test):
                continue
            elif isinstance(node, (ast.If, ast.Try, ast.With)):
                for body in (getattr(node, "body", []), getattr(node, "orelse", []), getattr(node, "finalbody", [])):
                    visit(body)
                for handler in getattr(node, "handlers", []):
                    visit(handler.body)

    visit(tree.body)
    return found


def main() -> int:
    dists = distributions()
    owner = {module: name for name, info in dists.items() for module in info["modules"]}  # type: ignore[union-attr]
    problems: list[str] = []
    for name, info in dists.items():
        allowed = set(info["modules"])  # type: ignore[arg-type]
        for dep in info["deps"]:  # type: ignore[attr-defined]
            if dep in dists:
                allowed |= set(dists[dep]["modules"])  # type: ignore[arg-type]
        for path in sorted((info["dir"] / "src").rglob("*.py")):  # type: ignore[operator]
            for module in top_level_austial_imports(path) - allowed:
                if module in owner:
                    problems.append(
                        f"{path.relative_to(ROOT.parent)}: imports austial.{module} ({owner[module]}), "
                        f"which {name} does not depend on"
                    )
    for problem in problems:
        print(problem)
    print(f"{len(dists)} distributions, {len(problems)} boundary violations")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
