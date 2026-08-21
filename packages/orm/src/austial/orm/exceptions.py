"""ORM-specific exceptions."""

from __future__ import annotations

from typing import Any


class OrmError(Exception):
    """Base class for every exception raised by ``austial.orm``."""


class EntityNotFoundError(OrmError):
    """Raised when ``find_one``/``find_one_by`` is asked to fail-hard and no row matches."""

    def __init__(self, entity: type, criteria: Any):
        super().__init__(f"Could not find any entity of type {entity.__name__!r} matching {criteria!r}")
        self.entity = entity
        self.criteria = criteria


class QueryFailedError(OrmError):
    """Raised when the underlying driver rejects a compiled query."""

    def __init__(self, sql: str, cause: Exception):
        super().__init__(f"Query failed: {sql}\n{cause}")
        self.sql = sql
        self.__cause__ = cause


class RelationNotFoundError(OrmError):
    """Raised when a relation name passed to ``FindOptions.relations``/``QueryBuilder`` joins
    doesn't exist on the entity's metadata."""

    def __init__(self, entity: type, relation_name: str):
        super().__init__(f"No relation {relation_name!r} was found on entity {entity.__name__!r}")
        self.entity = entity
        self.relation_name = relation_name


class MissingPrimaryKeyError(OrmError):
    """Raised when an entity has no ``PrimaryColumn``/``PrimaryGeneratedColumn`` declared."""

    def __init__(self, entity: type):
        super().__init__(
            f"Entity {entity.__name__!r} has no primary key -- declare one column as "
            f"PrimaryColumn() or PrimaryGeneratedColumn()"
        )
        self.entity = entity


class TransactionError(OrmError):
    """Raised for misuse of ``DataSource.transaction()`` (e.g. nested-transaction misuse)."""


class AppendOnlyViolationError(OrmError):
    """Raised when ``EntityManager`` is asked to UPDATE/remove/delete a row belonging to an
    ``@Entity(append_only=True)`` entity -- INSERT (via ``save()`` on an instance with no primary
    key set) is the only mutation such an entity ever permits. This is an application-level guard
    inside ``EntityManager``, not a database-level trigger/permission -- raw SQL issued outside the
    ORM (or a DB user with direct table access) is not covered."""

    def __init__(self, entity: type, operation: str):
        super().__init__(
            f"{entity.__name__!r} is an append-only entity (@Entity(append_only=True)) -- {operation} is not permitted"
        )
        self.entity = entity
        self.operation = operation
