"""OpenAPI decorators -- mirror ``@nestjs/swagger``. They only add metadata; the router turns it into the
operation's tags, summary, responses and security in FastAPI's generated schema (``/docs``, ``/openapi.json``).

::

    @ApiTags("cats")
    @ApiBearerAuth()
    @Controller("cats")
    class CatsController:
        @Get(":id")
        @ApiOperation(summary="Find one cat", description="Looks a cat up by id.")
        @ApiOkResponse(description="The cat", model=Cat)
        @ApiNotFoundResponse(description="No such cat")
        async def find_one(self, id: int): ...

    class CreateCatDto(BaseModel):
        name: str = ApiProperty(description="The cat's name", example="Tom")
        age: int | None = ApiPropertyOptional(minimum=0)
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from pydantic import Field

from austial.core.metadata import OPENAPI_METADATA, get_metadata, set_metadata


def _stamp(**partial: Any) -> Callable:
    def decorator(target):
        current = dict(get_metadata(OPENAPI_METADATA, target, {}))
        for key, value in partial.items():
            if key in ("tags", "security"):
                current[key] = [*current.get(key, []), *value]
            elif key == "responses":
                current[key] = {**current.get(key, {}), **value}
            else:
                current[key] = value
        set_metadata(OPENAPI_METADATA, current)(target)
        return target

    return decorator


def ApiTags(*tags: str) -> Callable:  # noqa: N802
    """Group the controller's (or one route's) operations under ``tags`` in the docs."""
    return _stamp(tags=list(tags))


def ApiOperation(  # noqa: N802
    *,
    summary: str | None = None,
    description: str | None = None,
    deprecated: bool | None = None,
    operation_id: str | None = None,
) -> Callable:
    fields = {"summary": summary, "description": description, "deprecated": deprecated, "operation_id": operation_id}
    return _stamp(**{k: v for k, v in fields.items() if v is not None})


def ApiResponse(status: int, description: str = "", model: Any = None) -> Callable:  # noqa: N802
    """Document a response. ``model`` is a pydantic model (or ``list[Model]``) describing its body."""
    entry: dict[str, Any] = {"description": description or f"HTTP {status}"}
    if model is not None:
        entry["model"] = model
    return _stamp(responses={status: entry})


def _shortcut(status: int, default: str) -> Callable[..., Callable]:
    def factory(description: str = default, model: Any = None) -> Callable:
        return ApiResponse(status, description, model)

    return factory


ApiOkResponse = _shortcut(200, "OK")
ApiCreatedResponse = _shortcut(201, "Created")
ApiAcceptedResponse = _shortcut(202, "Accepted")
ApiNoContentResponse = _shortcut(204, "No Content")
ApiBadRequestResponse = _shortcut(400, "Bad Request")
ApiUnauthorizedResponse = _shortcut(401, "Unauthorized")
ApiForbiddenResponse = _shortcut(403, "Forbidden")
ApiNotFoundResponse = _shortcut(404, "Not Found")
ApiConflictResponse = _shortcut(409, "Conflict")
ApiUnprocessableEntityResponse = _shortcut(422, "Unprocessable Entity")
ApiTooManyRequestsResponse = _shortcut(429, "Too Many Requests")
ApiInternalServerErrorResponse = _shortcut(500, "Internal Server Error")


def ApiSecurity(name: str, scopes: Sequence[str] = ()) -> Callable:  # noqa: N802
    """Require the security scheme ``name`` (declared with ``DocumentBuilder.add_*_auth``) on these operations."""
    return _stamp(security=[(name, tuple(scopes))])


def ApiBearerAuth(name: str = "bearer") -> Callable:  # noqa: N802
    return ApiSecurity(name)


def ApiBasicAuth(name: str = "basic") -> Callable:  # noqa: N802
    return ApiSecurity(name)


def ApiExcludeEndpoint() -> Callable:  # noqa: N802
    """Hide this route from the generated docs (it still works)."""
    return _stamp(exclude=True)


def ApiExcludeController() -> Callable:  # noqa: N802
    """Hide every route of this controller from the generated docs."""
    return _stamp(exclude=True)


def ApiProperty(default: Any = ..., *, description: str | None = None, example: Any = None, **constraints: Any) -> Any:  # noqa: N802
    """A pydantic ``Field`` with docs metadata: ``description``, ``example`` and any constraint
    (``minimum`` / ``maximum`` / ``min_length`` ...; ``minimum``/``maximum`` map to ``ge``/``le``)."""
    renames = {"minimum": "ge", "maximum": "le", "exclusive_minimum": "gt", "exclusive_maximum": "lt"}
    options = {renames.get(k, k): v for k, v in constraints.items()}
    if example is not None:
        options["examples"] = [example]
    return Field(default, description=description, **options)


def ApiPropertyOptional(default: Any = None, **kwargs: Any) -> Any:  # noqa: N802
    """Like :func:`ApiProperty`, but optional (default ``None``)."""
    return ApiProperty(default, **kwargs)
