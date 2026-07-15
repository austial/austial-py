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
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ValidationError

from austial.common.exceptions.http_exceptions import BadRequestException


@dataclass
class ArgumentMetadata:
    # Field name intentionally mirrors Nest's `ArgumentMetadata.type` -- annotate
    # `metatype` via `builtins.type` to avoid this field shadowing the builtin.
    type: Literal["body", "query", "param", "custom"]
    data: str | None
    metatype: builtins.type | None


class PipeTransform(ABC):
    @abstractmethod
    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        raise NotImplementedError


class ValidationPipe(PipeTransform):
    """Re-validates pydantic-model arguments, raising Nest-shaped
    ``BadRequestException``s on failure -- the workhorse pipe almost every
    Nest app registers globally via ``app.useGlobalPipes(new ValidationPipe())``."""

    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        if isinstance(value, BaseModel):
            try:
                type(value).model_validate(value.model_dump())
            except ValidationError as exc:
                raise BadRequestException(
                    {"message": [str(e["msg"]) for e in exc.errors()], "error": "Bad Request"}
                ) from exc
        return value
