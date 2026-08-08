"""``PostgresDriver`` -- primary/production dialect (asyncpg)."""

from __future__ import annotations

from austial.orm.driver._sqlalchemy_engine_driver import SqlAlchemyEngineDriver


class PostgresDriver(SqlAlchemyEngineDriver):
    dialect_name = "postgresql"

    def __init__(self, url: str, **engine_kwargs: object):
        super().__init__(url, **engine_kwargs)
