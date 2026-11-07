"""``@WebSocketGateway``, ``@SubscribeMessage`` and parameter helpers -- mirror ``@nestjs/websockets``.

::

    @WebSocketGateway("/chat")
    @Injectable()
    class ChatGateway(OnGatewayConnection, OnGatewayDisconnect):
        server: WsServer                      # set by the framework

        async def handle_connection(self, client: WsClient):
            await client.send("welcome", {"id": client.id})

        @SubscribeMessage("message")
        async def on_message(self, text: str = MessageBody("text"), client: WsClient = ConnectedSocket()):
            await self.server.to("lobby").emit("message", {"from": client.id, "text": text})
            return {"delivered": True}         # answered as {"event": "message", "data": {"delivered": true}}

Clients speak JSON text frames: ``{"event": "message", "data": {...}, "id": 1}``; the optional ``id`` is echoed on the
reply so the client can match it up.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from austial.core.metadata import set_metadata

GATEWAY_METADATA = "austial:ws:gateway"
SUBSCRIBE_METADATA = "austial:ws:subscribe"


@dataclass(frozen=True)
class GatewayOptions:
    path: str = "/"


def WebSocketGateway(path: str = "/") -> Callable:  # noqa: N802
    """Class decorator: this provider serves a WebSocket endpoint at ``path`` (list it in a module's ``providers``)."""
    return set_metadata(GATEWAY_METADATA, GatewayOptions(path="/" + path.strip("/") if path.strip("/") else "/"))


def SubscribeMessage(event: str) -> Callable:  # noqa: N802
    """Method decorator: handle messages whose ``event`` is ``event``."""
    return set_metadata(SUBSCRIBE_METADATA, event)


class MessageBodyMarker:
    def __init__(self, key: str | None, pipes: tuple):
        self.key, self.pipes = key, pipes


class ConnectedSocketMarker:
    pass


def MessageBody(key: str | None = None, *pipes: Any) -> Any:  # noqa: N802
    """The message ``data`` (or, with ``key``, one field of it), optionally run through ``pipes``."""
    return MessageBodyMarker(key, pipes)


def ConnectedSocket() -> Any:  # noqa: N802
    """The :class:`WsClient` that sent the message."""
    return ConnectedSocketMarker()


class OnGatewayInit:
    def after_init(self, server: Any) -> Any: ...


class OnGatewayConnection:
    def handle_connection(self, client: Any) -> Any: ...


class OnGatewayDisconnect:
    def handle_disconnect(self, client: Any) -> Any: ...
