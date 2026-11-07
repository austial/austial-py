"""``austial.migrations`` -- Alembic-backed schema migrations for Austial's ORM.

Ships a :class:`MigrationsModule` (``for_root(...)`` dynamic module), a
:class:`MigrationRunner` service with ``revision``/``upgrade``/``downgrade``/``current``
/``history`` operations, an :func:`alembic_env` helper that keeps every product's
``env.py`` a one-line delegation, and a standalone ``austial-migrate`` Typer CLI so
migrations run at deploy time without booting the DI container.

The runner takes a SQLAlchemy ``Engine`` or URL string plus the SQLAlchemy ``MetaData``
that ``DataSource.get_metadata()`` returns -- deliberately not the ``DataSource``
itself, so the CLI never has to import the app's full module graph just to run
``upgrade head``.
"""

from austial.migrations.alembic_env import alembic_env
from austial.migrations.config import MigrationsConfig
from austial.migrations.errors import (
    MigrationConfigurationError,
    MigrationError,
    MigrationTargetError,
)
from austial.migrations.migration_runner import MigrationRunner
from austial.migrations.migrations_module import MigrationsModule

__all__ = [
    "MigrationConfigurationError",
    "MigrationError",
    "MigrationRunner",
    "MigrationTargetError",
    "MigrationsConfig",
    "MigrationsModule",
    "alembic_env",
]
