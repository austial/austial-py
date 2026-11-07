"""``CanActivate`` + ``ExecutionContext`` -- mirrors ``@nestjs/common``."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from starlette.requests import Request
from starlette.responses import Response


class ExecutionContext:
    """Gives guards/interceptors/filters access to the current request and to
    the controller class + handler function being invoked, mirroring Nest's
    ``ExecutionContext``."""

    def __init__(self, request: Request, controller_class: type, handler: Any, response: Response | None = None):
        self._request = request
        self._controller_class = controller_class
        self._handler = handler
        self._response = response

    def get_type(self) -> str:
        """The kind of request being handled: always ``"http"`` -- Austial has no WebSocket or RPC
        transport (Nest's other values are ``"ws"`` and ``"rpc"``)."""
        return "http"

    def switch_to_http(self) -> ExecutionContext:
        return self

    def switch_to_ws(self) -> Any:
        raise NotImplementedError("Austial has no WebSocket transport: this is an HTTP execution context.")

    def switch_to_rpc(self) -> Any:
        raise NotImplementedError("Austial has no RPC transport: this is an HTTP execution context.")

    def get_args(self) -> list[Any]:
        """``[request, response]``, mirroring Nest's ``[req, res, next]`` (there is no ``next``)."""
        return [self._request, self._response]

    def get_arg_by_index(self, index: int) -> Any:
        return self.get_args()[index]

    def get_request(self) -> Request:
        return self._request

    def get_response(self) -> Response | None:
        """The response being built for this request (the object ``@Res()`` hands a handler). Headers
        set on it are sent; ``None`` when a filter builds its own response."""
        return self._response

    def get_class(self) -> type:
        return self._controller_class

    def get_handler(self) -> Any:
        return self._handler


class CanActivate(ABC):
    """Base class for guards. Implement ``can_activate`` to allow/deny a request."""

    @abstractmethod
    async def can_activate(self, context: ExecutionContext) -> bool:
        raise NotImplementedError
