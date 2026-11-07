"""Helpers for live tests: a real uvicorn server on a real TCP port, driven by real HTTP/WebSocket clients."""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@asynccontextmanager
async def serve(app: Any, port: int | None = None, **config: Any) -> AsyncIterator[str]:
    """Runs ``app`` under uvicorn (lifespan on, so startup and shutdown hooks run) and yields its base URL."""
    port = port or free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", **config))
    task = asyncio.create_task(server.serve())
    for _ in range(200):
        if server.started or task.done():
            break
        await asyncio.sleep(0.02)
    if not server.started:
        task.cancel()
        raise RuntimeError("the server did not start")
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def wait_until(condition: Any, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while not condition():
        if asyncio.get_running_loop().time() > deadline:
            raise AssertionError("condition never became true")
        await asyncio.sleep(0.02)
