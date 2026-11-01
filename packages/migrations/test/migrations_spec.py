"""``austial.migrations`` unit tests.

Covers the five load-bearing behaviours a product depends on:

- ``MigrationRunner.init()`` scaffolds a working ``env.py`` + ``versions/`` tree.
- ``revision(autogenerate=True)`` diffs SQLAlchemy metadata and emits ``op.create_table``.
- ``upgrade("head")`` applies the revision (verified by inspecting the sqlite schema).
- ``downgrade("-1")`` reverses it.
- ``current()``/``history()`` report the revision id + walk after apply.
- ``revision(autogenerate=True)`` without ``metadata=`` raises ``MigrationConfigurationError``.
- ``MigrationsModule.for_root`` wires ``MigrationRunner`` as a value provider.

Uses a temp directory + on-disk SQLite -- no external services, no ``asyncpg`` /
``greenlet`` dependency, and the alembic run itself is fully sync so no
``pytest.mark.asyncio`` here.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import sqlalchemy as sa

from austial.migrations import (
    MigrationConfigurationError,
    MigrationRunner,
    MigrationsConfig,
    MigrationsModule,
)


def _metadata_with_users() -> sa.MetaData:
    metadata = sa.MetaData()
    sa.Table(
        "users",
        metadata,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
    )
    return metadata


def _runner(tmp_path: Path, *, metadata: sa.MetaData | None = None) -> tuple[MigrationRunner, str]:
    db_path = tmp_path / "test.db"
    url = f"sqlite:///{db_path}"
    config = MigrationsConfig(script_location=str(tmp_path / "alembic"))
    runner = MigrationRunner(url, config, metadata=metadata)
    runner.init()
    return runner, url


def test_init_scaffolds_env_and_versions(tmp_path: Path) -> None:
    runner, _ = _runner(tmp_path)
    script_dir = Path(tmp_path / "alembic")
    assert (script_dir / "env.py").is_file()
    assert (script_dir / "script.py.mako").is_file()
    assert (script_dir / "versions").is_dir()
    env_source = (script_dir / "env.py").read_text()
    assert "alembic_env" in env_source


def test_revision_autogenerate_emits_create_table(tmp_path: Path) -> None:
    runner, _ = _runner(tmp_path, metadata=_metadata_with_users())
    rev_id = runner.revision("create users", autogenerate=True)
    assert rev_id
    versions = list((tmp_path / "alembic" / "versions").glob("*.py"))
    assert len(versions) == 1
    content = versions[0].read_text()
    assert "op.create_table" in content
    assert "users" in content


def test_revision_autogenerate_without_metadata_raises(tmp_path: Path) -> None:
    runner, _ = _runner(tmp_path)
    with pytest.raises(MigrationConfigurationError):
        runner.revision("noop", autogenerate=True)


def test_upgrade_head_applies_schema(tmp_path: Path) -> None:
    runner, url = _runner(tmp_path, metadata=_metadata_with_users())
    runner.revision("create users", autogenerate=True)
    runner.upgrade("head")

    engine = sa.create_engine(url)
    inspector = sa.inspect(engine)
    assert "users" in inspector.get_table_names()
    columns = {col["name"] for col in inspector.get_columns("users")}
    assert {"id", "email"}.issubset(columns)


def test_downgrade_reverses_schema(tmp_path: Path) -> None:
    runner, url = _runner(tmp_path, metadata=_metadata_with_users())
    runner.revision("create users", autogenerate=True)
    runner.upgrade("head")
    runner.downgrade("-1")

    engine = sa.create_engine(url)
    inspector = sa.inspect(engine)
    assert "users" not in inspector.get_table_names()


def test_current_reports_revision_id(tmp_path: Path) -> None:
    runner, _ = _runner(tmp_path, metadata=_metadata_with_users())
    rev_id = runner.revision("create users", autogenerate=True)
    assert runner.current() is None
    runner.upgrade("head")
    assert runner.current() == rev_id


def test_history_lists_revisions(tmp_path: Path) -> None:
    runner, _ = _runner(tmp_path, metadata=_metadata_with_users())
    rev_id = runner.revision("create users", autogenerate=True)
    history = runner.history()
    assert len(history) == 1
    entry = history[0]
    assert entry["revision"] == rev_id
    assert entry["is_head"] is True
    assert entry["down_revision"] is None
    assert "create users" in (entry["message"] or "")


def test_module_for_root_registers_runner_when_url_provided(tmp_path: Path) -> None:
    url = f"sqlite:///{tmp_path}/mod.db"
    config = MigrationsConfig(script_location=str(tmp_path / "alembic"))
    dyn = MigrationsModule.for_root(config, url=url, metadata=_metadata_with_users())

    providers = {p.get("provide") if isinstance(p, dict) else p: p for p in dyn.providers}
    assert MigrationsConfig in providers
    assert MigrationRunner in providers
    runner_provider = providers[MigrationRunner]
    assert isinstance(runner_provider, dict)
    assert isinstance(runner_provider["useValue"], MigrationRunner)
    assert MigrationRunner in dyn.exports


def test_module_for_root_without_url_only_exports_config() -> None:
    dyn = MigrationsModule.for_root(MigrationsConfig(script_location="alembic"))
    exported = list(dyn.exports)
    assert MigrationsConfig in exported
    assert MigrationRunner not in exported
