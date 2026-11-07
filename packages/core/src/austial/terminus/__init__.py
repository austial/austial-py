from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from austial.orm.database_health_indicator import DatabaseHealthIndicator
from austial.terminus.health_check_service import HealthCheckService, HealthIndicatorFunction
from austial.terminus.health_indicator import HealthCheckError, HealthIndicator, HealthIndicatorResult
from austial.terminus.memory_health_indicator import MemoryHealthIndicator
from austial.terminus.network_health_indicators import (
    DiskHealthIndicator,
    HttpHealthIndicator,
    MongoHealthIndicator,
    TcpHealthIndicator,
)

__all__ = [
    "DatabaseHealthIndicator",
    "DiskHealthIndicator",
    "HttpHealthIndicator",
    "MongoHealthIndicator",
    "TcpHealthIndicator",
    "HealthCheckService",
    "HealthIndicatorFunction",
    "HealthCheckError",
    "HealthIndicator",
    "HealthIndicatorResult",
    "MemoryHealthIndicator",
]


def __getattr__(name: str) -> Any:
    # DatabaseHealthIndicator lives in austial-orm; imported only when asked for, so health checks work without it.
    if name == "DatabaseHealthIndicator":
        from austial.orm.database_health_indicator import DatabaseHealthIndicator

        return DatabaseHealthIndicator
    raise AttributeError(f"module 'austial.terminus' has no attribute {name!r}")
