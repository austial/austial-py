"""HTTP exceptions -- mirrors ``@nestjs/common``'s exception hierarchy.

All of these carry a ``status_code`` and a Nest-shaped ``response`` payload
(``{"statusCode": ..., "message": ..., "error": ...}``) so the default
:class:`~austial.common.filters.all_exceptions_filter.AllExceptionsFilter`
can render them exactly like Nest's built-in filter does.
"""

from __future__ import annotations

from typing import Any


class HttpException(Exception):
    def __init__(self, message: str | dict | None = None, status_code: int = 500, error: str | None = None):
        self.status_code = status_code
        if isinstance(message, dict):
            self.response: dict[str, Any] = {"statusCode": status_code, **message}
        else:
            self.response = {
                "statusCode": status_code,
                "message": message or _default_message(status_code),
                "error": error or _default_message(status_code),
            }
        super().__init__(str(self.response.get("message")))

    def get_status(self) -> int:
        return self.status_code

    def get_response(self) -> dict:
        return self.response


def _default_message(status_code: int) -> str:
    return _REASON_PHRASES.get(status_code, "Error")


_REASON_PHRASES = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    406: "Not Acceptable",
    408: "Request Timeout",
    409: "Conflict",
    410: "Gone",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
    501: "Not Implemented",
    502: "Bad Gateway",
    503: "Service Unavailable",
}


class BadRequestException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 400)


class UnauthorizedException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 401)


class ForbiddenException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 403)


class NotFoundException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 404)


class MethodNotAllowedException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 405)


class ConflictException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 409)


class UnprocessableEntityException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 422)


class TooManyRequestsException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 429)


class InternalServerErrorException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 500)


class NotImplementedException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 501)


class ServiceUnavailableException(HttpException):
    def __init__(self, message: str | dict | None = None):
        super().__init__(message, 503)
