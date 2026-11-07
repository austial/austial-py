"""Base types for health indicators -- mirrors ``@nestjs/terminus``."""

from __future__ import annotations

from typing import Any

HealthIndicatorResult = dict[str, dict[str, Any]]


class HealthCheckError(Exception):
    """Raised by an indicator to signal it's unhealthy; carries the same
    ``HealthIndicatorResult`` shape that a healthy check would have returned."""

    def __init__(self, message: str, causes: HealthIndicatorResult):
        super().__init__(message)
        self.causes = causes


class HealthIndicator:
    """Base class for health indicators. Subclasses expose one or more
    ``async def xxx_check(self, key: str, ...) -> HealthIndicatorResult``
    methods built on top of :meth:`get_status`."""

    def get_status(self, key: str, is_healthy: bool, data: dict | None = None) -> HealthIndicatorResult:
        payload: dict[str, Any] = {"status": "up" if is_healthy else "down"}
        if data:
            payload.update(data)
        return {key: payload}
