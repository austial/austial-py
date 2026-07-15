"""``@Injectable()`` and ``@Inject(token)`` -- mirrors ``@nestjs/common``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from austial.common.enums import Scope
from austial.core.metadata import INJECTABLE_METADATA, set_metadata

T = TypeVar("T")


def Injectable(scope: Scope = Scope.DEFAULT) -> Callable[[T], T]:
    """Marks a class as a provider that the DI container can construct.

    Usable as ``@Injectable()`` or ``@Injectable(scope=Scope.TRANSIENT)``,
    exactly like Nest.
    """

    def decorator(cls: T) -> T:
        set_metadata(INJECTABLE_METADATA, {"scope": scope})(cls)
        return cls

    return decorator


def Inject(token: Any):
    """Parameter-level marker for constructor injection by *token* rather than
    by type. Mirrors Nest's ``@Inject(TOKEN)``.

    Usage::

        class CatsService:
            def __init__(self, @Inject("CATS_CONFIG") config: dict): ...

    Python has no parameter decorators, so instead this is used as a *default
    value* combined with a type-hint-less parameter, e.g.::

        class CatsService:
            def __init__(self, config = Inject("CATS_CONFIG")): ...

    The container recognises :class:`InjectMarker` sentinels returned here and
    resolves them by token instead of by annotation type.
    """
    return InjectMarker(token)


class InjectMarker:
    __slots__ = ("token",)

    def __init__(self, token: Any):
        self.token = token

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"InjectMarker({self.token!r})"


def Optional_() -> OptionalMarker:  # noqa: N802 - mirrors Nest's @Optional()
    return OptionalMarker()


class OptionalMarker:
    """Marks a constructor param as optional; unresolved deps become ``None``
    instead of raising, mirroring Nest's ``@Optional()``."""

    def __repr__(self) -> str:  # pragma: no cover
        return "OptionalMarker()"
