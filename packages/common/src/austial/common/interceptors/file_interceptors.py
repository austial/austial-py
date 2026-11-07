"""Upload interceptors -- mirror ``@nestjs/platform-express``'s ``FileInterceptor``,
``FilesInterceptor``, ``FileFieldsInterceptor`` and ``AnyFilesInterceptor``.

FastAPI/Starlette already parse ``multipart/form-data``; these interceptors add the *limits*
Nest's multer options give you -- per-file size, file count, allowed fields, a filter -- and
reject the request with the matching HTTP error before the handler runs::

    @Post("avatar")
    @UseInterceptors(FileInterceptor("avatar", max_size=2 * 1024 * 1024))
    async def avatar(self, avatar: UploadFile = UploadedFile("avatar")): ...
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

from austial.common.exceptions.http_exceptions import BadRequestException, PayloadTooLargeException
from austial.common.guards.base import ExecutionContext
from austial.common.interceptors.base import CallHandler, NestInterceptor

FileFilter = Callable[[Any, Any], bool]  # (request, upload) -> keep?


def _is_upload(value: Any) -> bool:
    return hasattr(value, "filename") and hasattr(value, "file")


def _size(upload: Any) -> int:
    size = getattr(upload, "size", None)
    if size is not None:
        return int(size)
    stream = upload.file
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return int(size)


class _UploadInterceptor(NestInterceptor):
    def __init__(self, *, max_size: int | None = None, file_filter: FileFilter | None = None) -> None:
        self._max_size = max_size
        self._file_filter = file_filter

    def _fields(self) -> dict[str, int | None] | None:
        """Allowed ``field -> max count`` (``None`` count = unlimited); ``None`` allows any field."""
        raise NotImplementedError

    async def intercept(self, context: ExecutionContext, next: CallHandler) -> Any:
        request = context.get_request()
        form = await request.form()
        allowed = self._fields()
        counts: dict[str, int] = {}
        for field, raw in form.multi_items():
            value: Any = raw
            if not _is_upload(value):
                continue
            if allowed is not None and field not in allowed:
                raise BadRequestException(f"Unexpected field '{field}'")
            counts[field] = counts.get(field, 0) + 1
            limit = None if allowed is None else allowed[field]
            if limit is not None and counts[field] > limit:
                raise BadRequestException(f"Too many files for field '{field}' (max {limit})")
            if self._max_size is not None and _size(value) > self._max_size:
                raise PayloadTooLargeException(f"File '{value.filename}' too large (max {self._max_size} bytes)")
            if self._file_filter is not None and not self._file_filter(request, value):
                raise BadRequestException(f"File '{value.filename}' rejected")
        return await next.handle()


class FileInterceptor(_UploadInterceptor):
    """One file in ``field_name``."""

    def __init__(self, field_name: str, **options: Any) -> None:
        super().__init__(**options)
        self._field = field_name

    def _fields(self) -> dict[str, int | None]:
        return {self._field: 1}


class FilesInterceptor(_UploadInterceptor):
    """Up to ``max_count`` files in ``field_name``."""

    def __init__(self, field_name: str, max_count: int | None = None, **options: Any) -> None:
        super().__init__(**options)
        self._field = field_name
        self._max_count = max_count

    def _fields(self) -> dict[str, int | None]:
        return {self._field: self._max_count}


class FileFieldsInterceptor(_UploadInterceptor):
    """Several named fields: ``FileFieldsInterceptor([{"name": "avatar", "max_count": 1}, {"name": "docs"}])``."""

    def __init__(self, fields: Sequence[dict[str, Any]], **options: Any) -> None:
        super().__init__(**options)
        self._spec = {f["name"]: f.get("max_count") for f in fields}

    def _fields(self) -> dict[str, int | None]:
        return dict(self._spec)


class AnyFilesInterceptor(_UploadInterceptor):
    """Any number of files in any field."""

    def _fields(self) -> None:
        return None
