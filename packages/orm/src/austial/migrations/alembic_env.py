"""``alembic_env(config, metadata)`` -- the online/offline runner used by every
product's ``env.py``.

The bundled ``env.py`` template calls this exactly once; keeping the online/offline
switch in the framework means the ``env.py`` a product commits never has to change when
Alembic gains new options we want to standardise on (``version_table``, ``compare_type``,
future ``batch_alter_table`` opt-ins on SQLite, ...).

The function reads runtime overrides off ``alembic.config.Config.attributes`` -- the
same dict :class:`~austial.migrations.migration_runner.MigrationRunner` writes to before
invoking ``alembic.command.*`` -- so a caller can hand in a live SQLAlchemy ``Engine``
without ``env.py`` having to know about it.
"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import context as alembic_context
from alembic.config import Config as AlembicConfig


def alembic_env(config: AlembicConfig, metadata: sa.MetaData | None) -> None:
    """Configure and run Alembic in either offline or online mode.

    Called from a product's ``env.py`` -- pass ``alembic.context.config`` and the
    SQLAlchemy ``MetaData`` describing the schema (from
    ``DataSource.get_metadata()``). Nothing here talks to Alembic beyond the two APIs
    every product's ``env.py`` already imports, so upgrading Alembic itself never
    requires regenerating ``env.py``.
    """
    attributes: dict[str, Any] = getattr(config, "attributes", {})
    version_table: str = attributes.get("version_table", "alembic_version")
    compare_type: bool = attributes.get("compare_type", True)
    compare_server_default: bool = attributes.get("compare_server_default", True)
    connectable: sa.Engine | sa.Connection | None = attributes.get("engine")

    if alembic_context.is_offline_mode():
        url = config.get_main_option("sqlalchemy.url")
        alembic_context.configure(
            url=url,
            target_metadata=metadata,
            literal_binds=True,
            version_table=version_table,
            compare_type=compare_type,
            compare_server_default=compare_server_default,
            dialect_opts={"paramstyle": "named"},
        )
        with alembic_context.begin_transaction():
            alembic_context.run_migrations()
        return

    if connectable is None:
        section = config.get_section(config.config_ini_section) or {}
        main_url = config.get_main_option("sqlalchemy.url")
        if main_url is not None:
            section.setdefault("sqlalchemy.url", main_url)
        connectable = sa.engine_from_config(
            section,
            prefix="sqlalchemy.",
            poolclass=sa.pool.NullPool,
        )

    engine = connectable if isinstance(connectable, sa.Engine) else connectable.engine
    with engine.connect() as connection:
        alembic_context.configure(
            connection=connection,
            target_metadata=metadata,
            version_table=version_table,
            compare_type=compare_type,
            compare_server_default=compare_server_default,
        )
        with alembic_context.begin_transaction():
            alembic_context.run_migrations()
