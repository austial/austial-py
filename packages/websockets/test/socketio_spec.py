from __future__ import annotations

import asyncio
import socket
from contextlib import asynccontextmanager

import pytest
import socketio
import uvicorn

from austial import AustialFactory, Injectable, Module
from austial.websockets import (
    ConnectedSocket,
    MessageBody,
    SocketIoAdapter,
    SubscribeMessage,
    WebSocketGateway,
    WebSocketsModule,
    WsClient,
    WsException,
    WsResponse,
    WsServer,
)

LOG: list[str] = []


@WebSocketGateway("/chat")
@Injectable()
class SioGateway:
    server: WsServer

    async def handle_connection(self, client: WsClient) -> None:
        LOG.append("connect")
        if client.data.get("auth") == "deny":
            await client.close()
            return
        await client.send("welcome", {"ok": True})

    def handle_disconnect(self, client: WsClient) -> None:
        LOG.append("disconnect")

    @SubscribeMessage("greet")
    def greet(self, name: str = MessageBody("name")):
        return f"hello {name}"  # acknowledgement

    @SubscribeMessage("rename")
    def rename(self, name: str = MessageBody("name")):
        return WsResponse("renamed", {"name": name})

    @SubscribeMessage("join")
    async def join(self, room: str = MessageBody("room"), client: WsClient = ConnectedSocket()):
        await client.join(room)
        await self.server.to(room).emit("joined", {"room": room})

    @SubscribeMessage("denied")
    def denied(self):
        raise WsException("not allowed")

    @SubscribeMessage("boom")
    def boom(self):
        raise RuntimeError("bug")


@Module(imports=[WebSocketsModule.for_root(adapter=SocketIoAdapter())], providers=[SioGateway])
class SioApp:
    pass


@asynccontextmanager
async def running_server():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    config = uvicorn.Config(AustialFactory.create(SioApp), host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    task = asyncio.create_task(server.serve())
    while not server.started:
        await asyncio.sleep(0.02)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def connect(url: str, **kwargs) -> socketio.AsyncClient:
    sio = socketio.AsyncClient()
    await sio.connect(url, namespaces=["/chat"], wait_timeout=5, **kwargs)
    return sio


async def wait_for(box: list, count: int = 1) -> None:
    for _ in range(200):
        if len(box) >= count:
            return
        await asyncio.sleep(0.02)
    raise AssertionError("timed out waiting for event")


async def test_events_acknowledgements_and_rooms():
    async with running_server() as url:
        a, b = await connect(url), await connect(url)
        got: list = []
        a.on("welcome", lambda data: got.append(("welcome", data)), namespace="/chat")
        a.on("renamed", lambda data: got.append(("renamed", data)), namespace="/chat")
        b.on("joined", lambda data: got.append(("b-joined", data)), namespace="/chat")

        ack = await a.call("greet", {"name": "ada"}, namespace="/chat", timeout=5)
        assert ack == "hello ada"

        await a.emit("rename", {"name": "x"}, namespace="/chat")
        await wait_for(got)
        assert ("renamed", {"name": "x"}) in got

        await b.call("join", {"room": "r1"}, namespace="/chat", timeout=5)
        await wait_for(got, 2)
        assert ("b-joined", {"room": "r1"}) in got

        await a.disconnect()
        await b.disconnect()
        await asyncio.sleep(0.2)
    assert LOG.count("connect") >= 2 and "disconnect" in LOG


async def test_errors_are_events_not_dropped_connections():
    async with running_server() as url:
        c = await connect(url)
        events: list = []
        c.on("exception", lambda data: events.append(data), namespace="/chat")
        await c.emit("denied", namespace="/chat")
        await c.emit("boom", namespace="/chat")
        await wait_for(events, 2)
        assert events[0]["message"] == "not allowed"
        assert events[1]["message"] == "Internal server error"
        assert c.connected
        await c.disconnect()


async def test_connection_can_be_rejected():
    async with running_server() as url:
        sio = socketio.AsyncClient()
        with pytest.raises(socketio.exceptions.ConnectionError):
            await sio.connect(url, namespaces=["/chat"], auth="deny", wait_timeout=5)
