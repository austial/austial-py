"""``MemoryHealthIndicator`` -- mirrors ``@nestjs/terminus``'s ``MemoryHealthIndicator``."""

from __future__ import annotations

import resource
import sys

from austial.common.decorators.injectable import Injectable
from austial.terminus.health_indicator import HealthCheckError, HealthIndicator, HealthIndicatorResult


def _max_rss_bytes() -> int:
    """Peak resident set size in bytes. ``ru_maxrss`` is reported in bytes on macOS
    but in kilobytes on Linux and the BSDs."""
    max_rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return max_rss if sys.platform == "darwin" else max_rss * 1024


@Injectable()
class MemoryHealthIndicator(HealthIndicator):
    async def check_heap(self, key: str, threshold_bytes: int) -> HealthIndicatorResult:
        used_bytes = _max_rss_bytes()
        is_healthy = used_bytes < threshold_bytes
        result = self.get_status(key, is_healthy, {"used_bytes": used_bytes, "threshold_bytes": threshold_bytes})
        if not is_healthy:
            raise HealthCheckError("Memory usage exceeded threshold", result)
        return result
