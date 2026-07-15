"""``ExceptionFilter`` + ``ArgumentsHost`` -- mirrors ``@nestjs/common``."""

from __future__ import annotations

from abc import ABC, abstractmethod

from starlette.requests import Request
from starlette.responses import Response


class ArgumentsHost:
    """Minimal stand-in for Nest's ``ArgumentsHost`` -- gives filters access to
    the underlying HTTP request."""

    def __init__(self, request: Request):
        self._request = request

    def switch_to_http(self) -> ArgumentsHost:
        return self

    def get_request(self) -> Request:
        return self._request


class ExceptionFilter(ABC):
    @abstractmethod
    async def catch(self, exception: BaseException, host: ArgumentsHost) -> Response:
        raise NotImplementedError
