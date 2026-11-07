"""``@Module()`` -- mirrors ``@nestjs/common``'s ``@Module()`` decorator."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from austial.core.metadata import MODULE_METADATA, set_metadata

T = TypeVar("T")


@dataclass
class ModuleMetadata:
    imports: list[Any] = field(default_factory=list)
    controllers: list[type] = field(default_factory=list)
    providers: list[Any] = field(default_factory=list)
    exports: list[Any] = field(default_factory=list)
    is_global: bool = False


def Module(
    *,
    imports: Sequence[Any] = (),
    controllers: Sequence[type] = (),
    providers: Sequence[Any] = (),
    exports: Sequence[Any] = (),
) -> Callable[[T], T]:
    """Class decorator declaring a module's imports/controllers/providers/exports.

    Example::

        @Module(
            imports=[ConfigModule.for_root()],
            controllers=[HealthController],
            providers=[HealthService],
            exports=[HealthService],
        )
        class HealthModule:
            pass
    """

    def decorator(cls: T) -> T:
        metadata = ModuleMetadata(
            imports=list(imports),
            controllers=list(controllers),
            providers=list(providers),
            exports=list(exports),
        )
        set_metadata(MODULE_METADATA, metadata)(cls)
        return cls

    return decorator


def Global(cls: T) -> T:
    """Class decorator marking a module's providers as available application-wide
    without needing to be re-imported, mirroring Nest's ``@Global()``."""
    from austial.core.metadata import get_metadata

    metadata: ModuleMetadata = get_metadata(MODULE_METADATA, cls)
    if metadata is not None:
        metadata.is_global = True
    return cls
