"""``austial new`` writes one AGENTS.md and points every AI tool's instructions file at it."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from austial.cli.generators import create_new_project
from austial.cli.generators.agent_files import AGENT_LINKS


def _scaffold(tmp_path: Path, **kwargs) -> Path:
    return create_new_project("my-app", directory=tmp_path / "my-app", skip_install=True, skip_git=True, **kwargs)


def test_new_project_writes_agents_md_with_project_name(tmp_path):
    project = _scaffold(tmp_path)

    text = (project / "AGENTS.md").read_text()
    assert "my-app -- <what this service does>" in text
    assert "{{" not in text and "{%" not in text


@pytest.mark.skipif(not hasattr(os, "symlink"), reason="platform has no symlink support")
def test_every_tool_file_is_a_symlink_that_resolves_to_agents_md(tmp_path):
    project = _scaffold(tmp_path)

    for link in AGENT_LINKS:
        path = project / link
        assert path.is_symlink(), link
        assert path.resolve() == (project / "AGENTS.md").resolve(), link
        assert path.read_text() == (project / "AGENTS.md").read_text()


def test_skip_agents_writes_none_of_them(tmp_path):
    project = _scaffold(tmp_path, skip_agents=True)

    assert not (project / "AGENTS.md").exists()
    for link in AGENT_LINKS:
        assert not (project / link).exists() and not (project / link).is_symlink()


def test_falls_back_to_copies_when_symlinks_are_unavailable(tmp_path, monkeypatch):
    def _no_symlinks(*args, **kwargs):
        raise OSError("symlinks not permitted")

    monkeypatch.setattr(os, "symlink", _no_symlinks)

    project = _scaffold(tmp_path)

    for link in AGENT_LINKS:
        path = project / link
        assert path.is_file() and not path.is_symlink(), link
        assert path.read_text() == (project / "AGENTS.md").read_text()


def test_existing_tool_file_is_left_untouched(tmp_path):
    from austial.cli.generators.agent_files import link_agent_files

    (tmp_path / "AGENTS.md").write_text("canonical")
    (tmp_path / "CLAUDE.md").write_text("mine")

    link_agent_files(tmp_path)

    assert (tmp_path / "CLAUDE.md").read_text() == "mine"
    assert (tmp_path / "GEMINI.md").read_text() == "canonical"


def test_new_project_uses_the_modular_layout(tmp_path):
    project = _scaffold(tmp_path)
    src = project / "src"

    assert (src / "main.py").exists()
    for name in ("app_module.py", "app_controller.py", "app_service.py"):
        assert (src / "app" / name).exists(), name
    assert not (src / "app_module.py").exists()  # the flat layout is gone
    assert (src / "app" / "modules" / "health" / "health_module.py").exists()
    assert not (src / "modules").exists()  # feature modules live under src/app/
    assert (src / "shared" / "guards" / "api_key_guard.py").exists()
    for folder in ("guards", "services", "pipes", "interceptors", "filters", "decorators", "dto"):
        assert (src / "shared" / folder / "__init__.py").exists(), folder
    assert (src / "templates" / "email" / ".gitkeep").exists()
    assert not (src / "app" / "modules" / "health" / "guards").exists()  # the guard moved to shared/

    app_module = (src / "app" / "app_module.py").read_text()
    assert "from src.app.app_controller import AppController" in app_module
    assert "from src.app.modules.health.health_module import HealthModule" in app_module
    assert (
        "from src.shared.guards.api_key_guard import ApiKeyGuard"
        in (src / "app" / "modules" / "health" / "health_module.py").read_text()
    )
    assert "from src.app.app_module import AppModule" in (src / "main.py").read_text()


def test_generated_docs_describe_the_same_layout(tmp_path):
    project = _scaffold(tmp_path)

    for doc in ("README.md", "AGENTS.md"):
        text = (project / doc).read_text()
        assert "shared/" in text and "templates/" in text and "app_module.py" in text, doc
        assert "{{" not in text and "{%" not in text, doc
