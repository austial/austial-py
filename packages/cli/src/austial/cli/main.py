"""``austial`` -- the CLI, mirrors the ``nest`` command.

austial new my-app
austial generate module cats      (alias: austial g module cats)
austial generate controller cats
austial generate service cats
austial generate resource cats
austial generate guard auth/api-key [--flat] [--dry-run]
   (also: pipe, interceptor, filter, middleware, decorator, class)
austial info
austial serve
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from austial.cli.generators import (
    COMPONENT_KINDS,
    create_new_project,
    generate_app,
    generate_component,
    generate_controller,
    generate_library,
    generate_module,
    generate_resource,
    generate_service,
)
from austial.cli.generators.base import ProjectNotFoundError, dry_run, find_project_root

console = Console()
app = typer.Typer(
    name="austial",
    help="Austial CLI -- scaffold and run NestJS-style Python projects, built on FastAPI.",
    add_completion=False,
    no_args_is_help=True,
)

_SCHEMATICS = {
    "module": generate_module,
    "controller": generate_controller,
    "service": generate_service,
    "provider": generate_service,  # Nest calls a service a "provider"; same schematic
    "resource": generate_resource,
    "library": generate_library,
    "app": generate_app,
}

# Schematics that accept `--flat` (the ones that create a single file rather than a feature folder).
_FLAT_SCHEMATICS = set(COMPONENT_KINDS)

# `nest g` short aliases.
_ALIASES = {
    "mo": "module",
    "co": "controller",
    "s": "service",
    "pr": "provider",
    "r": "resource",
    "gu": "guard",
    "pi": "pipe",
    "in": "interceptor",
    "f": "filter",
    "mi": "middleware",
    "d": "decorator",
    "cl": "class",
    "ga": "gateway",
    "res": "resolver",
    "cmd": "command",
    "li": "listener",
    "lib": "library",
}

_ALL_SCHEMATICS = sorted({*_SCHEMATICS, *COMPONENT_KINDS})
_SCHEMATIC_HELP = "One of: " + ", ".join(_ALL_SCHEMATICS) + " (or a short alias: " + ", ".join(sorted(_ALIASES)) + ")"


@app.command("new")
def new_project(
    name: str = typer.Argument(..., help="Name of the new project/directory to create."),
    directory: str | None = typer.Option(None, "--directory", "-d", help="Target directory (defaults to ./<name>)."),
    skip_install: bool = typer.Option(False, "--skip-install", help="Don't run `uv sync` after scaffolding."),
    skip_git: bool = typer.Option(False, "--skip-git", help="Don't run `git init` after scaffolding."),
    skip_agents: bool = typer.Option(
        False,
        "--skip-agents",
        help="Don't write AGENTS.md or the per-tool symlinks (CLAUDE.md, GEMINI.md, ...).",
    ),
    link: str | None = typer.Option(
        None,
        "--link",
        help="Path to a local Austial framework checkout to depend on via `uv`'s editable path sources "
        "(useful before the framework is published to PyPI).",
    ),
) -> None:
    """Scaffold a brand-new Austial project -- mirrors `nest new <name>`."""
    console.print(f"[bold green]CREATE[/bold green] {name}/ ...")
    target = Path(directory).resolve() if directory else None
    project_dir = create_new_project(
        name,
        directory=target,
        austial_source_path=link,
        skip_install=skip_install,
        skip_git=skip_git,
        skip_agents=skip_agents,
    )
    console.print(f"[bold green]\u2714[/bold green] Project created at [bold]{project_dir}[/bold]")
    console.print("\nNext steps:")
    console.print(f"  cd {project_dir.name}")
    if skip_install:
        console.print("  uv sync")
    console.print("  cp .env.example .env")
    console.print("  uv run austial serve\n")


def _generate(schematic: str, name: str, *, flat: bool = False, dry: bool = False) -> None:
    schematic = _ALIASES.get(schematic.lower(), schematic.lower())
    if schematic not in _ALL_SCHEMATICS:
        console.print(
            f"[bold red]Unknown schematic[/bold red] '{schematic}'. Choose one of: {', '.join(_ALL_SCHEMATICS)}."
        )
        raise typer.Exit(code=1)
    if flat and schematic not in _FLAT_SCHEMATICS:
        console.print(f"[bold red]\u2716[/bold red] --flat applies to: {', '.join(sorted(_FLAT_SCHEMATICS))}.")
        raise typer.Exit(code=1)

    def run() -> Path:
        if schematic in COMPONENT_KINDS:
            return generate_component(schematic, name, flat=flat)
        return _SCHEMATICS[schematic](name)

    try:
        if dry:
            with dry_run() as created:
                run()
            for path in created:
                console.print(f"[bold yellow]CREATE[/bold yellow] {path} [dim](dry run)[/dim]")
            console.print("[dim]Dry run: nothing was written.[/dim]")
            return
        path = run()
    except ProjectNotFoundError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[bold green]CREATE[/bold green] {path}")


_FLAT_HELP = "Don't create a folder for the file (guard, pipe, interceptor, filter, middleware, decorator, class)."
_DRY_HELP = "Show what would be created without writing anything."


@app.command("generate")
def generate(
    schematic: str = typer.Argument(..., help=_SCHEMATIC_HELP),
    name: str = typer.Argument(..., help="Name, optionally with a path: 'cats' or 'auth/api-key'."),
    flat: bool = typer.Option(False, "--flat", help=_FLAT_HELP),
    dry: bool = typer.Option(False, "--dry-run", "-d", help=_DRY_HELP),
) -> None:
    """Generate an artifact -- mirrors `nest generate`."""
    _generate(schematic, name, flat=flat, dry=dry)


@app.command("g", hidden=True)
def generate_alias(
    schematic: str = typer.Argument(..., help=_SCHEMATIC_HELP),
    name: str = typer.Argument(..., help="Name, optionally with a path: 'cats' or 'auth/api-key'."),
    flat: bool = typer.Option(False, "--flat", help=_FLAT_HELP),
    dry: bool = typer.Option(False, "--dry-run", "-d", help=_DRY_HELP),
) -> None:
    """Alias for `generate` -- mirrors Nest CLI's `nest g`."""
    _generate(schematic, name, flat=flat, dry=dry)


@app.command("info")
def info() -> None:
    """Prints Python, platform and installed Austial package versions -- mirrors `nest info`."""
    import importlib.metadata as metadata
    import platform

    console.print(f"[bold]Python[/bold]    {platform.python_version()} ({platform.system()} {platform.machine()})")
    packages = sorted(
        (dist.metadata["Name"], dist.version)
        for dist in metadata.distributions()
        if (dist.metadata["Name"] or "").lower().startswith("austial")
    )
    console.print("[bold]Austial packages[/bold]")
    for name, version in packages:
        console.print(f"  {name:<22} {version}")
    try:
        console.print(f"[bold]Project[/bold]   {find_project_root()}")
    except ProjectNotFoundError:
        console.print("[bold]Project[/bold]   [dim](not inside an Austial project)[/dim]")


def _project_root_or_exit() -> Path:
    try:
        return find_project_root()
    except ProjectNotFoundError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(True, help="Auto-reload on file changes (dev mode)."),
) -> None:
    """Runs the current project with auto-reload (mirrors `nest start --watch`)."""
    _serve(host, port, reload)


@app.command("start")
def start(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    watch: bool = typer.Option(False, "--watch", "-w", help="Auto-reload on file changes."),
    target: str = typer.Option("src.main:app", "--app", help="ASGI app to run, e.g. apps.admin.main:app."),
) -> None:
    """Runs the project (mirrors `nest start`; add --watch for reload, --app for an app in apps/)."""
    _serve(host, port, watch, target)


@app.command("build")
def build() -> None:
    """Byte-compiles the project (src, libs, apps) and checks the module graph imports and scans cleanly."""
    from austial.cli.tools import TargetError, build_project, load_target, module_graph_for

    root = _project_root_or_exit()
    failed = build_project(root)
    if failed:
        console.print(f"[bold red]\u2716[/bold red] Compilation failed in: {', '.join(failed)}")
        raise typer.Exit(code=1)
    try:
        graph = module_graph_for(load_target("src.app_module:AppModule", root))
    except TargetError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[bold green]\u2714[/bold green] Build OK: {len(graph.records)} modules scanned")


@app.command("add")
def add(
    package: str = typer.Argument(..., help="Optional package, e.g. cache, events, websockets (see `austial add x`)."),
    dry: bool = typer.Option(False, "--dry-run", "-d", help="Print the command without running it."),
) -> None:
    """Installs an optional Austial package into the project with uv (mirrors `nest add`)."""
    import subprocess

    from austial.cli.tools import TargetError, add_command

    try:
        command = add_command(package)
    except TargetError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[bold]$ {' '.join(command)}[/bold]")
    if dry:
        return
    raise typer.Exit(code=subprocess.run(command, cwd=_project_root_or_exit()).returncode)


@app.command("graph")
def graph(
    target: str = typer.Argument("src.app_module:AppModule", help="module.path:RootModule"),
    fmt: str = typer.Option("mermaid", "--format", "-f", help="mermaid or json."),
) -> None:
    """Prints the module graph (imports, providers, controllers, exports), like Nest's devtools graph."""
    import json

    from austial.cli.tools import TargetError, load_target, module_graph_for

    try:
        module_graph = module_graph_for(load_target(target, _project_root_or_exit()))
    except TargetError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    typer.echo(json.dumps(module_graph.to_dict(), indent=2) if fmt == "json" else module_graph.to_mermaid())


@app.command("repl")
def repl(target: str = typer.Argument("src.app_module:AppModule", help="module.path:RootModule")) -> None:
    """Starts a Python REPL with the app booted: get(Token), run(coroutine). Mirrors Nest's REPL."""
    import code

    from austial.cli.tools import ReplSession, TargetError, load_target

    try:
        session = ReplSession(load_target(target, _project_root_or_exit()))
    except TargetError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    try:
        code.interact(banner=session.banner(), local=session.namespace)
    finally:
        session.close()


def _serve(host: str, port: int, reload: bool, target: str = "src.main:app") -> None:
    import uvicorn

    try:
        project_root = find_project_root()
    except ProjectNotFoundError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    import sys

    sys.path.insert(0, str(project_root))
    console.print(f"[bold green]\u25b6[/bold green] Serving {project_root.name} on http://{host}:{port}")
    uvicorn.run(target, host=host, port=port, reload=reload, app_dir=str(project_root))


def run() -> None:
    app()


if __name__ == "__main__":
    run()
