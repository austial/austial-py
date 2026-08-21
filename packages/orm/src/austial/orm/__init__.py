"""``austial-orm`` -- a from-scratch, TypeORM-shaped ORM: entities/decorators, relations,
``Repository``/``EntityManager``, a fluent ``QueryBuilder``, and DI-native ``OrmModule`` wiring.
SQLAlchemy Core is used only as a hidden SQL-compilation/pooling seam behind ``Driver`` -- nothing
in this public API is a SQLAlchemy type, with one deliberate exception:
``DataSource.get_metadata()`` returns a real ``sqlalchemy.MetaData`` for Alembic's ``env.py`` to
use as ``target_metadata``."""

from austial.orm.data_source import DataSource
from austial.orm.decorators import (
    Column,
    CreateDateColumn,
    Entity,
    InjectRepository,
    JoinColumn,
    JoinTable,
    ManyToMany,
    ManyToOne,
    OneToMany,
    OneToOne,
    PrimaryColumn,
    PrimaryGeneratedColumn,
    UpdateDateColumn,
    repository_token,
)
from austial.orm.driver import Driver, PostgresDriver, SQLiteDriver
from austial.orm.entity_manager import DeleteResult, EntityManager, FindOptions, UpdateResult
from austial.orm.exceptions import (
    AppendOnlyViolationError,
    EntityNotFoundError,
    MissingPrimaryKeyError,
    OrmError,
    QueryFailedError,
    RelationNotFoundError,
    TransactionError,
)
from austial.orm.expression import AggregateFn, In, NotIn
from austial.orm.metadata.column_types import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    EnumType,
    Float,
    Integer,
    JSONType,
    Numeric,
    String,
    Text,
    Time,
    UUIDType,
)
from austial.orm.naming_strategy import DefaultNamingStrategy, NamingStrategy
from austial.orm.orm_module import OrmModule
from austial.orm.query_builder import QueryBuilder
from austial.orm.repository import Repository

__all__ = [
    "AggregateFn",
    "AppendOnlyViolationError",
    "BigInteger",
    "Boolean",
    "Column",
    "CreateDateColumn",
    "DataSource",
    "Date",
    "DateTime",
    "DefaultNamingStrategy",
    "DeleteResult",
    "Driver",
    "Entity",
    "EntityManager",
    "EntityNotFoundError",
    "EnumType",
    "FindOptions",
    "Float",
    "In",
    "InjectRepository",
    "Integer",
    "JSONType",
    "JoinColumn",
    "JoinTable",
    "ManyToMany",
    "ManyToOne",
    "MissingPrimaryKeyError",
    "NamingStrategy",
    "NotIn",
    "Numeric",
    "OneToMany",
    "OneToOne",
    "OrmError",
    "OrmModule",
    "PostgresDriver",
    "PrimaryColumn",
    "PrimaryGeneratedColumn",
    "QueryBuilder",
    "QueryFailedError",
    "RelationNotFoundError",
    "Repository",
    "SQLiteDriver",
    "String",
    "Text",
    "Time",
    "TransactionError",
    "UUIDType",
    "UpdateDateColumn",
    "UpdateResult",
    "repository_token",
]
