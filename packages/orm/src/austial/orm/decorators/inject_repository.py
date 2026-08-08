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

from austial.common.decorators.injectable import InjectMarker


def repository_token(entity: type) -> str:
    """The DI token a given entity's repository is registered/injected under. Computed the same
    way in ``orm_module.py`` (``OrmModule.for_feature``) and here, so both sides always agree."""
    return f"austial:orm:repository:{entity.__module__}.{entity.__qualname__}"


def InjectRepository(entity: type) -> InjectMarker:
    return InjectMarker(repository_token(entity))
