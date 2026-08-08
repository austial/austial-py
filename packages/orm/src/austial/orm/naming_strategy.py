"""Pluggable table/column naming, mirrors TypeORM's ``NamingStrategyInterface``/``SnakeNamingStrategy``.

Only :class:`DefaultNamingStrategy` (snake_case) ships today; ``DataSource(naming_strategy=...)``
already accepts alternate implementations of :class:`NamingStrategy` without any other code change.
"""

from __future__ import annotations

import re
from typing import Protocol

_CAMEL_BOUNDARY = re.compile(r"(?<!^)(?=[A-Z])")


def _snake(name: str) -> str:
    return _CAMEL_BOUNDARY.sub("_", name).lower()


class NamingStrategy(Protocol):
    def table_name(self, class_name: str, custom_name: str | None) -> str: ...

    def column_name(self, attribute_name: str, custom_name: str | None) -> str: ...

    def join_column_name(self, relation_name: str, referenced_column_name: str) -> str: ...

    def join_table_name(self, owning_table: str, inverse_table: str) -> str: ...

    def join_table_column_name(self, table_name: str, column_name: str) -> str: ...


class DefaultNamingStrategy:
    """snake_case everything, plural-agnostic (uses the class/attribute name as-is, just cased) --
    matches TypeORM's ``SnakeNamingStrategy`` rather than its (also snake_case, but pluralizing)
    default, since Python has no de-facto pluralization convention as uniform as JS's."""

    def table_name(self, class_name: str, custom_name: str | None) -> str:
        return custom_name if custom_name else _snake(class_name)

    def column_name(self, attribute_name: str, custom_name: str | None) -> str:
        return custom_name if custom_name else _snake(attribute_name)

    def join_column_name(self, relation_name: str, referenced_column_name: str) -> str:
        return f"{_snake(relation_name)}_{referenced_column_name}"

    def join_table_name(self, owning_table: str, inverse_table: str) -> str:
        return f"{owning_table}_{inverse_table}"

    def join_table_column_name(self, table_name: str, column_name: str) -> str:
        return f"{table_name}_{column_name}"
