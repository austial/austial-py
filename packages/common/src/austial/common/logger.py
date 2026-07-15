"""``Logger`` -- mirrors ``@nestjs/common``'s ``Logger``, including the
familiar colored ``[Austial] 12345  - 07/11/2026, 10:00:00 AM   LOG [Context] message``
startup banner style."""

from __future__ import annotations

import os
from datetime import datetime

from rich.console import Console

_console = Console()

_LEVEL_COLORS = {
    "LOG": "green",
    "ERROR": "red",
    "WARN": "yellow",
    "DEBUG": "magenta",
    "VERBOSE": "cyan",
}


class Logger:
    """Usable standalone (``Logger("HealthController").log("...")``) or as a
    class-level helper via the static methods, same dual API as Nest's."""

    app_name = "Austial"

    def __init__(self, context: str | None = None):
        self.context = context or "Austial"

    def _write(self, level: str, message: str, context: str | None = None) -> None:
        color = _LEVEL_COLORS.get(level, "white")
        timestamp = datetime.now().strftime("%m/%d/%Y, %I:%M:%S %p")
        ctx = context or self.context
        _console.print(
            f"[bold {color}][{self.app_name}][/bold {color}] "
            f"[dim]{os.getpid():<6}[/dim] - {timestamp}   "
            f"[bold {color}]{level:<7}[/bold {color}] "
            f"[yellow][{ctx}][/yellow] {message}"
        )

    def log(self, message: str, context: str | None = None) -> None:
        self._write("LOG", message, context)

    def error(self, message: str, context: str | None = None) -> None:
        self._write("ERROR", message, context)

    def warn(self, message: str, context: str | None = None) -> None:
        self._write("WARN", message, context)

    def debug(self, message: str, context: str | None = None) -> None:
        self._write("DEBUG", message, context)

    def verbose(self, message: str, context: str | None = None) -> None:
        self._write("VERBOSE", message, context)
