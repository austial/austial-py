"""``DatabaseHealthIndicator`` -- mirrors ``@nestjs/terminus``'s ``TypeOrmHealthIndicator``."""

from __future__ import annotations

from austial.common.decorators.injectable import Injectable
from austial.orm.data_source import DataSource
from austial.terminus.health_indicator import HealthCheckError, HealthIndicator, HealthIndicatorResult


@Injectable()
class DatabaseHealthIndicator(HealthIndicator):
    def __init__(self, data_source: DataSource):
        self._data_source = data_source

    async def ping_check(self, key: str) -> HealthIndicatorResult:
        try:
            # `execute_raw` is `Driver`'s escape hatch for callers that need raw SQL outside the
            # entity-centric API -- still goes through parameterized bind params, never string
            # formatting, even though this particular query has no params.
            await self._data_source.driver.execute_raw("SELECT 1")
            return self.get_status(key, True)
        except Exception as exc:  # noqa: BLE001
            result = self.get_status(key, False, {"message": str(exc)})
            raise HealthCheckError("Database health check failed", result) from exc
