"""``StreamableFile`` -- mirrors ``@nestjs/common``'s: return one from a handler to stream bytes
(a file, a generator, an in-memory buffer) with the right headers, instead of buffering a
JSON body::

    @Get("report")
    async def report(self) -> StreamableFile:
        return StreamableFile(open("report.pdf", "rb"), type="application/pdf",
                              disposition='attachment; filename="report.pdf"')
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterable, Iterable
from typing import Any, BinaryIO

_CHUNK_SIZE = 64 * 1024


class StreamableFile:
    def __init__(
        self,
        source: bytes | bytearray | BinaryIO | Iterable[bytes] | AsyncIterable[bytes] | os.PathLike | str,
        *,
        type: str = "application/octet-stream",  # noqa: A002 - mirrors Nest's `type` option
        disposition: str | None = None,
        length: int | None = None,
    ) -> None:
        self._source = source
        self.type = type
        self.disposition = disposition
        self.length = length if length is not None else self._guess_length(source)

    @staticmethod
    def _guess_length(source: Any) -> int | None:
        if isinstance(source, bytes | bytearray):
            return len(source)
        if isinstance(source, str | os.PathLike):
            try:
                return os.path.getsize(source)
            except OSError:
                return None
        fileno = getattr(source, "fileno", None)
        if callable(fileno):
            try:
                return os.fstat(fileno()).st_size
            except (OSError, ValueError):
                return None
        return None

    @property
    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": self.type}
        if self.disposition:
            headers["Content-Disposition"] = self.disposition
        if self.length is not None:
            headers["Content-Length"] = str(self.length)
        return headers

    def stream(self) -> Iterable[bytes] | AsyncIterable[bytes]:
        """The body as an (async) iterable of byte chunks, for a ``StreamingResponse``."""
        source = self._source
        if isinstance(source, bytes | bytearray):
            return iter([bytes(source)])
        if isinstance(source, str | os.PathLike):
            return self._read_path(source)
        if hasattr(source, "read"):
            return self._read_stream(source)
        return source  # already an iterable / async iterable of bytes

    @staticmethod
    def _read_path(path: Any) -> Iterable[bytes]:
        with open(path, "rb") as handle:
            while chunk := handle.read(_CHUNK_SIZE):
                yield chunk

    @staticmethod
    def _read_stream(stream: Any) -> Iterable[bytes]:
        try:
            while chunk := stream.read(_CHUNK_SIZE):
                yield chunk
        finally:
            close = getattr(stream, "close", None)
            if callable(close):
                close()
