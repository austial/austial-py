"""``DataSource.get_metadata()`` -- the public seam that hands Alembic's ``env.py`` the
``sqlalchemy.MetaData`` it needs as ``target_metadata`` (see that method's docstring and this
package's ``__init__.py`` module docstring for the one deliberate SQLAlchemy-type exception).
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa
from fixtures.entities import Cat, Owner, Toy

from austial.orm import DataSource, SQLiteDriver


def test_get_metadata_returns_sqlalchemy_metadata_without_initializing():
    # No `await data_source.initialize()` here at all -- building the catalog only walks entity
    # metadata, no DB connection, which is exactly what Alembic's `env.py` needs at import time.
    data_source = DataSource(SQLiteDriver("sqlite+aiosqlite:///:memory:"), [Owner, Cat, Toy])

    metadata = data_source.get_metadata()

    assert isinstance(metadata, sa.MetaData)
    assert {"owner", "cat", "toy"} <= set(metadata.tables)


def test_get_metadata_tables_carry_the_mapped_columns():
    data_source = DataSource(SQLiteDriver("sqlite+aiosqlite:///:memory:"), [Owner, Cat, Toy])

    metadata = data_source.get_metadata()

    cat_columns = set(metadata.tables["cat"].columns.keys())
    assert {"id", "name", "age", "created_at", "owner_id"} <= cat_columns


@pytest.mark.asyncio
async def test_get_metadata_works_the_same_before_and_after_initialize():
    data_source = DataSource(SQLiteDriver("sqlite+aiosqlite:///:memory:"), [Owner, Cat, Toy], synchronize=True)

    before_init = data_source.get_metadata()
    await data_source.initialize()
    after_init = data_source.get_metadata()

    # `initialize()` rebuilds its own catalog (see its docstring) -- `get_metadata()` must
    # describe the same schema either way, even though the two `MetaData` instances differ.
    assert set(before_init.tables) == set(after_init.tables)
    assert set(after_init.tables["cat"].columns.keys()) == set(before_init.tables["cat"].columns.keys())
    await data_source.destroy()


@pytest.mark.asyncio
async def test_get_metadata_after_initialize_reflects_the_catalog_actually_in_use():
    data_source = DataSource(SQLiteDriver("sqlite+aiosqlite:///:memory:"), [Owner, Cat, Toy], synchronize=True)
    await data_source.initialize()

    metadata = data_source.get_metadata()

    catalog = data_source._catalog  # noqa: SLF001 - same-package test, checking internal wiring
    assert catalog is not None
    assert metadata is catalog.sqla_metadata
    await data_source.destroy()
