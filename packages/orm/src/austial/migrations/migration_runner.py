"""``MigrationRunner`` -- injectable wrapper around ``alembic.command``.

Takes a SQLAlchemy ``Engine`` or a URL string (never a ``DataSource``) so the CLI can
drive migrations without booting the full DI container -- the same reason
``alembic.command.*`` accepts a plain ``Config`` in the first place.

Every method is deliberately synchronous: Alembic itself is sync all the way down (its
DBAPI connection layer is sync-only), and the framework's async ORM stays out of the
migration process entirely -- migrations run *before* the app opens its async pool, not
after.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import sqlalchemy as sa
from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory

from austial.common.decorators.injectable import Injectable
from austial.migrations._templates import ENV_PY_TEMPLATE, README_TEMPLATE, SCRIPT_MAKO_TEMPLATE
from austial.migrations.config import MigrationsConfig
from austial.migrations.errors import MigrationConfigurationError


@Injectable()
class MigrationRunner:
    """Programmatic entrypoint for revision/upgrade/downgrade/current/history.

    Constructed with:

    - ``engine_or_url``: a SQLAlchemy ``Engine`` (reused across calls) or a URL string
      (a fresh short-lived engine is opened per invocation, matching what the CLI does).
    - ``config``: a :class:`~austial.migrations.config.MigrationsConfig` -- controls
      script location, version table, and the two ``compare_*`` autogenerate switches.
    - ``metadata``: the SQLAlchemy ``MetaData`` describing the target schema -- required
      for ``revision(autogenerate=True)``; optional for the other operations.
    """

    def __init__(
        self,
        engine_or_url: sa.Engine | str,
        config: MigrationsConfig | None = None,
        *,
        metadata: sa.MetaData | None = None,
    ) -> None:
        self._config = config or MigrationsConfig()
        self._metadata = metadata
        if isinstance(engine_or_url, str):
            self._url = engine_or_url
            self._engine: sa.Engine | None = None
        else:
            self._engine = engine_or_url
            self._url = str(engine_or_url.url)

    # ------------------------------------------------------------------
    # Scaffolding

    def init(self) -> Path:
        """Scaffold the ``script_location`` directory with ``env.py``, ``script.py.mako``,
        ``versions/`` and a short README. Idempotent -- rewrites the templates so an
        upgrade of ``austial.migrations`` picks up any framework-side ``env.py`` change,
        but leaves ``versions/`` untouched.
        """
        script_dir = Path(self._config.script_location).resolve()
        (script_dir / "versions").mkdir(parents=True, exist_ok=True)
        (script_dir / "env.py").write_text(ENV_PY_TEMPLATE)
        (script_dir / "script.py.mako").write_text(SCRIPT_MAKO_TEMPLATE)
        (script_dir / "README").write_text(README_TEMPLATE)
        return script_dir

    # ------------------------------------------------------------------
    # Public API

    def revision(self, message: str, autogenerate: bool = True) -> str:
        """Create a revision file. Returns its Alembic revision id.

        With ``autogenerate=True`` (the default) Alembic diffs the current DB schema
        against ``metadata`` -- read the docs page for the well-known caveats.
        """
        if autogenerate and self._metadata is None:
            raise MigrationConfigurationError(
                "revision(autogenerate=True) requires a `metadata=` argument on MigrationRunner."
            )
        cfg = self._alembic_config(open_engine=autogenerate)
        script = alembic_command.revision(cfg, message=message, autogenerate=autogenerate)
        if isinstance(script, list):  # alembic returns a list when multiple heads exist.
            script = script[-1] if script else None
        return script.revision if script is not None else ""

    def upgrade(self, target: str = "head") -> None:
        cfg = self._alembic_config(open_engine=True)
        alembic_command.upgrade(cfg, target)

    def downgrade(self, target: str = "-1") -> None:
        cfg = self._alembic_config(open_engine=True)
        alembic_command.downgrade(cfg, target)

    def current(self) -> str | None:
        """Read the currently-applied revision id from the ``version_table``."""
        engine = self._resolve_engine()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn,
                opts={"version_table": self._config.version_table},
            )
            return ctx.get_current_revision()

    def history(self) -> list[dict[str, Any]]:
        """Return every revision in newest-first order, each entry with ``revision``,
        ``down_revision``, ``message`` and ``is_head`` keys.
        """
        cfg = self._alembic_config(open_engine=False)
        script = ScriptDirectory.from_config(cfg)
        heads = set(script.get_heads())
        result: list[dict[str, Any]] = []
        for rev in script.walk_revisions():
            result.append(
                {
                    "revision": rev.revision,
                    "down_revision": rev.down_revision,
                    "message": rev.doc,
                    "is_head": rev.revision in heads,
                }
            )
        return result

    # ------------------------------------------------------------------
    # Internals

    def _resolve_engine(self) -> sa.Engine:
        if self._engine is not None:
            return self._engine
        return sa.create_engine(self._url)

    def _alembic_config(self, *, open_engine: bool) -> AlembicConfig:
        script_dir = Path(self._config.script_location).resolve()
        if not (script_dir / "env.py").exists():
            raise MigrationConfigurationError(
                f"No env.py at {script_dir}/env.py -- run MigrationRunner.init() (or the "
                f"`austial-migrate init` CLI subcommand) first."
            )
        cfg = AlembicConfig()
        cfg.set_main_option("script_location", str(script_dir))
        cfg.set_main_option("sqlalchemy.url", self._url.replace("%", "%%"))
        cfg.attributes["target_metadata"] = self._metadata
        cfg.attributes["version_table"] = self._config.version_table
        cfg.attributes["compare_type"] = self._config.compare_type
        cfg.attributes["compare_server_default"] = self._config.compare_server_default
        if open_engine and self._engine is not None:
            cfg.attributes["engine"] = self._engine
        # Silence Alembic's own logging in library use -- the CLI re-enables it.
        cfg.attributes.setdefault("AUSTIAL_MIGRATIONS_CWD", os.getcwd())
        return cfg
