"""``@UseInterceptors()`` -- mirrors ``@nestjs/common``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.core.metadata import INTERCEPTORS_METADATA, get_metadata, set_metadata


def UseInterceptors(*interceptors: Any) -> Callable:
    """Attaches one or more ``NestInterceptor``s (classes or instances) to a
    controller or a single route handler."""

    def decorator(target):
        existing = list(get_metadata(INTERCEPTORS_METADATA, target, []))
        set_metadata(INTERCEPTORS_METADATA, existing + list(interceptors))(target)
        return target

    return decorator
