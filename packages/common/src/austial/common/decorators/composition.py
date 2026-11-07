"""``apply_decorators`` -- mirrors ``@nestjs/common``'s ``applyDecorators``: bundle several
decorators into one reusable decorator::

    def Auth(*roles):
        return apply_decorators(UseGuards(AuthGuard, RolesGuard), Roles(*roles))

    @Get("admin")
    @Auth("admin")
    async def admin_only(self): ...
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


def apply_decorators(*decorators: Callable[[Any], Any]) -> Callable[[Any], Any]:
    def decorator(target: Any) -> Any:
        # Applied left to right: `apply_decorators(a, b)` runs `a` first, then `b`.
        for inner in decorators:
            result = inner(target)
            if result is not None:
                target = result
        return target

    return decorator
