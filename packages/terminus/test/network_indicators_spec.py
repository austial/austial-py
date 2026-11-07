from __future__ import annotations

import asyncio
import socket
from types import SimpleNamespace

import httpx
import pytest

from austial.terminus import (
    DiskHealthIndicator,
    HealthCheckError,
    HealthCheckService,
    HttpHealthIndicator,
    MongoHealthIndicator,
    TcpHealthIndicator,
)


def mock(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


async def test_http_ping_check_statuses_and_errors() -> None:
    http = HttpHealthIndicator()
    ok = await http.ping_check("api", "http://x/health", transport=mock(lambda r: httpx.Response(200)))
    assert ok == {"api": {"status": "up", "status_code": 200}}
    redirect = await http.ping_check("api", "http://x", transport=mock(lambda r: httpx.Response(302)))
    assert redirect["api"]["status"] == "up"

    with pytest.raises(HealthCheckError) as caught:
        await http.ping_check("api", "http://x", transport=mock(lambda r: httpx.Response(503)))
    assert caught.value.causes["api"] == {"status": "down", "status_code": 503}

    exact = await http.ping_check("api", "http://x", expected_status=404, transport=mock(lambda r: httpx.Response(404)))
    assert exact["api"]["status"] == "up"
    with pytest.raises(HealthCheckError):
        await http.ping_check("api", "http://x", expected_status=200, transport=mock(lambda r: httpx.Response(201)))

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(HealthCheckError) as unreachable:
        await http.ping_check("api", "http://x", transport=mock(refuse))
    assert "ConnectError" in unreachable.value.causes["api"]["message"]


async def test_tcp_ping_check() -> None:
    server = await asyncio.start_server(lambda r, w: w.close(), "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        tcp = TcpHealthIndicator()
        assert (await tcp.ping_check("broker", "127.0.0.1", port))["broker"] == {
            "status": "up",
            "host": "127.0.0.1",
            "port": port,
        }
    finally:
        server.close()
        await server.wait_closed()

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        closed_port = sock.getsockname()[1]
    with pytest.raises(HealthCheckError) as caught:
        await TcpHealthIndicator().ping_check("broker", "127.0.0.1", closed_port, timeout=0.5)
    assert caught.value.causes["broker"]["status"] == "down" and caught.value.causes["broker"]["port"] == closed_port


async def test_disk_check_storage_thresholds(tmp_path) -> None:
    disk = DiskHealthIndicator()
    result = await disk.check_storage("disk", str(tmp_path), threshold_percent=1.0)
    assert result["disk"]["status"] == "up" and result["disk"]["total_bytes"] > 0

    with pytest.raises(HealthCheckError) as too_full:
        await disk.check_storage("disk", str(tmp_path), threshold_percent=0.0)
    assert too_full.value.causes["disk"]["status"] == "down"
    with pytest.raises(HealthCheckError):
        await disk.check_storage("disk", str(tmp_path), threshold_free_bytes=10**18)
    assert (await disk.check_storage("disk", str(tmp_path), threshold_free_bytes=1))["disk"]["status"] == "up"
    with pytest.raises(ValueError, match="threshold"):
        await disk.check_storage("disk", str(tmp_path))


async def test_mongo_ping_check() -> None:
    async def ok(name):
        return {"ok": 1}

    async def hang(name):
        await asyncio.sleep(5)

    async def broken(name):
        raise ConnectionError("down")

    mongo = MongoHealthIndicator()
    assert (await mongo.ping_check("mongo", SimpleNamespace(admin=SimpleNamespace(command=ok))))["mongo"][
        "status"
    ] == "up"
    for command in (broken, hang):
        with pytest.raises(HealthCheckError) as caught:
            await mongo.ping_check("mongo", SimpleNamespace(admin=SimpleNamespace(command=command)), timeout=0.05)
        assert caught.value.causes["mongo"]["status"] == "down"


async def test_new_indicators_compose_with_the_health_check_service() -> None:
    http, disk = HttpHealthIndicator(), DiskHealthIndicator()
    report = await HealthCheckService().check(
        [
            lambda: http.ping_check("upstream", "http://x", transport=mock(lambda r: httpx.Response(500))),
            lambda: disk.check_storage("disk", ".", threshold_percent=1.0),
        ],
        raise_on_error=False,
    )
    assert report["status"] == "error"
    assert report["error"]["upstream"]["status"] == "down" and report["info"]["disk"]["status"] == "up"
