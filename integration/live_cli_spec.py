"""The CLI and Commander, live: real subprocesses, a real scaffolded project, a server started by ``austial start``."""

import subprocess
import sys
import textwrap
import time
from pathlib import Path

import httpx

from integration.live import free_port

CLI = [sys.executable, "-c", "from austial.cli.main import app; app()"]


def austial(*args: str, cwd: Path, timeout: float = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*CLI, *args], cwd=cwd, capture_output=True, text=True, timeout=timeout)


def test_scaffold_generate_build_graph_and_start_a_real_project(tmp_path: Path) -> None:
    created = austial("new", "demo", "--skip-install", "--skip-git", cwd=tmp_path)
    assert created.returncode == 0, created.stdout + created.stderr
    project = tmp_path / "demo"
    assert (project / "src" / "main.py").exists() and (project / "src" / "app" / "app_module.py").exists()

    for schematic, name in [
        ("resource", "cats"),
        ("gateway", "chat"),
        ("command", "seed-db"),
        ("guard", "auth"),
        ("listener", "order"),
        ("resolver", "dogs"),
        ("library", "shared"),
    ]:
        result = austial("generate", schematic, name, cwd=project)
        assert result.returncode == 0, f"{schematic}: {result.stdout}{result.stderr}"

    assert (project / "src" / "app" / "modules" / "cats" / "cats_controller.py").exists()
    assert (project / "src" / "app" / "modules" / "chat" / "chat_gateway.py").exists()
    assert "CatsModule" in (project / "src" / "app" / "app_module.py").read_text()  # the resource was registered

    # every generated file must be valid, importable Python
    compiled = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "src", "libs"], cwd=project, capture_output=True, text=True
    )
    assert compiled.returncode == 0, compiled.stdout + compiled.stderr

    built = austial("build", cwd=project)
    assert built.returncode == 0, built.stdout + built.stderr

    graph = austial("graph", cwd=project)
    assert graph.returncode == 0 and "CatsModule" in graph.stdout and "AppModule" in graph.stdout

    info = austial("info", cwd=project)
    assert info.returncode == 0 and "austial-core" in info.stdout

    # A resource needs a database: without OrmModule.for_root the app must fail at STARTUP, not answer 500 forever.
    broken = subprocess.run(
        [*CLI, "start", "--host", "127.0.0.1", "--port", str(free_port())],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert broken.returncode != 0 and "resolve dependency" in broken.stdout + broken.stderr

    module_file = project / "src" / "app" / "app_module.py"
    source = module_file.read_text()
    source = source.replace(
        "from austial.config import ConfigModule",
        "from austial.config import ConfigModule\nfrom austial.orm import OrmModule",
    )
    source = source.replace(
        "from src.app.app_controller import AppController",
        "from src.app.app_controller import AppController\nfrom src.app.modules.cats.entities.cats_entity import Cats",
    )
    source = source.replace(
        "ConfigModule.for_root(),",
        "ConfigModule.for_root(), OrmModule.for_root(type_="
        '"sqlite", url="sqlite+aiosqlite:///./demo.db", entities=[Cats], synchronize=True),',
    )
    module_file.write_text(source)

    port = free_port()
    server = subprocess.Popen(
        [*CLI, "start", "--host", "127.0.0.1", "--port", str(port)],
        cwd=project,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                if httpx.get(base + "/cats", timeout=1).status_code < 500:
                    break
            except httpx.HTTPError:
                if server.poll() is not None:
                    raise AssertionError(
                        f"`austial start` exited early:\n{server.stdout.read() if server.stdout else ''}"
                    ) from None
                time.sleep(0.2)
        else:
            raise AssertionError("the server started by `austial start` never answered")
        assert httpx.get(base + "/cats").json() == []  # the generated resource serves requests, backed by SQLite
        made = httpx.post(base + "/cats", json={"name": "tom"})
        assert made.status_code in (200, 201), made.text
        assert [c["name"] for c in httpx.get(base + "/cats").json()] == ["tom"]
        assert httpx.get(base + "/nope").status_code == 404
        assert httpx.get(base + "/docs").status_code == 200  # FastAPI's UI is there too
    finally:
        server.terminate()
        output, _ = server.communicate(timeout=20)
    assert server.returncode in (0, -15), output  # a clean exit on SIGTERM, not a crash


def test_commander_app_runs_as_a_real_cli_with_exit_codes(tmp_path: Path) -> None:
    (tmp_path / "cli.py").write_text(
        textwrap.dedent("""
        from austial import Injectable, Module
        from austial.commander import Command, CommandFactory, CommandRunner, CommanderError, Option, Prompts


        @Injectable()
        class Greeter:
            def greet(self, name, title=None):
                return f"Hello, {title + ' ' if title else ''}{name}!"


        @Command(name="greet", description="Say hello", arguments="<name> [title]")
        @Injectable()
        class GreetCommand(CommandRunner):
            def __init__(self, greeter: Greeter):
                self.greeter = greeter

            async def run(self, passed_params, options):
                for _ in range(options["times"]):
                    print(self.greeter.greet(*passed_params))

            @Option(flags="-n, --times <count>", description="Repeat", default=1)
            def parse_times(self, value):
                return int(value)


        @Command(name="fail")
        @Injectable()
        class FailCommand(CommandRunner):
            async def run(self, passed_params, options):
                raise CommanderError("nope", exit_code=7)


        @Command(name="ask")
        @Injectable()
        class AskCommand(CommandRunner):
            async def run(self, passed_params, options):
                print("name=" + Prompts().ask("Name", default="anon"))


        @Module(providers=[Greeter, GreetCommand, FailCommand, AskCommand])
        class AppModule: ...


        if __name__ == "__main__":
            CommandFactory.main(AppModule, name="tool")
    """)
    )

    def run(*args: str, stdin: str | None = None):
        return subprocess.run(
            [sys.executable, "cli.py", *args], cwd=tmp_path, capture_output=True, text=True, input=stdin, timeout=60
        )

    ok = run("greet", "Ada", "Dr", "--times", "2")
    assert ok.returncode == 0 and ok.stdout.splitlines() == ["Hello, Dr Ada!", "Hello, Dr Ada!"], ok.stderr
    assert run("fail").returncode == 7
    assert run("greet").returncode == 2  # missing required argument: a usage error
    assert run("nonsense").returncode == 2
    assert "greet" in run("--help").stdout
    assert run("ask", stdin="").stdout.strip() == "name=anon"  # no terminal: the prompt falls back to its default
