"""``StorageConfig`` -- configuration passed to ``StorageModule.for_root(...)``.

Lives in its own module so the driver, service and signed-URL helpers can all
import it without pulling in ``StorageModule``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_MAX_OBJECT_SIZE_BYTES: int = 100 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class StorageConfig:
    """Framework-agnostic storage configuration.

    Fields are validated in ``__post_init__`` so a misconfiguration is a
    startup error, not a runtime surprise.
    """

    signed_url_secret: str
    driver: str = "local"
    local_base_dir: Path | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_endpoint_url: str | None = None
    max_object_size_bytes: int = DEFAULT_MAX_OBJECT_SIZE_BYTES
    allowed_content_types: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.signed_url_secret, str) or len(self.signed_url_secret) < 32:
            raise ValueError(
                "StorageConfig.signed_url_secret must be at least 32 characters "
                "(OWASP ASVS V6 -- signing secrets must have >=128 bits of entropy)."
            )
        if self.driver not in {"local", "s3"}:
            raise ValueError(f"StorageConfig.driver must be 'local' or 's3', not {self.driver!r}")
        if self.driver == "local" and self.local_base_dir is None:
            raise ValueError("StorageConfig.local_base_dir is required when driver='local'")
        if self.driver == "s3" and not self.s3_bucket:
            raise ValueError("StorageConfig.s3_bucket is required when driver='s3'")
        if self.max_object_size_bytes <= 0:
            raise ValueError("StorageConfig.max_object_size_bytes must be positive")
