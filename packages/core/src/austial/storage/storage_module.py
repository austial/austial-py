"""``StorageModule.for_root(...)`` -- wires a :class:`StorageDriver`,
:class:`StorageService`, :class:`SignedUrlService` and (optionally) a
:class:`VirusScanHook` into the DI container.

Product code can override the driver by passing ``driver=MyDriver(...)`` --
useful for tests or for pointing S3 at a MinIO endpoint. If no driver is
supplied, one is constructed from ``StorageConfig``.
"""

from __future__ import annotations

from typing import Any

from austial.common.decorators.modules import Module
from austial.core.dynamic_module import DynamicModule
from austial.storage.config import StorageConfig
from austial.storage.driver import StorageDriver
from austial.storage.local_driver import LocalDriver
from austial.storage.s3_driver import S3Driver
from austial.storage.signed_url_service import SignedUrlService
from austial.storage.storage_service import StorageService
from austial.storage.virus_scan import NoopVirusScan, VirusScanHook


@Module()
class StorageModule:
    """Import via ``StorageModule.for_root(config, ...)`` in ``AppModule``'s
    ``imports=[...]``. Registered ``@Global`` by default so any module can
    inject ``StorageService`` and ``SignedUrlService``."""

    @staticmethod
    def for_root(
        config: StorageConfig,
        *,
        driver: StorageDriver | None = None,
        virus_scan: VirusScanHook | None = None,
        is_global: bool = True,
    ) -> DynamicModule:
        resolved_driver: StorageDriver = driver if driver is not None else _driver_from_config(config)
        signed_urls = SignedUrlService(config.signed_url_secret)
        scan_hook: VirusScanHook = virus_scan if virus_scan is not None else NoopVirusScan()
        service = StorageService(
            driver=resolved_driver,
            config=config,
            signed_urls=signed_urls,
            virus_scan=scan_hook,
        )

        providers: list[Any] = [
            {"provide": StorageConfig, "useValue": config},
            {"provide": StorageDriver, "useValue": resolved_driver},
            {"provide": SignedUrlService, "useValue": signed_urls},
            {"provide": VirusScanHook, "useValue": scan_hook},
            {"provide": StorageService, "useValue": service},
        ]

        return DynamicModule(
            module=StorageModule,
            providers=providers,
            exports=[
                StorageConfig,
                StorageDriver,
                SignedUrlService,
                VirusScanHook,
                StorageService,
            ],
        )


def _driver_from_config(config: StorageConfig) -> StorageDriver:
    if config.driver == "local":
        assert config.local_base_dir is not None  # StorageConfig validates this
        return LocalDriver(config.local_base_dir)
    if config.driver == "s3":
        assert config.s3_bucket is not None  # StorageConfig validates this
        return S3Driver(
            bucket=config.s3_bucket,
            region=config.s3_region,
            endpoint_url=config.s3_endpoint_url,
        )
    raise ValueError(f"unsupported storage driver: {config.driver!r}")
