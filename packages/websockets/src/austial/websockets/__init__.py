"""``austial.websockets`` -- WebSocket gateways, mirrors ``@nestjs/websockets``.

from austial.websockets import (
    WebSocketsModule, WebSocketGateway, SubscribeMessage, MessageBody, ConnectedSocket, WsClient, WsServer,
)
"""

from austial.websockets.decorators import (
    ConnectedSocket,
    MessageBody,
    OnGatewayConnection,
    OnGatewayDisconnect,
    OnGatewayInit,
    SubscribeMessage,
    WebSocketGateway,
)
from austial.websockets.gateway_runner import GatewayRunner
from austial.websockets.socketio_adapter import SocketIoAdapter, SocketIoClient, SocketIoServer
from austial.websockets.types import WsArgumentsHost, WsClient, WsException, WsExecutionContext, WsResponse, WsServer
from austial.websockets.websockets_module import WebSocketsModule

__all__ = [
    "ConnectedSocket",
    "GatewayRunner",
    "MessageBody",
    "OnGatewayConnection",
    "OnGatewayDisconnect",
    "OnGatewayInit",
    "SubscribeMessage",
    "SocketIoAdapter",
    "SocketIoClient",
    "SocketIoServer",
    "WebSocketGateway",
    "WebSocketsModule",
    "WsArgumentsHost",
    "WsClient",
    "WsException",
    "WsExecutionContext",
    "WsResponse",
    "WsServer",
]
