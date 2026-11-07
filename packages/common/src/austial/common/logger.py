"""Logging -- mirrors ``@nestjs/common``'s ``Logger``, ``LoggerService`` and ``ConsoleLogger``.

* ``Logger("Context")`` is what application code uses. It forwards to the *active* logger.
* ``LoggerService`` is the interface a custom logger implements (``log``, ``error``, ``warn``, and
  optionally ``debug``, ``verbose``, ``fatal``).
* ``ConsoleLogger`` is the default: the familiar coloured
  ``[Austial] 12345  - 07/11/2026, 10:00:00 AM   LOG [Context] message`` line, with selectable
  levels and an optional JSON mode for log aggregators.

Swap the active logger for the whole process with ``Logger.override_logger(...)`` (or
``AustialFactory.create(AppModule, logger=...)`` / ``app.use_logger(...)``)::

    Logger.override_logger(["error", "warn"])      # only these levels, default console format
    Logger.override_logger(ConsoleLogger(json=True))
    Logger.override_logger(MyStructlogAdapter())   # any LoggerService
    Logger.override_logger(False)                  # silence everything

``buffer_logs=True`` holds records back until a custom logger is attached, so startup lines aren't
printed in the wrong format first.
"""

from __future__ import annotations

import json
import os
import sys
from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

from rich.console import Console

LOG_LEVELS = ("verbose", "debug", "log", "warn", "error", "fatal")

_console = Console()

_LEVEL_COLORS = {
    "LOG": "green",
    "ERROR": "red",
    "WARN": "yellow",
    "DEBUG": "magenta",
    "VERBOSE": "cyan",
    "FATAL": "bold red",
}


class LoggerService(ABC):
    """The interface a custom logger implements. Only ``log``, ``error`` and ``warn`` are required;
    the rest fall back to ``log``."""

    @abstractmethod
    def log(self, message: Any, context: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def error(self, message: Any, context: str | None = None) -> None:
        raise NotImplementedError

    @abstractmethod
    def warn(self, message: Any, context: str | None = None) -> None:
        raise NotImplementedError

    def debug(self, message: Any, context: str | None = None) -> None:
        self.log(message, context)

    def verbose(self, message: Any, context: str | None = None) -> None:
        self.log(message, context)

    def fatal(self, message: Any, context: str | None = None) -> None:
        self.error(message, context)


class ConsoleLogger(LoggerService):
    app_name = "Austial"

    def __init__(self, *, log_levels: Sequence[str] | None = None, json_output: bool = False) -> None:
        self.log_levels = tuple(log_levels) if log_levels is not None else LOG_LEVELS
        self.json_output = json_output

    def set_log_levels(self, levels: Sequence[str]) -> None:
        self.log_levels = tuple(levels)

    def is_level_enabled(self, level: str) -> bool:
        return level in self.log_levels

    def _write(self, level: str, message: Any, context: str | None) -> None:
        if not self.is_level_enabled(level):
            return
        text = message if isinstance(message, str) else repr(message)
        ctx = context or "Austial"
        if self.json_output:
            record = {
                "level": level,
                "pid": os.getpid(),
                "timestamp": datetime.now(UTC).isoformat(),
                "context": ctx,
                "message": text,
            }
            stream = sys.stderr if level in ("error", "fatal") else sys.stdout
            print(json.dumps(record), file=stream, flush=True)
            return
        label = level.upper() if level != "log" else "LOG"
        color = _LEVEL_COLORS.get(label, "white")
        timestamp = datetime.now().strftime("%m/%d/%Y, %I:%M:%S %p")
        _console.print(
            f"[bold {color}][{self.app_name}][/bold {color}] "
            f"[dim]{os.getpid():<6}[/dim] - {timestamp}   "
            f"[bold {color}]{label:<7}[/bold {color}] "
            f"[yellow][{ctx}][/yellow] {text}"
        )

    def log(self, message: Any, context: str | None = None) -> None:
        self._write("log", message, context)

    def error(self, message: Any, context: str | None = None) -> None:
        self._write("error", message, context)

    def warn(self, message: Any, context: str | None = None) -> None:
        self._write("warn", message, context)

    def debug(self, message: Any, context: str | None = None) -> None:
        self._write("debug", message, context)

    def verbose(self, message: Any, context: str | None = None) -> None:
        self._write("verbose", message, context)

    def fatal(self, message: Any, context: str | None = None) -> None:
        self._write("fatal", message, context)


class _NullLogger(LoggerService):
    def log(self, message: Any, context: str | None = None) -> None: ...
    def error(self, message: Any, context: str | None = None) -> None: ...
    def warn(self, message: Any, context: str | None = None) -> None: ...


class _State:
    logger: LoggerService = ConsoleLogger()
    buffer: list[tuple[str, Any, str | None]] | None = None


class Logger:
    """What application code uses: ``Logger("Cats").log("...")``. Forwards to the active logger."""

    app_name = "Austial"

    def __init__(self, context: str | None = None):
        self.context = context or "Austial"

    def _emit(self, level: str, message: Any, context: str | None) -> None:
        ctx = context or self.context
        if _State.buffer is not None:
            _State.buffer.append((level, message, ctx))
            return
        getattr(_State.logger, level)(message, ctx)

    def log(self, message: Any, context: str | None = None) -> None:
        self._emit("log", message, context)

    def error(self, message: Any, context: str | None = None) -> None:
        self._emit("error", message, context)

    def warn(self, message: Any, context: str | None = None) -> None:
        self._emit("warn", message, context)

    def debug(self, message: Any, context: str | None = None) -> None:
        self._emit("debug", message, context)

    def verbose(self, message: Any, context: str | None = None) -> None:
        self._emit("verbose", message, context)

    def fatal(self, message: Any, context: str | None = None) -> None:
        self._emit("fatal", message, context)

    # -- process-wide configuration ---------------------------------------------------
    @staticmethod
    def override_logger(logger: LoggerService | Sequence[str] | bool) -> None:
        """Replaces the active logger: a ``LoggerService``, a list of levels (default console
        format, only those levels), ``True`` (restore the default) or ``False`` (silence all)."""
        if isinstance(logger, LoggerService):
            _State.logger = logger
        elif logger is False:
            _State.logger = _NullLogger()
        elif logger is True:
            _State.logger = ConsoleLogger()
        else:
            _State.logger = ConsoleLogger(log_levels=list(logger))

    @staticmethod
    def active_logger() -> LoggerService:
        return _State.logger

    @staticmethod
    def attach_buffer() -> None:
        """Hold records back until :meth:`flush` -- so startup output waits for a custom logger."""
        if _State.buffer is None:
            _State.buffer = []

    @staticmethod
    def flush() -> None:
        """Replays buffered records through the (now final) active logger and stops buffering."""
        pending, _State.buffer = _State.buffer, None
        for level, message, context in pending or []:
            getattr(_State.logger, level)(message, context)
