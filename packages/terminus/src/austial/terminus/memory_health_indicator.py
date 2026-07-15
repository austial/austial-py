"""``MemoryHealthIndicator`` -- mirrors ``@nestjs/terminus``'s ``MemoryHealthIndicator``."""

from __future__ import annotations

import resource

from austial.common.decorators.injectable import Injectable
from austial.terminus.health_indicator import HealthCheckError, HealthIndicator, HealthIndicatorResult


@Injectable()
class MemoryHealthIndicator(HealthIndicator):
    async def check_heap(self, key: str, threshold_bytes: int) -> HealthIndicatorResult:
        # ru_maxrss is KB on Linux, bytes on macOS -- close enough for a demo indicator.
        used_bytes = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
        is_healthy = used_bytes < threshold_bytes
        result = self.get_status(key, is_healthy, {"used_bytes": used_bytes, "threshold_bytes": threshold_bytes})
        if not is_healthy:
            raise HealthCheckError("Memory usage exceeded threshold", result)
        return result
