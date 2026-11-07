"""Unit test for ``HealthCheckService`` -- the framework's own Terminus-style
health-check aggregator, exercised directly (no consumer app required): this
is a library test, so it builds indicators inline instead of importing a
sample app's ``HealthService``.
"""

from __future__ import annotations

import pytest

from austial.terminus import (
    HealthCheckError,
    HealthCheckService,
    HealthIndicator,
    HealthIndicatorResult,
    MemoryHealthIndicator,
)


@pytest.mark.asyncio
async def test_reports_ok_status_when_all_indicators_pass():
    service = HealthCheckService()
    memory = MemoryHealthIndicator()

    result = await service.check([lambda: memory.check_heap("memory_heap", 1024 * 1024 * 1024)])

    assert result["status"] == "ok"
    assert result["error"] == {}
    assert result["info"]["memory_heap"]["status"] == "up"
    assert result["details"] == result["info"]


@pytest.mark.asyncio
async def test_reports_error_status_when_an_indicator_fails():
    service = HealthCheckService()

    class _AlwaysDownIndicator(HealthIndicator):
        async def ping(self, key: str) -> HealthIndicatorResult:
            raise HealthCheckError("simulated failure", self.get_status(key, False, {"reason": "simulated"}))

    indicator = _AlwaysDownIndicator()

    result = await service.check([lambda: indicator.ping("dependency")], raise_on_error=False)

    assert result["status"] == "error"
    assert result["info"] == {}
    assert result["error"]["dependency"]["status"] == "down"
    assert result["details"] == result["error"]


async def test_an_unhealthy_check_raises_503_with_the_report_by_default() -> None:
    from austial.common.exceptions import ServiceUnavailableException

    class _Down(HealthIndicator):
        async def ping(self, key: str) -> HealthIndicatorResult:
            raise HealthCheckError("down", self.get_status(key, False))

    down = _Down()
    with pytest.raises(ServiceUnavailableException) as caught:
        await HealthCheckService().check([lambda: down.ping("db")])
    assert caught.value.get_status() == 503
    body = caught.value.get_response()
    assert body["status"] == "error" and body["error"]["db"]["status"] == "down"
