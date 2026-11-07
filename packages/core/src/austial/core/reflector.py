"""Reflector: the public, Nest-shaped API for reading decorator metadata back out."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Sequence
from typing import Any

from austial.core.metadata import get_metadata, set_metadata

_decorator_ids = itertools.count(1)


class Reflector:
    """Mirrors ``@nestjs/core``'s ``Reflector``.

    Usable as an injectable (constructor-injected into guards/interceptors)
    or via its static helpers.
    """

    @staticmethod
    def create_decorator(*, key: str | None = None, transform: Callable[[Any], Any] | None = None) -> Any:
        """Mirrors ``Reflector.createDecorator()``: builds a typed decorator *and* its metadata key in one go.

        ::

            Roles = Reflector.create_decorator()

            @Roles(["admin"])
            async def delete(self): ...

            roles = reflector.get(Roles, context.get_handler())     # ["admin"]

        ``Roles(value=True)`` stamps ``value`` (run through ``transform`` if given); ``Roles.KEY`` is the key.
        """
        metadata_key = key or f"austial:reflector:{next(_decorator_ids)}"

        def decorator(value: Any = True) -> Callable[[Any], Any]:
            return set_metadata(metadata_key, transform(value) if transform else value)

        decorator.KEY = metadata_key  # type: ignore[attr-defined]  # the key travels with the decorator
        return decorator

    @staticmethod
    def _key(key: Any) -> str:
        return key.KEY if hasattr(key, "KEY") else key

    def get(self, key: Any, target: Any, default: Any = None) -> Any:
        return get_metadata(self._key(key), target, default)

    def get_all_and_merge(self, key: Any, targets: Sequence[Any]) -> list:
        """Merges array-valued metadata (e.g. guards/interceptors) across
        class + method, matching Nest's ``getAllAndMerge``."""
        merged: list = []
        for target in targets:
            value = get_metadata(self._key(key), target, [])
            if value:
                merged.extend(value)
        return merged

    def get_all_and_override(self, key: Any, targets: Sequence[Any]) -> Any:
        """Returns the first non-empty metadata value found, method before
        class, matching Nest's ``getAllAndOverride``."""
        for target in targets:
            value = get_metadata(self._key(key), target, None)
            if value is not None:
                return value
        return None
