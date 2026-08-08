"""``SQLiteDriver`` -- zero-config local dev / fast test-suite dialect (aiosqlite)."""

from __future__ import annotations

from austial.orm.driver._sqlalchemy_engine_driver import SqlAlchemyEngineDriver


class SQLiteDriver(SqlAlchemyEngineDriver):
    dialect_name = "sqlite"

    def __init__(self, url: str = "sqlite+aiosqlite:///./austial.db", **engine_kwargs: object):
        super().__init__(url, **engine_kwargs)
