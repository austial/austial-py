"""Shared implementation behind ``PostgresDriver``/``SQLiteDriver`` -- both dialects only differ
by connection URL scheme and dialect-specific engine kwargs, so all query-compilation/execution
logic lives here once. Private module (leading underscore): not part of the public API, imported
only by ``driver/postgres.py``/``driver/sqlite.py``.
"""

from __future__ import annotations

import copy
from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from austial.orm.driver.base import Driver
from austial.orm.driver.sqlalchemy_support import (
    SchemaCatalog,
    compile_delete,
    compile_insert,
    compile_select,
    compile_update,
    rows_to_result,
)
from austial.orm.expression import DeleteSpec, DriverResult, InsertSpec, SelectSpec, UpdateSpec
from austial.orm.naming_strategy import DefaultNamingStrategy, NamingStrategy


class SqlAlchemyEngineDriver(Driver):
    """Base ``Driver`` implementation backed by a SQLAlchemy Core async engine. Subclasses only
    set ``dialect_name`` and forward their constructor to ``super().__init__(url, **kwargs)``."""

    def __init__(self, url: str, **engine_kwargs: Any):
        self._url = url
        self._engine_kwargs = engine_kwargs
        self._engine: AsyncEngine | None = None
        self._connection: AsyncConnection | None = None  # set only for a transaction-bound driver
        self._catalog: SchemaCatalog | None = None

    def bind_schema(self, entities: Sequence[type], naming_strategy: NamingStrategy | None = None) -> None:
        """Called once by ``DataSource.initialize()`` -- builds the ``SchemaCatalog`` for the
        entities this data source manages."""
        self._catalog = SchemaCatalog(entities, naming_strategy or DefaultNamingStrategy())

    @property
    def _catalog_required(self) -> SchemaCatalog:
        if self._catalog is None:
            raise RuntimeError(
                "Driver.bind_schema() must be called before executing queries (via DataSource.initialize())."
            )
        return self._catalog

    async def connect(self) -> None:
        if self._engine is None:
            self._engine = create_async_engine(self._url, **self._engine_kwargs)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None

    async def _run(self, fn: Any) -> Any:
        """Runs ``fn(conn)`` against either the transaction-bound connection (if this driver was
        obtained from ``.transaction()``) or a fresh pooled connection that commits+closes after."""
        if self._connection is not None:
            return await fn(self._connection)
        if self._engine is None:
            await self.connect()
        assert self._engine is not None
        async with self._engine.begin() as conn:
            return await fn(conn)

    async def execute_select(self, spec: SelectSpec) -> DriverResult:
        stmt, labels_by_alias = compile_select(spec, self._catalog_required)

        async def _do(conn: AsyncConnection) -> DriverResult:
            result = await conn.execute(stmt)
            return rows_to_result(result.fetchall())

        driver_result = await self._run(_do)
        driver_result.labels_by_alias = labels_by_alias
        return driver_result

    async def execute_insert(self, spec: InsertSpec) -> DriverResult:
        stmt = compile_insert(spec, self._catalog_required)

        async def _do(conn: AsyncConnection) -> DriverResult:
            result = await conn.execute(stmt)
            try:
                rows = result.fetchall()
            except Exception:  # pragma: no cover - driver without RETURNING support
                rows = []
            return rows_to_result(rows)

        return await self._run(_do)

    async def execute_update(self, spec: UpdateSpec) -> int:
        stmt = compile_update(spec, self._catalog_required)

        async def _do(conn: AsyncConnection) -> int:
            result = await conn.execute(stmt)
            return result.rowcount

        return await self._run(_do)

    async def execute_delete(self, spec: DeleteSpec) -> int:
        stmt = compile_delete(spec, self._catalog_required)

        async def _do(conn: AsyncConnection) -> int:
            result = await conn.execute(stmt)
            return result.rowcount

        return await self._run(_do)

    async def execute_raw(self, sql: str, params: dict | None = None) -> DriverResult:
        stmt = sa.text(sql).bindparams(**(params or {}))

        async def _do(conn: AsyncConnection) -> DriverResult:
            result = await conn.execute(stmt)
            try:
                rows = result.fetchall()
            except Exception:  # pragma: no cover - statements with no result set (DDL, etc.)
                rows = []
            return rows_to_result(rows)

        return await self._run(_do)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[Driver]:
        if self._engine is None:
            await self.connect()
        assert self._engine is not None
        async with self._engine.connect() as conn, conn.begin():
            tx_driver = copy.copy(self)
            tx_driver._connection = conn
            yield tx_driver

    async def create_all_schemas(self, entities: Sequence[type]) -> None:
        if self._engine is None:
            await self.connect()
        assert self._engine is not None
        catalog = self._catalog_required
        async with self._engine.begin() as conn:
            await conn.run_sync(catalog.sqla_metadata.create_all)

    def explain_select(self, spec: SelectSpec) -> str:
        stmt, _ = compile_select(spec, self._catalog_required)
        return str(stmt)
