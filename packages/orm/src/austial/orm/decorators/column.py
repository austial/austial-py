"""``Column()``/``PrimaryColumn()``/``PrimaryGeneratedColumn()``/``CreateDateColumn()``/
``UpdateDateColumn()`` -- mirrors TypeORM's column decorators.

Python has no field-level decorators, so (exactly like ``Inject()`` in ``austial-common``) each
of these is used as the attribute's *default value* instead::

    @Entity()
    class Cat:
        id: int = PrimaryGeneratedColumn()
        name: str = Column()

``@Entity()`` (``decorators/entity.py``) is what actually reads these markers back off the class
and converts them into :class:`~austial.orm.metadata.entity_metadata.ColumnMetadata` plus a real
dataclass field default -- a bare ``ColumnMarker`` never survives past class-decoration time.
"""

from __future__ import annotations

from typing import Any

from austial.orm.metadata.column_types import ColumnType


class ColumnMarker:
    __slots__ = (
        "column_name",
        "create_date",
        "default",
        "generated",
        "nullable",
        "primary",
        "type_",
        "unique",
        "index",
        "update_date",
    )

    def __init__(
        self,
        *,
        name: str | None = None,
        type_: ColumnType | None = None,
        primary: bool = False,
        generated: bool = False,
        nullable: bool = False,
        unique: bool = False,
        index: bool = False,
        default: Any = None,
        create_date: bool = False,
        update_date: bool = False,
    ):
        self.column_name = name
        self.type_ = type_
        self.primary = primary
        self.generated = generated
        self.nullable = nullable
        self.unique = unique
        self.index = index
        self.default = default
        self.create_date = create_date
        self.update_date = update_date

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ColumnMarker(name={self.column_name!r}, primary={self.primary!r})"


def Column(
    *,
    name: str | None = None,
    type_: ColumnType | None = None,
    nullable: bool = False,
    unique: bool = False,
    index: bool = False,
    default: Any = None,
) -> Any:
    """A regular mapped column. ``type_`` is inferred from the attribute's Python type
    annotation unless given explicitly (mirrors TypeORM inferring from the TS type)."""
    return ColumnMarker(name=name, type_=type_, nullable=nullable, unique=unique, index=index, default=default)


def PrimaryColumn(*, name: str | None = None, type_: ColumnType | None = None, default: Any = None) -> Any:
    """A primary-key column whose value the application assigns (not DB-generated)."""
    return ColumnMarker(name=name, type_=type_, primary=True, generated=False, nullable=False, default=default)


def PrimaryGeneratedColumn(*, name: str | None = None, default: Any = None) -> Any:
    """An auto-incrementing integer primary key -- the common case, TypeORM's
    ``@PrimaryGeneratedColumn()``. ``default`` stays ``None`` in virtually every real usage
    (the DB assigns the value on insert) -- exposed only so a bare ``id: int =
    PrimaryGeneratedColumn()`` still gets an unset-until-persisted attribute."""
    from austial.orm.metadata.column_types import Integer

    return ColumnMarker(name=name, type_=Integer(), primary=True, generated=True, nullable=False, default=default)


def CreateDateColumn(*, name: str | None = None, default: Any = None) -> Any:
    """Stamped with the current UTC time by ``EntityManager.save()`` on first insert."""
    from austial.orm.metadata.column_types import DateTime

    return ColumnMarker(name=name, type_=DateTime(timezone=True), nullable=True, create_date=True, default=default)


def UpdateDateColumn(*, name: str | None = None, default: Any = None) -> Any:
    """Stamped with the current UTC time by ``EntityManager.save()`` on every insert/update."""
    from austial.orm.metadata.column_types import DateTime

    return ColumnMarker(name=name, type_=DateTime(timezone=True), nullable=True, update_date=True, default=default)
