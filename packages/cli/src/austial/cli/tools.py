"""Logic behind ``austial graph|repl|build|add`` -- kept out of ``main.py`` so it can be tested directly."""

from __future__ import annotations

import asyncio
import compileall
import importlib
import sys
from pathlib import Path
from typing import Any

# Optional framework packages `austial add <name>` installs (PyPI name: austial-<name>).
KNOWN_PACKAGES = (
    "auth", "authz", "audit", "cache", "commander", "cqrs", "events", "graphql", "http", "i18n", "jobs",
    "microservices", "migrations", "mongo", "openapi", "orm", "prisma", "schedule", "security", "storage",
    "tenancy", "terminus", "websockets",
)  # fmt: skip


class TargetError(Exception):
    pass


def load_target(target: str, root: Path | None = None) -> Any:
    """Imports ``package.module:Attr`` (default attr: ``AppModule``) with the project root on ``sys.path``."""
    module_path, _, attr = target.partition(":")
    attr = attr or "AppModule"
    if root is not None and str(root) not in sys.path:
        sys.path.insert(0, str(root))
    try:
        module = importlib.import_module(module_path)
    except ImportError as exc:
        raise TargetError(f"Can't import '{module_path}': {exc}") from exc
    if not hasattr(module, attr):
        raise TargetError(f"'{module_path}' has no '{attr}'")
    return getattr(module, attr)


def module_graph_for(root_module: Any) -> Any:
    from austial.core.container import Container
    from austial.core.module_graph import ModuleGraph
    from austial.core.module_scanner import scan_module

    container = Container()
    scan_module(root_module, container)
    return ModuleGraph(container.module_records, set(container.internal_tokens))


class ReplSession:
    """A booted application context plus the event loop it lives on, for interactive use."""

    def __init__(self, root_module: Any):
        from austial.core.factory import AustialFactory

        self.runner = asyncio.Runner()
        self.context = self.runner.run(AustialFactory.create_application_context(root_module))
        self.namespace: dict[str, Any] = {
            "app": self.context,
            "get": self.context.get,
            "run": self.runner.run,  # run(coro): there's no top-level await in this REPL
            root_module.__name__: root_module,
        }

    def banner(self) -> str:
        return (
            "Austial REPL. Names: app (the application context), get(Token), run(coroutine).\n"
            "Example: run(get(CatsService).find_all())"
        )

    def close(self) -> None:
        self.runner.run(self.context.close())
        self.runner.close()


def build_project(root: Path) -> list[str]:
    """Byte-compiles every Python file under ``src`` (and ``libs``/``apps`` if present). Returns the files that
    failed to compile (empty = success)."""
    failed: list[str] = []
    for folder in ("src", "libs", "apps"):
        path = root / folder
        if path.is_dir() and not compileall.compile_dir(str(path), quiet=1, force=True):
            failed.append(folder)
    return failed


def add_command(name: str) -> list[str]:
    """The ``uv add`` invocation for ``austial add <name>`` (accepts ``cache`` or ``austial-cache``)."""
    short = name.removeprefix("austial-")
    if short not in KNOWN_PACKAGES:
        raise TargetError(f"Unknown package '{name}'. Available: {', '.join(KNOWN_PACKAGES)}")
    return ["uv", "add", f"austial-{short}"]
