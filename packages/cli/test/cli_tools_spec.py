"""`austial start|build|add|graph|repl` and the library/app schematics."""

from __future__ import annotations

import json
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from austial.cli.generators import create_new_project, generate_app, generate_library
from austial.cli.main import app
from austial.cli.tools import KNOWN_PACKAGES, ReplSession, TargetError, add_command, build_project, load_target

runner = CliRunner(env={"COLUMNS": "400"})


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    root = create_new_project("demo", directory=tmp_path / "demo", skip_install=True, skip_git=True)
    monkeypatch.chdir(root)
    monkeypatch.syspath_prepend(str(root))
    yield root
    for name in [m for m in sys.modules if m == "src" or m.startswith(("src.", "libs", "apps"))]:
        del sys.modules[name]


def test_graph_command_prints_mermaid_and_json(project: Path) -> None:
    mermaid = runner.invoke(app, ["graph"])
    assert mermaid.exit_code == 0 and mermaid.output.startswith("flowchart LR") and "AppModule" in mermaid.output

    as_json = runner.invoke(app, ["graph", "--format", "json"])
    names = [m["name"] for m in json.loads(as_json.output)["modules"]]
    assert "AppModule" in names

    missing = runner.invoke(app, ["graph", "src.nope:Thing"])
    assert missing.exit_code == 1 and "Can't import" in missing.output
    wrong_attr = runner.invoke(app, ["graph", "src.app_module:Nope"])
    assert wrong_attr.exit_code == 1 and "has no 'Nope'" in wrong_attr.output


def test_build_compiles_and_scans_the_module_graph(project: Path) -> None:
    ok = runner.invoke(app, ["build"])
    assert ok.exit_code == 0 and "Build OK" in ok.output

    (project / "src" / "broken.py").write_text("def oops(:\n")
    broken = runner.invoke(app, ["build"])
    assert broken.exit_code == 1 and "Compilation failed" in broken.output and "src" in broken.output
    assert build_project(project) == ["src"]


def test_add_validates_names_and_builds_the_uv_command(project: Path) -> None:
    assert add_command("redis") == ["uv", "add", "austial-microservices[redis]"]
    assert add_command("austial-orm") == ["uv", "add", "austial-orm"]
    assert add_command("mongo") == ["uv", "add", "austial-orm[pymongo]"]
    assert add_command("graphql") == ["uv", "add", "austial-core[strawberry]"]
    with pytest.raises(TargetError, match="part of austial-core"):  # a module that already ships with `austial`
        add_command("cache")
    with pytest.raises(TargetError, match="Unknown package"):
        add_command("left-pad")
    assert {"core", "orm", "auth", "redis", "socketio", "grpc-proto", "mongo", "lambda"} <= set(KNOWN_PACKAGES)

    dry = runner.invoke(app, ["add", "socketio", "--dry-run"])
    assert dry.exit_code == 0 and "uv add austial-core[socketio]" in dry.output
    included = runner.invoke(app, ["add", "cache", "--dry-run"])
    assert included.exit_code == 1 and "part of austial-core" in included.output
    unknown = runner.invoke(app, ["add", "nope", "--dry-run"])
    assert unknown.exit_code == 1 and "Unknown package" in unknown.output


def test_add_runs_uv_in_the_project_root(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list = []

    class Done:
        returncode = 0

    def fake_run(cmd, cwd=None):
        calls.append((cmd, cwd))
        return Done()

    monkeypatch.setattr("subprocess.run", fake_run)
    result = runner.invoke(app, ["add", "redis"])
    assert result.exit_code == 0
    assert calls == [(["uv", "add", "austial-microservices[redis]"], project)]


def test_start_command_passes_watch_and_app_through(project: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    seen: dict = {}
    monkeypatch.setattr(uvicorn, "run", lambda target, **kw: seen.update(target=target, **kw))
    runner.invoke(app, ["start", "--port", "9000"])
    assert seen["target"] == "src.main:app" and seen["reload"] is False and seen["port"] == 9000
    runner.invoke(app, ["start", "--watch", "--app", "apps.admin.main:app"])
    assert seen["target"] == "apps.admin.main:app" and seen["reload"] is True
    runner.invoke(app, ["serve"])
    assert seen["reload"] is True  # serve keeps its reload-by-default behaviour


def test_library_and_app_schematics(project: Path) -> None:
    lib = generate_library("shared-utils")
    assert lib == project / "libs" / "shared_utils" / "shared_utils_module.py"
    text = lib.read_text()
    assert "class SharedUtilsModule" in text and "from libs.shared_utils.shared_utils_service" in text
    assert (project / "libs" / "__init__.py").exists() and (project / "libs" / "shared_utils" / "__init__.py").exists()

    main = generate_app("admin")
    assert main == project / "apps" / "admin" / "main.py"
    assert "AdminAppModule" in (project / "apps" / "admin" / "app_module.py").read_text()
    assert "uvicorn apps.admin.main:app" in main.read_text()

    module = load_target("libs.shared_utils.shared_utils_module:SharedUtilsModule", project)
    admin = load_target("apps.admin.main:app", project)
    assert module.__name__ == "SharedUtilsModule" and admin is not None

    via_cli = runner.invoke(app, ["generate", "lib", "billing"])
    assert via_cli.exit_code == 0 and (project / "libs" / "billing" / "billing_module.py").exists()
    via_cli = runner.invoke(app, ["g", "app", "worker"])
    assert via_cli.exit_code == 0 and (project / "apps" / "worker" / "main.py").exists()


def test_repl_session_namespace_and_run(project: Path) -> None:
    root_module = load_target("src.app_module:AppModule", project)
    session = ReplSession(root_module)
    try:
        ns = session.namespace
        assert {"app", "get", "run", "AppModule"} <= set(ns)
        assert "run(" in session.banner()

        async def answer() -> int:
            return 42

        assert ns["run"](answer()) == 42
        from austial import ModuleRef

        assert ns["get"](ModuleRef) is not None
    finally:
        session.close()
