"""``austial new <name>`` -- mirrors ``nest new <name>``."""

from __future__ import annotations

import subprocess
from pathlib import Path

from austial.cli.generators.agent_files import link_agent_files
from austial.cli.generators.base import render, write_file
from austial.cli.naming import to_kebab_case

# Folders created under src/shared/ (each an importable package). `austial g <kind> <name> --shared` fills them.
SHARED_FOLDERS_SCAFFOLD = ("guards", "services", "pipes", "interceptors", "filters", "decorators", "dto")


def create_new_project(
    name: str,
    *,
    directory: Path | None = None,
    austial_source_path: str | None = None,
    skip_install: bool = False,
    skip_git: bool = False,
    skip_agents: bool = False,
) -> Path:
    project_dir = (directory or Path.cwd() / name).resolve()
    project_slug = to_kebab_case(name)
    ctx = {
        "project_name": name,
        "project_slug": project_slug,
        "austial_source_path": austial_source_path,
        "agents": not skip_agents,
    }

    write_file(project_dir / "pyproject.toml", render("project/pyproject.toml.j2", **ctx))
    write_file(project_dir / "README.md", render("project/readme.j2", **ctx))
    write_file(project_dir / ".env.example", render("project/env_example.j2", **ctx))
    write_file(project_dir / ".gitignore", render("project/gitignore.j2", **ctx))
    write_file(project_dir / ".pre-commit-config.yaml", render("project/pre_commit_config.yaml.j2", **ctx))

    if not skip_agents:
        write_file(project_dir / "AGENTS.md", render("project/agents_md.j2", **ctx))
        link_agent_files(project_dir)

    src = project_dir / "src"
    write_file(src / "__init__.py", "")
    write_file(src / "main.py", render("project/main.py.j2", **ctx))

    # src/app/: the root module and the app-level controller/service, with the feature modules under it.
    write_file(src / "app" / "__init__.py", "")
    write_file(src / "app" / "app_module.py", render("project/app_module.py.j2", **ctx))
    write_file(src / "app" / "app_controller.py", render("project/app_controller.py.j2", **ctx))
    write_file(src / "app" / "app_service.py", render("project/app_service.py.j2", **ctx))

    # src/app/modules/: one folder per feature.
    write_file(src / "app" / "modules" / "__init__.py", "")
    health_dir = src / "app" / "modules" / "health"
    write_file(health_dir / "__init__.py", "")
    write_file(health_dir / "health_module.py", render("project/modules/health/health_module.py.j2", **ctx))
    write_file(health_dir / "health_controller.py", render("project/modules/health/health_controller.py.j2", **ctx))
    write_file(health_dir / "health_service.py", render("project/modules/health/health_service.py.j2", **ctx))
    write_file(health_dir / "health_dto.py", render("project/modules/health/health_dto.py.j2", **ctx))

    # src/shared/: code several modules use. Folders for the kinds you add later are ready (and importable).
    write_file(src / "shared" / "__init__.py", "")
    for folder in SHARED_FOLDERS_SCAFFOLD:
        write_file(src / "shared" / folder / "__init__.py", "")
    write_file(
        src / "shared" / "guards" / "api_key_guard.py",
        render("project/shared/guards/api_key_guard.py.j2", **ctx),
    )

    # src/templates/: non-Python assets (email, ...). Not a package, so the folder is just kept in git.
    write_file(src / "templates" / "email" / ".gitkeep", "")

    write_file(project_dir / "tests" / "__init__.py", "")
    write_file(project_dir / "tests" / "unit" / "__init__.py", "")
    write_file(project_dir / "tests" / "e2e" / "__init__.py", "")
    write_file(
        project_dir / "tests" / "unit" / "health_service_spec.py",
        render("project/tests/unit/health_service_spec.py.j2", **ctx),
    )
    write_file(
        project_dir / "tests" / "e2e" / "app_e2e_spec.py",
        render("project/tests/e2e/app_e2e_spec.py.j2", **ctx),
    )

    if not skip_git:
        subprocess.run(["git", "init", "-q"], cwd=project_dir, check=False)

    if not skip_install:
        subprocess.run(["uv", "sync"], cwd=project_dir, check=False)

    return project_dir
