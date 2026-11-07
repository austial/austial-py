"""``MigrationsConfig`` -- configuration passed to ``MigrationsModule.for_root(...)``.

Lives in its own module so ``MigrationRunner`` can import it without pulling in
``MigrationsModule`` (which needs ``MigrationRunner`` in its providers).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MigrationsConfig:
    """Configuration for :class:`MigrationRunner`.

    Every field mirrors the equivalent Alembic setting -- ``script_location`` is
    the on-disk directory holding ``env.py`` plus the ``versions/`` folder,
    ``version_table`` is the bookkeeping table Alembic writes into, and the two
    ``compare_*`` flags govern how noisy ``--autogenerate`` is when reading
    server-side defaults / column types.
    """

    script_location: str = "alembic"
    version_table: str = "alembic_version"
    compare_type: bool = True
    compare_server_default: bool = True
