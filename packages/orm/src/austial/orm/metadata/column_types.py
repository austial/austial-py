"""Our own column-type value objects -- pure dataclasses, zero ``sqlalchemy`` import.

These are what :func:`austial.orm.decorators.column.Column` stores on
:class:`~austial.orm.metadata.entity_metadata.ColumnMetadata`; the *only* place that ever
translates one of these into a real SQL type is ``driver/sqlalchemy_support.py``. Nothing above
the ``Driver`` boundary needs to know a mapped SQL type exists beyond this module.
"""

from __future__ import annotations

from dataclasses import dataclass


class ColumnType:
    """Marker base class for all column type value objects."""


@dataclass(frozen=True)
class String(ColumnType):
    length: int | None = 255


@dataclass(frozen=True)
class Text(ColumnType):
    pass


@dataclass(frozen=True)
class Integer(ColumnType):
    pass


@dataclass(frozen=True)
class BigInteger(ColumnType):
    pass


@dataclass(frozen=True)
class Boolean(ColumnType):
    pass


@dataclass(frozen=True)
class Float(ColumnType):
    pass


@dataclass(frozen=True)
class Numeric(ColumnType):
    precision: int = 10
    scale: int = 2


@dataclass(frozen=True)
class DateTime(ColumnType):
    timezone: bool = False


@dataclass(frozen=True)
class Date(ColumnType):
    pass


@dataclass(frozen=True)
class Time(ColumnType):
    pass


@dataclass(frozen=True)
class UUIDType(ColumnType):
    pass


@dataclass(frozen=True)
class JSONType(ColumnType):
    pass


@dataclass(frozen=True)
class EnumType(ColumnType):
    values: tuple[str, ...] = ()


# Python-annotation -> default ColumnType inference table, consulted by
# ``decorators/entity.py`` whenever a ``Column()``/``PrimaryColumn()``/... marker doesn't specify
# ``type_`` explicitly. Kept here (next to the types themselves) so both stay in sync.
_PY_TYPE_DEFAULTS: dict[type, ColumnType] = {}


def _register_defaults() -> dict[type, ColumnType]:
    import datetime
    import uuid

    return {
        str: String(),
        int: Integer(),
        bool: Boolean(),
        float: Float(),
        datetime.datetime: DateTime(),
        datetime.date: Date(),
        datetime.time: Time(),
        uuid.UUID: UUIDType(),
        dict: JSONType(),
        list: JSONType(),
    }


_PY_TYPE_DEFAULTS.update(_register_defaults())


def infer_column_type(python_type: type) -> ColumnType:
    """Best-effort ``python_type -> ColumnType`` inference, mirroring TypeORM's own
    "infer from the TS type unless you override it" behavior. Falls back to :class:`String`
    for anything unrecognized rather than raising -- an explicit ``type_=`` always wins anyway."""
    return _PY_TYPE_DEFAULTS.get(python_type, String())
