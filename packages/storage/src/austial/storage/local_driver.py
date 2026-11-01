"""``LocalDriver`` -- POSIX filesystem backend for :class:`StorageDriver`.

Every object is written under ``base_dir/<key>``. Per-object metadata is kept
in an adjacent ``.<name>.meta.json`` (dot-prefixed so it's excluded from
listings and standard content-serving). The class enforces that the resolved
absolute path stays under ``base_dir`` -- defence in depth on top of the
:func:`assert_safe_key` check performed by :class:`StorageService`.

Deliberately synchronous under the hood: filesystem I/O is fast enough on
local disk that offloading to a thread pool is overhead for the common case.
The public API is still ``async`` so the driver is interchangeable with the
S3 driver.
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import os
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO

from austial.storage.driver import StorageDriver
from austial.storage.errors import ObjectNotFoundError, PathTraversalError
from austial.storage.paths import assert_safe_key, assert_safe_prefix
from austial.storage.stored_object import StoredObject

_META_SUFFIX = ".meta.json"


class LocalDriver(StorageDriver):
    """POSIX filesystem storage driver."""

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ helpers

    def _resolve(self, key: str) -> Path:
        assert_safe_key(key)
        candidate = (self._base_dir / key).resolve()
        try:
            candidate.relative_to(self._base_dir)
        except ValueError as exc:
            raise PathTraversalError(key) from exc
        return candidate

    def _meta_path(self, target: Path) -> Path:
        # ``.<name>.meta.json`` -- adjacent, dot-prefixed so listings and static
        # servers hide it by default.
        return target.with_name(f".{target.name}{_META_SUFFIX}")

    @staticmethod
    def _read_bytes(data: bytes | BinaryIO) -> bytes:
        if isinstance(data, (bytes, bytearray, memoryview)):
            return bytes(data)
        # BinaryIO
        return data.read()

    def _read_meta(self, target: Path) -> tuple[str, dict[str, str]]:
        meta_path = self._meta_path(target)
        if not meta_path.exists():
            content_type, _ = mimetypes.guess_type(target.name)
            return content_type or "application/octet-stream", {}
        raw = json.loads(meta_path.read_text(encoding="utf-8"))
        content_type = raw.get("content_type") or "application/octet-stream"
        metadata = {str(k): str(v) for k, v in (raw.get("metadata") or {}).items()}
        return content_type, metadata

    def _stat(self, key: str, target: Path, *, data: bytes | None = None) -> StoredObject:
        stat = target.stat()
        content_type, metadata = self._read_meta(target)
        last_modified = datetime.fromtimestamp(stat.st_mtime, tz=UTC)
        # etag = md5 hex, S3-compatible for single-part uploads
        if data is not None:
            etag = hashlib.md5(data).hexdigest()  # noqa: S324 -- content etag, not a security digest
        else:
            with target.open("rb") as fh:
                etag = hashlib.md5(fh.read()).hexdigest()  # noqa: S324
        return StoredObject(
            key=key,
            size=stat.st_size,
            content_type=content_type,
            last_modified=last_modified,
            etag=etag,
            metadata=metadata,
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
        target = self._resolve(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        payload = self._read_bytes(data)
        target.write_bytes(payload)

        if content_type is None:
            guessed, _ = mimetypes.guess_type(target.name)
            content_type = guessed or "application/octet-stream"

        meta_payload: dict[str, object] = {
            "content_type": content_type,
            "metadata": {str(k): str(v) for k, v in (metadata or {}).items()},
        }
        self._meta_path(target).write_text(json.dumps(meta_payload), encoding="utf-8")

        return self._stat(key, target, data=payload)

    async def get(self, key: str) -> StoredObject:
        target = self._resolve(key)
        if not target.exists() or not target.is_file():
            raise ObjectNotFoundError(key)
        payload = target.read_bytes()
        return self._stat(key, target, data=payload)

    async def stat(self, key: str) -> StoredObject:
        target = self._resolve(key)
        if not target.exists() or not target.is_file():
            raise ObjectNotFoundError(key)
        return self._stat(key, target)

    async def delete(self, key: str) -> None:
        target = self._resolve(key)
        if target.exists():
            target.unlink()
        meta = self._meta_path(target)
        if meta.exists():
            meta.unlink()

    async def list(  # noqa: A003 -- protocol contract
        self, prefix: str, *, limit: int = 1000
    ) -> AsyncIterator[StoredObject]:
        assert_safe_prefix(prefix)
        # Base directory to walk under; a trailing "/" (or empty prefix) means the whole
        # base dir. Everything else is joined onto base_dir and (re)resolved so we can
        # cheaply filter by prefix on the string of ``rel``.
        root = self._base_dir
        rel_prefix = prefix.replace("\\", "/")
        yielded = 0
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames.sort()
            for name in sorted(filenames):
                if name.startswith(".") and name.endswith(_META_SUFFIX):
                    continue
                abs_path = Path(dirpath) / name
                rel = abs_path.relative_to(root).as_posix()
                if rel_prefix and not rel.startswith(rel_prefix):
                    continue
                yield await self.stat(rel)
                yielded += 1
                if yielded >= limit:
                    return

    # ------------------------------------------------------------------ misc

    @property
    def base_dir(self) -> Path:
        return self._base_dir
