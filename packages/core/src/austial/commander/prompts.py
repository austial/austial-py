"""Interactive prompts for commands (Nest Commander's ``inquirer`` integration) without extra dependencies.

::

    @Command(name="init")
    @Injectable()
    class InitCommand(CommandRunner):
        async def run(self, passed_params, options):
            prompts = Prompts()
            name = prompts.ask("Project name", default="app")
            tls = prompts.confirm("Enable TLS?", default=False)
            db = prompts.choose("Database", ["postgres", "sqlite"], default="sqlite")
            secret = prompts.password("API token")

Input and output are injectable (``Prompts(input_fn=..., output_fn=...)``), so a command that prompts is
testable with scripted answers. When stdin is not a terminal, prompts fall back to their defaults instead of
blocking, and raise :class:`CommanderError` when a required answer has no default.
"""

from __future__ import annotations

import getpass
import sys
from collections.abc import Callable, Sequence
from typing import Any

from austial.commander.decorators import CommanderError


class Prompts:
    def __init__(
        self,
        *,
        input_fn: Callable[[str], str] | None = None,
        password_fn: Callable[[str], str] | None = None,
        output_fn: Callable[[str], Any] = print,
        interactive: bool | None = None,
    ):
        self._input = input_fn or input
        self._password = password_fn or getpass.getpass
        self._out = output_fn
        # an injected input function means "scripted": treat as interactive
        self.interactive = interactive if interactive is not None else (input_fn is not None or sys.stdin.isatty())

    def ask(self, question: str, *, default: str | None = None, validate: Callable[[str], bool] | None = None) -> str:
        """Free text. Re-asks until ``validate`` (if given) accepts the answer."""
        suffix = f" ({default})" if default is not None else ""
        while True:
            if not self.interactive:
                return self._fallback(question, default)
            answer = self._input(f"{question}{suffix}: ").strip() or (default or "")
            if answer and (validate is None or validate(answer)):
                return answer
            self._out("Invalid answer, try again." if answer else "An answer is required.")

    def confirm(self, question: str, *, default: bool = False) -> bool:
        hint = "Y/n" if default else "y/N"
        while True:
            if not self.interactive:
                return default
            answer = self._input(f"{question} [{hint}]: ").strip().lower()
            if not answer:
                return default
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            self._out("Please answer y or n.")

    def choose(self, question: str, choices: Sequence[str], *, default: str | None = None) -> str:
        """Pick one of ``choices`` by number or by name."""
        while True:
            if not self.interactive:
                return self._fallback(question, default)
            self._out(question)
            for number, choice in enumerate(choices, 1):
                self._out(f"  {number}) {choice}" + ("  (default)" if choice == default else ""))
            answer = self._input("> ").strip()
            if not answer and default is not None:
                return default
            if answer in choices:
                return answer
            if answer.isdigit() and 1 <= int(answer) <= len(choices):
                return choices[int(answer) - 1]
            self._out("Pick a number or a name from the list.")

    def password(self, question: str) -> str:
        """Hidden input (nothing echoed). No default: a non-interactive run fails instead of guessing."""
        if not self.interactive:
            raise CommanderError(f"'{question}' needs an interactive terminal")
        answer = self._password(f"{question}: ")
        if not answer:
            raise CommanderError(f"'{question}' is required")
        return answer

    def _fallback(self, question: str, default: str | None) -> str:
        if default is None:
            raise CommanderError(f"'{question}' needs an answer, but stdin is not a terminal and there is no default")
        return default
