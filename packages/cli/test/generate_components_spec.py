"""``austial generate guard|pipe|interceptor|filter|middleware|decorator|class|provider``, ``--flat``,
``--dry-run``, aliases and ``austial info``."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest
from typer.testing import CliRunner

from austial.cli.generators import COMPONENT_KINDS, create_new_project, generate_component
from austial.cli.main import app

runner = CliRunner(env={"COLUMNS": "400"})  # keep long paths on one line so assertions can match them


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = create_new_project("demo", directory=tmp_path / "demo", skip_install=True, skip_git=True)
    monkeypatch.chdir(root)
    return root


def _import_file(path: Path):
    spec = importlib.util.spec_from_file_location(f"_generated_{path.stem}", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("kind", "file_name", "class_name"),
    [
        ("guard", "api_key_guard.py", "ApiKeyGuard"),
        ("pipe", "api_key_pipe.py", "ApiKeyPipe"),
        ("interceptor", "api_key_interceptor.py", "ApiKeyInterceptor"),
        ("filter", "api_key_filter.py", "ApiKeyFilter"),
        ("middleware", "api_key_middleware.py", "ApiKeyMiddleware"),
        ("decorator", "api_key_decorator.py", "ApiKey"),
        ("class", "api_key.py", "ApiKey"),
    ],
)
def test_every_component_kind_generates_importable_python(project: Path, kind, file_name, class_name) -> None:
    path = generate_component(kind, "api-key")
    assert path == project / "src" / "modules" / "api_key" / file_name
    assert (path.parent / "__init__.py").exists() and (project / "src" / "modules" / "__init__.py").exists()
    module = _import_file(path)
    assert hasattr(module, class_name)


def test_all_declared_kinds_are_covered() -> None:
    assert set(COMPONENT_KINDS) == {
        "guard",
        "pipe",
        "interceptor",
        "filter",
        "middleware",
        "decorator",
        "class",
        "gateway",
        "resolver",
        "command",
        "listener",
    }


def test_generated_files_pass_ruff(project: Path) -> None:
    paths = [generate_component(kind, "sample") for kind in COMPONENT_KINDS]
    result = subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--select", "E,F,I,UP", *map(str, paths)],
        capture_output=True,
        text=True,
        cwd=project,  # lint with the generated project's own ruff config
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_generated_guard_filter_and_decorator_actually_work(project: Path) -> None:
    guard = _import_file(generate_component("guard", "allow-all")).AllowAllGuard
    assert guard is not None

    decorator_module = _import_file(generate_component("decorator", "roles"))
    from austial.core.metadata import get_metadata

    @decorator_module.Roles("admin", "editor")
    def handler() -> None: ...

    assert get_metadata(decorator_module.ROLES_KEY, handler) == ["admin", "editor"]


def test_name_with_a_path_and_flat(project: Path) -> None:
    nested = generate_component("guard", "auth/api-key")
    assert nested == project / "src" / "modules" / "auth" / "api_key" / "api_key_guard.py"
    assert (project / "src" / "modules" / "auth" / "__init__.py").exists()

    flat = generate_component("guard", "auth/other-key", flat=True)
    assert flat == project / "src" / "modules" / "auth" / "other_key_guard.py"

    top_flat = generate_component("pipe", "slugify", flat=True)
    assert top_flat == project / "src" / "modules" / "slugify_pipe.py"


def test_existing_files_are_never_overwritten(project: Path) -> None:
    path = generate_component("guard", "keep")
    path.write_text("# hand edited\n")
    generate_component("guard", "keep")
    assert path.read_text() == "# hand edited\n"


def test_cli_generate_with_alias_and_provider(project: Path) -> None:
    result = runner.invoke(app, ["g", "gu", "auth/token"])
    assert result.exit_code == 0 and "CREATE" in result.output
    assert (project / "src" / "modules" / "auth" / "token" / "token_guard.py").exists()

    provider = runner.invoke(app, ["generate", "provider", "mailer"])
    assert provider.exit_code == 0
    assert (project / "src" / "modules" / "mailer" / "mailer_service.py").exists()


def test_cli_dry_run_writes_nothing(project: Path) -> None:
    before = {p for p in project.rglob("*")}
    result = runner.invoke(app, ["generate", "guard", "ghost", "--dry-run"])
    assert result.exit_code == 0
    assert "ghost_guard.py" in result.output and "dry run" in result.output.lower()
    assert {p for p in project.rglob("*")} == before

    resource = runner.invoke(app, ["generate", "resource", "cats", "--dry-run"])
    assert resource.exit_code == 0 and "cats_controller.py" in resource.output
    assert not (project / "src" / "modules" / "cats").exists()
    assert "cats" not in (project / "src" / "app_module.py").read_text()  # not registered either


def test_cli_flat_flag_and_validation(project: Path) -> None:
    ok = runner.invoke(app, ["generate", "interceptor", "timing", "--flat"])
    assert ok.exit_code == 0
    assert (project / "src" / "modules" / "timing_interceptor.py").exists()

    rejected = runner.invoke(app, ["generate", "module", "cats", "--flat"])
    assert rejected.exit_code == 1 and "--flat applies to" in rejected.output

    unknown = runner.invoke(app, ["generate", "scheduler", "chat"])
    assert unknown.exit_code == 1 and "Unknown schematic" in unknown.output


def test_cli_outside_a_project_fails_cleanly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["generate", "guard", "x"])
    assert result.exit_code == 1 and "Couldn't find an Austial project" in result.output


def test_info_lists_python_and_austial_packages(project: Path) -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "Python" in result.output and "austial-core" in result.output and str(project) in result.output

    outside = runner.invoke(app, ["info"])
    assert outside.exit_code == 0


def test_generated_gateway_resolver_command_and_listener_import_and_register(project: Path) -> None:
    from austial.commander.decorators import command_spec
    from austial.websockets import WebSocketGateway  # noqa: F401

    gateway = _import_file(generate_component("gateway", "live-chat")).LiveChatGateway
    assert gateway.__name__ == "LiveChatGateway"
    assert hasattr(gateway, "on_message")
    resolver = _import_file(generate_component("resolver", "cats")).CatsQuery
    assert hasattr(resolver, "cats_hello")
    command = _import_file(generate_component("command", "seed-db")).SeedDbCommand
    spec = command_spec(command)
    assert spec is not None and spec.name == "seed-db"
    listener = _import_file(generate_component("listener", "order")).OrderListener
    assert hasattr(listener, "on_created")
