"""``AllExceptionsFilter`` -- the default global exception filter.

Renders errors in the exact shape Nest's built-in filter produces::

    {"statusCode": 404, "message": "Not Found", "error": "Not Found",
     "timestamp": "...", "path": "/cats/42"}
"""

from __future__ import annotations

from datetime import UTC, datetime

from starlette.responses import JSONResponse

from austial.common.exceptions.http_exceptions import HttpException
from austial.common.filters.base import ArgumentsHost, ExceptionFilter


class AllExceptionsFilter(ExceptionFilter):
    async def catch(self, exception: BaseException, host: ArgumentsHost) -> JSONResponse:
        request = host.get_request()
        if isinstance(exception, HttpException):
            status_code = exception.get_status()
            body = dict(exception.get_response())
        else:
            status_code = 500
            body = {"statusCode": 500, "message": "Internal Server Error", "error": "Internal Server Error"}

        body.setdefault("timestamp", datetime.now(UTC).isoformat())
        body.setdefault("path", request.url.path)
        return JSONResponse(status_code=status_code, content=body)
