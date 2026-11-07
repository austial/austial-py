"""``@UseGuards()`` -- mirrors ``@nestjs/common``. Applicable to controllers or handlers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.core.metadata import GUARDS_METADATA, get_metadata, set_metadata


def UseGuards(*guards: Any) -> Callable:
    """Attaches one or more ``CanActivate`` guards (classes or instances) to a
    controller or a single route handler. Stacks across repeated calls."""

    def decorator(target):
        existing = list(get_metadata(GUARDS_METADATA, target, []))
        set_metadata(GUARDS_METADATA, existing + list(guards))(target)
        return target

    return decorator
