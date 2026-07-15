"""``@UseFilters()`` / ``@Catch()`` -- mirrors ``@nestjs/common``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.core.metadata import CATCH_METADATA, FILTERS_METADATA, get_metadata, set_metadata


def UseFilters(*filters: Any) -> Callable:
    """Attaches one or more ``ExceptionFilter``s (classes or instances) to a
    controller or a single route handler."""

    def decorator(target):
        existing = list(get_metadata(FILTERS_METADATA, target, []))
        set_metadata(FILTERS_METADATA, existing + list(filters))(target)
        return target

    return decorator


def Catch(*exceptions: type[BaseException]) -> Callable:
    """Class decorator declaring which exception types a filter handles.
    An empty call (``@Catch()``) catches everything, mirroring Nest."""

    def decorator(cls):
        set_metadata(CATCH_METADATA, tuple(exceptions))(cls)
        return cls

    return decorator
