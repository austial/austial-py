"""``StorageDriver`` -- the async protocol every backend implements.

Kept in its own file so ``LocalDriver`` and ``S3Driver`` can import it
without a circular dependency through the module wiring.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import BinaryIO, Protocol, runtime_checkable

from austial.storage.stored_object import StoredObject


@runtime_checkable
class StorageDriver(Protocol):
    """Async CRUD over an object store."""

    async def put(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject: ...  # pragma: no cover

    async def get(self, key: str) -> StoredObject: ...  # pragma: no cover

    async def stat(self, key: str) -> StoredObject: ...  # pragma: no cover

    async def delete(self, key: str) -> None: ...  # pragma: no cover

    def list(  # noqa: A003 -- protocol names must match Nest/S3 conventions
        self, prefix: str, *, limit: int = 1000
    ) -> AsyncIterator[StoredObject]: ...  # pragma: no cover
