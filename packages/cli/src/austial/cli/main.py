"""``austial`` -- the CLI, mirrors the ``nest`` command.

austial new my-app
austial generate module cats      (alias: austial g module cats)
austial generate controller cats
austial generate service cats
austial generate resource cats
austial serve
"""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console

from austial.cli.generators import (
    create_new_project,
    generate_controller,
    generate_module,
    generate_resource,
    generate_service,
)
from austial.cli.generators.base import ProjectNotFoundError, find_project_root

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
    "resource": generate_resource,
}


@app.command("new")
def new_project(
    name: str = typer.Argument(..., help="Name of the new project/directory to create."),
    directory: str | None = typer.Option(None, "--directory", "-d", help="Target directory (defaults to ./<name>)."),
    skip_install: bool = typer.Option(False, "--skip-install", help="Don't run `uv sync` after scaffolding."),
    skip_git: bool = typer.Option(False, "--skip-git", help="Don't run `git init` after scaffolding."),
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
    )
    console.print(f"[bold green]\u2714[/bold green] Project created at [bold]{project_dir}[/bold]")
    console.print("\nNext steps:")
    console.print(f"  cd {project_dir.name}")
    if skip_install:
        console.print("  uv sync")
    console.print("  cp .env.example .env")
    console.print("  uv run austial serve\n")


def _generate(schematic: str, name: str) -> None:
    schematic = schematic.lower()
    if schematic not in _SCHEMATICS:
        console.print(f"[bold red]Unknown schematic[/bold red] '{schematic}'. Choose one of: {', '.join(_SCHEMATICS)}.")
        raise typer.Exit(code=1)
    try:
        path = _SCHEMATICS[schematic](name)
    except ProjectNotFoundError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    console.print(f"[bold green]CREATE[/bold green] {path}")


@app.command("generate")
def generate(
    schematic: str = typer.Argument(..., help="One of: module, controller, service, resource"),
    name: str = typer.Argument(..., help="Name for the generated artifact, e.g. 'cats'."),
) -> None:
    """Generate a module/controller/service/resource -- mirrors `nest generate`."""
    _generate(schematic, name)


@app.command("g", hidden=True)
def generate_alias(
    schematic: str = typer.Argument(..., help="One of: module, controller, service, resource"),
    name: str = typer.Argument(..., help="Name for the generated artifact, e.g. 'cats'."),
) -> None:
    """Alias for `generate` -- mirrors Nest CLI's `nest g`."""
    _generate(schematic, name)


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", help="Bind host."),
    port: int = typer.Option(8000, help="Bind port."),
    reload: bool = typer.Option(True, help="Auto-reload on file changes (dev mode)."),
) -> None:
    """Runs the current project (mirrors `nest start --watch`)."""
    import uvicorn

    try:
        project_root = find_project_root()
    except ProjectNotFoundError as exc:
        console.print(f"[bold red]\u2716[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    import sys

    sys.path.insert(0, str(project_root))
    console.print(f"[bold green]\u25b6[/bold green] Serving {project_root.name} on http://{host}:{port}")
    uvicorn.run("src.main:app", host=host, port=port, reload=reload, app_dir=str(project_root))


def run() -> None:
    app()


if __name__ == "__main__":
    run()
