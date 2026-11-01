"""``S3Driver`` -- S3 backend for :class:`StorageDriver`.

``boto3`` is imported lazily so that local dev without S3 credentials never
pays the import cost -- and, more importantly, doesn't force the framework
to ship ``boto3`` as a hard dependency. When ``boto3`` is not installed,
constructing the driver raises with a helpful message that names the extras.

The core methods are minimal but correct: single-shot ``put_object`` /
``get_object`` / ``head_object`` / ``delete_object`` / ``list_objects_v2``,
mapping S3's response shape onto :class:`StoredObject`. Streaming multipart
uploads, presigned URL delegation and lifecycle configuration are
deliberately out of scope -- the product owns those knobs.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, BinaryIO

from austial.storage.driver import StorageDriver
from austial.storage.errors import ObjectNotFoundError
from austial.storage.paths import assert_safe_key, assert_safe_prefix
from austial.storage.stored_object import StoredObject


class S3Driver(StorageDriver):
    """S3 driver. Requires ``boto3`` at construction time; if the import fails
    every call raises :class:`NotImplementedError` on top of the clear
    startup error, so tests can still import this class."""

    def __init__(
        self,
        *,
        bucket: str,
        region: str | None = None,
        endpoint_url: str | None = None,
        client: Any = None,
    ) -> None:
        self._bucket = bucket
        self._region = region
        self._endpoint_url = endpoint_url
        self._client = client
        if client is None:
            try:
                import boto3
            except ImportError as exc:  # pragma: no cover -- exercised only when boto3 absent
                raise ImportError(
                    "S3Driver requires boto3. Install it with `pip install boto3` "
                    "or set `driver='local'` in StorageConfig for local development."
                ) from exc
            self._client = boto3.client(
                "s3",
                region_name=region,
                endpoint_url=endpoint_url,
            )

    # ------------------------------------------------------------------ helpers

    @staticmethod
    def _to_bytes(data: bytes | BinaryIO) -> bytes:
        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)
        return data.read()

    def _stored_from_head(self, key: str, head: dict[str, Any], data: bytes | None = None) -> StoredObject:
        last_modified = head.get("LastModified")
        if last_modified is None:
            last_modified = datetime.now(tz=UTC)
        elif last_modified.tzinfo is None:
            last_modified = last_modified.replace(tzinfo=UTC)
        return StoredObject(
            key=key,
            size=int(head.get("ContentLength", len(data) if data is not None else 0)),
            content_type=head.get("ContentType", "application/octet-stream"),
            last_modified=last_modified,
            etag=(head.get("ETag") or "").strip('"') or None,
            metadata=dict(head.get("Metadata") or {}),
            data=data,
        )

    # ------------------------------------------------------------------ driver API

    async def put(
        self,
        key: str,
        data: bytes | BinaryIO,
        *,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> StoredObject:
        assert_safe_key(key)
        payload = self._to_bytes(data)
        params: dict[str, Any] = {"Bucket": self._bucket, "Key": key, "Body": payload}
        if content_type:
            params["ContentType"] = content_type
        if metadata:
            params["Metadata"] = {str(k): str(v) for k, v in metadata.items()}
        self._client.put_object(**params)
        head = self._client.head_object(Bucket=self._bucket, Key=key)
        return self._stored_from_head(key, head, data=payload)

    async def get(self, key: str) -> StoredObject:
        assert_safe_key(key)
        try:
            resp = self._client.get_object(Bucket=self._bucket, Key=key)
        except Exception as exc:  # noqa: BLE001 -- botocore raises many shapes; normalise
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise
        body = resp["Body"].read()
        return self._stored_from_head(key, resp, data=body)

    async def stat(self, key: str) -> StoredObject:
        assert_safe_key(key)
        try:
            head = self._client.head_object(Bucket=self._bucket, Key=key)
        except Exception as exc:  # noqa: BLE001
            if _is_not_found(exc):
                raise ObjectNotFoundError(key) from exc
            raise
        return self._stored_from_head(key, head)

    async def delete(self, key: str) -> None:
        assert_safe_key(key)
        self._client.delete_object(Bucket=self._bucket, Key=key)

    async def list(  # noqa: A003 -- protocol contract
        self, prefix: str, *, limit: int = 1000
    ) -> AsyncIterator[StoredObject]:
        assert_safe_prefix(prefix)
        yielded = 0
        continuation: str | None = None
        while True:
            params: dict[str, Any] = {
                "Bucket": self._bucket,
                "Prefix": prefix,
                "MaxKeys": min(1000, limit - yielded),
            }
            if continuation:
                params["ContinuationToken"] = continuation
            resp = self._client.list_objects_v2(**params)
            for entry in resp.get("Contents", ()):
                yield await self.stat(entry["Key"])
                yielded += 1
                if yielded >= limit:
                    return
            if not resp.get("IsTruncated"):
                return
            continuation = resp.get("NextContinuationToken")
            if not continuation:
                return

    # ------------------------------------------------------------------ misc

    @property
    def bucket(self) -> str:
        return self._bucket


def _is_not_found(exc: Exception) -> bool:
    """Botocore raises ``ClientError`` with an error code we can peek at.

    We keep the import inside the check so botocore stays optional.
    """

    try:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    except AttributeError:
        return False
    return code in {"NoSuchKey", "NotFound", "404"}
