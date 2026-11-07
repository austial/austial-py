"""Response serialization -- mirrors ``ClassSerializerInterceptor`` with ``@Exclude()`` /
``@Expose()`` / ``@SerializeOptions()`` from ``class-transformer``.

Python has no property decorators, so the field-level markers are *class* decorators naming
fields::

    @Exclude("password_hash")
    class User(BaseModel):
        id: int
        email: str
        password_hash: str

    @Controller("users")
    @UseInterceptors(ClassSerializerInterceptor())
    class UsersController:
        @Get(":id")
        async def find_one(self, id: int) -> User: ...        # password_hash never leaves the server

Strategy ``"exclude_all"`` flips the default: only ``@Expose``d fields are sent, optionally only
to callers in matching ``groups`` (``@Expose("email", groups=["admin"])`` + handler
``@SerializeOptions(groups=["admin"])``). Works on pydantic models, dataclasses and plain objects,
nested anywhere in lists/dicts.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Sequence
from enum import Enum
from typing import Any

from pydantic import BaseModel
from starlette.responses import Response

from austial.common.file.streamable_file import StreamableFile
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler, NestInterceptor
from austial.core.metadata import SERIALIZE_OPTIONS_METADATA, get_metadata, set_metadata

_POLICY_ATTR = "__austial_serialize__"
EXPOSE_ALL = "expose_all"
EXCLUDE_ALL = "exclude_all"


def _policy_of(cls: type) -> dict[str, Any]:
    policy = cls.__dict__.get(_POLICY_ATTR)
    if policy is None:
        policy = {"exclude": set(), "expose": {}}
        setattr(cls, _POLICY_ATTR, policy)
    return policy


def Exclude(*fields: str) -> Callable[[type], type]:  # noqa: N802 - mirrors class-transformer
    """Class decorator: ``fields`` are never serialized."""

    def decorator(cls: type) -> type:
        _policy_of(cls)["exclude"].update(fields)
        return cls

    return decorator


def Expose(*fields: str, groups: Sequence[str] | None = None) -> Callable[[type], type]:  # noqa: N802
    """Class decorator: ``fields`` are serialized (needed under ``"exclude_all"``). With ``groups``
    they're sent only when one of those groups is active via ``@SerializeOptions(groups=...)``."""

    def decorator(cls: type) -> type:
        expose = _policy_of(cls)["expose"]
        for name in fields:
            expose[name] = None if groups is None else set(groups)
        return cls

    return decorator


def SerializeOptions(*, strategy: str | None = None, groups: Sequence[str] | None = None) -> Callable:  # noqa: N802
    """Class/method decorator choosing the strategy and active groups for what the handler returns."""

    def decorator(target: Any) -> Any:
        set_metadata(SERIALIZE_OPTIONS_METADATA, {"strategy": strategy, "groups": list(groups or [])})(target)
        return target

    return decorator


def _collect_policy(cls: type) -> tuple[set[str], dict[str, set[str] | None]]:
    exclude: set[str] = set()
    expose: dict[str, set[str] | None] = {}
    for klass in reversed(cls.__mro__):
        policy = klass.__dict__.get(_POLICY_ATTR)
        if policy:
            exclude |= policy["exclude"]
            expose.update(policy["expose"])
    return exclude, expose


def _visible(name: str, exclude: set[str], expose: dict, strategy: str, groups: set[str]) -> bool:
    if name in exclude:
        return False
    if name in expose:
        required = expose[name]
        return required is None or bool(required & groups)
    return strategy != EXCLUDE_ALL


def serialize(value: Any, *, strategy: str = EXPOSE_ALL, groups: Iterable[str] = ()) -> Any:
    """Recursively turns ``value`` into JSON-ready data, applying ``@Exclude``/``@Expose``."""
    active = set(groups)

    def walk(obj: Any) -> Any:
        if obj is None or isinstance(obj, str | int | float | bool | bytes | Enum | Response | StreamableFile):
            return obj
        if isinstance(obj, list | tuple | set | frozenset):
            return [walk(item) for item in obj]
        if isinstance(obj, dict):
            return {key: walk(item) for key, item in obj.items()}
        if isinstance(obj, BaseModel):
            return walk_fields(obj, _pydantic_fields(obj))
        if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
            return walk_fields(obj, [(f.name, f.name) for f in dataclasses.fields(obj)])
        if hasattr(obj, "__dict__") and not isinstance(obj, type) and type(obj).__module__ != "builtins":
            return walk_fields(obj, [(n, n) for n in vars(obj) if not n.startswith("_")])
        return obj  # enums, datetimes, UUIDs, Decimals... left for FastAPI's encoder

    def walk_fields(obj: Any, fields: list[tuple[str, str]]) -> dict[str, Any]:
        exclude, expose = _collect_policy(type(obj))
        return {
            key: walk(getattr(obj, name)) for name, key in fields if _visible(name, exclude, expose, strategy, active)
        }

    return walk(value)


def _pydantic_fields(model: BaseModel) -> list[tuple[str, str]]:
    fields = []
    for name, info in type(model).model_fields.items():
        if info.exclude:
            continue
        fields.append((name, info.serialization_alias or info.alias or name))
    return fields


class ClassSerializerInterceptor(NestInterceptor):
    def __init__(self, *, strategy: str = EXPOSE_ALL, groups: Sequence[str] | None = None) -> None:
        self._strategy = strategy
        self._groups = list(groups or [])

    async def intercept(self, context: ExecutionContext, next: CallHandler) -> Any:
        result = await next.handle()
        strategy, groups = self._strategy, list(self._groups)
        for target in (context.get_class(), context.get_handler()):
            options = get_metadata(SERIALIZE_OPTIONS_METADATA, target)
            if options:
                strategy = options["strategy"] or strategy
                groups = options["groups"] or groups
        return serialize(result, strategy=strategy, groups=groups)
