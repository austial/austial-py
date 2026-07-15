"""``@UsePipes()`` -- mirrors ``@nestjs/common``."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from austial.core.metadata import PIPES_METADATA, get_metadata, set_metadata


def UsePipes(*pipes: Any) -> Callable:
    """Attaches one or more ``PipeTransform``s (classes or instances) to a
    controller or a single route handler."""

    def decorator(target):
        existing = list(get_metadata(PIPES_METADATA, target, []))
        set_metadata(PIPES_METADATA, existing + list(pipes))(target)
        return target

    return decorator
