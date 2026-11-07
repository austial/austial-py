"""``@Command``, ``@Option`` and ``CommandRunner`` -- mirror ``nest-commander``.

::

    @Command(name="greet", description="Say hello", arguments="<name> [title]", aliases=["hi"])
    @Injectable()
    class GreetCommand(CommandRunner):
        def __init__(self, greeter: GreeterService):
            self.greeter = greeter

        async def run(self, passed_params: list[str], options: dict) -> None:
            text = self.greeter.greet(*passed_params)
            print(text.upper() if options.get("shout") else text)

        @Option(flags="-s, --shout", description="Say it loudly")
        def parse_shout(self, value) -> bool:             # called with True for a flag, the text for a value
            return True

        @Option(flags="-n, --times <count>", description="Repeat", default=1)
        def parse_times(self, value: str) -> int:
            return int(value)

Flag syntax is commander.js's: no placeholder = boolean flag, ``<value>`` = a required value, ``[value]`` = an
optional one (``True`` if the flag is given bare). Options end up in the ``options`` dict under the long name,
snake_cased (``--dry-run`` -> ``dry_run``).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from austial.core.metadata import get_metadata, set_metadata

COMMAND_METADATA = "austial:commander:command"
OPTION_METADATA = "austial:commander:option"


class CommandRunner:
    """Base class for commands. Implement :meth:`run`."""

    async def run(self, passed_params: list[str], options: dict[str, Any]) -> Any:  # pragma: no cover - interface
        raise NotImplementedError


class CommanderError(Exception):
    """Raise from ``run`` to stop with a message on stderr and a chosen exit code (default 1)."""

    def __init__(self, message: str, exit_code: int = 1):
        super().__init__(message)
        self.exit_code = exit_code


@dataclass
class CommandSpec:
    name: str
    description: str = ""
    arguments: str = ""
    aliases: list[str] = field(default_factory=list)
    subcommands: list[type] = field(default_factory=list)
    default: bool = False  # run when no command is named (root-level)


@dataclass
class OptionSpec:
    flags: str
    description: str = ""
    required: bool = False
    default: Any = None
    choices: Sequence[str] | None = None
    multiple: bool = False


def Command(  # noqa: N802
    name: str,
    *,
    description: str = "",
    arguments: str = "",
    aliases: Sequence[str] = (),
    subcommands: Sequence[type] = (),
    default: bool = False,
) -> Callable:
    """Class decorator: this provider is a CLI command. ``arguments`` declares positionals: ``"<file> [mode]"``
    (``<x>`` required, ``[x]`` optional, a trailing ``...`` takes the rest: ``"<files...>"``)."""
    spec = CommandSpec(name, description, arguments, list(aliases), list(subcommands), default)
    return set_metadata(COMMAND_METADATA, spec)


def SubCommand(  # noqa: N802
    name: str, *, description: str = "", arguments: str = "", aliases: Sequence[str] = ()
) -> Callable:
    """Same as :func:`Command`, for classes listed in a parent's ``subcommands=[...]``."""
    return Command(name, description=description, arguments=arguments, aliases=aliases)


def Option(  # noqa: N802
    flags: str,
    *,
    description: str = "",
    required: bool = False,
    default: Any = None,
    choices: Sequence[str] | None = None,
    multiple: bool = False,
) -> Callable:
    """Method decorator: declares an option on the command and the function that parses its value. With
    ``multiple=True`` the flag may repeat and the option becomes a list."""
    spec = OptionSpec(flags, description, required, default, choices, multiple)

    def decorator(fn):
        set_metadata(OPTION_METADATA, spec)(fn)
        return fn

    return decorator


def command_spec(cls: type) -> CommandSpec | None:
    return get_metadata(COMMAND_METADATA, cls)
