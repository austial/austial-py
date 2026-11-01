"""``@InjectRepository(Entity)`` -- mirrors ``@nestjs/typeorm``'s ``@InjectRepository()``.

Reuses ``austial.common``'s ``InjectMarker`` directly rather than inventing a parallel marker
type, so the DI container's existing ``isinstance(default, InjectMarker)`` branch
(``packages/core/src/austial/core/container.py``) resolves it with zero core-package changes::

    @Injectable()
    class CatsService:
        def __init__(self, cats: Repository[Cat] = InjectRepository(Cat)):
            self._cats = cats
"""

from __future__ import annotations

from typing import Any

from austial.common.decorators.injectable import InjectMarker


def repository_token(entity: type) -> str:
    """The DI token a given entity's repository is registered/injected under. Computed the same
    way in ``orm_module.py`` (``OrmModule.for_feature``) and here, so both sides always agree."""
    return f"austial:orm:repository:{entity.__module__}.{entity.__qualname__}"


def InjectRepository(entity: type) -> Any:  # noqa: N802 - decorator-style naming
    """Returns an ``InjectMarker`` at runtime (see ``Container._resolve_constructor_args``), but is
    typed ``Any`` -- like every other param-marker helper (``Body()``, ``Inject()``, ...) -- so it
    can stand as the default for a parameter annotated ``Repository[Cat]`` without mypy flagging an
    ``InjectMarker``/``Repository[Cat]`` mismatch. The annotation is what callers actually get; this
    marker is swapped out for the real repository before the constructor ever runs.
    """
    return InjectMarker(repository_token(entity))
