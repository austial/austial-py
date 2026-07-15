"""``CanActivate`` + ``ExecutionContext`` -- mirrors ``@nestjs/common``."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from starlette.requests import Request


class ExecutionContext:
    """Gives guards/interceptors/filters access to the current request and to
    the controller class + handler function being invoked, mirroring Nest's
    ``ExecutionContext``."""

    def __init__(self, request: Request, controller_class: type, handler: Any):
        self._request = request
        self._controller_class = controller_class
        self._handler = handler

    def switch_to_http(self) -> ExecutionContext:
        return self

    def get_request(self) -> Request:
        return self._request

    def get_class(self) -> type:
        return self._controller_class

    def get_handler(self) -> Any:
        return self._handler


class CanActivate(ABC):
    """Base class for guards. Implement ``can_activate`` to allow/deny a request."""

    @abstractmethod
    async def can_activate(self, context: ExecutionContext) -> bool:
        raise NotImplementedError
