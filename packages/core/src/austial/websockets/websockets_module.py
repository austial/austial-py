"""``WebSocketsModule.for_root()`` -- registers the machinery that mounts ``@WebSocketGateway`` providers."""

from __future__ import annotations

from typing import Any

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.websockets.gateway_runner import WS_ADAPTER, GatewayRunner


@Module()
class WebSocketsModule:
    @staticmethod
    def for_root(*, adapter: Any = None) -> DynamicModule:
        """``adapter=SocketIoAdapter(...)`` serves the gateways over Socket.IO instead of plain WebSocket frames."""
        return DynamicModule(
            module=WebSocketsModule,
            providers=[{"provide": WS_ADAPTER, "useValue": adapter}, GatewayRunner],
            exports=[GatewayRunner],
        )
