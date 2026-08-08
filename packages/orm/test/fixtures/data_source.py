"""Shared in-memory ``DataSource`` builder for ``austial-orm``'s test suite -- every spec module
calls this instead of hand-rolling ``DataSource(...)`` + ``.initialize()``, so schema creation
(``synchronize=True``) stays consistent across files.
"""

from __future__ import annotations

from collections.abc import Sequence

from austial.orm import DataSource, SQLiteDriver


async def sqlite_data_source(entities: Sequence[type]) -> DataSource:
    data_source = DataSource(SQLiteDriver("sqlite+aiosqlite:///:memory:"), entities, synchronize=True)
    return await data_source.initialize()
