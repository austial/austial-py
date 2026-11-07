"""``ParseFilePipe`` and its validators -- mirrors ``@nestjs/common``'s.

::

    @Post("upload")
    async def upload(
        self,
        file: UploadFile = UploadedFile("file", ParseFilePipe(validators=[
            MaxFileSizeValidator(1024 * 1024),
            FileTypeValidator("image/png"),
        ])),
    ): ...
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Sequence
from typing import Any

from austial.common.exceptions.http_exceptions import HttpException
from austial.common.pipes.validation_pipe import ArgumentMetadata, PipeTransform


def _file_size(file: Any) -> int:
    size = getattr(file, "size", None)
    if size is not None:
        return int(size)
    stream = getattr(file, "file", file)
    position = stream.tell()
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(position)
    return int(size)


class FileValidator(ABC):
    @abstractmethod
    def is_valid(self, file: Any) -> bool:
        raise NotImplementedError

    @abstractmethod
    def build_error_message(self, file: Any) -> str:
        raise NotImplementedError


class MaxFileSizeValidator(FileValidator):
    def __init__(self, max_size: int, message: str | None = None) -> None:
        self._max_size = max_size
        self._message = message

    def is_valid(self, file: Any) -> bool:
        return _file_size(file) <= self._max_size

    def build_error_message(self, file: Any) -> str:
        return self._message or f"Validation failed (expected size is less than {self._max_size})"


class FileTypeValidator(FileValidator):
    """Checks the upload's declared ``Content-Type``: a ``str`` must be its suffix
    (``"png"`` accepts ``image/png``), a compiled regex must ``search`` it."""

    def __init__(self, file_type: str | re.Pattern[str]) -> None:
        self._file_type = file_type

    def is_valid(self, file: Any) -> bool:
        content_type = getattr(file, "content_type", None) or ""
        if isinstance(self._file_type, re.Pattern):
            return self._file_type.search(content_type) is not None
        return content_type.endswith(self._file_type)

    def build_error_message(self, file: Any) -> str:
        return f"Validation failed (expected type is {getattr(self._file_type, 'pattern', self._file_type)})"


class ParseFilePipe(PipeTransform):
    def __init__(
        self,
        *,
        validators: Sequence[FileValidator] = (),
        file_is_required: bool = True,
        error_http_status_code: int = 400,
        exception_factory: Callable[[str], Exception] | None = None,
    ) -> None:
        self._validators = list(validators)
        self._required = file_is_required
        self._status = error_http_status_code
        self._exception_factory = exception_factory

    def _fail(self, message: str) -> Any:
        if self._exception_factory is not None:
            raise self._exception_factory(message)
        raise HttpException(message, self._status)

    def transform(self, value: Any, metadata: ArgumentMetadata) -> Any:
        files = [] if value is None else (list(value) if isinstance(value, list | tuple) else [value])
        if not files:
            if self._required:
                self._fail("File is required")
            return value
        for file in files:
            for validator in self._validators:
                if not validator.is_valid(file):
                    self._fail(validator.build_error_message(file))
        return value
