"""``CommandFactory`` -- boots the app context, wires the discovered commands into an argument parser, runs one.

::

    # cli.py
    from austial.commander import CommandFactory
    from src.app_module import AppModule

    if __name__ == "__main__":
        CommandFactory.main(AppModule, name="mytool")        # exits with the command's code
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import re
import sys
from collections.abc import Sequence
from typing import Any

from austial.commander.decorators import (
    COMMAND_METADATA,
    OPTION_METADATA,
    CommanderError,
    CommandSpec,
    OptionSpec,
    command_spec,
)
from austial.common.logger import Logger
from austial.core.discovery import DiscoveryService
from austial.core.factory import AustialFactory
from austial.core.metadata import get_metadata

_ARG = re.compile(r"^([<\[])([A-Za-z0-9_-]+)(\.\.\.)?([>\]])$")


class _Parser(argparse.ArgumentParser):
    """argparse that raises instead of calling sys.exit, so the factory controls exit codes and output."""

    def error(self, message: str) -> Any:
        raise _UsageError(message, self.format_usage(), self.prog)


class _UsageError(Exception):
    def __init__(self, message: str, usage: str, prog: str):
        super().__init__(message)
        self.usage, self.prog = usage, prog


def _parse_flags(flags: str) -> tuple[list[str], str, str | None]:
    """``"-n, --number <count>"`` -> (["-n", "--number"], "number", "<count>")"""
    placeholder: str | None = None
    names: list[str] = []
    for part in (p.strip() for p in flags.split(",")):
        tokens = part.split()
        names.append(tokens[0])
        if len(tokens) > 1:
            placeholder = tokens[1]
    longs = [n for n in names if n.startswith("--")]
    dest = (longs[0] if longs else names[0]).lstrip("-").replace("-", "_")
    return names, dest, placeholder


def _add_options(parser: argparse.ArgumentParser, instance: Any) -> dict[str, Any]:
    """Registers the instance's @Option methods; returns dest -> (spec, parse function)."""
    registered: dict[str, Any] = {}
    for name, member in inspect.getmembers(type(instance), predicate=callable):
        spec: OptionSpec | None = get_metadata(OPTION_METADATA, member)
        if spec is None:
            continue
        names, dest, placeholder = _parse_flags(spec.flags)
        kwargs: dict[str, Any] = {"dest": dest, "help": spec.description, "default": argparse.SUPPRESS}
        if placeholder is None:
            kwargs["action"] = "store_const" if not spec.multiple else "append_const"
            kwargs["const"] = True
        else:
            kwargs["action"] = "append" if spec.multiple else "store"
            if placeholder.startswith("["):
                kwargs["nargs"] = "?"
                kwargs["const"] = True
            if spec.choices:
                kwargs["choices"] = list(spec.choices)
            kwargs["metavar"] = placeholder.strip("<>[]").upper()
        if spec.required:
            kwargs["required"] = True
        parser.add_argument(*names, **kwargs)
        registered[dest] = (spec, getattr(instance, name))
    return registered


def _add_arguments(parser: argparse.ArgumentParser, arguments: str) -> None:
    for token in arguments.split():
        match = _ARG.match(token)
        if match is None:
            raise ValueError(f"Bad argument declaration '{token}': use <name>, [name], <name...> or [name...]")
        opener, name, variadic, _ = match.groups()
        required = opener == "<"
        if variadic:
            parser.add_argument(name, nargs="+" if required else "*", metavar=name)
        else:
            parser.add_argument(name, nargs=None if required else "?", metavar=name)


class _Node:
    """A command in the tree: its parser, instance, options and subcommand parsers."""

    def __init__(self, spec: CommandSpec, instance: Any, parser: argparse.ArgumentParser):
        self.spec, self.instance, self.parser = spec, instance, parser
        self.options = _add_options(parser, instance)
        self.children: dict[str, _Node] = {}


def _build(commands: list[tuple[CommandSpec, Any]], parent: _Parser, resolve: Any, depth: int = 0) -> dict[str, _Node]:
    nodes: dict[str, _Node] = {}
    sub = (
        parent.add_subparsers(dest=f"__command_{depth}__", metavar="COMMAND", parser_class=_Parser)
        if commands
        else None
    )
    for spec, instance in commands:
        assert sub is not None
        parser = sub.add_parser(spec.name, aliases=spec.aliases, help=spec.description, description=spec.description)
        _add_arguments(parser, spec.arguments)
        node = _Node(spec, instance, parser)
        nested = [(command_spec(cls), resolve(cls)) for cls in spec.subcommands]
        node.children = _build([(s, i) for s, i in nested if s is not None], parser, resolve, depth + 1)
        nodes[spec.name] = node
        for alias in spec.aliases:
            nodes[alias] = node
    return nodes


class CommandFactory:
    @staticmethod
    async def run(
        root_module: type,
        argv: Sequence[str] | None = None,
        *,
        name: str = "cli",
        description: str = "",
        logger: Any = ("warn", "error"),
    ) -> int:
        """Boots the app, runs the command ``argv`` selects and returns its exit code (0 ok, 2 usage error,
        ``CommanderError.exit_code`` or 1 on failure). ``logger`` is the framework log level list (or ``False``)."""
        if logger is not None:
            Logger.override_logger(list(logger) if isinstance(logger, tuple) else logger)
        context = await AustialFactory.create_application_context(root_module)
        try:
            return await CommandFactory._dispatch(
                context, list(sys.argv[1:] if argv is None else argv), name, description
            )
        finally:
            await context.close()

    @staticmethod
    async def _dispatch(context: Any, argv: list[str], name: str, description: str) -> int:
        discovery = context.get(DiscoveryService)
        found = [
            (command_spec(w.metatype), context.get(w.token))
            for w in discovery.get_providers(COMMAND_METADATA)
            if w.metatype is not None
        ]
        commands = [(spec, inst) for spec, inst in found if spec is not None]
        # Classes listed as someone's subcommand are reachable through their parent only.
        nested = {cls for spec, _ in commands for cls in spec.subcommands}
        top = [(s, i) for s, i in commands if type(i) not in nested]

        parser = _Parser(prog=name, description=description)
        nodes = _build(top, parser, context.get)
        default = next((n for n in nodes.values() if n.spec.default), None)
        try:
            namespace = parser.parse_args(argv)
        except _UsageError as exc:
            print(exc.usage, end="", file=sys.stderr)
            print(f"{exc.prog}: error: {exc}", file=sys.stderr)
            return 2
        except SystemExit as exc:  # --help
            return int(exc.code or 0)

        node: _Node | None = nodes.get(getattr(namespace, "__command_0__", None) or "")
        if node is None:
            if default is None:
                parser.print_help()
                return 0 if not argv else 2
            node = default
        # descend into subcommands
        depth = 1
        while node.children:
            child = node.children.get(getattr(namespace, f"__command_{depth}__", None) or "")
            if child is None:
                break
            node, depth = child, depth + 1
        return await CommandFactory._invoke(node, namespace)

    @staticmethod
    async def _invoke(node: _Node, namespace: argparse.Namespace) -> int:
        spec = node.spec
        values = vars(namespace)
        passed: list[str] = []
        for token in spec.arguments.split():
            match = _ARG.match(token)
            if match is None:
                continue
            value = values.get(match.group(2))
            if value is None:
                continue
            passed.extend(value if isinstance(value, list) else [value])
        options: dict[str, Any] = {}
        for dest, (option, parser_fn) in node.options.items():
            if dest in values:
                raw = values[dest]
                options[dest] = [parser_fn(r) for r in raw] if isinstance(raw, list) else parser_fn(raw)
            elif option.default is not None:
                options[dest] = option.default
        try:
            result = node.instance.run(passed, options)
            if inspect.isawaitable(result):
                result = await result
        except CommanderError as exc:
            print(str(exc), file=sys.stderr)
            return exc.exit_code
        except Exception as exc:  # noqa: BLE001 - report like a CLI, not a stack trace
            print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 1
        return result if isinstance(result, int) and not isinstance(result, bool) else 0

    @staticmethod
    def main(root_module: type, **kwargs: Any) -> None:
        """``sys.exit(asyncio.run(CommandFactory.run(...)))`` -- the usual last line of a ``cli.py``."""
        sys.exit(asyncio.run(CommandFactory.run(root_module, **kwargs)))
