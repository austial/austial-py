"""``austial.commander`` -- command-line apps with dependency injection, mirrors ``nest-commander``.

from austial.commander import Command, SubCommand, Option, CommandRunner, CommandFactory, CommanderError
"""

from austial.commander.decorators import (
    Command,
    CommanderError,
    CommandRunner,
    CommandSpec,
    Option,
    OptionSpec,
    SubCommand,
)
from austial.commander.factory import CommandFactory

__all__ = [
    "Command",
    "CommandFactory",
    "CommandRunner",
    "CommandSpec",
    "CommanderError",
    "Option",
    "OptionSpec",
    "SubCommand",
]
