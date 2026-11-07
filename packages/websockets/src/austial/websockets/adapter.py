"""``WsAdapter`` -- the extension point for serving gateways over another WebSocket protocol (Nest's
``WebSocketAdapter``).

The default serves plain JSON text frames; :class:`~austial.websockets.SocketIoAdapter` serves Socket.IO. To add a
protocol, subclass this and pass an instance to ``WebSocketsModule.for_root(adapter=...)``::

    class MyAdapter(WsAdapter):
        def mount(self, runner, app, path, gateway, handlers):
            server = MyServer()                       # a WsServer subclass: emit(), to(room).emit(), clients
            ...register routes / mounts on `app`; on each message, call
               `await runner.process(gateway, handlers[event], client, event, data)` -- it applies guards, pipes,
               interceptors and error mapping, and returns ``(reply_event, payload)`` or ``None``...
            return server

``handlers`` maps event names to the gateway's ``@SubscribeMessage`` methods. Clients should be :class:`WsClient`
subclasses so ``ConnectedSocket()``, rooms and ``handle_connection`` / ``handle_disconnect`` behave as everywhere else.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from austial.websockets.types import WsServer


class WsAdapter(ABC):
    @abstractmethod
    def mount(self, runner: Any, app: Any, path: str, gateway: Any, handlers: dict[str, Any]) -> WsServer:
        """Registers the gateway on ``app`` at ``path``; returns the :class:`WsServer` set as ``gateway.server``."""
