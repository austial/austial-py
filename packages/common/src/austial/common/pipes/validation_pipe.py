"""``PipeTransform`` + ``ValidationPipe`` -- mirrors ``@nestjs/common``.

FastAPI/pydantic already parse and validate the request body against a
handler's type hints (that's Austial's equivalent of Nest's ``class-validator``
integration). The pipe pipeline still runs for real on top of that, mirroring
Nest's "pipes transform/validate arguments right before the handler runs":
each resolved argument is passed through ``transform()`` for every pipe in
scope (global -> controller -> route), in order.
"""

from __future__ import annotations

import builtins
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from austial.common.exceptions.http_exceptions import BadRequestException, HttpException


@dataclass
class ArgumentMetadata:
    # Field name intentionally mirrors Nest's `ArgumentMetadata.type` -- annotate
    # `metatype` via `builtins.type` to avoid this field shadowing the builtin.
    type: Literal["body", "query", "param", "custom"]
    data: str | None
    metatype: builtins.type | None
    request: Any = None  # the current Starlette Request, when the pipe runs inside a route


class PipeTransform(ABC):
    @abstractmethod
    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        raise NotImplementedError


class ValidationPipe(PipeTransform):
    """Re-validates pydantic-model arguments, raising Nest-shaped
    ``BadRequestException``s on failure -- the workhorse pipe almost every
    Nest app registers globally via ``app.useGlobalPipes(new ValidationPipe())``.

    Options (all keyword-only, mirroring Nest's):

    * ``whitelist`` -- drop properties the DTO doesn't declare. Pydantic's default (``extra="ignore"``)
      already drops them while parsing; this also strips them from models declared ``extra="allow"``.
    * ``forbid_non_whitelisted`` -- instead of dropping unknown **top-level** body properties, reject the
      request with ``property <name> should not exist``. Needs the raw body, so in this mode
      ``transform()`` returns a coroutine (the router awaits it; await it yourself in a unit test).
    * ``stop_at_first_error`` -- report only the first validation error.
    * ``disable_error_messages`` -- answer with the bare ``Bad Request`` instead of the error list.
    * ``error_http_status_code`` -- status for validation failures (default 400).
    * ``exception_factory`` -- ``errors: list[str] -> Exception`` to raise your own error.

    Nest's ``transform`` option has no equivalent: pydantic always hands the handler a typed model.
    """

    def __init__(
        self,
        *,
        whitelist: bool = False,
        forbid_non_whitelisted: bool = False,
        stop_at_first_error: bool = False,
        disable_error_messages: bool = False,
        error_http_status_code: int = 400,
        exception_factory: Callable[[list[str]], Exception] | None = None,
    ) -> None:
        self._whitelist = whitelist or forbid_non_whitelisted
        self._forbid = forbid_non_whitelisted
        self._stop_at_first = stop_at_first_error
        self._disable_messages = disable_error_messages
        self._status = error_http_status_code
        self._exception_factory = exception_factory

    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if not isinstance(value, BaseModel):
            return value
        if self._forbid and metadata.type == "body" and metadata.request is not None:
            return self._transform_strict(value, metadata)
        return self._validate(value)

    async def _transform_strict(self, value: BaseModel, metadata: ArgumentMetadata) -> BaseModel:
        try:
            raw = await metadata.request.json()
        except ValueError:
            raw = None
        if isinstance(raw, dict):
            known = _known_keys(type(value))
            candidate = raw
            if metadata.data in raw and isinstance(raw[metadata.data], dict) and not (known & raw.keys()):
                candidate = raw[metadata.data]  # an embedded body parameter: {"dto": {...}}
            extras = sorted(set(candidate) - known)
            if extras:
                self._fail([f"property {name} should not exist" for name in extras])
        return self._validate(value)

    def _validate(self, value: BaseModel) -> BaseModel:
        if self._whitelist and value.model_extra:
            value.__pydantic_extra__ = {}
        model = type(value)
        try:
            # Dump by alias first: a model with `Field(alias=...)` only validates from its aliases.
            try:
                model.model_validate(value.model_dump(by_alias=True))
            except ValidationError:
                model.model_validate(value.model_dump())
        except ValidationError as exc:
            self._fail([str(e["msg"]) for e in exc.errors()], cause=exc)
        return value

    def _fail(self, messages: list[str], cause: BaseException | None = None) -> Any:
        if self._stop_at_first:
            messages = messages[:1]
        if self._exception_factory is not None:
            raise self._exception_factory(messages) from cause
        if self._disable_messages:
            raise HttpException(None, self._status) from cause
        if self._status == 400:
            raise BadRequestException({"message": messages, "error": "Bad Request"}) from cause
        raise HttpException({"message": messages}, self._status) from cause


def _known_keys(model: builtins.type[BaseModel]) -> set[str]:
    keys: set[str] = set()
    for name, info in model.model_fields.items():
        keys.add(name)
        for alias in (info.alias, info.validation_alias):
            if isinstance(alias, str):
                keys.add(alias)
    return keys
