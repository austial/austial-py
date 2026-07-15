"""``HealthCheckService`` -- mirrors ``@nestjs/terminus``'s ``HealthCheckService``.

Usage, identical in shape to real Nest/Terminus code::

    result = await self.health_check_service.check([
        lambda: self.memory.check_heap("memory_heap", 300 * 1024 * 1024),
        lambda: self.database.ping_check("database"),
    ])
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from austial.common.decorators.injectable import Injectable
from austial.terminus.health_indicator import HealthCheckError, HealthIndicatorResult

HealthIndicatorFunction = Callable[[], Awaitable[HealthIndicatorResult]]


@Injectable()
class HealthCheckService:
    async def check(self, indicators: list[HealthIndicatorFunction]) -> dict:
        info: HealthIndicatorResult = {}
        error: HealthIndicatorResult = {}
        details: HealthIndicatorResult = {}

        for indicator in indicators:
            try:
                result = await indicator()
                info.update(result)
                details.update(result)
            except HealthCheckError as exc:
                error.update(exc.causes)
                details.update(exc.causes)
            except Exception as exc:  # noqa: BLE001 - an indicator blew up unexpectedly
                failure = {"unknown": {"status": "down", "message": str(exc)}}
                error.update(failure)
                details.update(failure)

        status = "error" if error else "ok"
        return {"status": status, "info": info, "error": error, "details": details}
