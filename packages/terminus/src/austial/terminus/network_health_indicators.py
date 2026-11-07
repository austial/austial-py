"""More ``@nestjs/terminus`` indicators: ``HttpHealthIndicator``, ``TcpHealthIndicator`` (Nest's
``MicroserviceHealthIndicator``), ``DiskHealthIndicator`` and ``MongoHealthIndicator``."""

from __future__ import annotations

import asyncio
import shutil
from typing import Any

import httpx

from austial.common.decorators.injectable import Injectable
from austial.terminus.health_indicator import HealthCheckError, HealthIndicator, HealthIndicatorResult


@Injectable()
class HttpHealthIndicator(HealthIndicator):
    async def ping_check(
        self,
        key: str,
        url: str,
        *,
        timeout: float = 1.5,
        expected_status: int | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> HealthIndicatorResult:
        """Healthy if ``url`` answers with a 2xx/3xx (or exactly ``expected_status``) within ``timeout`` seconds."""
        try:
            async with httpx.AsyncClient(timeout=timeout, transport=transport) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise HealthCheckError(
                f"{key} is not reachable", self.get_status(key, False, {"message": f"{type(exc).__name__}: {exc}"})
            ) from exc
        ok = response.status_code == expected_status if expected_status is not None else response.status_code < 400
        result = self.get_status(key, ok, {"status_code": response.status_code})
        if not ok:
            raise HealthCheckError(f"{key} answered {response.status_code}", result)
        return result


@Injectable()
class TcpHealthIndicator(HealthIndicator):
    """Healthy if a TCP connection to ``host:port`` opens in time (databases, brokers, TCP microservices)."""

    async def ping_check(self, key: str, host: str, port: int, *, timeout: float = 1.5) -> HealthIndicatorResult:
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(host, port), timeout)
        except (TimeoutError, OSError) as exc:
            raise HealthCheckError(
                f"{key} is not reachable",
                self.get_status(key, False, {"message": f"{type(exc).__name__}: {exc}", "host": host, "port": port}),
            ) from exc
        writer.close()
        return self.get_status(key, True, {"host": host, "port": port})


@Injectable()
class DiskHealthIndicator(HealthIndicator):
    async def check_storage(
        self,
        key: str,
        path: str,
        *,
        threshold_percent: float | None = None,
        threshold_free_bytes: int | None = None,
    ) -> HealthIndicatorResult:
        """Unhealthy if more than ``threshold_percent`` (0-1, e.g. ``0.9``) of the disk holding ``path`` is used, or
        if fewer than ``threshold_free_bytes`` remain. At least one threshold is required."""
        if threshold_percent is None and threshold_free_bytes is None:
            raise ValueError("check_storage needs threshold_percent and/or threshold_free_bytes")
        usage = shutil.disk_usage(path)
        used_fraction = usage.used / usage.total if usage.total else 1.0
        healthy = (threshold_percent is None or used_fraction <= threshold_percent) and (
            threshold_free_bytes is None or usage.free >= threshold_free_bytes
        )
        result = self.get_status(
            key,
            healthy,
            {"used_fraction": round(used_fraction, 4), "free_bytes": usage.free, "total_bytes": usage.total},
        )
        if not healthy:
            raise HealthCheckError("Disk usage exceeded the threshold", result)
        return result


@Injectable()
class MongoHealthIndicator(HealthIndicator):
    async def ping_check(self, key: str, client: Any, *, timeout: float = 1.5) -> HealthIndicatorResult:
        """Healthy if ``client.admin.command("ping")`` (a PyMongo async client) answers within ``timeout`` seconds."""
        try:
            await asyncio.wait_for(client.admin.command("ping"), timeout)
        except Exception as exc:  # noqa: BLE001
            raise HealthCheckError(
                "MongoDB health check failed", self.get_status(key, False, {"message": f"{type(exc).__name__}: {exc}"})
            ) from exc
        return self.get_status(key, True)
