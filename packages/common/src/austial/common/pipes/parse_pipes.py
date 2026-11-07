"""Built-in transformation pipes -- mirrors ``@nestjs/common``'s ``ParseIntPipe``,
``ParseFloatPipe``, ``ParseBoolPipe``, ``ParseUUIDPipe``, ``ParseEnumPipe``,
``ParseArrayPipe`` and ``DefaultValuePipe``.

Attach them to a single parameter (they then also receive the *raw string* from the URL,
instead of FastAPI's already-coerced value)::

    @Get(":id")
    async def find_one(self, id: int = Param("id", ParseIntPipe)): ...

    @Get()
    async def find_all(self, page: int = Query("page", DefaultValuePipe(1), ParseIntPipe)): ...

or at any pipe scope (``@UsePipes``, ``app.use_global_pipes``). Failures raise a 400 with
Nest's message, e.g. ``Validation failed (numeric string is expected)``; pass
``error_http_status_code=`` or ``exception_factory=`` to change that.
"""

from __future__ import annotations

import math
import re
import uuid
from collections.abc import Callable
from enum import Enum
from typing import Any, NoReturn

from austial.common.exceptions.http_exceptions import HttpException
from austial.common.pipes.validation_pipe import ArgumentMetadata, PipeTransform

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


class _ParsePipe(PipeTransform):
    def __init__(
        self,
        *,
        error_http_status_code: int = 400,
        exception_factory: Callable[[str], Exception] | None = None,
        optional: bool = False,
    ) -> None:
        self._status = error_http_status_code
        self._exception_factory = exception_factory
        self._optional = optional

    def _fail(self, message: str) -> NoReturn:
        if self._exception_factory is not None:
            raise self._exception_factory(message)
        raise HttpException(message, self._status)

    def _skip(self, value: Any) -> bool:
        return self._optional and value is None


def _is_numeric(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int | float):
        return math.isfinite(value)
    if isinstance(value, str) and value.strip():
        try:
            return math.isfinite(float(value))
        except ValueError:
            return False
    return False


class ParseIntPipe(_ParsePipe):
    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if self._skip(value):
            return value
        if not _is_numeric(value):
            self._fail("Validation failed (numeric string is expected)")
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                return int(float(value))  # "12.7" -> 12, like parseInt
        return int(value)


class ParseFloatPipe(_ParsePipe):
    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if self._skip(value):
            return value
        if not _is_numeric(value):
            self._fail("Validation failed (numeric string is expected)")
        return float(value)


class ParseBoolPipe(_ParsePipe):
    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if self._skip(value):
            return value
        if isinstance(value, bool):
            return value
        if value in ("true", True):
            return True
        if value in ("false", False):
            return False
        self._fail("Validation failed (boolean string is expected)")


class ParseUUIDPipe(_ParsePipe):
    def __init__(self, *, version: int | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._version = version

    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if self._skip(value):
            return value
        label = f"uuid v{self._version}" if self._version else "uuid"
        if not isinstance(value, str) or not _UUID_RE.match(value):
            self._fail(f"Validation failed ({label} is expected)")
        if self._version is not None and uuid.UUID(value).version != self._version:
            self._fail(f"Validation failed ({label} is expected)")
        return value


class ParseEnumPipe(_ParsePipe):
    def __init__(self, enum_type: type[Enum], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._enum = enum_type

    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if self._skip(value):
            return value
        if isinstance(value, self._enum):
            return value
        for member in self._enum:
            if member.value == value or str(member.value) == str(value):
                return member
        self._fail("Validation failed (enum string is expected)")


class ParseArrayPipe(_ParsePipe):
    """Splits ``"1,2,3"`` on ``separator`` (or passes a list through) and optionally parses each
    element -- ``items`` is ``int``/``float``/``bool`` or any pipe (class or instance)."""

    def __init__(self, *, items: Any = None, separator: str = ",", **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._separator = separator
        self._item_pipe = self._build_item_pipe(items)

    @staticmethod
    def _build_item_pipe(items: Any) -> PipeTransform | None:
        if items is None:
            return None
        builtin: dict[Any, Callable[[], PipeTransform]] = {
            int: ParseIntPipe,
            float: ParseFloatPipe,
            bool: ParseBoolPipe,
        }
        if items in builtin:
            return builtin[items]()
        if isinstance(items, type) and issubclass(items, PipeTransform):
            return items()
        if isinstance(items, PipeTransform):
            return items
        raise TypeError(f"ParseArrayPipe(items=...) must be int/float/bool or a pipe, got {items!r}")

    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if self._skip(value):
            return value
        if isinstance(value, str):
            value = [part.strip() for part in value.split(self._separator)] if value else []
        if not isinstance(value, list | tuple):
            self._fail("Validation failed (array string is expected)")
        if self._item_pipe is None:
            return list(value)
        return [self._item_pipe.transform(item, metadata) for item in value]


class DefaultValuePipe(PipeTransform):
    """Substitutes ``default`` when the value is missing (``None``) -- put it before a Parse pipe."""

    def __init__(self, default: Any) -> None:
        self._default = default

    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if value is None or (isinstance(value, float) and math.isnan(value)):
            return self._default
        return value
