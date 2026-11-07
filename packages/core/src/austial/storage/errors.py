"""Storage-specific exceptions.

They extend Austial's HTTP exception hierarchy so ``AllExceptionsFilter`` maps
each one to the right status code without a translation layer.
"""

from __future__ import annotations

from austial.common.exceptions import BadRequestException, ForbiddenException, NotFoundException


class StorageError(BadRequestException):
    """Base for storage-side rejections."""

    def __init__(self, message: str = "storage error"):
        super().__init__(message)


class PathTraversalError(StorageError):
    """Rejected -- object key contained ``..``, an absolute path, or a null byte."""

    def __init__(self, key: str):
        super().__init__(f"unsafe object key: {key!r}")


class ObjectTooLargeError(StorageError):
    """Rejected -- object exceeded ``StorageConfig.max_object_size_bytes``."""

    def __init__(self, size: int, limit: int):
        super().__init__(f"object of {size} bytes exceeds limit of {limit} bytes")


class MalwareDetectedError(StorageError):
    """Rejected -- ``VirusScanHook`` flagged the payload as infected."""

    def __init__(self, key: str, signature: str | None):
        detail = f" ({signature})" if signature else ""
        super().__init__(f"malware detected in {key!r}{detail}")


class InvalidSignedUrlError(ForbiddenException):
    """Signed URL is expired, tampered, missing fields, or method-mismatched."""

    def __init__(self, message: str = "invalid signed URL"):
        super().__init__(message)


class ObjectNotFoundError(NotFoundException):
    """The object key does not exist in the backing store."""

    def __init__(self, key: str):
        super().__init__(f"object not found: {key!r}")
