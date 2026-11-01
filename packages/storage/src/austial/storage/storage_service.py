"""``StorageService`` -- injectable service, thin wrapper over the active
driver.

Adds cross-cutting concerns the individual drivers should not each
re-implement:

- object-key safety (``../``, absolute paths, null bytes, control chars);
- content-type inference from the suffix when the caller didn't pass one;
- max object size enforcement (``StorageConfig.max_object_size_bytes``);
- optional virus scanning via a ``VirusScanHook``;
- an allow-list of content types when configured;
- composition with :class:`SignedUrlService` so the product can mint download
  URLs without knowing about HMAC details.
"""

from __future__ import annotations

import mimetypes
from collections.abc import AsyncIterator
from datetime import timedelta
from typing import BinaryIO

from austial.common.decorators.injectable import Injectable
from austial.storage.config import StorageConfig
from austial.storage.driver import StorageDriver
from austial.storage.errors import MalwareDetectedError, ObjectTooLargeError, StorageError
from austial.storage.paths import assert_safe_key, assert_safe_prefix
from austial.storage.signed_url_service import SignedUrlService
from austial.storage.stored_object import StoredObject
from austial.storage.virus_scan import VirusScanHook


@Injectable()
class StorageService:
    """Product-facing storage entry point."""

    def __init__(
        self,
        driver: StorageDriver,
        config: StorageConfig,
        signed_urls: SignedUrlService,
        virus_scan: VirusScanHook | None = None,
    ) -> None:
        self._driver = driver
        self._config = config
        self._signed_urls = signed_urls
        self._virus_scan = virus_scan

    # ------------------------------------------------------------------ writes

    async def put(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        assert_safe_key(key)
        payload = _to_bytes(data)
        if len(payload) > self._config.max_object_size_bytes:
            raise ObjectTooLargeError(len(payload), self._config.max_object_size_bytes)

        resolved_content_type = content_type or _guess_content_type(key)
        if self._config.allowed_content_types and resolved_content_type not in self._config.allowed_content_types:
            raise StorageError(f"content type {resolved_content_type!r} is not allowed")

        if self._virus_scan is not None:
            result = await self._virus_scan.scan(key, payload)
            if not result.clean:
                raise MalwareDetectedError(key, result.signature)

        return await self._driver.put(
            key,
            payload,
            content_type=resolved_content_type,
            metadata=metadata,
        )

    async def delete(self, key: str) -> None:
        assert_safe_key(key)
        await self._driver.delete(key)

    # ------------------------------------------------------------------ reads

    async def get(self, key: str) -> StoredObject:
        assert_safe_key(key)
        return await self._driver.get(key)

    async def stat(self, key: str) -> StoredObject:
        assert_safe_key(key)
        return await self._driver.stat(key)

    async def list(  # noqa: A003 -- mirrors driver
        self, prefix: str = "", *, limit: int = 1000
    ) -> AsyncIterator[StoredObject]:
        assert_safe_prefix(prefix)
        async for obj in self._driver.list(prefix, limit=limit):
            yield obj

    # ------------------------------------------------------------------ signed URLs

    def issue_signed_url(self, key: str, *, ttl: timedelta, method: str = "GET") -> str:
        assert_safe_key(key)
        return self._signed_urls.issue(key, ttl=ttl, method=method)

    def verify_signed_url(self, url_or_fragment: str, expected_key: str, method: str) -> None:
        assert_safe_key(expected_key)
        self._signed_urls.verify(url_or_fragment, expected_key, method)

    # ------------------------------------------------------------------ access

    @property
    def driver(self) -> StorageDriver:
        return self._driver


def _to_bytes(data: bytes | BinaryIO) -> bytes:
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data)
    return data.read()


def _guess_content_type(key: str) -> str:
    guessed, _ = mimetypes.guess_type(key)
    return guessed or "application/octet-stream"
