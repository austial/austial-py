"""``austial new <name>`` -- mirrors ``nest new <name>``."""

from __future__ import annotations

import subprocess
from pathlib import Path

from austial.cli.generators.base import render, write_file
from austial.cli.naming import to_kebab_case


def create_new_project(
    name: str,
    *,
    directory: Path | None = None,
    austial_source_path: str | None = None,
    skip_install: bool = False,
    skip_git: bool = False,
) -> Path:
    project_dir = (directory or Path.cwd() / name).resolve()
    project_slug = to_kebab_case(name)
    ctx = {"project_name": name, "project_slug": project_slug, "austial_source_path": austial_source_path}

    write_file(project_dir / "pyproject.toml", render("project/pyproject.toml.j2", **ctx))
    write_file(project_dir / "README.md", render("project/readme.j2", **ctx))
    write_file(project_dir / ".env.example", render("project/env_example.j2", **ctx))
    write_file(project_dir / ".gitignore", render("project/gitignore.j2", **ctx))
    write_file(project_dir / ".pre-commit-config.yaml", render("project/pre_commit_config.yaml.j2", **ctx))

    write_file(project_dir / "src" / "__init__.py", "")
    write_file(project_dir / "src" / "main.py", render("project/main.py.j2", **ctx))
    write_file(project_dir / "src" / "app_module.py", render("project/app_module.py.j2", **ctx))
    write_file(project_dir / "src" / "app_controller.py", render("project/app_controller.py.j2", **ctx))
    write_file(project_dir / "src" / "app_service.py", render("project/app_service.py.j2", **ctx))

    write_file(project_dir / "src" / "modules" / "__init__.py", "")
    health_dir = project_dir / "src" / "modules" / "health"
    write_file(health_dir / "__init__.py", "")
    write_file(health_dir / "health_module.py", render("project/modules/health/health_module.py.j2", **ctx))
    write_file(health_dir / "health_controller.py", render("project/modules/health/health_controller.py.j2", **ctx))
    write_file(health_dir / "health_service.py", render("project/modules/health/health_service.py.j2", **ctx))
    write_file(health_dir / "health_dto.py", render("project/modules/health/health_dto.py.j2", **ctx))
    write_file(health_dir / "guards" / "__init__.py", "")
    write_file(
        health_dir / "guards" / "api_key_guard.py",
        render("project/modules/health/guards/api_key_guard.py.j2", **ctx),
    )

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
