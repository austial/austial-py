from __future__ import annotations

import pytest
from starlette.testclient import TestClient

from austial import (
    AustialFactory,
    CanActivate,
    ExecutionContext,
    Injectable,
    Module,
    NestInterceptor,
    ParseIntPipe,
    UseGuards,
    UseInterceptors,
    UsePipes,
)
from austial.common.exceptions import ForbiddenException
from austial.websockets import (
    ConnectedSocket,
    MessageBody,
    OnGatewayConnection,
    OnGatewayDisconnect,
    SubscribeMessage,
    WebSocketGateway,
    WebSocketsModule,
    WsClient,
    WsException,
    WsResponse,
    WsServer,
)

EVENTS: list[str] = []


class TokenGuard(CanActivate):
    async def can_activate(self, context: ExecutionContext) -> bool:
        assert context.get_type() == "ws"
        with pytest.raises(NotImplementedError):
            context.switch_to_http()
        client = context.switch_to_ws().get_client()
        return client.query_params.get("token") == "ok" and context.get_request() is client.websocket


class Tag(NestInterceptor):
    async def intercept(self, context, next):
        result = await next.handle()
        return {"tagged": result}


@Injectable()
class Greeter:
    def greet(self, name: str) -> str:
        return f"hello {name}"


@WebSocketGateway("/chat")
@Injectable()
class ChatGateway(OnGatewayConnection, OnGatewayDisconnect):
    server: WsServer

    def __init__(self, greeter: Greeter):
        self.greeter = greeter

    async def handle_connection(self, client: WsClient) -> None:
        EVENTS.append("connect")
        await client.send("welcome", {"id_len": len(client.id)})

    def handle_disconnect(self, client: WsClient) -> None:
        EVENTS.append("disconnect")

    @SubscribeMessage("greet")
    async def greet(self, name: str = MessageBody("name")):
        return self.greeter.greet(name)

    @SubscribeMessage("whole")
    def whole(self, data):  # an unmarked first parameter receives the data
        return {"echo": data}

    @SubscribeMessage("rename")
    def rename(self, client: WsClient, name: str = MessageBody("name")):
        client.data["name"] = name
        return WsResponse("renamed", {"name": name})

    @SubscribeMessage("join")
    async def join(self, room: str = MessageBody("room"), client: WsClient = ConnectedSocket()):
        await client.join(room)
        await self.server.to(room).emit("joined", {"room": room, "clients": len(self.server.clients)})

    @SubscribeMessage("shout")
    async def shout(self, text: str = MessageBody("text")):
        await self.server.emit("shout", text)

    @SubscribeMessage("room-say")
    async def room_say(self, room: str = MessageBody("room"), text: str = MessageBody("text")):
        await self.server.to(room).emit("said", text)

    @SubscribeMessage("quiet")
    def quiet(self):
        return None

    @SubscribeMessage("boom")
    def boom(self):
        raise RuntimeError("bug")

    @SubscribeMessage("denied")
    def denied(self):
        raise WsException("not allowed")

    @SubscribeMessage("http-error")
    def http_error(self):
        raise ForbiddenException("nope")

    @SubscribeMessage("number")
    @UsePipes(ParseIntPipe)
    def number(self, n: int = MessageBody("n")):
        return n + 1

    @SubscribeMessage("tagged")
    @UseInterceptors(Tag)
    def tagged(self):
        return "x"


@WebSocketGateway("/private")
@UseGuards(TokenGuard)
@Injectable()
class PrivateGateway:
    @SubscribeMessage("secret")
    def secret(self):
        return "classified"


@Module(imports=[WebSocketsModule.for_root()], providers=[ChatGateway, PrivateGateway, Greeter])
class WsApp:
    pass


def client() -> TestClient:
    return TestClient(AustialFactory.create(WsApp))


def send(ws, event, data=None, **extra):
    ws.send_json({"event": event, "data": data, **extra})
    return ws.receive_json()


def test_connect_message_reply_and_lifecycle_hooks() -> None:
    EVENTS.clear()
    with client() as c, c.websocket_connect("/chat") as ws:
        assert ws.receive_json()["event"] == "welcome"
        assert send(ws, "greet", {"name": "Ada"}) == {"event": "greet", "data": "hello Ada"}
        assert send(ws, "whole", {"a": 1}) == {"event": "whole", "data": {"echo": {"a": 1}}}
        assert send(ws, "rename", {"name": "Bo"}, id=7) == {"event": "renamed", "data": {"name": "Bo"}, "id": 7}
    assert EVENTS == ["connect", "disconnect"]


def test_rooms_and_broadcast_across_clients() -> None:
    with (
        client() as c,
        c.websocket_connect("/chat") as a,
        c.websocket_connect("/chat") as b,
        c.websocket_connect("/chat") as lone,
    ):
        for ws in (a, b, lone):
            ws.receive_json()  # welcome
        assert send(a, "join", {"room": "lobby"}) == {"event": "joined", "data": {"room": "lobby", "clients": 3}}
        assert send(b, "join", {"room": "lobby"})["data"]["room"] == "lobby"
        assert a.receive_json()["event"] == "joined"  # a also hears b joining

        b.send_json({"event": "room-say", "data": {"room": "lobby", "text": "hi"}})
        assert a.receive_json() == {"event": "said", "data": "hi"}
        assert b.receive_json() == {"event": "said", "data": "hi"}

        lone.send_json({"event": "shout", "data": {"text": "everyone"}})
        for ws in (a, b, lone):
            assert ws.receive_json() == {"event": "shout", "data": "everyone"}

        a.send_json({"event": "room-say", "data": {"room": "lobby", "text": "second"}})
        assert b.receive_json()["data"] == "second"  # `lone` (not in the room) hears nothing: next frame is ours
        assert a.receive_json()["data"] == "second"


def test_errors_unknown_events_malformed_frames_and_silent_handlers() -> None:
    with client() as c, c.websocket_connect("/chat") as ws:
        ws.receive_json()
        assert send(ws, "nope", id=1) == {
            "event": "exception",
            "data": {"status": "error", "message": "Unknown event 'nope'"},
            "id": 1,
        }
        ws.send_text("not json")
        assert ws.receive_json()["data"]["message"].startswith("Expected")
        ws.send_text('{"no": "event"}')
        assert ws.receive_json()["event"] == "exception"
        assert send(ws, "denied")["data"] == {"status": "error", "message": "not allowed"}
        assert send(ws, "http-error")["data"]["message"] == "nope"
        assert send(ws, "boom")["data"]["message"] == "Internal server error"  # internals aren't leaked
        ws.send_json({"event": "quiet"})  # None -> no reply; the next answer proves the connection is alive
        assert send(ws, "greet", {"name": "still-here"})["data"] == "hello still-here"


def test_pipes_and_interceptors_apply_to_messages() -> None:
    with client() as c, c.websocket_connect("/chat") as ws:
        ws.receive_json()
        assert send(ws, "number", {"n": "41"})["data"] == 42  # ParseIntPipe on the body field
        assert send(ws, "number", {"n": "x"})["data"]["message"].startswith("Validation failed")
        assert send(ws, "tagged")["data"] == {"tagged": "x"}


def test_guards_see_a_ws_context() -> None:
    with client() as c:
        with c.websocket_connect("/private?token=ok") as ws:
            assert send(ws, "secret")["data"] == "classified"
        with c.websocket_connect("/private?token=bad") as ws:
            assert send(ws, "secret")["data"] == {"status": "error", "message": "Forbidden resource"}


def test_two_gateways_on_one_path_are_rejected() -> None:
    @WebSocketGateway("/dup")
    @Injectable()
    class A: ...

    @WebSocketGateway("/dup")
    @Injectable()
    class B: ...

    @Module(imports=[WebSocketsModule.for_root()], providers=[A, B])
    class Dup:
        pass

    with pytest.raises(RuntimeError, match="both listen on /dup"), TestClient(AustialFactory.create(Dup)):
        pass


async def test_custom_adapters_receive_the_gateway_handlers_and_run_messages_through_the_pipeline() -> None:
    from austial.websockets import WsAdapter

    mounted: dict[str, tuple] = {}

    class Recording(WsAdapter):
        def mount(self, runner, app, path, gateway, handlers):
            mounted[path] = (runner, gateway, handlers)
            return WsServer()

    @Module(imports=[WebSocketsModule.for_root(adapter=Recording())], providers=[ChatGateway, PrivateGateway, Greeter])
    class Custom:
        pass

    app = AustialFactory.create(Custom)
    await app.init()
    assert set(mounted) == {"/chat", "/private"}
    runner, gateway, handlers = mounted["/chat"]
    assert {"greet", "whole", "boom"} <= set(handlers)
    client = WsClient(None, WsServer())  # type: ignore[arg-type]
    assert await runner.process(gateway, handlers["whole"], client, "whole", {"a": 1}) == ("whole", {"echo": {"a": 1}})
    assert await runner.process(gateway, handlers["quiet"], client, "quiet", None) is None
    assert await runner.process(gateway, handlers["denied"], client, "denied", None) == (
        "exception",
        {"status": "error", "message": "not allowed"},
    )
    event, payload = await runner.process(gateway, handlers["boom"], client, "boom", None)
    assert event == "exception" and payload["message"] == "Internal server error"
