"""Reflector: the public, Nest-shaped API for reading decorator metadata back out."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from austial.core.metadata import get_metadata


class Reflector:
    """Mirrors ``@nestjs/core``'s ``Reflector``.

    Usable as an injectable (constructor-injected into guards/interceptors)
    or via its static helpers.
    """

    def get(self, key: str, target: Any, default: Any = None) -> Any:
        return get_metadata(key, target, default)

    def get_all_and_merge(self, key: str, targets: Sequence[Any]) -> list:
        """Merges array-valued metadata (e.g. guards/interceptors) across
        class + method, matching Nest's ``getAllAndMerge``."""
        merged: list = []
        for target in targets:
            value = get_metadata(key, target, [])
            if value:
                merged.extend(value)
        return merged

    def get_all_and_override(self, key: str, targets: Sequence[Any]) -> Any:
        """Returns the first non-empty metadata value found, method before
        class, matching Nest's ``getAllAndOverride``."""
        for target in targets:
            value = get_metadata(key, target, None)
            if value is not None:
                return value
        return None
