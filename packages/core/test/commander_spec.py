from __future__ import annotations

import pytest

from austial import Injectable, Module, OnModuleDestroy, OnModuleInit
from austial.commander import (
    Command,
    CommanderError,
    CommandFactory,
    CommandRunner,
    Option,
    SubCommand,
)

LOG: list[str] = []


@Injectable()
class Greeter(OnModuleInit, OnModuleDestroy):
    def on_module_init(self) -> None:
        LOG.append("greeter:init")

    def on_module_destroy(self) -> None:
        LOG.append("greeter:destroy")

    def greet(self, name: str, title: str | None = None) -> str:
        return f"Hello, {title + ' ' if title else ''}{name}!"


@Command(name="greet", description="Say hello", arguments="<name> [title]", aliases=["hi"])
@Injectable()
class GreetCommand(CommandRunner):
    def __init__(self, greeter: Greeter):
        self.greeter = greeter

    async def run(self, passed_params, options):
        text = self.greeter.greet(*passed_params)
        print(text.upper() if options.get("shout") else text)
        for _ in range(options["times"]):
            LOG.append(f"greeted:{passed_params[0]}")
        if options.get("tag"):
            print("tags=" + ",".join(options["tag"]))
        if options.get("mode"):
            print(f"mode={options['mode']}")
        if options.get("verbose"):
            print(f"verbose={options['verbose']!r}")

    @Option(flags="-s, --shout", description="Say it loudly")
    def parse_shout(self, value) -> bool:
        return True

    @Option(flags="-n, --times <count>", description="Repeat", default=1)
    def parse_times(self, value: str) -> int:
        return int(value)

    @Option(flags="-t, --tag <tag>", description="Tag (repeatable)", multiple=True)
    def parse_tag(self, value: str) -> str:
        return value.lower()

    @Option(flags="-m, --mode <mode>", description="Mode", choices=["fast", "slow"])
    def parse_mode(self, value: str) -> str:
        return value

    @Option(flags="--verbose [level]", description="Verbosity")
    def parse_verbose(self, value) -> object:
        return value


@Command(name="sum", arguments="<numbers...>", description="Add numbers")
@Injectable()
class SumCommand(CommandRunner):
    def run(self, passed_params, options):  # sync run() works too
        print(sum(int(n) for n in passed_params))
        return 0


@Command(name="fail", description="Always fails")
@Injectable()
class FailCommand(CommandRunner):
    async def run(self, passed_params, options):
        if options.get("exit"):
            raise CommanderError("custom failure", exit_code=options["exit"])
        raise RuntimeError("boom")

    @Option(flags="--exit <code>", description="Exit code")
    def parse_exit(self, value: str) -> int:
        return int(value)


@Command(name="returns", description="Returns an exit code")
@Injectable()
class ReturnsCommand(CommandRunner):
    def run(self, passed_params, options):
        return 7


@SubCommand(name="add", arguments="<name>", description="Add a remote")
@Injectable()
class RemoteAdd(CommandRunner):
    def run(self, passed_params, options):
        print(f"added {passed_params[0]} url={options.get('url')}")

    @Option(flags="-u, --url <url>", description="URL", required=True)
    def parse_url(self, value: str) -> str:
        return value


@SubCommand(name="list", description="List remotes", aliases=["ls"])
@Injectable()
class RemoteList(CommandRunner):
    def run(self, passed_params, options):
        print("remotes: origin")


@Command(name="remote", description="Manage remotes", subcommands=[RemoteAdd, RemoteList])
@Injectable()
class RemoteCommand(CommandRunner):
    def run(self, passed_params, options):
        print("remote (no subcommand)")


@Module(
    providers=[Greeter, GreetCommand, SumCommand, FailCommand, ReturnsCommand, RemoteCommand, RemoteAdd, RemoteList]
)
class CliModule:
    pass


async def run(*argv: str, **kwargs) -> int:
    return await CommandFactory.run(CliModule, list(argv), name="tool", **kwargs)


async def test_command_with_di_arguments_aliases_and_option_parsers(capsys) -> None:
    LOG.clear()
    assert await run("greet", "Ada") == 0
    assert capsys.readouterr().out == "Hello, Ada!\n"
    assert await run("hi", "Ada", "Dr", "--shout", "-n", "3") == 0  # alias, optional argument, flag, value
    assert capsys.readouterr().out == "HELLO, DR ADA!\n"
    assert LOG.count("greeted:Ada") == 4  # 1 default + 3
    assert LOG[0] == "greeter:init" and LOG[-1] == "greeter:destroy"  # the app's lifecycle wraps each run


async def test_repeatable_choice_and_optional_value_options(capsys) -> None:
    assert await run("greet", "Ada", "-t", "A", "--tag", "B", "-m", "fast", "--verbose") == 0
    out = capsys.readouterr().out
    assert "tags=a,b" in out and "mode=fast" in out and "verbose=True" in out  # [level] bare -> True
    assert await run("greet", "Ada", "--verbose", "3") == 0
    assert "verbose='3'" in capsys.readouterr().out


async def test_variadic_arguments_and_returned_exit_codes(capsys) -> None:
    assert await run("sum", "1", "2", "3") == 0
    assert capsys.readouterr().out == "6\n"
    assert await run("returns") == 7


async def test_failures_map_to_exit_codes_without_tracebacks(capsys) -> None:
    assert await run("fail") == 1
    assert "Error: RuntimeError: boom" in capsys.readouterr().err
    assert await run("fail", "--exit", "42") == 42
    assert "custom failure" in capsys.readouterr().err


async def test_usage_errors_return_2_and_help_returns_0(capsys) -> None:
    assert await run("greet") == 2  # missing <name>
    err = capsys.readouterr().err
    assert "usage:" in err and "required" in err.lower()
    assert await run("greet", "Ada", "--mode", "medium") == 2  # not one of the choices
    assert "invalid choice" in capsys.readouterr().err
    assert await run("nope") == 2
    assert await run("greet", "--help") == 0
    help_text = capsys.readouterr().out
    assert "Say hello" in help_text and "--shout" in help_text and "--times" in help_text
    assert await run() == 0  # no command: prints help
    assert "greet" in capsys.readouterr().out


async def test_subcommands_and_their_aliases_and_required_options(capsys) -> None:
    assert await run("remote", "add", "origin", "--url", "git@x") == 0
    assert capsys.readouterr().out == "added origin url=git@x\n"
    assert await run("remote", "list") == 0
    assert await run("remote", "ls") == 0
    assert capsys.readouterr().out.count("remotes: origin") == 2
    assert await run("remote", "add", "origin") == 2  # --url is required
    assert "--url" in capsys.readouterr().err
    assert await run("remote") == 0 and "remote (no subcommand)" in capsys.readouterr().out
    assert await run("add", "x") == 2  # subcommands aren't reachable at the top level


async def test_default_command_runs_when_none_is_named(capsys) -> None:
    @Command(name="main", default=True, description="the default")
    @Injectable()
    class MainCommand(CommandRunner):
        def run(self, passed_params, options):
            print("default ran")

    @Module(providers=[MainCommand])
    class OnlyDefault:
        pass

    assert await CommandFactory.run(OnlyDefault, [], name="tool") == 0
    assert "default ran" in capsys.readouterr().out


def test_bad_argument_declarations_are_rejected() -> None:
    @Command(name="bad", arguments="name")
    @Injectable()
    class Bad(CommandRunner):
        def run(self, passed_params, options): ...

    @Module(providers=[Bad])
    class BadModule:
        pass

    import asyncio

    with pytest.raises(ValueError, match="Bad argument declaration"):
        asyncio.run(CommandFactory.run(BadModule, ["bad"], name="t"))


def test_main_exits_with_the_command_code(capsys) -> None:
    with pytest.raises(SystemExit) as caught:
        CommandFactory.main(CliModule, argv=["returns"], name="tool")
    assert caught.value.code == 7


def test_prompts_ask_confirm_choose_with_scripted_answers() -> None:
    from austial.commander import Prompts

    answers = iter(["", "bad", "ok", "maybe", "y", "9", "2", "x", "sqlite"])
    out: list[str] = []
    prompts = Prompts(input_fn=lambda _p: next(answers), password_fn=lambda _p: "s3cret", output_fn=out.append)

    assert prompts.ask("Name", default="app") == "app"  # empty answer takes the default
    assert prompts.ask("Code", validate=lambda v: v == "ok") == "ok"  # "bad" rejected, "ok" accepted
    assert "Invalid answer, try again." in out
    assert prompts.confirm("Sure?") is True  # "maybe" re-asked, then "y"
    assert prompts.choose("DB", ["postgres", "sqlite"]) == "sqlite"  # "9" rejected, "2" by number
    assert prompts.choose("DB", ["postgres", "sqlite"]) == "sqlite"  # "x" rejected, then by name
    assert prompts.password("Token") == "s3cret"


def test_prompts_fall_back_to_defaults_without_a_terminal_and_fail_without_one() -> None:
    from austial.commander import Prompts

    prompts = Prompts(interactive=False)
    assert prompts.ask("Name", default="app") == "app"
    assert prompts.confirm("Sure?", default=True) is True
    assert prompts.choose("DB", ["a", "b"], default="b") == "b"
    for call in (lambda: prompts.ask("Name"), lambda: prompts.password("Token")):
        with pytest.raises(CommanderError):
            call()
