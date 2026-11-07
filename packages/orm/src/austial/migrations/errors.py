"""Exceptions raised by :mod:`austial.migrations`.

All errors extend :class:`austial.common.exceptions.HttpException` variants where a runtime
outcome maps naturally to an HTTP status, so the framework's ``AllExceptionsFilter`` maps
them without extra work. Every migration-flow failure surfaced by the CLI or
``MigrationRunner`` inherits from :class:`MigrationError`, giving product code a single
umbrella to catch in health checks or admin endpoints.
"""

from __future__ import annotations


class MigrationError(RuntimeError):
    """Base for every failure raised by :class:`MigrationRunner`."""


class MigrationConfigurationError(MigrationError):
    """The ``script_location`` directory or ``env.py`` is missing/misconfigured."""


class MigrationTargetError(MigrationError):
    """The requested revision id does not exist in the script directory."""
