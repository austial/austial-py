"""``austial.storage`` -- file / blob storage abstraction.

Ships a ``StorageModule.for_root(...)`` dynamic module, a ``StorageService``
(injectable, wraps the active driver with path-safety, size limits,
content-type inference, virus scanning and signed-URL minting), a local
filesystem driver (default), an S3 driver stub (lazy boto3 import), and a
``SignedUrlService`` that issues short-lived HMAC-signed download URLs the
product can verify without cookies.

Design mirrors NestJS's storage patterns: the framework provides the driver
contract and the service; product code wires it up and provides an HTTP
controller that verifies signed URLs.
"""

from austial.storage.config import DEFAULT_MAX_OBJECT_SIZE_BYTES, StorageConfig
from austial.storage.driver import StorageDriver
from austial.storage.errors import (
    InvalidSignedUrlError,
    MalwareDetectedError,
    ObjectNotFoundError,
    ObjectTooLargeError,
    PathTraversalError,
    StorageError,
)
from austial.storage.local_driver import LocalDriver
from austial.storage.paths import assert_safe_key, assert_safe_prefix
from austial.storage.s3_driver import S3Driver
from austial.storage.signed_url_service import SignedUrlService
from austial.storage.storage_module import StorageModule
from austial.storage.storage_service import StorageService
from austial.storage.stored_object import StoredObject
from austial.storage.virus_scan import NoopVirusScan, ScanResult, VirusScanHook

__all__ = [
    "DEFAULT_MAX_OBJECT_SIZE_BYTES",
    "InvalidSignedUrlError",
    "LocalDriver",
    "MalwareDetectedError",
    "NoopVirusScan",
    "ObjectNotFoundError",
    "ObjectTooLargeError",
    "PathTraversalError",
    "S3Driver",
    "ScanResult",
    "SignedUrlService",
    "StorageConfig",
    "StorageDriver",
    "StorageError",
    "StorageModule",
    "StorageService",
    "StoredObject",
    "VirusScanHook",
    "assert_safe_key",
    "assert_safe_prefix",
]
