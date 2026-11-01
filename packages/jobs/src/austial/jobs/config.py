"""``JobsConfig`` -- configuration passed to ``JobsModule.for_root(...)``.

Lives in its own module so ``JobQueue`` and ``Worker`` (which need the defaults
and poll interval) can import it without pulling in ``JobsModule``.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class JobsConfig:
    """Every field has a sensible default so the module can be wired with a bare
    ``JobsModule.for_root(JobsConfig())``. Override per environment."""

    concurrency: int = 4
    """Maximum number of jobs the ``Worker`` will run in parallel."""

    default_max_attempts: int = 3
    """Applied to ``@Job``-decorated methods that don't set their own."""

    default_backoff_seconds: int = 30
    """Base backoff between retry attempts. Exponential per attempt."""

    poll_interval_seconds: float = 1.0
    """How often the worker polls the backend for due jobs."""
