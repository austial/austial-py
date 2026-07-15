"""``DatabaseHealthIndicator`` -- mirrors ``@nestjs/terminus``'s ``TypeOrmHealthIndicator``."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from austial.common.decorators.injectable import Inject, Injectable
from austial.database.database_module import DATABASE_SESSION_FACTORY
from austial.terminus.health_indicator import HealthCheckError, HealthIndicator, HealthIndicatorResult


@Injectable()
class DatabaseHealthIndicator(HealthIndicator):
    def __init__(self, session_factory: Any = Inject(DATABASE_SESSION_FACTORY)):
        self._session_factory = session_factory

    async def ping_check(self, key: str) -> HealthIndicatorResult:
        try:
            async with self._session_factory() as session:
                await session.execute(text("SELECT 1"))
            return self.get_status(key, True)
        except Exception as exc:  # noqa: BLE001
            result = self.get_status(key, False, {"message": str(exc)})
            raise HealthCheckError("Database health check failed", result) from exc
